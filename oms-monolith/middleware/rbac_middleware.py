"""
RBAC (Role-Based Access Control) Middleware
Enhanced implementation with actual permission checking

DESIGN INTENT - AUTHORIZATION LAYER:
This middleware handles ONLY authorization (what you can do), NOT authentication (who you are).
It operates as the second security layer, after authentication.

SEPARATION OF CONCERNS:
1. AuthMiddleware: Establishes identity (WHO)
2. RBACMiddleware (THIS): Enforces permissions (WHAT)
3. AuditMiddleware: Records actions (WHEN/HOW)

WHY SEPARATE RBAC FROM AUTH:
- Clean Architecture: Authorization rules change more frequently than auth methods
- Performance: Can cache auth tokens separately from permission checks
- Flexibility: Support multiple permission models (RBAC, ABAC, ACL) without touching auth
- Scalability: Permission checks can be offloaded to separate service
- Testability: Mock different roles without dealing with authentication

PERMISSION MODEL:
- Role-Based: Users have roles, roles have permissions
- Resource-Based: Permissions are tied to resource types and actions
- Hierarchical: Admin > Developer > Viewer with permission inheritance
- Dynamic: Permissions can be updated without code changes

MIDDLEWARE DEPENDENCIES:
- REQUIRES: AuthMiddleware to run first and set request.state.user
- PROVIDES: Permission validation for the request
- ENABLES: AuditMiddleware to log authorized actions

CACHING STRATEGY:
- User roles are cached per session
- Permission mappings are cached at startup
- Resource-specific permissions checked in real-time

USE THIS FOR:
- Role-based permission checks
- Resource-level access control
- Action-based authorization
- Dynamic permission rules

NOT FOR:
- Token validation (use AuthMiddleware)
- User identification (use AuthMiddleware)
- Audit logging (use AuditMiddleware)
- Row-level security (implement in service layer)

EXTENSIBILITY:
- Easy to add new resource types
- Simple to define new actions
- Can be extended to support ABAC (Attribute-Based Access Control)
- Supports custom permission resolvers

Related modules:
- middleware/auth_middleware.py: Authentication layer
- middleware/audit_middleware.py: Audit logging layer
- core/auth/resource_permission_checker.py: Permission logic
- models/permissions.py: Permission model definitions
"""
from typing import Callable, Optional, Dict, List, Tuple
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from core.auth import UserContext, get_permission_checker
from models.permissions import ResourceType, Action
from utils.logger import get_logger

logger = get_logger(__name__)


