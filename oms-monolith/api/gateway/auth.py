"""
Gateway Authentication Module
Provides authentication and authorization functionality
"""

from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel

security = HTTPBearer()

class UserContext(BaseModel):
    """User context for authenticated requests"""
    user_id: str
    username: str
    email: Optional[str] = None
    permissions: list[str] = []
    
class User(BaseModel):
    """User model"""
    id: str
    username: str
    email: Optional[str] = None
    is_active: bool = True

async def get_current_user(token: str = Depends(security)) -> UserContext:
    """Get current authenticated user"""
    # For now, return a mock user for testing
    # TODO: Implement actual JWT token validation
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Mock user for testing
    return UserContext(
        user_id="test-user",
        username="test",
        email="test@example.com",
        permissions=["read", "write"]
    )