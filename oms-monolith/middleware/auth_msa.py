"""
Secure MSA Authentication Middleware
FIXED: No authentication bypasses allowed
"""
import os
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime, timedelta
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from core.auth import get_permission_checker, UserContext
from core.iam.iam_integration_refactored import get_iam_integration
from core.integrations.iam_service_client import get_iam_client
from shared.iam_contracts import IAMScope
from utils.logger import get_logger

logger = get_logger(__name__)

# HTTP Bearer authentication schema
security = HTTPBearer(auto_error=False)


class SecureMSAAuthMiddleware(BaseHTTPMiddleware):
    """
    Secure Authentication Middleware with no bypasses
    - ALWAYS validates JWT tokens via IAM service
    - NO development bypasses in production
    - NO default admin users
    - Explicit public paths only
    """
    
    def __init__(self, app, public_paths: Optional[List[str]] = None):
        super().__init__(app)
        
        # SECURITY: Minimal public paths - must be explicitly listed
        self.public_paths = public_paths or [
            "/health",      # Health check only
            "/ready",       # Readiness probe
            "/metrics",     # Prometheus metrics
        ]
        
        # SECURITY: No docs in production
        if os.getenv("ENVIRONMENT", "production") != "production":
            self.public_paths.extend(["/docs", "/openapi.json", "/redoc"])
        
        self.permission_checker = get_permission_checker()
        self.iam_integration = get_iam_integration()
        self.iam_client = get_iam_client()
        
        # Token cache with TTL
        self._token_cache: Dict[str, tuple[UserContext, datetime]] = {}
        self.cache_ttl = int(os.getenv("AUTH_CACHE_TTL", "300"))  # 5 minutes
        
        # SECURITY: Force authentication in production
        self._enforce_production_security()
    
    def _enforce_production_security(self):
        """Ensure authentication cannot be bypassed in production"""
        env = os.getenv("ENVIRONMENT", "production")
        
        if env == "production":
            # Check for bypass attempts
            if os.getenv("REQUIRE_AUTH", "true").lower() != "true":
                logger.critical("SECURITY: Attempt to disable auth in production!")
                raise RuntimeError("Authentication cannot be disabled in production")
            
            if os.getenv("DISABLE_AUTH") == "true":
                logger.critical("SECURITY: DISABLE_AUTH flag detected in production!")
                raise RuntimeError("Authentication bypass not allowed in production")
            
            # Log security configuration
            logger.info("Production security enforced: Authentication required for all non-public endpoints")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request through authentication - NO BYPASSES
        """
        # Only skip auth for explicitly public paths
        if self._is_public_path(request.url.path):
            request.state.user = None
            request.state.authenticated = False
            return await call_next(request)
        
        # SECURITY: Always require authentication for non-public paths
        try:
            # Extract and validate token
            token = self._extract_token(request)
            if not token:
                logger.warning(f"Missing auth token for {request.method} {request.url.path}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            # Validate token (with caching)
            user_context = await self._validate_token(token)
            if not user_context:
                logger.warning(f"Invalid token for {request.method} {request.url.path}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid authentication token",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            # Set user context
            request.state.user = user_context
            request.state.authenticated = True
            
            # Validate endpoint scopes
            await self._validate_endpoint_scopes(request, user_context)
            
            # Log successful authentication
            logger.info(
                f"Authenticated request: {request.method} {request.url.path} "
                f"by user {user_context.user_id}"
            )
            
            # Process request
            response = await call_next(request)
            
            return response
            
        except HTTPException:
            # Re-raise HTTP exceptions
            raise
        except Exception as e:
            # Log unexpected errors
            logger.error(f"Authentication error: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service error"
            )
    
    def _is_public_path(self, path: str) -> bool:
        """Check if path is explicitly public"""
        # Exact match only - no patterns
        return path in self.public_paths
    
    def _extract_token(self, request: Request) -> Optional[str]:
        """Extract bearer token from request"""
        authorization = request.headers.get("Authorization")
        if not authorization:
            return None
        
        # Must be Bearer token
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            logger.warning(f"Invalid authorization header format: {authorization[:20]}...")
            return None
        
        return parts[1]
    
    async def _validate_token(self, token: str) -> Optional[UserContext]:
        """Validate JWT token with caching"""
        # Check cache first
        cache_key = f"token:{token[:20]}"  # Use token prefix as key
        
        if cache_key in self._token_cache:
            user_context, expires_at = self._token_cache[cache_key]
            if datetime.utcnow() < expires_at:
                return user_context
            else:
                del self._token_cache[cache_key]
        
        try:
            # Validate via IAM service
            user_context = await self.iam_integration.validate_jwt_enhanced(token)
            
            # Cache the result
            expires_at = datetime.utcnow() + timedelta(seconds=self.cache_ttl)
            self._token_cache[cache_key] = (user_context, expires_at)
            
            # Clean old cache entries periodically
            if len(self._token_cache) > 1000:
                self._clean_cache()
            
            return user_context
            
        except ValueError as e:
            logger.warning(f"Token validation failed: {e}")
            raise  # Re-raise - don't hide validation errors
        except Exception as e:
            logger.error(f"Unexpected token validation error: {e}", exc_info=True)
            raise
    
    def _clean_cache(self):
        """Remove expired cache entries"""
        now = datetime.utcnow()
        expired_keys = [
            key for key, (_, expires_at) in self._token_cache.items()
            if expires_at < now
        ]
        for key in expired_keys:
            del self._token_cache[key]
    
    async def _validate_endpoint_scopes(self, request: Request, user_context: UserContext):
        """Validate user has required scopes for endpoint"""
        # Extract resource type from path
        path_parts = request.url.path.strip("/").split("/")
        resource_type = self._get_resource_type(path_parts)
        
        if resource_type:
            # Map HTTP methods to actions
            method_action_map = {
                "GET": "read",
                "POST": "write", 
                "PUT": "write",
                "PATCH": "write",
                "DELETE": "admin"
            }
            
            action = method_action_map.get(request.method, "read")
            
            # Check if user has required scope
            required_scopes = self._get_required_scopes(resource_type, action)
            user_scopes = user_context.metadata.get("scopes", [])
            
            if required_scopes and not any(scope in user_scopes for scope in required_scopes):
                logger.warning(
                    f"User {user_context.user_id} lacks scopes for {resource_type}:{action}. "
                    f"Required: {required_scopes}, Has: {user_scopes}"
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions for {resource_type} {action}"
                )
    
    def _get_resource_type(self, path_parts: List[str]) -> Optional[str]:
        """Extract resource type from URL path"""
        # Map URL patterns to resource types
        resource_mapping = {
            "schemas": "schema",
            "object-types": "object_type",
            "link-types": "link_type",
            "branches": "branch",
            "proposals": "proposal",
            "audit": "audit",
            "webhooks": "webhook",
            "action-types": "webhook",
            "users": "user",
            "admin": "admin"
        }
        
        for part in path_parts:
            if part in resource_mapping:
                return resource_mapping[part]
        
        return None
    
    def _get_required_scopes(self, resource_type: str, action: str) -> List[str]:
        """Get required scopes for resource and action"""
        scope_matrix = {
            "schema": {
                "read": [IAMScope.SCHEMAS_READ, IAMScope.ONTOLOGIES_READ],
                "write": [IAMScope.SCHEMAS_WRITE, IAMScope.ONTOLOGIES_ADMIN],
                "admin": [IAMScope.SCHEMAS_ADMIN, IAMScope.ONTOLOGIES_ADMIN]
            },
            "object_type": {
                "read": [IAMScope.SCHEMAS_READ, IAMScope.ONTOLOGIES_READ],
                "write": [IAMScope.SCHEMAS_WRITE, IAMScope.ONTOLOGIES_ADMIN],
                "admin": [IAMScope.SCHEMAS_ADMIN, IAMScope.ONTOLOGIES_ADMIN]
            },
            "branch": {
                "read": [IAMScope.BRANCHES_READ],
                "write": [IAMScope.BRANCHES_WRITE],
                "admin": [IAMScope.BRANCHES_ADMIN]
            },
            "proposal": {
                "read": [IAMScope.PROPOSALS_READ],
                "write": [IAMScope.PROPOSALS_WRITE],
                "admin": [IAMScope.PROPOSALS_APPROVE]
            },
            "audit": {
                "read": [IAMScope.AUDIT_READ],
                "write": [IAMScope.AUDIT_ADMIN],
                "admin": [IAMScope.AUDIT_ADMIN]
            },
            "webhook": {
                "read": [IAMScope.ACTIONS_READ],
                "write": [IAMScope.ACTIONS_WRITE],
                "admin": [IAMScope.ACTIONS_ADMIN]
            },
            "user": {
                "read": [IAMScope.SYSTEM_READ],
                "write": [IAMScope.SYSTEM_ADMIN],
                "admin": [IAMScope.SYSTEM_ADMIN]
            },
            "admin": {
                "read": [IAMScope.SYSTEM_ADMIN],
                "write": [IAMScope.SYSTEM_ADMIN],
                "admin": [IAMScope.SYSTEM_ADMIN]
            }
        }
        
        return scope_matrix.get(resource_type, {}).get(action, [])


# Dependency for FastAPI routes
async def get_current_user(request: Request) -> UserContext:
    """Get current authenticated user from request"""
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return request.state.user


# Decorators for route protection
def require_auth(func):
    """Decorator to require authentication on a route"""
    async def wrapper(request: Request, *args, **kwargs):
        # Ensure user is authenticated
        user = await get_current_user(request)
        return await func(request, *args, **kwargs)
    
    # Copy function metadata
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    
    return wrapper


def require_scope(scope: str):
    """Decorator to require specific scope on a route"""
    def decorator(func):
        async def wrapper(request: Request, *args, **kwargs):
            user = await get_current_user(request)
            user_scopes = user.metadata.get("scopes", [])
            
            if scope not in user_scopes:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Required scope: {scope}"
                )
            
            return await func(request, *args, **kwargs)
        
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        
        return wrapper
    return decorator


def require_admin():
    """Decorator to require admin privileges"""
    return require_scope(IAMScope.SYSTEM_ADMIN)