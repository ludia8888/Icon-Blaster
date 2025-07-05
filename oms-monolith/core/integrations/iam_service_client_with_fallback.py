"""
IAM Service Client with Fallback Support
MSA 통합 + 로컬 JWT 검증 fallback
"""
import os
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta
import httpx
import jwt
from jwt import PyJWKClient
from functools import lru_cache
import backoff

from shared.iam_contracts import (
    IAMScope,
    TokenValidationRequest,
    TokenValidationResponse,
    UserInfoResponse
)
from core.auth_utils import UserContext
from utils.logger import get_logger
from prometheus_client import Counter, Histogram, Gauge
from database.clients.unified_http_client import create_iam_client

logger = get_logger(__name__)


# Custom exceptions for explicit error handling
class ServiceUnavailableError(Exception):
    """Raised when service is unavailable (circuit breaker open, network down)"""
    pass


class ServiceTimeoutError(Exception):
    """Raised when service request times out"""
    pass


class IAMServiceError(Exception):
    """General IAM service error"""
    pass

# Prometheus metrics
iam_fallback_counter = Counter(
    'iam_fallback_total',
    'Total number of fallbacks to local JWT validation',
    ['reason']
)
iam_validation_duration = Histogram(
    'iam_validation_duration_seconds',
    'Duration of token validation',
    ['method']  # 'remote' or 'local'
)
iam_service_health = Gauge(
    'iam_service_health',
    'IAM service health status (1=healthy, 0=unhealthy)'
)


