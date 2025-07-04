"""
⚠️ ⚠️ ⚠️ DEPRECATED MODULE - DO NOT USE ⚠️ ⚠️ ⚠️

This module is DEPRECATED and will be REMOVED in v2.0 (Target: Q1 2025)

MIGRATION REQUIRED:
==================
1. Replace imports:
   ❌ from core.auth.unified_auth import get_current_user
   ✅ from middleware.auth_middleware import get_current_user

2. Update database usage:
   ❌ db = await get_unified_database_client()
   ✅ from database.dependencies import get_secure_database
   ✅ db: SecureDatabaseAdapter = Depends(get_secure_database)

3. For GraphQL optional auth:
   ❌ from core.auth.unified_auth import get_current_user_optional
   ✅ from api.graphql.auth import get_current_user_optional

4. Update your code to use SecureDatabaseAdapter for ALL database writes
   to ensure proper audit tracking.

See /docs/AUTHENTICATION_MIGRATION.md for detailed migration guide.
"""

import warnings
from typing import Optional
from fastapi import Request, Depends
from fastapi.security import HTTPAuthorizationCredentials

from middleware.auth_middleware import get_current_user as middleware_get_current_user
from core.auth import UserContext

# Show deprecation warning on import - make it very visible
warnings.warn(
    "\n" + "="*70 + "\n" +
    "DEPRECATION WARNING: core.auth.unified_auth is DEPRECATED!\n" +
    "This module will be REMOVED in v2.0 (Q1 2025).\n" +
    "Update your imports NOW:\n" +
    "  FROM: core.auth.unified_auth\n" + 
    "  TO:   middleware.auth_middleware\n" +
    "="*70 + "\n",
    DeprecationWarning,
    stacklevel=2
)


# Backward compatibility exports
get_current_user = middleware_get_current_user


async def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = None
) -> Optional[UserContext]:
    """
    DEPRECATED: Use api.graphql.auth.get_current_user_optional instead
    """
    warnings.warn(
        "get_current_user_optional is deprecated. Use api.graphql.auth.get_current_user_optional instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    # Try to get user from request state
    user = getattr(request.state, "user", None)
    return user


# Legacy exports for backward compatibility
get_current_user_standard = middleware_get_current_user
get_current_user_async = middleware_get_current_user


def get_current_user_sync(request: Request) -> UserContext:
    """
    DEPRECATED: Synchronous version - use async version instead
    """
    warnings.warn(
        "get_current_user_sync is deprecated. Use async get_current_user instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    user = getattr(request.state, "user", None)
    if not user:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    return user