"""
Schema Freeze Middleware
Enforces branch locks and prevents write operations during indexing
"""
from typing import Callable, Optional, Dict, Any, List
from datetime import datetime, timezone
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from core.auth import UserContext
from core.branch.lock_manager import get_lock_manager, LockConflictError
from models.branch_state import BranchState
from utils.logger import get_logger

logger = get_logger(__name__)


class SchemaFreezeMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces schema freeze by checking branch locks
    before allowing write operations
    """
    
    def __init__(self, app, config: Optional[Dict] = None):
        super().__init__(app)
        self.lock_manager = get_lock_manager()
        self.config = config or {}
        
        # Paths exempt from freeze checks
        self.exempt_paths = self.config.get("exempt_paths", [
            "/health",
            "/metrics",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/",
            "/ws",
            "/api/v1/rbac-test/",
            "/api/v1/branch-locks/",  # Lock management endpoints
        ])
        
        # Methods that require write permission check
        self.write_methods = {"POST", "PUT", "PATCH", "DELETE"}
        
        # URL patterns that affect schema
        self.schema_affecting_patterns = [
            "/api/v1/schemas/",
            "/action-types/",
            "/api/v1/proposals/",
            "/graphql"  # GraphQL mutations
        ]
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip exempt paths
        if any(request.url.path.startswith(path) for path in self.exempt_paths):
            return await call_next(request)
        
        # Only check write operations on schema-affecting endpoints
        if (request.method in self.write_methods and 
            self._affects_schema(request.url.path)):
            
            # Get user context (set by AuthMiddleware)
            user: Optional[UserContext] = getattr(request.state, "user", None)
            
            # Extract branch from request
            branch_name = self._extract_branch_from_request(request)
            if not branch_name:
                branch_name = "main"  # Default branch
            
            # Extract resource information
            resource_type, resource_id = self._extract_resource_info(request)
            
            try:
                # Check write permission
                can_write, reason = await self.lock_manager.check_write_permission(
                    branch_name=branch_name,
                    action="write",
                    resource_type=resource_type
                )
                
                if not can_write:
                    logger.warning(
                        f"Write operation blocked on {branch_name}: {reason}. "
                        f"User: {user.username if user else 'unknown'}, "
                        f"Path: {request.url.path}"
                    )
                    
                    # Get detailed lock information for better UX
                    lock_info = await self._get_detailed_lock_info(branch_name, resource_type)
                    
                    return JSONResponse(
                        status_code=status.HTTP_423_LOCKED,
                        content={
                            "error": "SchemaFrozen",
                            "message": self._create_user_friendly_message(branch_name, resource_type, lock_info),
                            "reason": reason,
                            "branch": branch_name,
                            "resource_type": resource_type,
                            "lock_scope": lock_info.get("scope", "unknown"),
                            "other_resources_available": lock_info.get("other_resources_available", True),
                            "indexing_progress": lock_info.get("progress_percent"),
                            "eta_seconds": lock_info.get("eta_seconds"),
                            "retry_after": lock_info.get("eta_seconds") or self._estimate_retry_time(branch_name),
                            "alternative_actions": self._suggest_alternatives(resource_type, lock_info)
                        }
                    )
                
                # Add branch info to request state for downstream use
                request.state.branch_name = branch_name
                request.state.schema_freeze_checked = True
                
                logger.debug(
                    f"Schema freeze check passed for {branch_name}: "
                    f"{request.method} {request.url.path}"
                )
                
            except Exception as e:
                logger.error(f"Error checking schema freeze status: {e}")
                # In case of error, allow operation but log warning
                logger.warning(
                    f"Schema freeze check failed, allowing operation: "
                    f"{request.method} {request.url.path}"
                )
        
        # Continue to next middleware/handler
        response = await call_next(request)
        return response
    
    def _affects_schema(self, path: str) -> bool:
        """Check if the path affects schema structure"""
        return any(pattern in path for pattern in self.schema_affecting_patterns)
    
    def _extract_branch_from_request(self, request: Request) -> Optional[str]:
        """Extract branch name from request URL or headers"""
        # Method 1: From URL path (e.g., /api/v1/schemas/{branch}/...)
        path_parts = request.url.path.strip("/").split("/")
        
        if len(path_parts) >= 4 and path_parts[2] == "schemas":
            return path_parts[3]
        
        # Method 2: From query parameters
        branch = request.query_params.get("branch")
        if branch:
            return branch
        
        # Method 3: From headers
        branch = request.headers.get("X-OMS-Branch")
        if branch:
            return branch
        
        # Method 4: From request body (for GraphQL or JSON requests)
        # This would require reading the body, which we'll skip for now
        # to avoid interfering with request processing
        
        return None
    
    def _extract_resource_info(self, request: Request) -> tuple[Optional[str], Optional[str]]:
        """Extract resource type and ID from request"""
        path_parts = request.url.path.strip("/").split("/")
        
        # Pattern: /api/v1/schemas/{branch}/object-types/{id}
        if "object-types" in path_parts:
            resource_type = "object_type"
            try:
                type_index = path_parts.index("object-types")
                if len(path_parts) > type_index + 1:
                    resource_id = path_parts[type_index + 1]
                else:
                    resource_id = None
            except (ValueError, IndexError):
                resource_id = None
            return resource_type, resource_id
        
        # Pattern: /api/v1/schemas/{branch}/link-types/{id}
        if "link-types" in path_parts:
            resource_type = "link_type"
            try:
                type_index = path_parts.index("link-types")
                if len(path_parts) > type_index + 1:
                    resource_id = path_parts[type_index + 1]
                else:
                    resource_id = None
            except (ValueError, IndexError):
                resource_id = None
            return resource_type, resource_id
        
        # Pattern: /action-types/{id}
        if "action-types" in path_parts:
            resource_type = "action_type"
            try:
                type_index = path_parts.index("action-types")
                if len(path_parts) > type_index + 1:
                    resource_id = path_parts[type_index + 1]
                else:
                    resource_id = None
            except (ValueError, IndexError):
                resource_id = None
            return resource_type, resource_id
        
        # Pattern: /api/v1/proposals/{id}
        if "proposals" in path_parts:
            resource_type = "proposal"
            try:
                type_index = path_parts.index("proposals")
                if len(path_parts) > type_index + 1:
                    resource_id = path_parts[type_index + 1]
                else:
                    resource_id = None
            except (ValueError, IndexError):
                resource_id = None
            return resource_type, resource_id
        
        # Default for GraphQL or other endpoints
        if "graphql" in request.url.path:
            return "schema", None
        
        return None, None
    
    async def _estimate_retry_time(self, branch_name: str) -> Optional[int]:
        """Estimate when the branch might be available for writes (in seconds)"""
        try:
            branch_state = await self.lock_manager.get_branch_state(branch_name)
            
            if branch_state.current_state == BranchState.LOCKED_FOR_WRITE:
                # Look for indexing locks to estimate completion time
                for lock in branch_state.active_locks:
                    if lock.is_active and lock.expires_at:
                        from datetime import datetime, timezone
                        remaining = lock.expires_at - datetime.now(timezone.utc)
                        if remaining.total_seconds() > 0:
                            return int(remaining.total_seconds())
                
                # Default estimate for indexing operations
                return 1800  # 30 minutes
            
            return None
            
        except Exception as e:
            logger.error(f"Error estimating retry time: {e}")
            return None
    
    async def _get_detailed_lock_info(self, branch_name: str, resource_type: Optional[str]) -> Dict[str, Any]:
        """
        Get detailed information about current locks for better UX
        """
        try:
            branch_state = await self.lock_manager.get_branch_state(branch_name)
            
            # Analyze active locks
            active_locks = [lock for lock in branch_state.active_locks if lock.is_active]
            indexing_locks = [lock for lock in active_locks if lock.lock_type.value == "indexing"]
            
            # Determine lock scope
            branch_locks = [lock for lock in active_locks if lock.lock_scope.value == "branch"]
            resource_type_locks = [lock for lock in active_locks if lock.lock_scope.value == "resource_type"]
            
            lock_scope = "branch" if branch_locks else "resource_type" if resource_type_locks else "resource"
            
            # Check if other resources are available
            locked_resource_types = set()
            for lock in resource_type_locks:
                if lock.resource_type:
                    locked_resource_types.add(lock.resource_type)
            
            # Common schema resource types
            all_resource_types = {"object_type", "link_type", "action_type", "function_type"}
            available_resource_types = all_resource_types - locked_resource_types
            other_resources_available = len(available_resource_types) > 0 and lock_scope != "branch"
            
            # Estimate progress and ETA
            progress_percent = None
            eta_seconds = None
            
            if indexing_locks:
                # Simple progress estimation based on time elapsed
                latest_lock = max(indexing_locks, key=lambda l: l.created_at)
                if latest_lock.created_at and latest_lock.expires_at:
                    total_duration = (latest_lock.expires_at - latest_lock.created_at).total_seconds()
                    elapsed = (datetime.now(timezone.utc) - latest_lock.created_at).total_seconds()
                    
                    if total_duration > 0:
                        progress_percent = min(int((elapsed / total_duration) * 100), 95)  # Cap at 95%
                        eta_seconds = max(int(total_duration - elapsed), 10)  # At least 10 seconds
            
            return {
                "scope": lock_scope,
                "other_resources_available": other_resources_available,
                "available_resource_types": list(available_resource_types),
                "locked_resource_types": list(locked_resource_types),
                "progress_percent": progress_percent,
                "eta_seconds": eta_seconds,
                "indexing_locks_count": len(indexing_locks),
                "total_locks_count": len(active_locks)
            }
            
        except Exception as e:
            logger.error(f"Error getting detailed lock info: {e}")
            return {"scope": "unknown", "other_resources_available": True}
    
    def _create_user_friendly_message(self, branch_name: str, resource_type: Optional[str], lock_info: Dict[str, Any]) -> str:
        """
        Create a user-friendly message explaining the lock situation
        """
        scope = lock_info.get("scope", "unknown")
        progress = lock_info.get("progress_percent")
        eta = lock_info.get("eta_seconds")
        
        if scope == "branch":
            message = f"Branch '{branch_name}' is completely locked for indexing."
            if progress and eta:
                message += f" Progress: {progress}%, estimated completion in {eta // 60}m {eta % 60}s."
        elif scope == "resource_type" and resource_type:
            message = f"Resource type '{resource_type}' in branch '{branch_name}' is currently being indexed."
            if lock_info.get("other_resources_available"):
                available = lock_info.get("available_resource_types", [])
                if available:
                    message += f" Other resource types are available: {', '.join(available)}."
            if progress and eta:
                message += f" Indexing progress: {progress}%, ETA: {eta // 60}m {eta % 60}s."
        else:
            message = f"Resource in branch '{branch_name}' is temporarily locked for indexing."
            if eta:
                message += f" Expected completion in {eta // 60}m {eta % 60}s."
        
        return message
    
    def _suggest_alternatives(self, resource_type: Optional[str], lock_info: Dict[str, Any]) -> List[str]:
        """
        Suggest alternative actions the user can take
        """
        alternatives = []
        
        scope = lock_info.get("scope", "unknown")
        available_types = lock_info.get("available_resource_types", [])
        
        if scope == "resource_type" and available_types:
            alternatives.append(f"Work on other resource types: {', '.join(available_types)}")
        
        if scope != "branch":
            alternatives.append("Create a new branch for parallel development")
            alternatives.append("Work on non-schema changes (tests, documentation)")
        
        eta = lock_info.get("eta_seconds")
        if eta and eta < 300:  # Less than 5 minutes
            alternatives.append(f"Wait ~{eta // 60}m {eta % 60}s for indexing to complete")
        else:
            alternatives.append("Check back later or contact your team lead")
        
        alternatives.append("Use 'draft' commits if supported by your workflow")
        
        return alternatives


class SchemaFreezeError(HTTPException):
    """Custom exception for schema freeze violations"""
    
    def __init__(
        self,
        branch_name: str,
        reason: str,
        resource_type: Optional[str] = None,
        retry_after: Optional[int] = None
    ):
        detail = {
            "error": "SchemaFrozen",
            "message": f"Branch '{branch_name}' is currently locked for write operations",
            "reason": reason,
            "branch": branch_name,
            "resource_type": resource_type,
            "retry_after": retry_after
        }
        
        headers = {}
        if retry_after:
            headers["Retry-After"] = str(retry_after)
        
        super().__init__(
            status_code=status.HTTP_423_LOCKED,
            detail=detail,
            headers=headers
        )


# Utility functions for manual checks

async def check_branch_write_permission(
    branch_name: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None
) -> tuple[bool, str]:
    """
    Utility function to manually check write permission
    Can be used in service layer for additional checks
    """
    lock_manager = get_lock_manager()
    return await lock_manager.check_write_permission(
        branch_name=branch_name,
        action="write",
        resource_type=resource_type
    )


async def require_write_permission(
    branch_name: str,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None
):
    """
    Utility function that raises exception if write is not allowed
    Can be used as a decorator or called directly in services
    """
    can_write, reason = await check_branch_write_permission(
        branch_name, resource_type, resource_id
    )
    
    if not can_write:
        raise SchemaFreezeError(
            branch_name=branch_name,
            reason=reason,
            resource_type=resource_type
        )


def schema_freeze_exempt(func):
    """
    Decorator to mark functions as exempt from schema freeze checks
    Useful for administrative operations
    """
    func._schema_freeze_exempt = True
    return func