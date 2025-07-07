"""
Provider for the distributed lock manager.
"""
from typing import Any
from bootstrap.config import get_config
from core.branch.lock_manager import BranchLockManager as MemoryLockManager
from core.branch.redis_lock_manager import RedisLockManager
from .base import Provider
import redis.asyncio as redis

class LockManagerProvider(Provider[Any]):
    """
    Provides the appropriate lock manager based on the application configuration.
    Reads from LockConfig and instantiates either a RedisLockManager or a
    MemoryLockManager.
    """
    def __init__(self):
        self._config = get_config().lock
        self._instance = None
        self._redis_client = None

    async def provide(self) -> Any:
        """Create lock manager instance based on config."""
        if self._instance is None:
            if self._config.backend == "redis":
                self._redis_client = redis.from_url(
                    self._config.redis_url,
                    decode_responses=True
                )
                self._instance = RedisLockManager(
                    redis_client=self._redis_client,
                    namespace=self._config.namespace,
                    default_ttl=self._config.ttl
                )
            elif self._config.backend == "memory":
                self._instance = MemoryLockManager()
                await self._instance.initialize()
            else:
                raise ValueError(f"Unknown lock backend: {self._config.backend}")
        
        return self._instance

    async def shutdown(self) -> None:
        """Shutdown the lock manager connection if applicable."""
        # MemoryLockManager has a shutdown method for its background tasks
        if isinstance(self._instance, MemoryLockManager):
            await self._instance.shutdown()
        
        # If a redis client was created, close its connection pool
        if self._redis_client:
            await self._redis_client.close() 