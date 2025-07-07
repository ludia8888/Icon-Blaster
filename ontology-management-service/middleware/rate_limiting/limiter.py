"""
Main rate limiter implementation
"""
from typing import Dict, Optional, Any
import logging
from functools import wraps
import asyncio

from .models import RateLimitConfig, RateLimitResult, RateLimitScope, RateLimitKey
from .strategies.base import RateLimitStrategy

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Main rate limiter class that applies rate limiting
    """
    
    def __init__(self):
        self.logger = logger
    
    def limit(
        self,
        requests: int = 100,
        window: int = 60,
        scope: RateLimitScope = RateLimitScope.USER,
        key_func: Optional[callable] = None
    ):
        """
        Decorator for rate limiting functions/methods
        
        Args:
            requests: Number of requests allowed per window
            window: Time window in seconds
            scope: Rate limit scope
            key_func: Function to extract rate limit key from arguments
        """
        config = RateLimitConfig(
            requests_per_window=requests,
            window_seconds=window,
            scope=scope
        )
        
        def decorator(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                # Extract rate limit key
                if key_func:
                    identifier = key_func(*args, **kwargs)
                else:
                    identifier = self._default_key_func(scope, *args, **kwargs)
                
                key = RateLimitKey(scope, identifier)
                
                # Check rate limit
                from .coordinator import RateLimitCoordinator
                coordinator = RateLimitCoordinator(config)
                result = await coordinator._check_standard(key, config)
                
                if not result.allowed:
                    raise RateLimitExceeded(result)
                
                # Execute function
                return await func(*args, **kwargs)
            
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                # For sync functions, we need to run in event loop
                loop = asyncio.get_event_loop()
                
                # Extract rate limit key
                if key_func:
                    identifier = key_func(*args, **kwargs)
                else:
                    identifier = self._default_key_func(scope, *args, **kwargs)
                
                key = RateLimitKey(scope, identifier)
                
                # Check rate limit
                from .coordinator import RateLimitCoordinator
                coordinator = RateLimitCoordinator(config)
                result = loop.run_until_complete(
                    coordinator._check_standard(key, config)
                )
                
                if not result.allowed:
                    raise RateLimitExceeded(result)
                
                # Execute function
                return func(*args, **kwargs)
            
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper
        
        return decorator
    
    def _default_key_func(
        self, 
        scope: RateLimitScope, 
        *args, 
        **kwargs
    ) -> str:
        """Default function to extract rate limit key"""
        # Try to extract from common patterns
        
        # Check for request object (web frameworks)
        for arg in args:
            if hasattr(arg, 'user') and scope == RateLimitScope.USER:
                user = getattr(arg, 'user')
                if hasattr(user, 'id'):
                    return str(user.id)
                elif hasattr(user, 'username'):
                    return user.username
            
            if hasattr(arg, 'META') and scope == RateLimitScope.IP:
                # Django-style request
                return arg.META.get('REMOTE_ADDR', 'unknown')
            
            if hasattr(arg, 'remote_addr') and scope == RateLimitScope.IP:
                # Flask-style request
                return arg.remote_addr
            
            if hasattr(arg, 'path') and scope == RateLimitScope.ENDPOINT:
                return arg.path
        
        # Check kwargs
        if scope == RateLimitScope.USER:
            return kwargs.get('user_id', 'anonymous')
        elif scope == RateLimitScope.IP:
            return kwargs.get('ip_address', 'unknown')
        elif scope == RateLimitScope.ENDPOINT:
            return kwargs.get('endpoint', 'unknown')
        
        return 'default'


class RateLimitExceeded(Exception):
    """Exception raised when rate limit is exceeded"""
    
    def __init__(self, result: RateLimitResult):
        self.result = result
        super().__init__(
            f"Rate limit exceeded. Retry after {result.retry_after} seconds"
        )