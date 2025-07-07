"""
Base rate limiting strategy interface
"""
from abc import ABC, abstractmethod
from typing import Optional
from ..models import RateLimitConfig, RateLimitResult, RateLimitState, RateLimitKey


class RateLimitStrategy(ABC):
    """Abstract base class for rate limiting strategies"""
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
    
    @abstractmethod
    async def check_limit(
        self,
        key: RateLimitKey,
        state: Optional[RateLimitState] = None
    ) -> tuple[RateLimitResult, RateLimitState]:
        """
        Check if request is within rate limit.
        Returns result and updated state.
        """
        pass
    
    @abstractmethod
    async def consume(
        self,
        key: RateLimitKey,
        amount: int = 1,
        state: Optional[RateLimitState] = None
    ) -> tuple[bool, RateLimitState]:
        """
        Consume from rate limit allowance.
        Returns success status and updated state.
        """
        pass
    
    @abstractmethod
    async def reset(self, key: RateLimitKey) -> RateLimitState:
        """Reset rate limit for given key"""
        pass