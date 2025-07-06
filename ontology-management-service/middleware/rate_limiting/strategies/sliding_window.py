"""
Sliding window rate limiting strategy
"""
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from .base import RateLimitStrategy
from ..models import (
    RateLimitConfig, RateLimitResult, RateLimitState, RateLimitKey
)


class SlidingWindowStrategy(RateLimitStrategy):
    """
    Sliding window rate limiting using counters.
    More accurate than fixed window but uses more memory.
    """
    
    def __init__(self, config: RateLimitConfig):
        super().__init__(config)
        # Store request timestamps for sliding window
        self._request_history: Dict[str, List[datetime]] = {}
    
    async def check_limit(
        self,
        key: RateLimitKey,
        state: Optional[RateLimitState] = None
    ) -> tuple[RateLimitResult, RateLimitState]:
        """Check if request is within rate limit"""
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=self.config.window_seconds)
        
        # Get request history
        key_str = key.to_string()
        history = self._request_history.get(key_str, [])
        
        # Remove expired entries
        history = [ts for ts in history if ts > window_start]
        self._request_history[key_str] = history
        
        # Count requests in window
        count = len(history)
        limit = self.config.get_limit_for(key.identifier)
        
        # Calculate result
        allowed = count < limit
        remaining = max(0, limit - count)
        
        # Find when oldest request expires
        if history:
            oldest = min(history)
            reset_at = oldest + timedelta(seconds=self.config.window_seconds)
        else:
            reset_at = now + timedelta(seconds=self.config.window_seconds)
        
        retry_after = None
        if not allowed and history:
            # Calculate when we can accept next request
            oldest = min(history)
            retry_after = int((oldest + timedelta(seconds=self.config.window_seconds) - now).total_seconds())
        
        result = RateLimitResult(
            allowed=allowed,
            limit=limit,
            remaining=remaining,
            reset_at=reset_at,
            retry_after=retry_after,
            metadata={
                "algorithm": "sliding_window",
                "window_seconds": self.config.window_seconds,
                "current_count": count
            }
        )
        
        # Update state
        new_state = RateLimitState(
            count=count,
            window_start=window_start
        )
        
        return result, new_state
    
    async def consume(
        self,
        key: RateLimitKey,
        amount: int = 1,
        state: Optional[RateLimitState] = None
    ) -> tuple[bool, RateLimitState]:
        """Consume from rate limit allowance"""
        result, new_state = await self.check_limit(key, state)
        
        if result.allowed:
            # Add timestamps for consumed requests
            key_str = key.to_string()
            now = datetime.utcnow()
            
            if key_str not in self._request_history:
                self._request_history[key_str] = []
            
            for _ in range(amount):
                self._request_history[key_str].append(now)
            
            new_state.count += amount
            return True, new_state
        
        return False, new_state
    
    async def reset(self, key: RateLimitKey) -> RateLimitState:
        """Reset rate limit for given key"""
        key_str = key.to_string()
        if key_str in self._request_history:
            del self._request_history[key_str]
        
        return RateLimitState()