"""
Audit Middleware
Automatically captures and publishes audit events for all write operations
"""
import time
from typing import Callable, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse
import json

from core.auth import UserContext
from core.audit.audit_publisher import get_audit_publisher
from models.audit_events import AuditAction, TargetInfo, ResourceType, ChangeDetails
from utils.logger import get_logger

logger = get_logger(__name__)


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware that automatically audits all write operations
    Works in conjunction with AuthMiddleware and RBACMiddleware
    """
    
    def __init__(self, app, audit_config: Optional[dict] = None):
        super().__init__(app)
        self.audit_publisher = get_audit_publisher()
        self.config = audit_config or {}
        
        # Paths to exclude from auditing
        self.exclude_paths = self.config.get("exclude_paths", [
            "/health",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/",
            "/api/v1/rbac-test/generate-tokens"  # Test endpoint
        ])
        
        # Methods that trigger audit
        self.audit_methods = {"POST", "PUT", "PATCH", "DELETE"}
        
        # Path to action mapping
        self.path_action_map = self._build_path_action_map()
    
    def _build_path_action_map(self):
        """Build mapping of URL patterns to audit actions"""
        return {
            # Object Types
            ("POST", "/api/v1/schemas/{branch}/object-types"): (AuditAction.OBJECT_TYPE_CREATE, ResourceType.OBJECT_TYPE),
            ("PUT", "/api/v1/schemas/{branch}/object-types/{type_id}"): (AuditAction.OBJECT_TYPE_UPDATE, ResourceType.OBJECT_TYPE),
            ("PATCH", "/api/v1/schemas/{branch}/object-types/{type_id}"): (AuditAction.OBJECT_TYPE_UPDATE, ResourceType.OBJECT_TYPE),
            ("DELETE", "/api/v1/schemas/{branch}/object-types/{type_id}"): (AuditAction.OBJECT_TYPE_DELETE, ResourceType.OBJECT_TYPE),
            
            # Link Types
            ("POST", "/api/v1/schemas/{branch}/link-types"): (AuditAction.LINK_TYPE_CREATE, ResourceType.LINK_TYPE),
            ("PUT", "/api/v1/schemas/{branch}/link-types/{type_id}"): (AuditAction.LINK_TYPE_UPDATE, ResourceType.LINK_TYPE),
            ("DELETE", "/api/v1/schemas/{branch}/link-types/{type_id}"): (AuditAction.LINK_TYPE_DELETE, ResourceType.LINK_TYPE),
            
            # Action Types
            ("POST", "/action-types"): (AuditAction.ACTION_TYPE_CREATE, ResourceType.ACTION_TYPE),
            ("PUT", "/action-types/{action_type_id}"): (AuditAction.ACTION_TYPE_UPDATE, ResourceType.ACTION_TYPE),
            ("DELETE", "/action-types/{action_type_id}"): (AuditAction.ACTION_TYPE_DELETE, ResourceType.ACTION_TYPE),
            
            # Branches
            ("POST", "/api/v1/branches"): (AuditAction.BRANCH_CREATE, ResourceType.BRANCH),
            ("PUT", "/api/v1/branches/{branch_id}"): (AuditAction.BRANCH_UPDATE, ResourceType.BRANCH),
            ("DELETE", "/api/v1/branches/{branch_id}"): (AuditAction.BRANCH_DELETE, ResourceType.BRANCH),
            ("POST", "/api/v1/branches/{branch_id}/merge"): (AuditAction.BRANCH_MERGE, ResourceType.BRANCH),
            
            # Proposals
            ("POST", "/api/v1/proposals"): (AuditAction.PROPOSAL_CREATE, ResourceType.PROPOSAL),
            ("PUT", "/api/v1/proposals/{proposal_id}"): (AuditAction.PROPOSAL_UPDATE, ResourceType.PROPOSAL),
            ("POST", "/api/v1/proposals/{proposal_id}/approve"): (AuditAction.PROPOSAL_APPROVE, ResourceType.PROPOSAL),
            ("POST", "/api/v1/proposals/{proposal_id}/reject"): (AuditAction.PROPOSAL_REJECT, ResourceType.PROPOSAL),
            
            # Schema operations
            ("POST", "/api/v1/schema/revert"): (AuditAction.SCHEMA_REVERT, ResourceType.SCHEMA),
        }
    
    def _match_path_action(self, method: str, path: str) -> Optional[tuple]:
        """Match request to audit action"""
        # Try exact match first
        key = (method, path)
        if key in self.path_action_map:
            return self.path_action_map[key]
        
        # Try pattern matching
        import re
        for (pattern_method, pattern_path), (action, resource_type) in self.path_action_map.items():
            if method != pattern_method:
                continue
            
            # Convert path pattern to regex
            regex_pattern = pattern_path
            regex_pattern = re.sub(r'\{[^}]+\}', r'[^/]+', regex_pattern)
            regex_pattern = f"^{regex_pattern}$"
            
            if re.match(regex_pattern, path):
                return (action, resource_type)
        
        return None
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip if path is excluded or method is not auditable
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            return await call_next(request)
        
        if request.method not in self.audit_methods:
            return await call_next(request)
        
        # Get user context (set by AuthMiddleware)
        user: Optional[UserContext] = getattr(request.state, "user", None)
        if not user:
            # No user context, skip auditing
            return await call_next(request)
        
        # Capture request details
        start_time = time.time()
        request_id = request.headers.get("X-Request-ID") or str(time.time())
        
        # Try to capture request body for audit
        request_body = None
        if request.method in {"POST", "PUT", "PATCH"}:
            try:
                # Store body for both audit and downstream processing
                body_bytes = await request.body()
                request_body = json.loads(body_bytes) if body_bytes else None
                
                # Reconstruct request with body
                async def receive():
                    return {"type": "http.request", "body": body_bytes}
                request._receive = receive
            except Exception as e:
                logger.warning(f"Failed to capture request body for audit: {e}")
        
        # Process request
        response = await call_next(request)
        
        # Calculate duration
        duration_ms = int((time.time() - start_time) * 1000)
        
        # Determine if operation was successful
        success = 200 <= response.status_code < 400
        
        # Match action and resource type
        action_info = self._match_path_action(request.method, request.url.path)
        if not action_info:
            # Unknown action, log but don't fail
            logger.debug(f"No audit action mapping for {request.method} {request.url.path}")
            return response
        
        action, resource_type = action_info
        
        # Extract resource ID from path
        resource_id = self._extract_resource_id(request.url.path, resource_type)
        branch = self._extract_branch(request.url.path)
        
        # Create target info
        target = TargetInfo(
            resource_type=resource_type,
            resource_id=resource_id or "unknown",
            branch=branch
        )
        
        # Create change details if applicable
        changes = None
        if request_body and request.method in {"POST", "PUT", "PATCH"}:
            changes = ChangeDetails(
                new_values=request_body,
                fields_changed=list(request_body.keys()) if isinstance(request_body, dict) else []
            )
        
        # Get issue information from request state (set by IssueTrackingMiddleware)
        issue_refs = getattr(request.state, "issue_refs", [])
        emergency_override = getattr(request.state, "emergency_override", False)
        override_justification = getattr(request.state, "override_justification", None)
        
        # Build issue metadata
        issue_metadata = {}
        if issue_refs:
            issue_metadata["primary_issue"] = issue_refs[0].get_display_name()
            if len(issue_refs) > 1:
                issue_metadata["related_issues"] = [ref.get_display_name() for ref in issue_refs[1:]]
        if emergency_override:
            issue_metadata["emergency_override"] = True
            issue_metadata["override_justification"] = override_justification
        
        # Publish audit event
        try:
            await self.audit_publisher.publish_audit_event(
                action=action,
                user=user,
                target=target,
                changes=changes,
                success=success,
                error_code=str(response.status_code) if not success else None,
                request_id=request_id,
                duration_ms=duration_ms,
                metadata={
                    "method": request.method,
                    "path": request.url.path,
                    "query": str(request.url.query),
                    "ip_address": request.client.host if request.client else None,
                    "user_agent": request.headers.get("User-Agent"),
                    **issue_metadata  # Include issue tracking information
                }
            )
        except Exception as e:
            logger.error(f"Failed to publish audit event: {e}")
            # Don't fail the request if audit fails
        
        return response
    
    def _extract_resource_id(self, path: str, resource_type: ResourceType) -> Optional[str]:
        """Extract resource ID from path"""
        parts = path.strip("/").split("/")
        
        # Common patterns
        if resource_type == ResourceType.OBJECT_TYPE and "object-types" in path:
            # /api/v1/schemas/{branch}/object-types/{type_id}
            if len(parts) > 5:
                return parts[5]
        elif resource_type == ResourceType.LINK_TYPE and "link-types" in path:
            if len(parts) > 5:
                return parts[5]
        elif resource_type == ResourceType.ACTION_TYPE and "action-types" in path:
            if len(parts) > 1:
                return parts[-1]
        elif resource_type == ResourceType.BRANCH and "branches" in path:
            if len(parts) > 3:
                return parts[3]
        elif resource_type == ResourceType.PROPOSAL and "proposals" in path:
            if len(parts) > 3:
                return parts[3]
        
        return None
    
    def _extract_branch(self, path: str) -> Optional[str]:
        """Extract branch from path"""
        parts = path.strip("/").split("/")
        
        # /api/v1/schemas/{branch}/...
        if len(parts) > 3 and parts[2] == "schemas":
            return parts[3]
        
        return None