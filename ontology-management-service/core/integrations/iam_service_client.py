"""
IAM Service Client for MSA Integration
Clean implementation without circular dependencies
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
    IAMConfig,
    TokenValidationRequest,
    TokenValidationResponse,
    UserInfoRequest,
    UserInfoResponse,
    ServiceAuthRequest,
    ServiceAuthResponse,
    ScopeCheckRequest,
    ScopeCheckResponse,
    IAMHealthResponse
)
from core.auth_utils import UserContext
from common_logging.setup import get_logger
from database.clients.unified_http_client import UnifiedHTTPClient, HTTPClientConfig
import redis.asyncio as redis

logger = get_logger(__name__)


class IAMServiceClient:
    """
    Client for IAM Microservice
    Handles all communication with the external IAM service
    """
    
    def __init__(self, config: Optional[IAMConfig] = None):
        self.config = config or self._load_config()
        
        # HTTP client with connection pooling
        http_config = HTTPClientConfig(
            base_url=self.config.iam_service_url,
            timeout=self.config.timeout,
            verify_ssl=self.config.verify_ssl,
            headers={
                "Content-Type": "application/json",
                "X-Service-ID": self.config.service_id
            }
        )
        self._client = UnifiedHTTPClient(http_config)
        
        # JWKS client for key rotation
        self._jwks_client = None
        if self.config.enable_jwks and self.config.jwks_url:
            try:
                self._jwks_client = PyJWKClient(self.config.jwks_url)
                logger.info(f"JWKS client initialized: {self.config.jwks_url}")
            except Exception as e:
                logger.warning(f"Failed to initialize JWKS client: {e}")
        
        # Redis for caching (optional)
        self._redis_client = None
        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            try:
                self._redis_client = redis.from_url(redis_url)
                logger.info("Redis cache initialized for IAM client")
            except Exception as e:
                logger.warning(f"Redis initialization failed: {e}")
        
        # Service token cache
        self._service_token = None
        self._service_token_expires = None
    
    def _load_config(self) -> IAMConfig:
        """Load configuration from environment"""
        return IAMConfig(
            iam_service_url=os.getenv("IAM_SERVICE_URL", "http://user-service:8000"),
            jwks_url=os.getenv("IAM_JWKS_URL"),
            expected_issuer=os.getenv("JWT_ISSUER", "iam.company"),
            expected_audience=os.getenv("JWT_AUDIENCE", "oms"),
            service_id=os.getenv("IAM_SERVICE_ID", "oms-service"),
            service_secret=os.getenv("IAM_SERVICE_SECRET"),
            timeout=int(os.getenv("IAM_TIMEOUT", "10")),
            retry_count=int(os.getenv("IAM_RETRY_COUNT", "3")),
            cache_ttl=int(os.getenv("IAM_CACHE_TTL", "300")),
            enable_jwks=os.getenv("IAM_ENABLE_JWKS", "true").lower() == "true",
            verify_ssl=os.getenv("IAM_VERIFY_SSL", "true").lower() == "true"
        )
    
    async def _ensure_service_auth(self) -> str:
        """Ensure we have a valid service token"""
        if self._service_token and self._service_token_expires:
            if datetime.utcnow() < self._service_token_expires:
                return self._service_token
        
        # Get new service token
        auth_response = await self.authenticate_service()
        self._service_token = auth_response.access_token
        self._service_token_expires = datetime.utcnow() + timedelta(
            seconds=auth_response.expires_in - 60  # Refresh 1 minute early
        )
        return self._service_token
    
    @backoff.on_exception(
        backoff.expo,
        (httpx.RequestError, httpx.HTTPStatusError),
        max_tries=3,
        max_time=30
    )
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        use_service_auth: bool = False
    ) -> Dict[str, Any]:
        """Make HTTP request to IAM service with retry logic"""
        headers = {}
        if use_service_auth:
            token = await self._ensure_service_auth()
            headers["Authorization"] = f"Bearer {token}"
        
        response = await self._client.request(
            method=method,
            url=endpoint,
            json=data,
            headers=headers
        )
        if response.status_code >= 400:
            raise httpx.HTTPStatusError(
                message=f"HTTP {response.status_code}",
                request=None,
                response=response
            )
        return response.json()
    
    async def validate_token(self, token: str, required_scopes: Optional[List[str]] = None) -> TokenValidationResponse:
        """
        Validate JWT token with IAM service
        
        Args:
            token: JWT token to validate
            required_scopes: Optional list of required scopes
            
        Returns:
            TokenValidationResponse with validation results
        """
        # Check cache first
        cache_key = f"iam:token:{token[:20]}"  # Use first 20 chars as key
        if self._redis_client:
            try:
                cached = await self._redis_client.get(cache_key)
                if cached:
                    import json
                    return TokenValidationResponse(**json.loads(cached))
            except Exception as e:
                logger.warning(f"Cache read error: {e}")
        
        # Validate with IAM service
        request = TokenValidationRequest(
            token=token,
            validate_scopes=bool(required_scopes),
            required_scopes=required_scopes
        )
        
        try:
            result = await self._make_request(
                "POST",
                "/api/v1/auth/validate",
                data=request.model_dump()
            )
            
            response = TokenValidationResponse(**result)
            
            # Cache successful validation
            if response.valid and self._redis_client:
                try:
                    await self._redis_client.setex(
                        cache_key,
                        self.config.cache_ttl,
                        response.json()
                    )
                except Exception as e:
                    logger.warning(f"Cache write error: {e}")
            
            return response
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return TokenValidationResponse(
                    valid=False,
                    error="Invalid or expired token"
                )
            raise
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return TokenValidationResponse(
                valid=False,
                error=f"Validation service error: {str(e)}"
            )
    
    async def get_user_info(self, 
                           user_id: Optional[str] = None,
                           username: Optional[str] = None,
                           email: Optional[str] = None,
                           include_permissions: bool = False) -> Optional[UserInfoResponse]:
        """
        Get user information from IAM service
        
        Args:
            user_id: User ID to lookup
            username: Username to lookup
            email: Email to lookup
            include_permissions: Include detailed permissions
            
        Returns:
            UserInfoResponse or None if not found
        """
        if not any([user_id, username, email]):
            raise ValueError("Must provide user_id, username, or email")
        
        request = UserInfoRequest(
            user_id=user_id,
            username=username,
            email=email,
            include_permissions=include_permissions
        )
        
        try:
            result = await self._make_request(
                "POST",
                "/api/v1/users/info",
                data=request.model_dump(),
                use_service_auth=True
            )
            return UserInfoResponse(**result)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise
    
    async def check_user_scopes(self,
                               user_id: str,
                               required_scopes: List[str],
                               check_mode: str = "any") -> ScopeCheckResponse:
        """
        Check if user has required scopes
        
        Args:
            user_id: User ID to check
            required_scopes: List of required scopes
            check_mode: "any" or "all"
            
        Returns:
            ScopeCheckResponse with authorization result
        """
        request = ScopeCheckRequest(
            user_id=user_id,
            required_scopes=required_scopes,
            check_mode=check_mode
        )
        
        try:
            result = await self._make_request(
                "POST",
                "/api/v1/auth/check-scopes",
                data=request.model_dump(),
                use_service_auth=True
            )
            return ScopeCheckResponse(**result)
        except Exception as e:
            logger.error(f"Scope check error: {e}")
            return ScopeCheckResponse(
                authorized=False,
                missing_scopes=required_scopes
            )
    
    async def authenticate_service(self) -> ServiceAuthResponse:
        """
        Authenticate this service with IAM
        
        Returns:
            ServiceAuthResponse with service token
        """
        if not self.config.service_secret:
            raise ValueError("Service secret not configured")
        
        request = ServiceAuthRequest(
            service_id=self.config.service_id,
            service_secret=self.config.service_secret,
            requested_scopes=[
                IAMScope.SERVICE_ACCOUNT,
                IAMScope.ONTOLOGIES_READ,
                IAMScope.SCHEMAS_READ
            ]
        )
        
        try:
            result = await self._make_request(
                "POST",
                "/api/v1/auth/service",
                data=request.model_dump()
            )
            return ServiceAuthResponse(**result)
        except Exception as e:
            logger.error(f"Service authentication failed: {e}")
            raise
    
    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh access token using refresh token
        
        Args:
            refresh_token: Refresh token
            
        Returns:
            New token response
        """
        try:
            result = await self._make_request(
                "POST",
                "/api/v1/auth/refresh",
                data={"refresh_token": refresh_token}
            )
            return result
        except Exception as e:
            logger.error(f"Token refresh failed: {e}")
            raise
    
    async def health_check(self) -> IAMHealthResponse:
        """
        Check IAM service health
        
        Returns:
            IAMHealthResponse with service status
        """
        try:
            result = await self._make_request("GET", "/health")
            return IAMHealthResponse(**result)
        except Exception:
            return IAMHealthResponse(
                status="unhealthy",
                version="unknown",
                timestamp=datetime.utcnow().isoformat()
            )
    
    def create_user_context(self, validation_response: TokenValidationResponse) -> UserContext:
        """
        Create UserContext from token validation response
        
        Args:
            validation_response: Response from token validation
            
        Returns:
            UserContext for the authenticated user
        """
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
                "iam_metadata": validation_response.metadata
            }
        )
    
    async def close(self):
        """Close client connections"""
        await self._client.close()
        if self._redis_client:
            await self._redis_client.close()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# Global client instance
_iam_client: Optional[IAMServiceClient] = None


def get_iam_client() -> IAMServiceClient:
    """Get global IAM client instance"""
    global _iam_client
    if _iam_client is None:
        _iam_client = IAMServiceClient()
    return _iam_client


async def validate_token_with_iam(token: str, required_scopes: Optional[List[str]] = None) -> Optional[UserContext]:
    """
    Convenience function to validate token and get user context
    
    Args:
        token: JWT token to validate
        required_scopes: Optional required scopes
        
    Returns:
        UserContext if valid, None otherwise
    """
    client = get_iam_client()
    response = await client.validate_token(token, required_scopes)
    
    if response.valid:
        return client.create_user_context(response)
    
    return None