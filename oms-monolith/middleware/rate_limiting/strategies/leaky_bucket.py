"""
Leaky bucket rate limiting strategy
"""
from datetime import datetime, timedelta
from typing import Optional, List
from collections import deque
from .base import RateLimitStrategy
from ..models import (
    RateLimitConfig, RateLimitResult, RateLimitState, RateLimitKey
)


class LeakyBucketStrategy(RateLimitStrategy):
    """
    Leaky bucket algorithm for rate limiting.
    Processes requests at a constant rate.
    """
    
    def __init__(self, config: RateLimitConfig):
        super().__init__(config)
        # Set bucket size
        self.bucket_size = config.burst_size or config.requests_per_window
        # Calculate leak rate (requests per second)
        self.leak_rate = config.refill_rate or (
            config.requests_per_window / config.window_seconds
        )
        # Request queues per key
        self._queues: Dict[str, deque] = {}
    
    async def check_limit(
        self,
        key: RateLimitKey,
        state: Optional[RateLimitState] = None
    ) -> tuple[RateLimitResult, RateLimitState]:
        """Check if request is within rate limit"""
        now = datetime.utcnow()
        key_str = key.to_string()
        
        # Get or create queue
        if key_str not in self._queues:
            self._queues[key_str] = deque(maxlen=self.bucket_size)
        
        queue = self._queues[key_str]
        
        # Process leaked requests
        self._process_leaks(queue, now)
        
        # Check if we can accept request
        allowed = len(queue) < self.bucket_size
        remaining = self.bucket_size - len(queue)
        
        # Calculate when next slot will be available
        if queue:
            # Time when oldest request will leak
            oldest_request = queue[0]
            leak_time = oldest_request + timedelta(seconds=1.0/self.leak_rate)
            reset_at = max(leak_time, now)
        else:
            reset_at = now
        
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
                "algorithm": "leaky_bucket",
                "bucket_size": self.bucket_size,
                "leak_rate": self.leak_rate,
                "queue_length": len(queue)
            }
        )
        
        # Update state
        new_state = RateLimitState(
            count=len(queue),
            last_update=now
        )
        
        return result, new_state
    
    async def consume(
        self,
        key: RateLimitKey,
        amount: int = 1,
        state: Optional[RateLimitState] = None
    ) -> tuple[bool, RateLimitState]:
        """Add request to bucket"""
        result, new_state = await self.check_limit(key, state)
        
        if result.allowed:
            key_str = key.to_string()
            queue = self._queues[key_str]
            now = datetime.utcnow()
            
            # Add requests to queue
            for _ in range(amount):
                if len(queue) < self.bucket_size:
                    queue.append(now)
                else:
                    return False, new_state
            
            new_state.count = len(queue)
            return True, new_state
        
        return False, new_state
    
    async def reset(self, key: RateLimitKey) -> RateLimitState:
        """Reset rate limit for given key"""
        key_str = key.to_string()
        if key_str in self._queues:
            self._queues[key_str].clear()
        
        return RateLimitState()
    
    def _process_leaks(self, queue: deque, now: datetime):
        """Remove leaked (processed) requests from queue"""
        if not queue:
            return
        
        # Calculate how many requests should have leaked
        time_since_oldest = (now - queue[0]).total_seconds()
        leaked_count = int(time_since_oldest * self.leak_rate)
        
        # Remove leaked requests
        for _ in range(min(leaked_count, len(queue))):
            queue.popleft()