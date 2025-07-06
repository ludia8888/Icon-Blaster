"""
Common Redis utilities and patterns for middleware components

DESIGN INTENT:
This module provides a simple Redis client for DEVELOPMENT and TESTING environments,
as well as non-critical production use cases. It offers:
- Connection pooling with singleton pattern
- Common operation helpers (JSON serialization, sorted sets, etc.)
- Distributed locking primitives
- Key pattern constants for consistency

USE CASES:
- Development and testing environments
- Simple caching without HA requirements
- Rate limiting and session storage
- Distributed locks for coordination

NOT FOR:
- Production environments requiring high availability (use database/clients/redis_ha_client.py)
- Mission-critical data storage
- Environments with Redis Sentinel

Related modules:
- database/clients/redis_ha_client.py: Production HA Redis client with Sentinel
- Direct redis.asyncio usage: Being phased out, migrate to this or RedisHAClient

Migration note:
If you're using redis.asyncio directly, please migrate to either:
- This module (RedisClient) for dev/test/simple cases
- RedisHAClient for production HA requirements
"""
import asyncio
import json
import logging
from typing import Any, Dict, Optional, Union, Callable
from functools import wraps
import redis.asyncio as redis
from redis.asyncio.connection import ConnectionPool
from datetime import timedelta

logger = logging.getLogger(__name__)


class RedisConnectionPool:
    """Singleton Redis connection pool manager"""
    
    _instance = None
    _pool = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def get_pool(self, **kwargs) -> ConnectionPool:
        """Get or create Redis connection pool"""
        if self._pool is None:
            default_config = {
                'host': 'localhost',
                'port': 6379,
                'db': 0,
                'decode_responses': True,
                'max_connections': 50,
                'socket_keepalive': True,
                'socket_keepalive_options': {
                    1: 1,  # TCP_KEEPIDLE
                    2: 1,  # TCP_KEEPINTVL
                    3: 3,  # TCP_KEEPCNT
                }
            }
            config = {**default_config, **kwargs}
            self._pool = redis.ConnectionPool(**config)
        return self._pool
    
    async def close(self):
        """Close connection pool"""
        if self._pool:
            await self._pool.disconnect()
            self._pool = None


