"""
Scope-based RBAC Middleware
Enhanced RBAC middleware that supports both role-based and scope-based authorization
"""
from typing import Callable, Optional, List, Dict, Tuple
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from core.auth_utils import UserContext
from core.iam.iam_integration import get_iam_integration, IAMScope
from models.permissions import ResourceType, Action
from common_logging.setup import get_logger
from shared.terminus_context import get_branch, is_readonly_branch

logger = get_logger(__name__)


class ScopeRBACMiddleware(BaseHTTPMiddleware):
    """
    Enhanced RBAC Middleware that supports both traditional roles and IAM scopes
    Works as a layer on top of the existing RBAC middleware
    """
    
    def __init__(self, app, config: Optional[Dict] = None):
        super().__init__(app)
        self.iam = get_iam_integration()
        self.config = config or {}
        
        # Public paths that don't require authorization
        self.public_paths = self.config.get("public_paths", [
            "/health",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/",
            "/ws",
            "/api/v1/rbac-test/generate-tokens"
        ])
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip public paths
        if any(request.url.path.startswith(path) for path in self.public_paths):
            return await call_next(request)
        
        # Get user context (set by AuthMiddleware)
        if not hasattr(request.state, "user"):
            logger.warning(f"No user context for protected endpoint {request.url.path}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authentication required"}
            )
        
        user: UserContext = request.state.user
        
        # Fetch real permissions from user-service if not cached
        # This part remains to ensure permissions are loaded into the user context
        # for potential downstream use, though direct checking is now deprecated here.
        if "permissions" not in user.metadata:
            auth_header = request.headers.get("Authorization", "")
            token = auth_header.replace("Bearer ", "") if auth_header.startswith("Bearer ") else None
            
            if token is None:
                # This should not happen if AuthMiddleware is working correctly,
                # but as a safeguard:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Authorization token missing"}
                )

            try:
                permissions = await self.iam.get_user_permissions(user.user_id, token)
                user.metadata["permissions"] = permissions
                request.state.permissions = permissions
                logger.info(f"Fetched {len(permissions)} permissions for user {user.username}")
            except Exception as e:
                from core.iam.iam_integration import IAMServiceUnavailableError
                if isinstance(e, IAMServiceUnavailableError):
                    logger.error(f"IAM service unavailable: {e}")
                    return JSONResponse(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        content={
                            "detail": "Permission verification service is temporarily unavailable",
                            "error_type": "service_unavailable",
                            "retry_after": 30
                        },
                        headers={"Retry-After": "30"}
                    )
                else:
                    logger.error(f"Unexpected error fetching permissions: {e}")
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={
                            "detail": "Unable to verify permissions",
                            "error_type": "permission_verification_failed"
                        }
                    )
        
        # The core scope-checking logic is now DELEGATED to endpoint dependencies.
        # This middleware now primarily ensures a user context exists and handles
        # broad checks like read-only branches.
        
        # Check branch-based permissions
        if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
            current_branch = get_branch()
            if is_readonly_branch(current_branch):
                logger.warning(
                    f"Write operation denied on read-only branch: {current_branch} "
                    f"by user {user.username}"
                )
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "detail": f"Write operations not allowed on branch: {current_branch}",
                        "branch": current_branch,
                        "readonly": True
                    }
                )
        
        # Continue to next middleware
        return await call_next(request)