"""
Token bucket rate limiting strategy
"""
from datetime import datetime, timedelta
from typing import Optional
from .base import RateLimitStrategy
from ..models import (
    RateLimitConfig, RateLimitResult, RateLimitState, RateLimitKey
)


class TokenBucketStrategy(RateLimitStrategy):
    """
    Token bucket algorithm for rate limiting.
    Allows burst traffic up to bucket capacity.
    """
    
    def __init__(self, config: RateLimitConfig):
        super().__init__(config)
        # Set burst size to window limit if not specified
        self.burst_size = config.burst_size or config.requests_per_window
        # Calculate refill rate (tokens per second)
        self.refill_rate = config.refill_rate or (
            config.requests_per_window / config.window_seconds
        )
    
    async def check_limit(
        self,
        key: RateLimitKey,
        state: Optional[RateLimitState] = None
    ) -> tuple[RateLimitResult, RateLimitState]:
        """Check if request is within rate limit"""
        now = datetime.utcnow()
        
        # Initialize state if not provided
        if state is None:
            state = RateLimitState(
                tokens=float(self.burst_size),
                last_update=now
            )
        
        # Calculate tokens to add based on time elapsed
        elapsed = (now - state.last_update).total_seconds()
        tokens_to_add = elapsed * self.refill_rate
        
        # Update token count (cap at burst size)
        current_tokens = min(
            state.tokens + tokens_to_add,
            float(self.burst_size)
        )
        
        # Check if we have tokens available
        allowed = current_tokens >= 1.0
        remaining = int(current_tokens)
        
        # Calculate when bucket will have tokens again
        if allowed:
            reset_at = now
        else:
            seconds_until_token = (1.0 - current_tokens) / self.refill_rate
            reset_at = now + timedelta(seconds=seconds_until_token)
        
        retry_after = None
        if not allowed:
            retry_after = int((reset_at - now).total_seconds()) + 1
        
        result = RateLimitResult(
            allowed=allowed,
            limit=self.config.requests_per_window,
            remaining=remaining,
            reset_at=reset_at,
            retry_after=retry_after,
            metadata={
                "algorithm": "token_bucket",
                "burst_size": self.burst_size,
                "refill_rate": self.refill_rate,
                "current_tokens": current_tokens
            }
        )
        
        # Update state
        new_state = RateLimitState(
            tokens=current_tokens,
            last_update=now
        )
        
        return result, new_state
    
    async def consume(
        self,
        key: RateLimitKey,
        amount: int = 1,
        state: Optional[RateLimitState] = None
    ) -> tuple[bool, RateLimitState]:
        """Consume tokens from bucket"""
        result, new_state = await self.check_limit(key, state)
        
        if result.allowed and new_state.tokens >= amount:
            # Consume tokens
            new_state.tokens -= amount
            return True, new_state
        
        return False, new_state
    
    async def reset(self, key: RateLimitKey) -> RateLimitState:
        """Reset rate limit for given key"""
        return RateLimitState(
            tokens=float(self.burst_size),
            last_update=datetime.utcnow()
        )