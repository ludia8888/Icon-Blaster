"""Common Rate Limiting Package

Unified rate limiting utilities for all services.
Provides consistent rate limiting implementations with multiple backends.
"""

from .core import RateLimiter, RateLimitExceeded
from .middleware import (
    RateLimitMiddleware,
    FastAPIRateLimitMiddleware,
    rate_limit_decorator
)
from .backends import RedisBackend, InMemoryBackend, Backend
from .algorithms import SlidingWindowAlgorithm, TokenBucketAlgorithm, FixedWindowAlgorithm

__version__ = "1.0.0"
__all__ = [
    "RateLimiter",
    "RateLimitExceeded",
    "RateLimitMiddleware",
    "FastAPIRateLimitMiddleware",
    "rate_limit_decorator",
    "RedisBackend",
    "InMemoryBackend",
    "Backend",
    "SlidingWindowAlgorithm",
    "TokenBucketAlgorithm",
    "FixedWindowAlgorithm",
]