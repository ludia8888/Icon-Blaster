"""
Core Authentication and Authorization Module
Provides user context and permission checking functionality
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from models.permissions import get_permission_checker as _get_permission_checker, PermissionChecker


class UserContext(BaseModel):
    """
    User context for authenticated requests
    Contains user information and roles from JWT token
    """
    user_id: str
    username: str
    email: Optional[str] = None
    roles: List[str] = []  # List of role names
    tenant_id: Optional[str] = None  # For multi-tenant support
    metadata: Dict[str, Any] = {}  # Additional user metadata
    
    @property
    def is_admin(self) -> bool:
        """Check if user has admin role"""
        return "admin" in self.roles
    
    @property
    def is_developer(self) -> bool:
        """Check if user has developer role"""
        return "developer" in self.roles
    
    @property
    def is_reviewer(self) -> bool:
        """Check if user has reviewer role"""
        return "reviewer" in self.roles
    
    @property
    def is_service_account(self) -> bool:
        """Check if user is a service account"""
        return "service_account" in self.roles
    
    def has_role(self, role: str) -> bool:
        """Check if user has specific role"""
        return role in self.roles
    
    def has_any_role(self, roles: List[str]) -> bool:
        """Check if user has any of the specified roles"""
        return any(role in self.roles for role in roles)
    
    def has_all_roles(self, roles: List[str]) -> bool:
        """Check if user has all of the specified roles"""
        return all(role in self.roles for role in roles)


def get_permission_checker() -> PermissionChecker:
    """Get the global permission checker instance"""
    return _get_permission_checker()