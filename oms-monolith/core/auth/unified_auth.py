"""
Unified Authentication Module
Consolidates various get_current_user implementations
"""

import logging
from typing import Optional, Union, Callable
from enum import Enum
from fastapi import Request, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from core.auth import UserContext
from core.auth.resource_permission_checker import UserContext as ExtendedUserContext

logger = logging.getLogger(__name__)

# Security scheme for API endpoints
security = HTTPBearer(auto_error=False)


class AuthMode(Enum):
    """Authentication modes for different use cases"""
    STANDARD = "standard"          # Default FastAPI middleware-based
    MSA = "msa"                   # Microservice architecture
    LIFE_CRITICAL = "life_critical"  # Enhanced security for production
    GRAPHQL = "graphql"           # GraphQL with optional auth
    GATEWAY = "gateway"           # API Gateway (deprecated)
    TEST = "test"                 # Testing mode


class AuthConfig:
    """Configuration for authentication behavior"""
    
    def __init__(
        self,
        mode: AuthMode = AuthMode.STANDARD,
        optional: bool = False,
        allow_service_accounts: bool = False,
        require_scopes: Optional[list] = None,
        enhanced_validation: bool = False,
        use_extended_context: bool = False
    ):
        self.mode = mode
        self.optional = optional
        self.allow_service_accounts = allow_service_accounts
        self.require_scopes = require_scopes or []
        self.enhanced_validation = enhanced_validation
        self.use_extended_context = use_extended_context


class UnifiedAuth:
    """Unified authentication handler"""
    
    def __init__(self, config: AuthConfig = None):
        self.config = config or AuthConfig()
    
    async def get_current_user(
        self,
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
    ) -> Optional[Union[UserContext, ExtendedUserContext]]:
        """
        Unified get_current_user implementation
        Handles all authentication modes based on configuration
        """
        
        # Handle test/gateway mode
        if self.config.mode == AuthMode.TEST:
            return self._get_test_user()
        
        if self.config.mode == AuthMode.GATEWAY:
            import os
            if os.getenv("ENVIRONMENT") == "production":
                raise HTTPException(
                    status_code=403,
                    detail="Gateway mock auth is not allowed in production"
                )
            return self._get_test_user()
        
        # Try to get user from request state (set by middleware)
        user = getattr(request.state, "user", None)
        
        # If not in request state and we have credentials, try direct validation
        if not user and credentials and self.config.mode in [AuthMode.GRAPHQL, AuthMode.MSA]:
            user = await self._validate_token_directly(credentials.credentials)
        
        # Handle optional authentication
        if not user and self.config.optional:
            return None
        
        # Raise exception if no user found
        if not user:
            detail = "Not authenticated"
            headers = {}
            
            if self.config.mode == AuthMode.MSA:
                headers["WWW-Authenticate"] = 'Bearer realm="OMS API"'
            
            if self.config.mode == AuthMode.LIFE_CRITICAL:
                detail = "Authentication required for life-critical operation"
            
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=detail,
                headers=headers
            )
        
        # Enhanced validation for life-critical mode
        if self.config.enhanced_validation:
            self._validate_life_critical(user)
        
        # Validate scopes if required
        if self.config.require_scopes:
            self._validate_scopes(user, self.config.require_scopes)
        
        # Convert to extended context if needed
        if self.config.use_extended_context and not isinstance(user, ExtendedUserContext):
            user = self._to_extended_context(user)
        
        return user
    
    def _get_test_user(self) -> UserContext:
        """Get test user for non-production environments"""
        return UserContext(
            user_id="test-user-123",
            username="testuser",
            email="test@example.com",
            roles=["admin"],
            tenant_id="test-tenant",
            is_active=True,
            metadata={"test": True}
        )
    
    async def _validate_token_directly(self, token: str) -> Optional[UserContext]:
        """Validate JWT token directly (for GraphQL/MSA modes)"""
        try:
            # This would call the actual JWT validation service
            # For now, return None to indicate implementation needed
            logger.warning("Direct token validation not implemented")
            return None
        except Exception as e:
            logger.error(f"Token validation failed: {e}")
            return None
    
    def _validate_life_critical(self, user: UserContext) -> None:
        """Enhanced validation for life-critical operations"""
        if not user.is_active:
            raise HTTPException(
                status_code=403,
                detail="Inactive users cannot perform life-critical operations"
            )
        
        if not user.roles:
            raise HTTPException(
                status_code=403,
                detail="User must have assigned roles for life-critical operations"
            )
    
    def _validate_scopes(self, user: UserContext, required_scopes: list) -> None:
        """Validate user has required scopes"""
        user_scopes = user.metadata.get("scopes", [])
        for scope in required_scopes:
            if scope not in user_scopes:
                raise HTTPException(
                    status_code=403,
                    detail=f"Missing required scope: {scope}"
                )
    
    def _to_extended_context(self, user: UserContext) -> ExtendedUserContext:
        """Convert standard UserContext to ExtendedUserContext"""
        return ExtendedUserContext(
            user_id=user.user_id,
            username=user.username,
            email=user.email,
            roles=user.roles,
            tenant_id=user.tenant_id,
            is_active=user.is_active,
            teams=user.metadata.get("teams", []),
            permissions=user.metadata.get("permissions", []),
            metadata=user.metadata
        )


# Factory functions for different authentication modes

def get_current_user_standard(request: Request) -> UserContext:
    """Standard synchronous authentication (backward compatible)"""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    return user


async def get_current_user_async(request: Request) -> UserContext:
    """Standard async authentication"""
    auth = UnifiedAuth(AuthConfig(mode=AuthMode.STANDARD))
    return await auth.get_current_user(request)


async def get_current_user_msa(request: Request) -> UserContext:
    """MSA authentication with service account support"""
    auth = UnifiedAuth(AuthConfig(
        mode=AuthMode.MSA,
        allow_service_accounts=True
    ))
    return await auth.get_current_user(request)


async def get_current_user_life_critical(request: Request) -> UserContext:
    """Life-critical authentication with enhanced validation"""
    auth = UnifiedAuth(AuthConfig(
        mode=AuthMode.LIFE_CRITICAL,
        enhanced_validation=True
    ))
    return await auth.get_current_user(request)


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[UserContext]:
    """Optional authentication for GraphQL"""
    auth = UnifiedAuth(AuthConfig(
        mode=AuthMode.GRAPHQL,
        optional=True
    ))
    return await auth.get_current_user(request, credentials)


# Alias for backward compatibility
get_current_user = get_current_user_standard


# Decorator for scope-based authorization
def require_scope(scope: str):
    """Decorator to require specific scope"""
    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            # Get user from kwargs or first arg that is Request
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            for key, value in kwargs.items():
                if isinstance(value, Request):
                    request = value
                    break
            
            if not request:
                raise ValueError("No Request object found in arguments")
            
            auth = UnifiedAuth(AuthConfig(require_scopes=[scope]))
            await auth.get_current_user(request)
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator


# Export all variants
__all__ = [
    "UnifiedAuth",
    "AuthConfig", 
    "AuthMode",
    "get_current_user",
    "get_current_user_standard",
    "get_current_user_async",
    "get_current_user_msa",
    "get_current_user_life_critical",
    "get_current_user_optional",
    "require_scope"
]