class LocalJWTValidator:
    """Local JWT validation fallback"""
    
    def __init__(self):
        # FIXED: Fail fast on missing JWT_SECRET
        secret = os.getenv("JWT_SECRET")
        if not secret:
            raise ValueError("SECURITY: JWT_SECRET environment variable is required")
        
        # FIXED: Validate secret security
        self._validate_secret_security(secret)
        
        self.secret_key = secret
        self.expected_issuer = os.getenv("JWT_ISSUER", "iam.company")
        self.expected_audience = os.getenv("JWT_AUDIENCE", "oms")
        self.jwks_client = None
        
        # Try to initialize JWKS client for RS256
        jwks_url = os.getenv("JWT_JWKS_URL")
        if jwks_url:
            try:
                self.jwks_client = PyJWKClient(jwks_url)
            except Exception as e:
                logger.warning(f"Failed to initialize JWKS client: {e}")
    
    def _validate_secret_security(self, secret):
        """Comprehensive but not overly strict secret validation"""
        
        # Length check
        if len(secret) < 32:
            raise ValueError("SECURITY: JWT_SECRET must be at least 32 characters")
        
        # Common weak secrets (case insensitive)
        weak_secrets = {
            "your-secret-key",
            "your-super-secret-key-change-in-production",
            "change-in-production",
            "secret", "default", "password", "123456789",
            "admin", "test", "demo"
        }
        
        if secret.lower() in {s.lower() for s in weak_secrets}:
            raise ValueError("SECURITY: JWT_SECRET cannot be a common weak value")
        
        # Check for obviously dangerous patterns (injection attempts)
        dangerous_patterns = ["drop", "delete", "script", "<script", "rm -rf", "../"]
        if any(pattern in secret.lower() for pattern in dangerous_patterns):
            raise ValueError("SECURITY: JWT_SECRET contains suspicious patterns")
        
        # FIXED: More reasonable entropy check
        if self._has_critically_low_entropy(secret):
            raise ValueError("SECURITY: JWT_SECRET has insufficient entropy")
    
    def _has_critically_low_entropy(self, secret):
        """Check for CRITICALLY low entropy only - not overly strict"""
        
        # Check 1: Too few unique characters (very basic check)
        unique_chars = len(set(secret))
        if unique_chars < 6:  # Reduced from 8 to 6
            return True
        
        # Check 2: All same character
        if len(set(secret)) == 1:
            return True
        
        # Check 3: Only simple repeating patterns (like "abcabcabc...")
        if len(secret) >= 9:  # Only check longer secrets
            # Check for very simple patterns (2-4 chars repeating)
            for pattern_length in range(2, 5):  # Reduced range
                if len(secret) % pattern_length == 0:  # Only check if divisible
                    pattern = secret[:pattern_length]
                    expected_repetitions = len(secret) // pattern_length
                    repeated = pattern * expected_repetitions
                    
                    if secret == repeated:
                        return True  # Found simple repetition like "abababab"
        
        # Check 4: All digits or all letters (but allow mixed)
        if secret.isdigit() or secret.isalpha():
            if len(secret) < 40:  # Allow long all-letter passphrases
                return True
        
        # If we get here, entropy is acceptable
        return False
    
    async def validate_token(self, token: str) -> TokenValidationResponse:
        """Validate JWT token locally"""
        try:
            # Try RS256 with JWKS first
            if self.jwks_client:
                try:
                    signing_key = self.jwks_client.get_signing_key_from_jwt(token)
                    key = signing_key.key
                    algorithms = ["RS256"]
                except Exception:
                    # Fallback to HS256
                    key = self.secret_key
                    algorithms = ["HS256"]
            else:
                key = self.secret_key
                algorithms = ["HS256"]
            
            # Decode JWT
            payload = jwt.decode(
                token,
                key,
                algorithms=algorithms,
                audience=self.expected_audience,
                issuer=self.expected_issuer,
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_aud": True,
                    "verify_iss": True
                }
            )
            
            # Extract user info
            # Build metadata dict with only non-None values
            metadata = {"validation_method": "local_fallback"}
            if payload.get("auth_time") is not None:
                metadata["auth_time"] = payload.get("auth_time")
            if payload.get("jti") is not None:
                metadata["jti"] = payload.get("jti")
            
            return TokenValidationResponse(
                valid=True,
                user_id=payload.get("sub"),
                username=payload.get("preferred_username", payload.get("username")),
                email=payload.get("email"),
                scopes=payload.get("scope", "").split() if payload.get("scope") else [],
                roles=payload.get("roles", []),
                tenant_id=payload.get("tenant_id"),
                expires_at=datetime.fromtimestamp(payload.get("exp", 0)).isoformat(),
                metadata=metadata
            )
            
        except jwt.ExpiredSignatureError:
            return TokenValidationResponse(
                valid=False,
                error="Token has expired"
            )
        except jwt.InvalidTokenError as e:
            return TokenValidationResponse(
                valid=False,
                error=f"Invalid token: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Local JWT validation error: {e}")
            return TokenValidationResponse(
                valid=False,
                error=f"Validation failed: {str(e)}"
            )


