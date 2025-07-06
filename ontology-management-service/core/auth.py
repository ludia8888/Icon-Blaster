"""
Core Authentication and Authorization Models
This file defines pure data models with no external dependencies within the core service.
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
    permissions: List[str] = []

    # Properties like is_admin are moved to middleware or services
    # to keep this model a pure data container.