class RedisClient:
    """Redis client with common patterns and error handling"""
    
    def __init__(self, pool: Optional[ConnectionPool] = None):
        self.pool = pool
        self._client = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        if self.pool is None:
            pool_manager = RedisConnectionPool()
            self.pool = await pool_manager.get_pool()
        self._client = redis.Redis(connection_pool=self.pool)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self._client:
            await self._client.close()
    
    async def get_json(self, key: str) -> Optional[Dict[str, Any]]:
        """Get JSON value from Redis"""
        try:
            value = await self._client.get(key)
            return json.loads(value) if value else None
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in key {key}")
            return None
        except Exception as e:
            logger.error(f"Redis get error for key {key}: {e}")
            return None
    
    async def set_json(
        self, 
        key: str, 
        value: Dict[str, Any], 
        expire: Optional[Union[int, timedelta]] = None
    ) -> bool:
        """Set JSON value in Redis with optional expiration"""
        try:
            json_value = json.dumps(value)
            if expire:
                if isinstance(expire, timedelta):
                    expire = int(expire.total_seconds())
                return await self._client.setex(key, expire, json_value)
            return await self._client.set(key, json_value)
        except Exception as e:
            logger.error(f"Redis set error for key {key}: {e}")
            return False
    
    async def increment(
        self, 
        key: str, 
        amount: int = 1, 
        expire: Optional[int] = None
    ) -> int:
        """Atomic increment with optional expiration"""
        try:
            value = await self._client.incrby(key, amount)
            if expire and value == amount:  # First increment
                await self._client.expire(key, expire)
            return value
        except Exception as e:
            logger.error(f"Redis increment error for key {key}: {e}")
            raise
    
    async def add_to_sorted_set(
        self, 
        key: str, 
        member: str, 
        score: float,
        expire: Optional[int] = None
    ) -> bool:
        """Add member to sorted set with score"""
        try:
            result = await self._client.zadd(key, {member: score})
            if expire:
                await self._client.expire(key, expire)
            return bool(result)
        except Exception as e:
            logger.error(f"Redis zadd error for key {key}: {e}")
            return False
    
    async def get_sorted_set_range(
        self, 
        key: str, 
        start: int = 0, 
        stop: int = -1,
        withscores: bool = False
    ) -> list:
        """Get range from sorted set"""
        try:
            return await self._client.zrange(key, start, stop, withscores=withscores)
        except Exception as e:
            logger.error(f"Redis zrange error for key {key}: {e}")
            return []
    
    async def remove_from_sorted_set(
        self, 
        key: str, 
        member: str
    ) -> bool:
        """Remove member from sorted set"""
        try:
            result = await self._client.zrem(key, member)
            return bool(result)
        except Exception as e:
            logger.error(f"Redis zrem error for key {key}: {e}")
            return False
    
    async def set_hash_field(
        self, 
        key: str, 
        field: str, 
        value: Union[str, Dict[str, Any]],
        expire: Optional[int] = None
    ) -> bool:
        """Set hash field value"""
        try:
            if isinstance(value, dict):
                value = json.dumps(value)
            result = await self._client.hset(key, field, value)
            if expire:
                await self._client.expire(key, expire)
            return bool(result)
        except Exception as e:
            logger.error(f"Redis hset error for key {key}, field {field}: {e}")
            return False
    
    async def get_hash_field(
        self, 
        key: str, 
        field: str,
        as_json: bool = False
    ) -> Optional[Union[str, Dict[str, Any]]]:
        """Get hash field value"""
        try:
            value = await self._client.hget(key, field)
            if value and as_json:
                return json.loads(value)
            return value
        except Exception as e:
            logger.error(f"Redis hget error for key {key}, field {field}: {e}")
            return None
    
    async def delete_keys(self, pattern: str) -> int:
        """Delete keys matching pattern"""
        try:
            keys = await self._client.keys(pattern)
            if keys:
                return await self._client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Redis delete error for pattern {pattern}: {e}")
            return 0
    
    async def acquire_lock(
        self, 
        key: str, 
        timeout: int = 10,
        blocking: bool = True,
        blocking_timeout: Optional[float] = None
    ) -> Optional['RedisLock']:
        """Acquire distributed lock"""
        lock = self._client.lock(
            key, 
            timeout=timeout, 
            blocking=blocking,
            blocking_timeout=blocking_timeout
        )
        if await lock.acquire():
            return RedisLock(lock)
        return None
    
    @property
    def client(self) -> redis.Redis:
        """Get raw Redis client"""
        return self._client


class RedisLock:
    """Wrapper for Redis lock with async context manager"""
    
    def __init__(self, lock):
        self.lock = lock
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.lock.release()
    
    async def extend(self, additional_time: float) -> bool:
        """Extend lock timeout"""
        return await self.lock.extend(additional_time)


def redis_retry(max_attempts: int = 3, delay: float = 0.1):
    """Decorator for retrying Redis operations"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_error = None
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except redis.ConnectionError as e:
                    last_error = e
                    if attempt < max_attempts - 1:
                        await asyncio.sleep(delay * (2 ** attempt))
                    else:
                        logger.error(f"Redis operation failed after {max_attempts} attempts: {e}")
                        raise
            raise last_error
        return wrapper
    return decorator


# Key patterns for different middleware components
class RedisKeyPatterns:
    """Standard key patterns for middleware components"""
    
    # Health check keys
    HEALTH_STATUS = "health:status:{component}"
    HEALTH_DEPENDENCY = "health:dependency:{component}:{dependency}"
    HEALTH_METRICS = "health:metrics:{component}"
    
    # Rate limiting keys
    RATE_LIMIT_USER = "ratelimit:user:{user_id}:{endpoint}"
    RATE_LIMIT_IP = "ratelimit:ip:{ip}:{endpoint}"
    RATE_LIMIT_GLOBAL = "ratelimit:global:{endpoint}"
    
    # Service discovery keys
    SERVICE_REGISTRY = "discovery:services:{service_name}"
    SERVICE_INSTANCE = "discovery:instance:{service_name}:{instance_id}"
    SERVICE_HEALTH = "discovery:health:{service_name}:{instance_id}"
    
    # DLQ keys
    DLQ_MESSAGES = "dlq:messages:{queue_name}"
    DLQ_RETRY_COUNT = "dlq:retry:{message_id}"
    DLQ_POISON = "dlq:poison:{queue_name}"
    
    # Circuit breaker keys
    CIRCUIT_STATE = "circuit:state:{service}"
    CIRCUIT_FAILURES = "circuit:failures:{service}"
    CIRCUIT_SUCCESS = "circuit:success:{service}"