"""
Gateway Authentication Module
Provides authentication and authorization functionality

DEPRECATED: This module contains test-only mock authentication.
Use middleware.auth_middleware.get_current_user for production.
"""
import os
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel

from utils.logger import get_logger

logger = get_logger(__name__)

security = HTTPBearer()

class UserContext(BaseModel):
    """User context for authenticated requests"""
    user_id: str
    username: str
    email: Optional[str] = None
    permissions: list[str] = []
    roles: list[str] = []  # Add roles field
    
class User(BaseModel):
    """User model"""
    id: str
    username: str
    email: Optional[str] = None
    is_active: bool = True

async def get_current_user(token: str = Depends(security)) -> UserContext:
    """
    DEPRECATED: Mock authentication for testing only.
    
    WARNING: This function returns a hardcoded test user and should NOT be used in production.
    Use middleware.auth_middleware.get_current_user instead.
    """
    # Check environment
    env = os.getenv("ENV", "development")
    if env == "production":
        logger.error("SECURITY WARNING: Mock auth function called in production!")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Mock authentication is not allowed in production"
        )
    
    # Log warning in non-production environments
    logger.warning(
        "Using mock authentication (api.gateway.auth.get_current_user). "
        "This should only be used for testing!"
    )
    
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
        permissions=["read", "write"],
        roles=["developer"]  # Added roles field
    )