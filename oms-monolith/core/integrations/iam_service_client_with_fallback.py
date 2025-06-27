"""
IAM Service Client with Fallback Support
MSA 통합 + 로컬 JWT 검증 fallback
"""
import os
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
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
from core.auth import UserContext
from utils.logger import get_logger
from prometheus_client import Counter, Histogram, Gauge

logger = get_logger(__name__)

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
        self.secret_key = os.getenv("JWT_SECRET", "your-secret-key")
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
            return TokenValidationResponse(
                valid=True,
                user_id=payload.get("sub"),
                username=payload.get("preferred_username", payload.get("username")),
                email=payload.get("email"),
                scopes=payload.get("scope", "").split() if payload.get("scope") else [],
                roles=payload.get("roles", []),
                tenant_id=payload.get("tenant_id"),
                expires_at=datetime.fromtimestamp(payload.get("exp", 0)).isoformat(),
                metadata={
                    "auth_time": payload.get("auth_time"),
                    "jti": payload.get("jti"),
                    "validation_method": "local_fallback"
                }
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
        
        # HTTP client
        self._client = httpx.AsyncClient(
            base_url=self.iam_service_url,
            timeout=self.timeout,
            headers={"Content-Type": "application/json"}
        )
        
        # Local validator for fallback
        self._local_validator = LocalJWTValidator()
        
        # Circuit breaker state
        self._circuit_open = False
        self._circuit_failures = 0
        self._circuit_threshold = 5
        self._circuit_reset_time = None
        self._circuit_timeout = 60  # seconds
    
    def _check_circuit_breaker(self) -> bool:
        """Check if circuit breaker should be open"""
        if self._circuit_open:
            if self._circuit_reset_time and datetime.utcnow() > self._circuit_reset_time:
                # Try to close circuit
                self._circuit_open = False
                self._circuit_failures = 0
                logger.info("Circuit breaker closed, retrying IAM service")
            else:
                return True
        return False
    
    def _record_failure(self):
        """Record a failure for circuit breaker"""
        self._circuit_failures += 1
        if self._circuit_failures >= self._circuit_threshold:
            self._circuit_open = True
            self._circuit_reset_time = datetime.utcnow() + timedelta(seconds=self._circuit_timeout)
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
        if self._check_circuit_breaker():
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
                    json=request.dict(),
                    timeout=self.timeout
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
        Get user info - no fallback available for this
        Returns None if service is unavailable
        """
        if self._check_circuit_breaker():
            logger.warning("Circuit breaker open, cannot get user info")
            return None
        
        try:
            response = await self._client.post(
                "/api/v1/users/info",
                json={"user_id": user_id},
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                self._record_success()
                return UserInfoResponse(**response.json())
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get user info: {e}")
            self._record_failure()
            return None
    
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
        """Check IAM service health"""
        try:
            response = await self._client.get("/health", timeout=2)
            if response.status_code == 200:
                self._record_success()
                return {
                    "status": "healthy",
                    "circuit_breaker": "closed",
                    "failures": self._circuit_failures
                }
        except Exception:
            pass
        
        return {
            "status": "unhealthy",
            "circuit_breaker": "open" if self._circuit_open else "closed",
            "failures": self._circuit_failures,
            "fallback_available": True
        }
    
    async def close(self):
        """Close client connections"""
        await self._client.aclose()


# Global instance with fallback support
_iam_client_with_fallback: Optional[IAMServiceClientWithFallback] = None


def get_iam_client_with_fallback() -> IAMServiceClientWithFallback:
    """Get IAM client with fallback support"""
    global _iam_client_with_fallback
    if _iam_client_with_fallback is None:
        _iam_client_with_fallback = IAMServiceClientWithFallback()
    return _iam_client_with_fallback