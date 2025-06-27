"""
RBAC Test Routes
Example endpoints demonstrating role-based access control
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer

from core.auth import UserContext
from middleware.auth_middleware import get_current_user
from core.integrations.user_service_client import create_mock_jwt

router = APIRouter(prefix="/api/v1/rbac-test", tags=["RBAC Test"])
security = HTTPBearer()


@router.get("/generate-tokens")
async def generate_test_tokens():
    """
    Generate test JWT tokens for different roles
    Public endpoint for testing purposes
    """
    tokens = {
        "admin": create_mock_jwt(
            user_id="admin-001",
            username="admin_user",
            roles=["admin"]
        ),
        "developer": create_mock_jwt(
            user_id="dev-001",
            username="dev_user",
            roles=["developer"]
        ),
        "reviewer": create_mock_jwt(
            user_id="rev-001",
            username="reviewer_user",
            roles=["reviewer"]
        ),
        "viewer": create_mock_jwt(
            user_id="view-001",
            username="viewer_user",
            roles=["viewer"]
        ),
        "multi_role": create_mock_jwt(
            user_id="multi-001",
            username="multi_user",
            roles=["developer", "reviewer"]
        )
    }
    
    return {
        "tokens": tokens,
        "usage": "Use these tokens in Authorization header as 'Bearer <token>'",
        "note": "These are test tokens for development only"
    }


@router.get("/me")
async def get_current_user_info(user: UserContext = Depends(get_current_user)):
    """
    Get current user information
    Requires authentication
    """
    return {
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email,
        "roles": user.roles,
        "tenant_id": user.tenant_id,
        "is_admin": user.is_admin,
        "is_developer": user.is_developer,
        "is_reviewer": user.is_reviewer
    }


@router.get("/admin-only")
async def admin_only_endpoint(user: UserContext = Depends(get_current_user)):
    """
    Admin-only endpoint
    This will be blocked by RBAC middleware for non-admin users
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint requires admin role"
        )
    
    return {
        "message": "Welcome admin!",
        "user": user.username,
        "secret_data": "Only admins can see this"
    }


@router.get("/developer-action")
async def developer_action(user: UserContext = Depends(get_current_user)):
    """
    Developer action endpoint
    Developers and admins can access this
    """
    if not (user.is_developer or user.is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint requires developer or admin role"
        )
    
    return {
        "message": "Developer action executed",
        "user": user.username,
        "can_create_schemas": True
    }


@router.get("/reviewer-action")
async def reviewer_action(user: UserContext = Depends(get_current_user)):
    """
    Reviewer action endpoint
    Reviewers and admins can access this
    """
    if not (user.is_reviewer or user.is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint requires reviewer or admin role"
        )
    
    return {
        "message": "Reviewer action executed",
        "user": user.username,
        "can_approve_proposals": True
    }


@router.get("/public-read")
async def public_read_endpoint(user: UserContext = Depends(get_current_user)):
    """
    Public read endpoint
    All authenticated users can access this
    """
    return {
        "message": "This is public data",
        "user": user.username,
        "roles": user.roles,
        "data": ["item1", "item2", "item3"]
    }


@router.post("/test-permission-check")
async def test_permission_check(
    resource_type: str,
    action: str,
    user: UserContext = Depends(get_current_user)
):
    """
    Test specific permission check
    Useful for debugging RBAC rules
    """
    from models.permissions import get_permission_checker
    
    checker = get_permission_checker()
    has_permission = checker.check_permission(
        user_roles=user.roles,
        resource_type=resource_type,
        action=action
    )
    
    return {
        "user": user.username,
        "roles": user.roles,
        "resource_type": resource_type,
        "action": action,
        "has_permission": has_permission,
        "all_permissions": [
            {
                "resource_type": perm.resource_type.value,
                "actions": [a.value for a in perm.actions]
            }
            for perm in checker.get_user_permissions(user.roles)
        ]
    }


# Add router to main app in main.py:
# app.include_router(rbac_test_routes.router)