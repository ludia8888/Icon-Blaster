"""Rate Limiting Middleware

Provides middleware implementations for different frameworks.
"""

import asyncio
import functools
from typing import Callable, Optional, Dict, Any, Union

from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .core import RateLimiter, RateLimitExceeded, RateLimitScope


class RateLimitMiddleware:
    """
    Generic rate limiting middleware.
    Can be adapted for different frameworks.
    """
    
    def __init__(
        self,
        rate_limiter: RateLimiter,
        limit: Optional[int] = None,
        window: Optional[int] = None,
        key_func: Optional[Callable[[Any], str]] = None,
        on_rate_limited: Optional[Callable[[RateLimitExceeded], Any]] = None
    ):
        """
        Initialize middleware.
        
        Args:
            rate_limiter: RateLimiter instance
            limit: Request limit (overrides rate_limiter default)
            window: Time window in seconds (overrides rate_limiter default)
            key_func: Function to extract rate limit key
            on_rate_limited: Callback when rate limited
        """
        self.rate_limiter = rate_limiter
        self.limit = limit
        self.window = window
        self.key_func = key_func
        self.on_rate_limited = on_rate_limited
    
    async def __call__(self, request: Any, call_next: Callable) -> Any:
        """Generic middleware implementation"""
        try:
            # Get rate limit key
            if self.key_func:
                key = self.key_func(request)
            else:
                key = self.rate_limiter.get_key(request)
            
            # Check rate limit
            result = await self.rate_limiter.check_rate_limit(
                key=key,
                limit=self.limit,
                window=self.window
            )
            
            # Add rate limit headers to response
            response = await call_next(request)
            self._add_rate_limit_headers(response, result)
            
            return response
            
        except RateLimitExceeded as e:
            if self.on_rate_limited:
                return self.on_rate_limited(e)
            else:
                return self._default_rate_limited_response(e)
    
    def _add_rate_limit_headers(self, response: Any, result: Dict[str, Any]):
        """Add rate limit headers to response"""
        if hasattr(response, "headers"):
            headers = response.headers
            if hasattr(headers, "__setitem__"):
                headers["X-RateLimit-Limit"] = str(result.get("limit", ""))
                headers["X-RateLimit-Remaining"] = str(result.get("remaining", ""))
                
                reset_time = result.get("reset_time")
                if reset_time:
                    headers["X-RateLimit-Reset"] = str(int(reset_time.timestamp()))
    
    def _default_rate_limited_response(self, exc: RateLimitExceeded) -> Any:
        """Default response when rate limited"""
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "message": str(exc),
                "retry_after": exc.retry_after
            },
            headers={
                "Retry-After": str(exc.retry_after or 60),
                "X-RateLimit-Limit": str(exc.limit or ""),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(exc.reset_time.timestamp())) if exc.reset_time else ""
            }
        )


class FastAPIRateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI/Starlette specific rate limiting middleware.
    Drop-in replacement for user-service RateLimitMiddleware.
    """
    
    def __init__(
        self,
        app,
        rate_limiter: Optional[RateLimiter] = None,
        limit: int = 100,
        window: int = 60,
        scope: Union[str, RateLimitScope] = RateLimitScope.IP,
        key_func: Optional[Callable[[Request], str]] = None,
        exclude_paths: Optional[list] = None
    ):
        """
        Initialize FastAPI middleware.
        
        Args:
            app: FastAPI/Starlette app
            rate_limiter: RateLimiter instance (creates default if None)
            limit: Request limit
            window: Time window in seconds
            scope: Rate limiting scope
            key_func: Function to extract rate limit key
            exclude_paths: Paths to exclude from rate limiting
        """
        super().__init__(app)
        
        # Convert string scope to enum
        if isinstance(scope, str):
            scope = RateLimitScope(scope)
        
        # Create rate limiter if not provided
        if rate_limiter is None:
            rate_limiter = RateLimiter(
                default_limit=limit,
                default_window=window,
                scope=scope,
                key_func=key_func
            )
        
        self.rate_limiter = rate_limiter
        self.limit = limit
        self.window = window
        self.exclude_paths = exclude_paths or []
        
        # Initialize rate limiter on startup
        asyncio.create_task(self.rate_limiter.initialize())
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """Process request through rate limiter"""
        # Check if path is excluded
        if request.url.path in self.exclude_paths:
            return await call_next(request)
        
        try:
            # Get rate limit key
            key = self.rate_limiter.get_key(request)
            
            # Check rate limit
            result = await self.rate_limiter.check_rate_limit(
                key=key,
                limit=self.limit,
                window=self.window
            )
            
            # Process request
            response = await call_next(request)
            
            # Add rate limit headers
            response.headers["X-RateLimit-Limit"] = str(result.get("limit", self.limit))
            response.headers["X-RateLimit-Remaining"] = str(result.get("remaining", 0))
            
            reset_time = result.get("reset_time")
            if reset_time:
                response.headers["X-RateLimit-Reset"] = str(int(reset_time.timestamp()))
            
            return response
            
        except RateLimitExceeded as e:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after": e.retry_after
                },
                headers={
                    "Retry-After": str(e.retry_after or 60),
                    "X-RateLimit-Limit": str(e.limit or self.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(e.reset_time.timestamp())) if e.reset_time else ""
                }
            )
        except Exception:
            # If rate limiting fails, allow request
            # This prevents rate limiter issues from breaking the service
            return await call_next(request)


def rate_limit_decorator(
    limit: Optional[int] = None,
    window: Optional[int] = None,
    key_func: Optional[Callable] = None,
    rate_limiter: Optional[RateLimiter] = None,
    scope: Union[str, RateLimitScope] = RateLimitScope.ENDPOINT
):
    """
    Decorator for rate limiting individual endpoints.
    Compatible with FastAPI and other async frameworks.
    """
    def decorator(func: Callable) -> Callable:
        # Create rate limiter if not provided
        nonlocal rate_limiter
        if rate_limiter is None:
            if isinstance(scope, str):
                scope_enum = RateLimitScope(scope)
            else:
                scope_enum = scope
                
            rate_limiter = RateLimiter(
                default_limit=limit or 100,
                default_window=window or 60,
                scope=scope_enum,
                key_func=key_func
            )
        
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Try to find request object
            request = None
            for arg in args:
                if hasattr(arg, "url") or hasattr(arg, "path"):
                    request = arg
                    break
            
            if not request and "request" in kwargs:
                request = kwargs["request"]
            
            if request:
                # Get rate limit key
                if key_func:
                    key = key_func(request)
                else:
                    key = rate_limiter.get_key(request)
                
                # Check rate limit
                try:
                    result = await rate_limiter.check_rate_limit(
                        key=key,
                        limit=limit,
                        window=window
                    )
                    
                    # Call function
                    response = await func(*args, **kwargs)
                    
                    # Add headers if response object
                    if hasattr(response, "headers"):
                        response.headers["X-RateLimit-Limit"] = str(result.get("limit", ""))
                        response.headers["X-RateLimit-Remaining"] = str(result.get("remaining", ""))
                        
                        reset_time = result.get("reset_time")
                        if reset_time:
                            response.headers["X-RateLimit-Reset"] = str(int(reset_time.timestamp()))
                    
                    return response
                    
                except RateLimitExceeded as e:
                    raise HTTPException(
                        status_code=429,
                        detail="Rate limit exceeded",
                        headers={
                            "Retry-After": str(e.retry_after or 60),
                            "X-RateLimit-Limit": str(e.limit or ""),
                            "X-RateLimit-Remaining": "0",
                            "X-RateLimit-Reset": str(int(e.reset_time.timestamp())) if e.reset_time else ""
                        }
                    )
            
            # No request found, just call function
            return await func(*args, **kwargs)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For sync functions, we need to run in event loop
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(async_wrapper(*args, **kwargs))
        
        # Return appropriate wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# Convenience functions for specific scopes
def rate_limit_ip(limit: int, window: int = 60, **kwargs):
    """Rate limit by IP address"""
    return rate_limit_decorator(
        limit=limit,
        window=window,
        scope=RateLimitScope.IP,
        **kwargs
    )


def rate_limit_user(limit: int, window: int = 60, **kwargs):
    """Rate limit by user"""
    return rate_limit_decorator(
        limit=limit,
        window=window,
        scope=RateLimitScope.USER,
        **kwargs
    )


def rate_limit_endpoint(limit: int, window: int = 60, **kwargs):
    """Rate limit by endpoint"""
    return rate_limit_decorator(
        limit=limit,
        window=window,
        scope=RateLimitScope.ENDPOINT,
        **kwargs
    )