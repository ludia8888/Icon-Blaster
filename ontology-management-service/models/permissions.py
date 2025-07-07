"""
Permission Matrix and Role Definitions for OMS
Implements fine-grained RBAC for all resources
"""
from enum import Enum
from typing import Dict, List, Set, Optional, Any
from pydantic import BaseModel


class ResourceType(str, Enum):
    """OMS Resource Types"""
    SCHEMA = "schema"
    OBJECT_TYPE = "object_type"
    LINK_TYPE = "link_type"
    ACTION_TYPE = "action_type"
    FUNCTION_TYPE = "function_type"
    BRANCH = "branch"
    PROPOSAL = "proposal"
    AUDIT = "audit"
    WEBHOOK = "webhook"


class Action(str, Enum):
    """Available Actions on Resources"""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    APPROVE = "approve"
    REJECT = "reject"
    MERGE = "merge"
    REVERT = "revert"
    EXECUTE = "execute"


class Role(str, Enum):
    """System Roles"""
    ADMIN = "admin"
    DEVELOPER = "developer"
    REVIEWER = "reviewer"
    VIEWER = "viewer"
    SERVICE_ACCOUNT = "service_account"


class Permission(BaseModel):
    """Permission Definition"""
    resource_type: ResourceType
    actions: List[Action]
    resource_ids: Optional[List[str]] = None  # None means all resources
    conditions: Optional[Dict[str, Any]] = None  # Additional conditions


# Role-Based Permission Matrix
PERMISSION_MATRIX: Dict[Role, List[Permission]] = {
    Role.ADMIN: [
        # Admin has restricted access following least privilege principle
        # Cannot delete critical resources or modify audit logs
        Permission(resource_type=ResourceType.SCHEMA, actions=[Action.CREATE, Action.READ, Action.UPDATE]),
        Permission(resource_type=ResourceType.OBJECT_TYPE, actions=[Action.CREATE, Action.READ, Action.UPDATE]),
        Permission(resource_type=ResourceType.LINK_TYPE, actions=[Action.CREATE, Action.READ, Action.UPDATE]),
        Permission(resource_type=ResourceType.ACTION_TYPE, actions=[Action.CREATE, Action.READ, Action.UPDATE]),
        Permission(resource_type=ResourceType.FUNCTION_TYPE, actions=[Action.CREATE, Action.READ, Action.UPDATE]),
        Permission(resource_type=ResourceType.BRANCH, actions=[Action.CREATE, Action.READ, Action.UPDATE, Action.MERGE]),
        Permission(resource_type=ResourceType.PROPOSAL, actions=[Action.CREATE, Action.READ, Action.UPDATE, Action.APPROVE, Action.REJECT]),
        Permission(resource_type=ResourceType.AUDIT, actions=[Action.READ]),  # Read-only audit logs
        Permission(resource_type=ResourceType.WEBHOOK, actions=[Action.CREATE, Action.READ, Action.UPDATE, Action.EXECUTE]),
    ],
    
    Role.DEVELOPER: [
        # Developers can read all, create/update most, but not delete critical resources
        Permission(resource_type=ResourceType.SCHEMA, actions=[Action.READ]),
        Permission(resource_type=ResourceType.OBJECT_TYPE, actions=[Action.CREATE, Action.READ, Action.UPDATE]),
        Permission(resource_type=ResourceType.LINK_TYPE, actions=[Action.CREATE, Action.READ, Action.UPDATE]),
        Permission(resource_type=ResourceType.ACTION_TYPE, actions=[Action.CREATE, Action.READ, Action.UPDATE]),
        Permission(resource_type=ResourceType.FUNCTION_TYPE, actions=[Action.CREATE, Action.READ, Action.UPDATE]),
        Permission(resource_type=ResourceType.BRANCH, actions=[Action.CREATE, Action.READ, Action.UPDATE, Action.DELETE]),
        Permission(resource_type=ResourceType.PROPOSAL, actions=[Action.CREATE, Action.READ, Action.UPDATE]),
        Permission(resource_type=ResourceType.AUDIT, actions=[Action.READ]),
        Permission(resource_type=ResourceType.WEBHOOK, actions=[Action.READ, Action.EXECUTE]),
    ],
    
    Role.REVIEWER: [
        # Reviewers can read everything and approve/reject proposals
        Permission(resource_type=ResourceType.SCHEMA, actions=[Action.READ]),
        Permission(resource_type=ResourceType.OBJECT_TYPE, actions=[Action.READ]),
        Permission(resource_type=ResourceType.LINK_TYPE, actions=[Action.READ]),
        Permission(resource_type=ResourceType.ACTION_TYPE, actions=[Action.READ]),
        Permission(resource_type=ResourceType.FUNCTION_TYPE, actions=[Action.READ]),
        Permission(resource_type=ResourceType.BRANCH, actions=[Action.READ]),
        Permission(resource_type=ResourceType.PROPOSAL, actions=[Action.READ, Action.APPROVE, Action.REJECT]),
        Permission(resource_type=ResourceType.AUDIT, actions=[Action.READ]),
        Permission(resource_type=ResourceType.WEBHOOK, actions=[Action.READ]),
    ],
    
    Role.VIEWER: [
        # Viewers have read-only access
        Permission(resource_type=ResourceType.SCHEMA, actions=[Action.READ]),
        Permission(resource_type=ResourceType.OBJECT_TYPE, actions=[Action.READ]),
        Permission(resource_type=ResourceType.LINK_TYPE, actions=[Action.READ]),
        Permission(resource_type=ResourceType.ACTION_TYPE, actions=[Action.READ]),
        Permission(resource_type=ResourceType.FUNCTION_TYPE, actions=[Action.READ]),
        Permission(resource_type=ResourceType.BRANCH, actions=[Action.READ]),
        Permission(resource_type=ResourceType.PROPOSAL, actions=[Action.READ]),
        Permission(resource_type=ResourceType.AUDIT, actions=[Action.READ]),
    ],
    
    Role.SERVICE_ACCOUNT: [
        # Service accounts have specific permissions for system integration
        Permission(resource_type=ResourceType.SCHEMA, actions=[Action.READ]),
        Permission(resource_type=ResourceType.OBJECT_TYPE, actions=[Action.READ]),
        Permission(resource_type=ResourceType.LINK_TYPE, actions=[Action.READ]),
        Permission(resource_type=ResourceType.ACTION_TYPE, actions=[Action.READ]),
        Permission(resource_type=ResourceType.FUNCTION_TYPE, actions=[Action.READ]),
        Permission(resource_type=ResourceType.WEBHOOK, actions=[Action.READ, Action.EXECUTE]),
        Permission(resource_type=ResourceType.AUDIT, actions=[Action.CREATE, Action.READ]),
    ],
}


