"""
FastAPI Dependencies for IAM (Identity and Access Management)
"""
from typing import List, Optional
from fastapi import Request, HTTPException, Depends, status

from ..auth_utils import UserContext
from .iam_integration import get_iam_integration, IAMScope

iam_integration = get_iam_integration()

def require_scope(required_scopes: List[IAMScope]):
    """
    Factory for creating a FastAPI dependency that checks for required scopes.
    This should be used in endpoint definitions to enforce permission checks.

    Args:
        required_scopes: A list of IAMScope enums that are required to access the endpoint.
                         The user must have AT LEAST ONE of these scopes.

    Returns:
        A FastAPI dependency function.
    """
    async def scope_checker(request: Request) -> None:
        """
        The actual dependency function that will be executed by FastAPI.
        It checks if the user context has any of the required scopes.
        """
        # User context should have been set by the AuthMiddleware
        user: Optional[UserContext] = getattr(request.state, "user", None)
        
        if not user:
            # This should technically never be reached if AuthMiddleware is active
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        
        # System Admin has universal access
        if iam_integration.check_scope(user, IAMScope.SYSTEM_ADMIN):
            return

        # Check if the user has any of the required scopes
        if not iam_integration.check_any_scope(user, required_scopes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
                headers={
                    "X-Required-Scopes": ",".join([s.value for s in required_scopes])
                },
            )

    return scope_checker