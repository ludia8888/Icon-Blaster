"""Core Rate Limiter Implementation

Provides a unified rate limiter that can work with different backends and algorithms.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, Union, Callable, Any, Dict
from enum import Enum

from .backends import Backend, RedisBackend, InMemoryBackend
from .algorithms import RateLimitAlgorithm, SlidingWindowAlgorithm


class RateLimitScope(Enum):
    """Scope for rate limiting"""
    USER = "user"
    IP = "ip"
    ENDPOINT = "endpoint"
    GLOBAL = "global"
    CUSTOM = "custom"


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded"""
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        limit: Optional[int] = None,
        remaining: int = 0,
        reset_time: Optional[datetime] = None
    ):
        super().__init__(message)
        self.retry_after = retry_after
        self.limit = limit
        self.remaining = remaining
        self.reset_time = reset_time


class RateLimiter:
    """
    Unified rate limiter supporting multiple backends and algorithms.
    
    This replaces:
    - OMS gateway/rate_limiter.py
    - OMS graphql/middleware/security.py 
    - OMS middleware/rate_limiting/limiter.py
    - user-service/src/core/rate_limit.py
    """
    
    def __init__(
        self,
        backend: Optional[Backend] = None,
        algorithm: Optional[RateLimitAlgorithm] = None,
        default_limit: int = 100,
        default_window: int = 60,
        burst_size: Optional[int] = None,
        scope: RateLimitScope = RateLimitScope.USER,
        key_func: Optional[Callable[[Any], str]] = None,
        error_handler: Optional[Callable[[Exception], None]] = None
    ):
        """
        Initialize rate limiter.
        
        Args:
            backend: Storage backend (defaults to InMemoryBackend)
            algorithm: Rate limiting algorithm (defaults to SlidingWindowAlgorithm)
            default_limit: Default request limit
            default_window: Default time window in seconds
            burst_size: Optional burst size for token bucket algorithm
            scope: Rate limiting scope
            key_func: Function to extract rate limit key
            error_handler: Optional error handler for backend failures
        """
        self.backend = backend or InMemoryBackend()
        self.algorithm = algorithm or SlidingWindowAlgorithm()
        self.default_limit = default_limit
        self.default_window = default_window
        self.burst_size = burst_size or default_limit
        self.scope = scope
        self.key_func = key_func
        self.error_handler = error_handler
        self._initialized = False
    
    async def initialize(self):
        """Initialize the rate limiter (connect to backend, etc.)"""
        if not self._initialized:
            await self.backend.initialize()
            self._initialized = True
    
    async def check_rate_limit(
        self,
        key: str,
        limit: Optional[int] = None,
        window: Optional[int] = None,
        cost: int = 1
    ) -> Dict[str, Any]:
        """
        Check if request is within rate limit.
        
        Args:
            key: Rate limit key (e.g., user ID, IP address)
            limit: Request limit (uses default if not specified)
            window: Time window in seconds (uses default if not specified)
            cost: Cost of this request (default 1)
            
        Returns:
            Dict with rate limit info (allowed, remaining, reset_time, etc.)
            
        Raises:
            RateLimitExceeded: If rate limit is exceeded
        """
        if not self._initialized:
            await self.initialize()
        
        limit = limit or self.default_limit
        window = window or self.default_window
        
        try:
            # Get current state from backend
            state = await self.backend.get_state(key)
            
            # Apply rate limiting algorithm
            result = await self.algorithm.is_allowed(
                state=state,
                limit=limit,
                window=window,
                cost=cost,
                burst_size=self.burst_size
            )
            
            # Update state in backend
            if result["allowed"]:
                await self.backend.update_state(key, result["new_state"], window)
            
            # Raise exception if not allowed
            if not result["allowed"]:
                raise RateLimitExceeded(
                    message=f"Rate limit exceeded for key: {key}",
                    retry_after=result.get("retry_after"),
                    limit=limit,
                    remaining=result.get("remaining", 0),
                    reset_time=result.get("reset_time")
                )
            
            return result
            
        except Exception as e:
            if self.error_handler:
                self.error_handler(e)
            # In case of backend errors, we can choose to allow or deny
            # For now, we'll allow to avoid breaking the service
            return {
                "allowed": True,
                "remaining": limit - cost,
                "limit": limit,
                "reset_time": datetime.utcnow() + timedelta(seconds=window)
            }
    
    def get_key(self, request: Any, custom_key: Optional[str] = None) -> str:
        """
        Get rate limit key based on scope and request.
        
        Args:
            request: Request object (framework-specific)
            custom_key: Optional custom key
            
        Returns:
            Rate limit key string
        """
        if custom_key:
            return custom_key
        
        if self.key_func:
            return self.key_func(request)
        
        # Default key extraction based on scope
        if self.scope == RateLimitScope.GLOBAL:
            return "global"
        elif self.scope == RateLimitScope.ENDPOINT:
            # Extract endpoint from request (framework-specific)
            endpoint = getattr(request, "path", getattr(request, "url", {}).get("path", "unknown"))
            return f"endpoint:{endpoint}"
        elif self.scope == RateLimitScope.IP:
            # Extract IP from request
            ip = self._extract_ip(request)
            return f"ip:{ip}"
        elif self.scope == RateLimitScope.USER:
            # Extract user ID from request
            user_id = self._extract_user_id(request)
            return f"user:{user_id}"
        else:
            return "unknown"
    
    def _extract_ip(self, request: Any) -> str:
        """Extract IP address from request (framework-specific)"""
        # Try common patterns
        if hasattr(request, "client"):
            # FastAPI/Starlette
            if request.client:
                return request.client.host
        elif hasattr(request, "remote_addr"):
            # Flask
            return request.remote_addr
        elif hasattr(request, "META"):
            # Django
            return request.META.get("REMOTE_ADDR", "unknown")
        
        # Check headers for forwarded IPs
        headers = getattr(request, "headers", {})
        for header in ["x-forwarded-for", "x-real-ip"]:
            if header in headers:
                return headers[header].split(",")[0].strip()
        
        return "unknown"
    
    def _extract_user_id(self, request: Any) -> str:
        """Extract user ID from request (framework-specific)"""
        # Try to get user from request
        user = getattr(request, "user", None)
        if user:
            # Try common user ID attributes
            for attr in ["id", "user_id", "username", "email"]:
                user_id = getattr(user, attr, None)
                if user_id:
                    return str(user_id)
        
        # Try to get from request state (FastAPI)
        if hasattr(request, "state"):
            user = getattr(request.state, "user", None)
            if user:
                return str(user.get("user_id", user.get("id", "anonymous")))
        
        return "anonymous"
    
    async def reset(self, key: str):
        """Reset rate limit for a specific key"""
        await self.backend.reset(key)
    
    async def close(self):
        """Close connections and cleanup"""
        if self._initialized:
            await self.backend.close()
            self._initialized = False


class DistributedRateLimiter(RateLimiter):
    """
    Distributed rate limiter with Redis backend.
    Provides compatibility with OMS gateway rate limiter.
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        **kwargs
    ):
        """Initialize distributed rate limiter with Redis backend"""
        backend = RedisBackend(redis_url=redis_url)
        super().__init__(backend=backend, **kwargs)
    
    async def check_multiple_windows(
        self,
        key: str,
        limits: Dict[int, int],
        cost: int = 1
    ) -> Dict[str, Any]:
        """
        Check rate limits for multiple time windows.
        
        Args:
            key: Rate limit key
            limits: Dict mapping window (seconds) to limit
            cost: Cost of request
            
        Returns:
            Combined rate limit result
        """
        results = []
        
        for window, limit in limits.items():
            try:
                result = await self.check_rate_limit(key, limit, window, cost)
                results.append(result)
            except RateLimitExceeded as e:
                # If any window is exceeded, raise with that info
                raise e
        
        # Return the most restrictive result
        return min(results, key=lambda r: r.get("remaining", float("inf")))