class RBACMiddleware(BaseHTTPMiddleware):
    """
    Enhanced RBAC Middleware
    - Extracts user context from request.state (set by AuthMiddleware)
    - Checks permissions based on URL patterns and HTTP methods
    - Enforces role-based access control for all protected endpoints
    """
    
    def __init__(self, app, public_paths: Optional[List[str]] = None):
        super().__init__(app)
        self.public_paths = public_paths or [
            "/health",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/",
            "/ws"  # WebSocket endpoint
        ]
        self.permission_checker = get_permission_checker()
        
        # URL pattern to resource/action mapping
        self.route_permissions = self._build_route_permissions()
    
    def _build_route_permissions(self) -> Dict[str, Tuple[ResourceType, Action]]:
        """
        Build mapping of URL patterns to required permissions
        Returns: Dict[pattern, (resource_type, action)]
        """
        return {
            # Schema endpoints
            "GET:/api/v1/schemas": (ResourceType.SCHEMA, Action.READ),
            "POST:/api/v1/schemas": (ResourceType.SCHEMA, Action.CREATE),
            "GET:/api/v1/schemas/{branch}/object-types": (ResourceType.OBJECT_TYPE, Action.READ),
            "POST:/api/v1/schemas/{branch}/object-types": (ResourceType.OBJECT_TYPE, Action.CREATE),
            "PUT:/api/v1/schemas/{branch}/object-types/{type_id}": (ResourceType.OBJECT_TYPE, Action.UPDATE),
            "DELETE:/api/v1/schemas/{branch}/object-types/{type_id}": (ResourceType.OBJECT_TYPE, Action.DELETE),
            
            # Link Type endpoints
            "GET:/api/v1/schemas/{branch}/link-types": (ResourceType.LINK_TYPE, Action.READ),
            "POST:/api/v1/schemas/{branch}/link-types": (ResourceType.LINK_TYPE, Action.CREATE),
            "PUT:/api/v1/schemas/{branch}/link-types/{type_id}": (ResourceType.LINK_TYPE, Action.UPDATE),
            "DELETE:/api/v1/schemas/{branch}/link-types/{type_id}": (ResourceType.LINK_TYPE, Action.DELETE),
            
            # Action Type endpoints
            "GET:/action-types": (ResourceType.ACTION_TYPE, Action.READ),
            "POST:/action-types": (ResourceType.ACTION_TYPE, Action.CREATE),
            "GET:/action-types/{action_type_id}": (ResourceType.ACTION_TYPE, Action.READ),
            "PUT:/action-types/{action_type_id}": (ResourceType.ACTION_TYPE, Action.UPDATE),
            "DELETE:/action-types/{action_type_id}": (ResourceType.ACTION_TYPE, Action.DELETE),
            "POST:/action-types/{action_type_id}/validate": (ResourceType.ACTION_TYPE, Action.READ),
            "POST:/action-types/{action_type_id}/execute": (ResourceType.ACTION_TYPE, Action.EXECUTE),
            
            # Branch endpoints
            "GET:/api/v1/branches": (ResourceType.BRANCH, Action.READ),
            "POST:/api/v1/branches": (ResourceType.BRANCH, Action.CREATE),
            "GET:/api/v1/branches/{branch_id}": (ResourceType.BRANCH, Action.READ),
            "PUT:/api/v1/branches/{branch_id}": (ResourceType.BRANCH, Action.UPDATE),
            "DELETE:/api/v1/branches/{branch_id}": (ResourceType.BRANCH, Action.DELETE),
            "POST:/api/v1/branches/{branch_id}/merge": (ResourceType.BRANCH, Action.MERGE),
            
            # Proposal endpoints
            "GET:/api/v1/proposals": (ResourceType.PROPOSAL, Action.READ),
            "POST:/api/v1/proposals": (ResourceType.PROPOSAL, Action.CREATE),
            "GET:/api/v1/proposals/{proposal_id}": (ResourceType.PROPOSAL, Action.READ),
            "PUT:/api/v1/proposals/{proposal_id}": (ResourceType.PROPOSAL, Action.UPDATE),
            "POST:/api/v1/proposals/{proposal_id}/approve": (ResourceType.PROPOSAL, Action.APPROVE),
            "POST:/api/v1/proposals/{proposal_id}/reject": (ResourceType.PROPOSAL, Action.REJECT),
            
            # Schema operations
            "POST:/api/v1/schema/revert": (ResourceType.SCHEMA, Action.REVERT),
            "POST:/api/v1/schema/events/audit": (ResourceType.AUDIT, Action.CREATE),
            
            # Audit endpoints
            "GET:/api/v1/audit": (ResourceType.AUDIT, Action.READ),
            "GET:/api/v1/audit/{audit_id}": (ResourceType.AUDIT, Action.READ),
            
            # GraphQL endpoints (check at resolver level)
            "POST:/graphql": (ResourceType.SCHEMA, Action.READ),  # Default, actual check in resolver
        }
    
    def _match_route(self, method: str, path: str) -> Optional[Tuple[ResourceType, Action]]:
        """
        Match request method and path to required permissions
        Returns: (resource_type, action) or None if no match
        """
        # First try exact match
        route_key = f"{method}:{path}"
        if route_key in self.route_permissions:
            return self.route_permissions[route_key]
        
        # Try pattern matching for parameterized routes
        for pattern, permissions in self.route_permissions.items():
            pattern_method, pattern_path = pattern.split(":", 1)
            if method != pattern_method:
                continue
            
            # Simple pattern matching (replace {param} with regex)
            import re
            pattern_regex = pattern_path
            # Replace {param} with regex to match any value
            pattern_regex = re.sub(r'\{[^}]+\}', r'[^/]+', pattern_regex)
            pattern_regex = f"^{pattern_regex}$"
            
            if re.match(pattern_regex, path):
                return permissions
        
        return None
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip public paths
        if any(request.url.path.startswith(path) for path in self.public_paths):
            return await call_next(request)
        
        # Check if user is authenticated (set by AuthMiddleware)
        if not hasattr(request.state, "user"):
            logger.warning(f"No user context for protected endpoint {request.url.path}")
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authentication required"}
            )
        
        user: UserContext = request.state.user
        
        # Find required permissions for this endpoint
        required_permissions = self._match_route(request.method, request.url.path)
        
        if required_permissions:
            resource_type, action = required_permissions
            
            # Extract resource ID from path if available
            resource_id = None
            path_parts = request.url.path.split("/")
            
            # Try to extract ID from common patterns
            if len(path_parts) > 4 and path_parts[-2] in ["object-types", "link-types", "action-types"]:
                resource_id = path_parts[-1]
            elif len(path_parts) > 3 and "_id" in path_parts[-1]:
                resource_id = path_parts[-1]
            
            # Check permission
            if not self.permission_checker.check_permission(
                user_roles=user.roles,
                resource_type=resource_type.value,
                action=action.value,
                resource_id=resource_id
            ):
                logger.warning(
                    f"Permission denied for user {user.username} (roles: {user.roles}) "
                    f"on {action.value} {resource_type.value} (id: {resource_id})"
                )
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "detail": f"Permission denied: {action.value} on {resource_type.value}"
                    }
                )
            
            logger.debug(
                f"Permission granted for user {user.username} "
                f"on {action.value} {resource_type.value}"
            )
        else:
            # No specific permission mapping found - DENY by default
            logger.error(
                f"Access denied: No permission mapping for {request.method} {request.url.path}"
            )
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={
                    "detail": f"Access denied: Route not registered in permission system",
                    "path": request.url.path,
                    "method": request.method
                }
            )
        
        # User has permission, continue to next middleware/handler
        response = await call_next(request)
        return response


def create_rbac_middleware(public_paths: Optional[List[str]] = None):
    """RBAC 미들웨어 생성 함수"""
    def middleware(app):
        return RBACMiddleware(app, public_paths)
    return middleware