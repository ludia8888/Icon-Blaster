"""
Database Dependencies for FastAPI
Provides secure database access with user context propagation
"""
from typing import Optional
from fastapi import Depends, Request

from database.clients.unified_database_client import get_unified_database_client
from database.clients.secure_database_adapter import SecureDatabaseAdapter
from core.auth import UserContext
from middleware.auth_middleware import get_current_user
from utils.logger import get_logger

logger = get_logger(__name__)


async def get_database_client():
    """
    Get basic database client (for system operations)
    Use this only for operations that don't require user context
    """
    return await get_unified_database_client()


async def get_secure_database(
    request: Request,
    user: UserContext = Depends(get_current_user)
) -> SecureDatabaseAdapter:
    """
    Get secure database adapter with user context
    
    This ensures all database operations include proper author tracking
    from the authenticated user context.
    
    Args:
        request: FastAPI request object
        user: Authenticated user context from middleware
        
    Returns:
        SecureDatabaseAdapter with user context
    """
    # Get the base database client
    base_client = await get_unified_database_client()
    
    # Wrap with secure adapter
    secure_adapter = SecureDatabaseAdapter(base_client)
    
    # Store in request state for potential reuse within same request
    if not hasattr(request.state, "secure_db"):
        request.state.secure_db = secure_adapter
    
    logger.debug(f"Created secure database adapter for user: {user.username}")
    
    return secure_adapter


async def get_secure_database_optional(
    request: Request,
    user: Optional[UserContext] = None
) -> SecureDatabaseAdapter:
    """
    Get secure database adapter with optional user context
    
    For endpoints that may or may not have authentication.
    Falls back to system database if no user context.
    
    Args:
        request: FastAPI request object
        user: Optional user context
        
    Returns:
        SecureDatabaseAdapter or UnifiedDatabaseClient
    """
    # Try to get user from request state if not provided
    if not user:
        user = getattr(request.state, "user", None)
    
    base_client = await get_unified_database_client()
    
    if user:
        # Return secure adapter with user context
        return SecureDatabaseAdapter(base_client)
    else:
        # Return base client for system operations
        logger.warning("No user context available, using system database client")
        return base_client