"""
MSA Authentication Middleware
Uses IAM microservice for JWT validation
No circular dependencies
"""
import os
from typing import Optional, Callable, Dict, Any
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


class MSAAuthMiddleware(BaseHTTPMiddleware):
    """
    Microservice Architecture Authentication Middleware
    - Validates JWT tokens via IAM service
    - Stores user context in request.state
    - Skips authentication for public paths
    - Implements token caching for performance
    """
    
    def __init__(self, app, public_paths: Optional[list] = None):
        super().__init__(app)
        self.public_paths = public_paths or [
            "/health",
            "/ready", 
            "/metrics",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/favicon.ico"
        ]
        self.permission_checker = get_permission_checker()
        self.iam_integration = get_iam_integration()
        self.iam_client = get_iam_client()
        
        # Simple in-memory cache (consider Redis for production)
        self._token_cache: Dict[str, tuple[UserContext, datetime]] = {}
        self.cache_ttl = int(os.getenv("AUTH_CACHE_TTL", "300"))  # 5 minutes
        
        # Configuration
        self.require_auth = os.getenv("REQUIRE_AUTH", "true").lower() == "true"
        self.validate_scopes = os.getenv("VALIDATE_SCOPES", "true").lower() == "true"
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request through authentication
        """
        # Skip auth for public paths
        if self._is_public_path(request.url.path):
            request.state.user = None
            return await call_next(request)
        
        # Skip auth if disabled (development only)
        if not self.require_auth:
            request.state.user = self._get_default_user()
            return await call_next(request)
        
        try:
            # Extract token
            token = self._extract_token(request)
            if not token:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Missing authentication token",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            # Get user context (with caching)
            user_context = await self._get_user_context(token)
            if not user_context:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token",
                    headers={"WWW-Authenticate": "Bearer"}
                )
            
            # Validate scopes for the endpoint
            if self.validate_scopes:
                await self._validate_endpoint_scopes(request, user_context)
            
            # Store user context
            request.state.user = user_context
            
            # Process request
            response = await call_next(request)
            
            # Add auth headers to response
            response.headers["X-User-ID"] = user_context.user_id
            response.headers["X-Auth-Method"] = "iam-msa"
            
            return response
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service error"
            )
    
    def _is_public_path(self, path: str) -> bool:
        """Check if path is public"""
        # Exact matches
        if path in self.public_paths:
            return True
        
        # Prefix matches
        public_prefixes = ["/api/v1/public/", "/static/"]
        return any(path.startswith(prefix) for prefix in public_prefixes)
    
    def _extract_token(self, request: Request) -> Optional[str]:
        """Extract bearer token from request"""
        # Check Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            return auth_header[7:]
        
        # Check cookie (for web apps)
        return request.cookies.get("access_token")
    
    async def _get_user_context(self, token: str) -> Optional[UserContext]:
        """Get user context with caching"""
        # Check cache
        cache_key = token[:20]  # Use first 20 chars as key
        if cache_key in self._token_cache:
            user_context, expires_at = self._token_cache[cache_key]
            if datetime.utcnow() < expires_at:
                logger.debug(f"Cache hit for user {user_context.user_id}")
                return user_context
            else:
                del self._token_cache[cache_key]
        
        # Validate with IAM service
        try:
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
            return None
    
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
        # Map HTTP methods to actions
        method_action_map = {
            "GET": "read",
            "POST": "create",
            "PUT": "update",
            "PATCH": "update",
            "DELETE": "delete"
        }
        
        action = method_action_map.get(request.method, "read")
        
        # Determine resource type from path
        path_parts = request.url.path.strip("/").split("/")
        resource_type = self._get_resource_type(path_parts)
        
        if resource_type:
            # Get required scopes
            required_scopes = self.iam_integration.get_required_scopes(resource_type, action)
            
            if required_scopes:
                # Check if user has any of the required scopes
                if not self.iam_integration.check_any_scope(user_context, required_scopes):
                    logger.warning(
                        f"User {user_context.user_id} lacks scopes for {resource_type}:{action}. "
                        f"Required: {required_scopes}, Has: {user_context.metadata.get('scopes', [])}"
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Insufficient permissions for {resource_type} {action}"
                    )
    
    def _get_resource_type(self, path_parts: list) -> Optional[str]:
        """Extract resource type from URL path"""
        # Map URL patterns to resource types
        if "schemas" in path_parts:
            if "object-types" in path_parts:
                return "object_type"
            elif "link-types" in path_parts:
                return "link_type"
            else:
                return "schema"
        elif "branches" in path_parts:
            return "branch"
        elif "proposals" in path_parts:
            return "proposal"
        elif "audit" in path_parts:
            return "audit"
        elif "webhooks" in path_parts or "action-types" in path_parts:
            return "webhook"
        
        return None
    
    def _get_default_user(self) -> UserContext:
        """Get default user for development"""
        return UserContext(
            user_id="dev-user",
            username="developer",
            email="dev@example.com",
            roles=["admin"],
            metadata={
                "scopes": [
                    IAMScope.SYSTEM_ADMIN,
                    IAMScope.ONTOLOGIES_ADMIN,
                    IAMScope.SCHEMAS_WRITE,
                    IAMScope.BRANCHES_WRITE,
                    IAMScope.PROPOSALS_APPROVE
                ],
                "auth_method": "dev-bypass"
            }
        )


async def get_current_user(request: Request) -> UserContext:
    """
    Dependency to get current authenticated user
    
    Usage:
        @router.get("/api/resource")
        async def get_resource(user: UserContext = Depends(get_current_user)):
            return {"user_id": user.user_id}
    """
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return user


async def require_scopes(*scopes: str):
    """
    Dependency to require specific scopes
    
    Usage:
        @router.post("/api/admin-action")
        async def admin_action(
            user: UserContext = Depends(get_current_user),
            _: None = Depends(require_scopes(IAMScope.SYSTEM_ADMIN))
        ):
            return {"status": "admin action performed"}
    """
    async def scope_checker(user: UserContext = Depends(get_current_user)):
        iam = get_iam_integration()
        if not iam.check_any_scope(user, list(scopes)):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Required scopes: {', '.join(scopes)}"
            )
    
    return scope_checker