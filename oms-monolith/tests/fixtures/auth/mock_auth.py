"""
Mock Authentication for Testing
WARNING: This module should ONLY be used in test environments
"""
import os
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer

from core.auth import UserContext

# Ensure this is only imported in test environments
if os.getenv("ENV", "development") == "production":
    raise ImportError(
        "mock_auth.py cannot be imported in production environment! "
        "This module is for testing only."
    )

security = HTTPBearer(auto_error=False)


async def get_mock_user(
    token: str = Depends(security),
    mock_user_type: Optional[str] = None
) -> UserContext:
    """
    Get mock user for testing
    
    Args:
        token: Bearer token (ignored in mock)
        mock_user_type: Type of mock user to return (admin, developer, viewer, etc.)
    
    Returns:
        Mock UserContext for testing
    """
    # Different mock users for testing different scenarios
    mock_users = {
        "admin": UserContext(
            user_id="test-admin",
            username="test_admin",
            email="admin@test.example.com",
            roles=["admin"],
            metadata={"mock": True, "environment": "test"}
        ),
        "developer": UserContext(
            user_id="test-dev",
            username="test_developer",
            email="dev@test.example.com",
            roles=["developer"],
            metadata={"mock": True, "environment": "test"}
        ),
        "reviewer": UserContext(
            user_id="test-reviewer",
            username="test_reviewer",
            email="reviewer@test.example.com",
            roles=["reviewer"],
            metadata={"mock": True, "environment": "test"}
        ),
        "viewer": UserContext(
            user_id="test-viewer",
            username="test_viewer",
            email="viewer@test.example.com",
            roles=["viewer"],
            metadata={"mock": True, "environment": "test"}
        ),
        "default": UserContext(
            user_id="test-user",
            username="test",
            email="test@example.com",
            roles=["developer"],
            metadata={"mock": True, "environment": "test"}
        )
    }
    
    # Return requested mock user type or default
    return mock_users.get(mock_user_type or "default", mock_users["default"])


# Dependency overrides for testing
def get_test_user_dependency(user_type: str = "default"):
    """
    Create a dependency override for testing specific user types
    
    Usage in tests:
        app.dependency_overrides[get_current_user] = get_test_user_dependency("admin")
    """
    async def _get_test_user():
        return await get_mock_user(mock_user_type=user_type)
    return _get_test_user