class PermissionChecker:
    """Permission checking utility"""
    
    def __init__(self):
        self.permission_matrix = PERMISSION_MATRIX
        # Cache for faster lookups
        self._permission_cache: Dict[str, Set[str]] = {}
        self._build_cache()
    
    def _build_cache(self):
        """Build permission cache for faster lookups"""
        for role, permissions in self.permission_matrix.items():
            role_key = role.value
            self._permission_cache[role_key] = set()
            
            for permission in permissions:
                for action in permission.actions:
                    cache_key = f"{permission.resource_type.value}:{action.value}"
                    self._permission_cache[role_key].add(cache_key)
    
    def check_permission(
        self,
        user_roles: List[str],
        resource_type: str,
        action: str,
        resource_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Check if user has permission to perform action on resource
        
        Args:
            user_roles: List of user's roles
            resource_type: Type of resource
            action: Action to perform
            resource_id: Specific resource ID (optional)
            context: Additional context for condition checking
            
        Returns:
            bool: True if user has permission, False otherwise
        """
        # Convert to enums for validation
        try:
            resource_enum = ResourceType(resource_type)
            action_enum = Action(action)
        except ValueError:
            # Invalid resource type or action
            return False
        
        # Check each role
        for role_str in user_roles:
            try:
                role = Role(role_str)
            except ValueError:
                # Skip invalid roles
                continue
            
            # Quick cache check
            cache_key = f"{resource_type}:{action}"
            if cache_key in self._permission_cache.get(role_str, set()):
                # Found permission in cache, now check detailed conditions
                permissions = self.permission_matrix.get(role, [])
                
                for permission in permissions:
                    if (permission.resource_type == resource_enum and 
                        action_enum in permission.actions):
                        
                        # Check resource ID restrictions if any
                        if permission.resource_ids and resource_id:
                            if resource_id not in permission.resource_ids:
                                continue
                        
                        # Check additional conditions if any
                        if permission.conditions and context:
                            if not self._check_conditions(permission.conditions, context):
                                continue
                        
                        return True
        
        return False
    
    def _check_conditions(self, conditions: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Check if conditions are met"""
        for key, expected_value in conditions.items():
            if key not in context:
                return False
            
            if isinstance(expected_value, list):
                if context[key] not in expected_value:
                    return False
            else:
                if context[key] != expected_value:
                    return False
        
        return True
    
    def get_user_permissions(self, user_roles: List[str]) -> List[Permission]:
        """Get all permissions for user's roles"""
        all_permissions = []
        
        for role_str in user_roles:
            try:
                role = Role(role_str)
                all_permissions.extend(self.permission_matrix.get(role, []))
            except ValueError:
                # Skip invalid roles
                continue
        
        return all_permissions
    
    def can_approve_proposal(self, user_roles: List[str]) -> bool:
        """Check if user can approve proposals"""
        return self.check_permission(user_roles, ResourceType.PROPOSAL.value, Action.APPROVE.value)
    
    def can_create_branch(self, user_roles: List[str]) -> bool:
        """Check if user can create branches"""
        return self.check_permission(user_roles, ResourceType.BRANCH.value, Action.CREATE.value)
    
    def can_modify_schema(self, user_roles: List[str], resource_type: str) -> bool:
        """Check if user can modify schema resources"""
        return self.check_permission(user_roles, resource_type, Action.UPDATE.value)


# Global permission checker instance
_permission_checker = PermissionChecker()


def get_permission_checker() -> PermissionChecker:
    """Get global permission checker instance"""
    return _permission_checker