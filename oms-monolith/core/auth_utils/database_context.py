"""
Database Context Management
Provides thread-local storage for user context in database operations

This module bridges the gap between request-scoped user context
and database operations that may happen in background tasks or services.
"""
import contextvars
from typing import Optional, TypeVar, Callable, Any
from functools import wraps
from starlette.middleware.base import BaseHTTPMiddleware

from core.auth_utils import UserContext
from database.clients.secure_database_adapter import SecureDatabaseAdapter
from database.clients.unified_database_client import UnifiedDatabaseClient, get_unified_database_client
from utils.logger import get_logger

logger = get_logger(__name__)

# Context variable to store current user across async boundaries
_current_user_context: contextvars.ContextVar[Optional[UserContext]] = contextvars.ContextVar(
    'current_user_context',
    default=None
)

# Context variable for database client
_current_db_context: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar(
    'current_db_context', 
    default=None
)


def set_current_user_context(user: UserContext) -> None:
    """Set the current user context for database operations"""
    _current_user_context.set(user)
    logger.debug(f"Set database user context: {user.username}")


def get_current_user_context() -> Optional[UserContext]:
    """Get the current user context for database operations"""
    return _current_user_context.get()


def clear_current_user_context() -> None:
    """Clear the current user context"""
    _current_user_context.set(None)


async def get_contextual_database() -> Any:
    """
    Get database client based on current context
    
    Returns:
        SecureDatabaseAdapter if user context exists
        UnifiedDatabaseClient for system operations
    """
    # Check if we already have a database in context
    cached_db = _current_db_context.get()
    if cached_db:
        return cached_db
    
    # Get base client
    base_client = await get_unified_database_client()
    
    # Check for user context
    user_context = get_current_user_context()
    
    if user_context:
        # Create secure adapter with user context
        db_client = SecureDatabaseAdapter(base_client)
        logger.debug(f"Created secure database for user: {user_context.username}")
    else:
        # Use base client for system operations
        db_client = base_client
        logger.debug("Using system database client (no user context)")
    
    # Cache in context
    _current_db_context.set(db_client)
    
    return db_client


def with_user_context(user: UserContext):
    """
    Decorator to set user context for database operations
    
    Usage:
        @with_user_context(user)
        async def my_service_method():
            db = await get_contextual_database()
            # db will be SecureDatabaseAdapter with user context
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Save previous context
            previous_user = get_current_user_context()
            previous_db = _current_db_context.get()
            
            try:
                # Set new context
                set_current_user_context(user)
                _current_db_context.set(None)  # Clear DB cache
                
                # Execute function
                return await func(*args, **kwargs)
            finally:
                # Restore previous context
                _current_user_context.set(previous_user)
                _current_db_context.set(previous_db)
        
        return wrapper
    return decorator


def with_system_context(func: Callable) -> Callable:
    """
    Decorator to explicitly use system context (no user)
    
    Usage:
        @with_system_context
        async def system_task():
            db = await get_contextual_database()
            # db will be UnifiedDatabaseClient
    """
    @wraps(func)
    async def wrapper(*args, **kwargs):
        # Save previous context
        previous_user = get_current_user_context()
        previous_db = _current_db_context.get()
        
        try:
            # Clear user context
            clear_current_user_context()
            _current_db_context.set(None)
            
            # Execute function
            return await func(*args, **kwargs)
        finally:
            # Restore previous context
            _current_user_context.set(previous_user)
            _current_db_context.set(previous_db)
    
    return wrapper


class DatabaseContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware to propagate user context to database operations
    
    This ensures that any database operation within a request
    automatically includes the authenticated user context.
    
    Must be added AFTER AuthMiddleware in the middleware stack.
    """
    
    async def dispatch(self, request, call_next):
        """
        Process request and set database context
        
        Args:
            request: FastAPI/Starlette Request object
            call_next: Next middleware/handler in chain
        """
        # Extract user from request.state (set by AuthMiddleware)
        user = getattr(request.state, "user", None)
        
        if user:
            # Set user context for this request
            set_current_user_context(user)
            logger.debug(f"DatabaseContextMiddleware: Set context for user {user.username}")
            
            try:
                response = await call_next(request)
                return response
            finally:
                # Clear context after request
                clear_current_user_context()
                _current_db_context.set(None)
                logger.debug("DatabaseContextMiddleware: Cleared context")
        else:
            # No user context - proceed without setting
            logger.debug("DatabaseContextMiddleware: No user context found")
            return await call_next(request)