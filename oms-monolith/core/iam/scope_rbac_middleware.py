"""
Scope-based RBAC Middleware
Enhanced RBAC middleware that supports both role-based and scope-based authorization
"""
from typing import Callable, Optional, List, Dict, Tuple
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from core.auth import UserContext
from core.iam.iam_integration import get_iam_integration, IAMScope
from models.permissions import ResourceType, Action
from utils.logger import get_logger

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
        
        # Build scope requirements for each endpoint
        self.endpoint_scopes = self._build_endpoint_scopes()
    
    def _build_endpoint_scopes(self) -> Dict[str, List[str]]:
        """
        Build mapping of endpoints to required scopes
        Can be either a single scope or multiple scopes (ANY match)
        """
        return {
            # Schema endpoints
            "GET:/api/v1/schemas": [IAMScope.SCHEMAS_READ],
            "POST:/api/v1/schemas": [IAMScope.SCHEMAS_WRITE],
            
            # Object Types
            "GET:/api/v1/schemas/{branch}/object-types": [IAMScope.ONTOLOGIES_READ],
            "POST:/api/v1/schemas/{branch}/object-types": [IAMScope.ONTOLOGIES_WRITE],
            "PUT:/api/v1/schemas/{branch}/object-types/{type_id}": [IAMScope.ONTOLOGIES_WRITE],
            "DELETE:/api/v1/schemas/{branch}/object-types/{type_id}": [IAMScope.ONTOLOGIES_WRITE, IAMScope.ONTOLOGIES_ADMIN],
            
            # Link Types
            "GET:/api/v1/schemas/{branch}/link-types": [IAMScope.ONTOLOGIES_READ],
            "POST:/api/v1/schemas/{branch}/link-types": [IAMScope.ONTOLOGIES_WRITE],
            "PUT:/api/v1/schemas/{branch}/link-types/{type_id}": [IAMScope.ONTOLOGIES_WRITE],
            "DELETE:/api/v1/schemas/{branch}/link-types/{type_id}": [IAMScope.ONTOLOGIES_WRITE, IAMScope.ONTOLOGIES_ADMIN],
            
            # Branches
            "GET:/api/v1/branches": [IAMScope.BRANCHES_READ],
            "POST:/api/v1/branches": [IAMScope.BRANCHES_WRITE],
            "GET:/api/v1/branches/{branch_id}": [IAMScope.BRANCHES_READ],
            "PUT:/api/v1/branches/{branch_id}": [IAMScope.BRANCHES_WRITE],
            "DELETE:/api/v1/branches/{branch_id}": [IAMScope.BRANCHES_WRITE],
            "POST:/api/v1/branches/{branch_id}/merge": [IAMScope.BRANCHES_WRITE],
            
            # Proposals
            "GET:/api/v1/proposals": [IAMScope.PROPOSALS_READ],
            "POST:/api/v1/proposals": [IAMScope.PROPOSALS_WRITE],
            "GET:/api/v1/proposals/{proposal_id}": [IAMScope.PROPOSALS_READ],
            "PUT:/api/v1/proposals/{proposal_id}": [IAMScope.PROPOSALS_WRITE],
            "POST:/api/v1/proposals/{proposal_id}/approve": [IAMScope.PROPOSALS_APPROVE],
            "POST:/api/v1/proposals/{proposal_id}/reject": [IAMScope.PROPOSALS_APPROVE],
            
            # Audit
            "GET:/api/v1/audit": [IAMScope.AUDIT_READ],
            
            # System operations
            "POST:/api/v1/schema/revert": [IAMScope.SCHEMAS_WRITE, IAMScope.ONTOLOGIES_ADMIN],
            
            # GraphQL - check at resolver level for fine-grained control
            "POST:/graphql": [IAMScope.ONTOLOGIES_READ],  # Minimum for access
        }
    
    def _match_endpoint_scopes(self, method: str, path: str) -> Optional[List[str]]:
        """
        Match request to required scopes
        Returns list of scopes (ANY match required)
        """
        # Try exact match
        endpoint_key = f"{method}:{path}"
        if endpoint_key in self.endpoint_scopes:
            return self.endpoint_scopes[endpoint_key]
        
        # Try pattern matching
        import re
        for pattern_key, scopes in self.endpoint_scopes.items():
            pattern_method, pattern_path = pattern_key.split(":", 1)
            if method != pattern_method:
                continue
            
            # Convert pattern to regex
            regex_pattern = pattern_path
            regex_pattern = re.sub(r'\{[^}]+\}', r'[^/]+', regex_pattern)
            regex_pattern = f"^{regex_pattern}$"
            
            if re.match(regex_pattern, path):
                return scopes
        
        return None
    
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
        
        # Check if user has system admin scope (bypass all checks)
        if self.iam.check_scope(user, IAMScope.SYSTEM_ADMIN):
            logger.debug(f"System admin access granted for {user.username}")
            return await call_next(request)
        
        # Find required scopes for this endpoint
        required_scopes = self._match_endpoint_scopes(request.method, request.url.path)
        
        if required_scopes:
            # Check if user has any of the required scopes
            if not self.iam.check_any_scope(user, required_scopes):
                logger.warning(
                    f"Scope check failed for user {user.username} "
                    f"on {request.method} {request.url.path}. "
                    f"Required: {required_scopes}, "
                    f"User has: {user.metadata.get('scopes', [])}"
                )
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={
                        "detail": "Insufficient permissions",
                        "required_scopes": required_scopes,
                        "user_scopes": user.metadata.get("scopes", [])
                    }
                )
            
            logger.debug(
                f"Scope check passed for user {user.username} "
                f"on {request.method} {request.url.path}"
            )
        else:
            # No specific scope requirement
            # This is where traditional role-based checks would apply
            # The existing RBACMiddleware will handle this
            logger.debug(
                f"No scope requirement for {request.method} {request.url.path}, "
                f"deferring to role-based checks"
            )
        
        # Continue to next middleware
        return await call_next(request)


def create_scope_rbac_middleware(config: Optional[Dict] = None):
    """Factory function to create ScopeRBACMiddleware"""
    def middleware(app):
        return ScopeRBACMiddleware(app, config)
    return middleware