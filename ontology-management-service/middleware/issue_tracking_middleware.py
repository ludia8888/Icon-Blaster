"""
Issue Tracking Middleware
Enforces issue ID requirements for all change operations
"""
from typing import Optional, List, Dict, Any, Callable
from fastapi import Request, Response, HTTPException, status
from fastapi.responses import JSONResponse
import json

from core.auth import UserContext
from core.issue_tracking.issue_service import get_issue_service
from models.issue_tracking import IssueReference, parse_issue_reference, extract_issue_references
from common_logging.setup import get_logger

logger = get_logger(__name__)


class IssueTrackingMiddleware:
    """
    Middleware to enforce issue tracking requirements
    """
    
    # Operations that require issue tracking
    TRACKED_OPERATIONS = {
        # Schema operations (fixed paths - note the 's' in schemas)
        ("POST", "/api/v1/schemas/{branch_name}/object-types"): "schema",
        ("PUT", "/api/v1/schemas/{branch_name}/object-types/{type_id}"): "schema",
        ("DELETE", "/api/v1/schemas/{branch_name}/object-types/{type_id}"): "deletion",
        ("POST", "/api/v1/schemas/{branch_name}/link-types"): "schema",
        ("PUT", "/api/v1/schemas/{branch_name}/link-types/{type_id}"): "schema",
        ("DELETE", "/api/v1/schemas/{branch_name}/link-types/{type_id}"): "deletion",
        ("POST", "/api/v1/schemas/{branch_name}/action-types"): "schema",
        ("PUT", "/api/v1/schemas/{branch_name}/action-types/{type_id}"): "schema",
        ("DELETE", "/api/v1/schemas/{branch_name}/action-types/{type_id}"): "deletion",
        ("POST", "/api/v1/schemas/{branch_name}/function-types"): "schema",
        ("PUT", "/api/v1/schemas/{branch_name}/function-types/{type_id}"): "schema",
        ("DELETE", "/api/v1/schemas/{branch_name}/function-types/{type_id}"): "deletion",
        
        # ACL operations
        ("POST", "/api/v1/acl/policies"): "acl",
        ("PUT", "/api/v1/acl/policies/{policy_id}"): "acl",
        ("DELETE", "/api/v1/acl/policies/{policy_id}"): "acl",
        
        # Branch operations
        ("POST", "/api/v1/branches/{branch_name}/merge"): "merge",
        ("DELETE", "/api/v1/branches/{branch_name}"): "deletion",
        
        # Proposal operations
        ("POST", "/api/v1/proposals/{proposal_id}/merge"): "merge",
    }
    
    def __init__(self):
        self.issue_service = None
    
    async def __call__(self, request: Request, call_next: Callable) -> Response:
        """Process request and enforce issue tracking"""
        # Skip if not a tracked operation
        operation_key = (request.method, request.url.path)
        change_type = None
        
        # Check if this is a tracked operation
        for tracked_key, tracked_type in self.TRACKED_OPERATIONS.items():
            method, path_pattern = tracked_key
            if method == request.method and self._matches_path_pattern(request.url.path, path_pattern):
                change_type = tracked_type
                break
        
        if not change_type:
            # Not a tracked operation, pass through
            return await call_next(request)
        
        # Initialize issue service if needed
        if not self.issue_service:
            self.issue_service = await get_issue_service()
        
        # Extract user context
        user = getattr(request.state, "user", None)
        if not user:
            # No user context, pass through (auth middleware should handle this)
            return await call_next(request)
        
        # Extract issue references from request
        issue_refs = await self._extract_issue_references(request)
        
        # Extract branch name from path
        branch_name = self._extract_branch_name(request.url.path)
        
        # Check for emergency override
        emergency_override = False
        override_justification = None
        
        if request.headers.get("X-Emergency-Override") == "true":
            emergency_override = True
            override_justification = request.headers.get("X-Override-Justification", "")
        
        # Validate issue requirements
        is_valid, error_message = await self.issue_service.validate_issue_requirement(
            user=user,
            change_type=change_type,
            branch_name=branch_name,
            issue_refs=issue_refs,
            emergency_override=emergency_override,
            override_justification=override_justification
        )
        
        if not is_valid:
            logger.warning(
                f"Issue validation failed for {request.method} {request.url.path} "
                f"by {user.username}: {error_message}"
            )
            
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={
                    "error": "Issue tracking requirement not met",
                    "message": error_message,
                    "change_type": change_type,
                    "branch": branch_name,
                    "help": "Include issue reference in X-Issue-ID header or request body",
                    "examples": {
                        "header": "X-Issue-ID: JIRA-123",
                        "body_field": "issue_id: 'JIRA-123'",
                        "multiple": "X-Issue-IDs: JIRA-123,GH-456",
                        "emergency": {
                            "header": "X-Emergency-Override: true",
                            "justification": "X-Override-Justification: Critical production fix for data loss"
                        }
                    }
                }
            )
        
        # Store validated issues in request state for downstream use
        request.state.issue_refs = issue_refs
        request.state.emergency_override = emergency_override
        request.state.override_justification = override_justification
        
        # Continue with request
        response = await call_next(request)
        
        # If successful, log the change-issue link
        if 200 <= response.status_code < 300 and issue_refs:
            try:
                # Extract change ID from response if available
                change_id = await self._extract_change_id(response)
                
                if change_id and issue_refs:
                    # Create change-issue link
                    link = await self.issue_service.link_change_to_issues(
                        change_id=change_id,
                        change_type=change_type,
                        branch_name=branch_name,
                        user=user,
                        primary_issue=issue_refs[0],
                        related_issues=issue_refs[1:] if len(issue_refs) > 1 else None,
                        emergency_override=emergency_override,
                        override_justification=override_justification
                    )
                    
                    logger.info(
                        f"Linked change {change_id} to issues: "
                        f"{[ref.get_display_name() for ref in issue_refs]}"
                    )
                    
            except Exception as e:
                logger.error(f"Failed to create change-issue link: {e}")
        
        return response
    
    async def _extract_issue_references(self, request: Request) -> List[IssueReference]:
        """Extract issue references from request headers and body"""
        issue_refs = []
        
        # Check headers
        # Single issue: X-Issue-ID: JIRA-123
        if "X-Issue-ID" in request.headers:
            ref = parse_issue_reference(request.headers["X-Issue-ID"])
            if ref:
                issue_refs.append(ref)
        
        # Multiple issues: X-Issue-IDs: JIRA-123,GH-456
        if "X-Issue-IDs" in request.headers:
            issue_ids = request.headers["X-Issue-IDs"].split(",")
            for issue_id in issue_ids:
                ref = parse_issue_reference(issue_id.strip())
                if ref:
                    issue_refs.append(ref)
        
        # Check request body
        try:
            if request.method in ["POST", "PUT", "PATCH"]:
                # Clone request body
                body = await request.body()
                if body:
                    request._body = body  # Store for downstream use
                    
                    try:
                        data = json.loads(body)
                        
                        # Check for issue_id field
                        if isinstance(data, dict):
                            if "issue_id" in data:
                                ref = parse_issue_reference(str(data["issue_id"]))
                                if ref and ref not in issue_refs:
                                    issue_refs.append(ref)
                            
                            # Check for issue_ids field
                            if "issue_ids" in data and isinstance(data["issue_ids"], list):
                                for issue_id in data["issue_ids"]:
                                    ref = parse_issue_reference(str(issue_id))
                                    if ref and ref not in issue_refs:
                                        issue_refs.append(ref)
                            
                            # Check commit message or description fields
                            for field in ["commit_message", "description", "message", "comment"]:
                                if field in data and isinstance(data[field], str):
                                    extracted = extract_issue_references(data[field])
                                    for ref in extracted:
                                        if ref not in issue_refs:
                                            issue_refs.append(ref)
                                            
                    except json.JSONDecodeError:
                        pass
                        
        except Exception as e:
            logger.debug(f"Error extracting issues from body: {e}")
        
        return issue_refs
    
    def _matches_path_pattern(self, path: str, pattern: str) -> bool:
        """Check if path matches pattern with placeholders"""
        # Convert pattern to regex-like matching
        # e.g., /api/v1/schema/{branch_name}/object-types -> /api/v1/schema/.*/object-types
        
        pattern_parts = pattern.split("/")
        path_parts = path.split("/")
        
        if len(pattern_parts) != len(path_parts):
            return False
        
        for pattern_part, path_part in zip(pattern_parts, path_parts):
            if pattern_part.startswith("{") and pattern_part.endswith("}"):
                # This is a placeholder, any value matches
                continue
            elif pattern_part != path_part:
                return False
        
        return True
    
    def _extract_branch_name(self, path: str) -> str:
        """Extract branch name from path"""
        parts = path.split("/")
        
        # Look for common patterns
        for i, part in enumerate(parts):
            if part == "schemas" and i + 1 < len(parts):  # Fixed: schemas not schema
                return parts[i + 1]
            elif part == "branches" and i + 1 < len(parts):
                return parts[i + 1]
        
        return "unknown"
    
    async def _extract_change_id(self, response: Response) -> Optional[str]:
        """Extract change ID from response"""
        try:
            # Try to get from response headers first
            if "X-Change-ID" in response.headers:
                return response.headers["X-Change-ID"]
            
            # Try to parse response body
            if hasattr(response, "_body"):
                body = response._body
                if body:
                    try:
                        data = json.loads(body)
                        # Look for common ID fields
                        for field in ["id", "change_id", "commit_id", "operation_id"]:
                            if field in data:
                                return str(data[field])
                    except json.JSONDecodeError:
                        pass
                        
        except Exception as e:
            logger.debug(f"Could not extract change ID: {e}")
        
        return None


def configure_issue_tracking(app):
    """Configure issue tracking middleware for the application"""
    middleware = IssueTrackingMiddleware()
    
    @app.middleware("http")
    async def issue_tracking_middleware(request: Request, call_next: Callable) -> Response:
        return await middleware(request, call_next)
    
    logger.info("Issue tracking middleware configured")