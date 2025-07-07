"""
Core Authentication/Authorization Data Models
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

class UserContext(BaseModel):
    """
    User context for authenticated requests
    Contains user information and roles from JWT token
    """
    user_id: str
    username: str
    email: Optional[str] = None
    roles: List[str] = []
    tenant_id: Optional[str] = None
    metadata: Dict[str, Any] = {}
    permissions: List[str] = [] # Scopes from IAM

    @property
    def is_admin(self) -> bool:
        """Check if user has admin role OR system_admin scope"""
        return "admin" in self.roles or "system:admin" in self.permissions
    
    @property
    def is_service_account(self) -> bool:
        """Check if user is a service account"""
        return "service_account" in self.roles

    def has_scope(self, scope: str) -> bool:
        """Check if user has a specific scope/permission."""
        # This allows for wildcard matching, e.g., "branches:*"
        for p in self.permissions:
            if p == scope:
                return True
            if p.endswith('*') and scope.startswith(p[:-1]):
                return True
        return False 