class IAMServiceClientWithFallback:
    """
    IAM Service Client with automatic fallback to local validation
    Ensures system continues working even if IAM service is down
    """
    
    def __init__(self):
        self.iam_service_url = os.getenv("IAM_SERVICE_URL", "http://user-service:8000")
        self.timeout = int(os.getenv("IAM_TIMEOUT", "5"))  # Shorter timeout for faster fallback
        self.max_retries = int(os.getenv("IAM_MAX_RETRIES", "2"))
        
        # HTTP client using UnifiedHTTPClient (but with internal CB disabled)
        self._client = create_iam_client(
            base_url=self.iam_service_url,
            verify_ssl=True,
            enable_fallback=False,  # We handle fallback ourselves
            timeout=self.timeout,
            headers={"Content-Type": "application/json"},
            enable_circuit_breaker=False,  # Use our custom CB logic
            max_retries=0  # We handle retries ourselves
        )
        
        # Local validator for fallback
        self._local_validator = LocalJWTValidator()
        
        # Circuit breaker state (keeping existing logic)
        self._circuit_open = False
        self._circuit_failures = 0
        self._circuit_threshold = 5
        self._circuit_reset_time = None
        self._circuit_timeout = 60  # seconds
    
    async def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker should be open"""
        if self._circuit_open:
            if self._circuit_reset_time and datetime.now(timezone.utc) > self._circuit_reset_time:
                # FIXED: Only reset if health check passes
                logger.info("Circuit breaker reset time reached, performing health check...")
                
                is_healthy = await self._perform_health_check()
                
                if is_healthy:
                    self._circuit_open = False
                    self._circuit_failures = 0
                    logger.info("Circuit breaker closed after successful health check")
                    return False
                else:
                    # Service still unhealthy - extend reset time
                    self._circuit_reset_time = datetime.now(timezone.utc) + timedelta(seconds=self._circuit_timeout)
                    logger.warning("Health check failed, circuit remains open")
                    return True
            else:
                return True
        return False
    
    async def _perform_health_check(self) -> bool:
        """Perform health check before resetting circuit breaker"""
        try:
            logger.debug("Performing health check on IAM service")
            
            # Try a lightweight health check endpoint
            response = await self._client.get("/health")
            
            if response.status_code == 200:
                logger.debug("Health check passed")
                return True
            else:
                logger.debug(f"Health check failed with status {response.status_code}")
                return False
                
        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            return False
    
    def _record_failure(self):
        """Record a failure for circuit breaker"""
        self._circuit_failures += 1
        if self._circuit_failures >= self._circuit_threshold:
            self._circuit_open = True
            self._circuit_reset_time = datetime.now(timezone.utc) + timedelta(seconds=self._circuit_timeout)
            logger.warning(f"Circuit breaker opened due to {self._circuit_failures} failures")
            iam_service_health.set(0)
    
    def _record_success(self):
        """Record a success for circuit breaker"""
        self._circuit_failures = 0
        self._circuit_open = False
        iam_service_health.set(1)
    
    async def validate_token(self, token: str, required_scopes: Optional[List[str]] = None) -> TokenValidationResponse:
        """
        Validate JWT token with automatic fallback
        1. Try IAM service (if circuit is closed)
        2. Fallback to local validation if service fails
        """
        # Check circuit breaker
        if await self._check_circuit_breaker():
            logger.info("Circuit breaker open, using local validation")
            iam_fallback_counter.labels(reason="circuit_breaker").inc()
            with iam_validation_duration.labels(method="local").time():
                return await self._local_validator.validate_token(token)
        
        # Try remote validation
        try:
            with iam_validation_duration.labels(method="remote").time():
                request = TokenValidationRequest(
                    token=token,
                    validate_scopes=bool(required_scopes),
                    required_scopes=required_scopes
                )
                
                response = await self._client.post(
                    "/api/v1/auth/validate",
                    json=request.dict()
                )
                
                if response.status_code == 200:
                    self._record_success()
                    result = response.json()
                    return TokenValidationResponse(**result)
                else:
                    raise httpx.HTTPStatusError(
                        f"Status {response.status_code}",
                        request=response.request,
                        response=response
                    )
                    
        except (httpx.RequestError, httpx.HTTPStatusError, asyncio.TimeoutError) as e:
            logger.warning(f"IAM service validation failed: {e}, falling back to local")
            self._record_failure()
            iam_fallback_counter.labels(reason="service_error").inc()
            
            # Fallback to local validation
            with iam_validation_duration.labels(method="local").time():
                return await self._local_validator.validate_token(token)
        except Exception as e:
            logger.error(f"Unexpected error in token validation: {e}")
            iam_fallback_counter.labels(reason="unexpected_error").inc()
            
            # Fallback to local validation
            with iam_validation_duration.labels(method="local").time():
                return await self._local_validator.validate_token(token)
    
    async def get_user_info(self, user_id: str) -> Optional[UserInfoResponse]:
        """
        Get user info with explicit error handling
        Returns None only when user is not found (404)
        Raises exceptions for all other error cases
        """
        # Input validation
        if not user_id or not isinstance(user_id, str):
            raise ValueError(f"Invalid user_id: {user_id}")
        
        if await self._check_circuit_breaker():
            logger.warning(f"Circuit breaker open, cannot get user info for {user_id}")
            raise ServiceUnavailableError("IAM service circuit breaker is open")
        
        try:
            response = await self._client.post(
                "/api/v1/users/info",
                json={"user_id": user_id}
            )
            
            if response.status_code == 404:
                # User not found is not an error - return None as documented
                logger.info(f"User {user_id} not found")
                return None
                
            if response.status_code == 200:
                self._record_success()
                return UserInfoResponse(**response.json())
            
            # Other status codes are errors
            logger.error(f"IAM service returned {response.status_code} for user {user_id}")
            raise IAMServiceError(f"IAM service returned status {response.status_code}")
            
        except httpx.TimeoutError as e:
            logger.warning(f"Timeout getting user info for {user_id}: {e}")
            self._record_failure()
            raise ServiceTimeoutError(f"IAM service timeout after {self.timeout}s") from e
            
        except httpx.RequestError as e:
            logger.error(f"Network error getting user info for {user_id}: {e}")
            self._record_failure()
            raise ServiceUnavailableError(f"Cannot reach IAM service: {e}") from e
            
        except (ValueError, IAMServiceError, ServiceTimeoutError, ServiceUnavailableError):
            # Re-raise our explicit exceptions
            raise
            
        except Exception as e:
            logger.error(f"Unexpected error getting user info for {user_id}: {e}", exc_info=True)
            self._record_failure()
            raise IAMServiceError(f"Unexpected IAM service error: {type(e).__name__}") from e
    
    def create_user_context(self, validation_response: TokenValidationResponse) -> UserContext:
        """Create UserContext from validation response"""
        if not validation_response.valid:
            raise ValueError("Cannot create context from invalid token")
        
        return UserContext(
            user_id=validation_response.user_id,
            username=validation_response.username,
            email=validation_response.email,
            roles=validation_response.roles,
            tenant_id=validation_response.tenant_id,
            metadata={
                "scopes": validation_response.scopes,
                "validation_method": validation_response.metadata.get("validation_method", "remote"),
                **validation_response.metadata
            }
        )
    
    async def health_check(self) -> Dict[str, Any]:
        """Check IAM service health with explicit error tracking"""
        health_status = {
            "status": "unhealthy",
            "circuit_breaker": "open" if self._circuit_open else "closed",
            "failures": self._circuit_failures,
            "fallback_available": True,
            "last_error": None
        }
        
        try:
            response = await self._client.get("/health")
            if response.status_code == 200:
                self._record_success()
                return {
                    "status": "healthy",
                    "circuit_breaker": "closed",
                    "failures": self._circuit_failures,
                    "response_time_ms": response.elapsed.total_seconds() * 1000 if hasattr(response, 'elapsed') else 0
                }
            else:
                logger.warning(f"Health check returned status {response.status_code}")
                health_status["last_error"] = f"HTTP {response.status_code}"
                
        except httpx.TimeoutError as e:
            logger.debug(f"Health check timeout: {e}")
            health_status["last_error"] = "Timeout"
            
        except httpx.RequestError as e:
            logger.debug(f"Health check network error: {e}")
            health_status["last_error"] = f"Network error: {type(e).__name__}"
            
        except Exception as e:
            logger.error(f"Unexpected health check error: {e}", exc_info=True)
            health_status["last_error"] = f"Unexpected error: {type(e).__name__}"
        
        return health_status
    
    async def close(self):
        """Close client connections"""
        await self._client.close()


# Global instance with fallback support
_iam_client_with_fallback: Optional[IAMServiceClientWithFallback] = None


def get_iam_client_with_fallback() -> IAMServiceClientWithFallback:
    """Get IAM client with fallback support"""
    global _iam_client_with_fallback
    if _iam_client_with_fallback is None:
        _iam_client_with_fallback = IAMServiceClientWithFallback()
    return _iam_client_with_fallback