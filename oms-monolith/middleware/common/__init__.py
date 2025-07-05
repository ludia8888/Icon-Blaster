"""
Common utilities for middleware components
"""

from .metrics import MetricsCollector, MetricType
from utils.retry_strategy import RetryStrategy

# Placeholder Redis utilities until proper implementation
class RedisConnectionPool:
    pass

class RedisClient:
    pass

def redis_retry(func):
    return func

# Temporary placeholder functions until proper implementation
def exponential_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
    """Calculate exponential backoff delay"""
    delay = min(base_delay * (2 ** attempt), max_delay)
    jitter = random.uniform(0, delay * 0.1)
    return delay + jitter

def retry_with_backoff(max_attempts: int = 3, base_delay: float = 1.0):
    """Decorator for retrying with exponential backoff"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    delay = exponential_backoff(attempt, base_delay)
                    await asyncio.sleep(delay)
            raise Exception("Max retries exceeded")
        return wrapper
    return decorator

import random
import functools
import asyncio

__all__ = [
    'RedisConnectionPool',
    'RedisClient', 
    'redis_retry',
    'MetricsCollector',
    'MetricType',
    'RetryStrategy',
    'exponential_backoff',
    'retry_with_backoff'
]