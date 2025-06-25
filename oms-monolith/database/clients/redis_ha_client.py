"""
Redis High Availability Client
Integrates with Redis Sentinel for automatic failover
"""

import asyncio
import time
from typing import Any, Dict, List, Optional

import redis
import redis.sentinel
import structlog
from redis.backoff import ExponentialBackoff
from redis.retry import Retry

logger = structlog.get_logger(__name__)

class RedisHAClient:
    """
    High Availability Redis client with Sentinel integration
    Provides automatic failover and connection management
    """

    def __init__(self,
                 sentinel_hosts: List[tuple],
                 master_name: str = 'oms-redis-master',
                 password: Optional[str] = None,
                 socket_timeout: float = 5.0,
                 socket_connect_timeout: float = 5.0,
                 retry_on_timeout: bool = True,
                 health_check_interval: int = 30,
                 max_connections: int = 50):

        self.sentinel_hosts = sentinel_hosts
        self.master_name = master_name
        self.password = password
        self.socket_timeout = socket_timeout
        self.socket_connect_timeout = socket_connect_timeout
        self.retry_on_timeout = retry_on_timeout
        self.health_check_interval = health_check_interval
        self.max_connections = max_connections

        # Sentinel and client instances
        self.sentinel = None
        self.master_client = None
        self.replica_client = None

        # Connection state
        self._master_host = None
        self._master_port = None
        self._last_health_check = 0
        self._connected = False

        # Health monitoring
        self._health_check_task = None
        self._running = False

        logger.info("Redis HA client initialized",
                   sentinel_hosts=sentinel_hosts,
                   master_name=master_name)

    async def connect(self) -> bool:
        """Initialize connection to Redis cluster via Sentinel"""
        try:
            # Initialize Sentinel
            self.sentinel = redis.sentinel.Sentinel(
                self.sentinel_hosts,
                socket_timeout=self.socket_timeout,
                socket_connect_timeout=self.socket_connect_timeout,
                retry_on_timeout=self.retry_on_timeout,
                password=self.password
            )

            # Discover master
            await self._discover_master()

            # Create Redis clients
            await self._create_clients()

            # Start health monitoring
            self._running = True
            self._health_check_task = asyncio.create_task(self._health_monitor())

            self._connected = True
            logger.info("Redis HA client connected successfully")
            return True

        except Exception as e:
            logger.error("Failed to connect Redis HA client", error=str(e))
            await self.disconnect()
            return False

    async def disconnect(self):
        """Disconnect from Redis cluster"""
        self._running = False
        self._connected = False

        # Stop health monitoring
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # Close connections
        if self.master_client:
            await asyncio.get_event_loop().run_in_executor(
                None, self.master_client.close
            )

        if self.replica_client:
            await asyncio.get_event_loop().run_in_executor(
                None, self.replica_client.close
            )

        logger.info("Redis HA client disconnected")

    async def _discover_master(self):
        """Discover current master from Sentinel"""
        try:
            master_info = await asyncio.get_event_loop().run_in_executor(
                None, self.sentinel.discover_master, self.master_name
            )

            if master_info:
                new_host, new_port = master_info

                # Check if master has changed
                if (self._master_host, self._master_port) != (new_host, new_port):
                    if self._master_host is not None:
                        logger.warning("Master changed, updating connections",
                                     old_master=f"{self._master_host}:{self._master_port}",
                                     new_master=f"{new_host}:{new_port}")

                    self._master_host = new_host
                    self._master_port = new_port

                    # Recreate clients with new master
                    if self._connected:
                        await self._create_clients()

                return True
            else:
                logger.error("No master discovered", master_name=self.master_name)
                return False

        except Exception as e:
            logger.error("Failed to discover master", error=str(e))
            return False

    async def _create_clients(self):
        """Create Redis clients for master and replica"""
        if not self._master_host or not self._master_port:
            raise Exception("Master not discovered")

        try:
            # Close existing connections
            if self.master_client:
                await asyncio.get_event_loop().run_in_executor(
                    None, self.master_client.close
                )
            if self.replica_client:
                await asyncio.get_event_loop().run_in_executor(
                    None, self.replica_client.close
                )

            # Create master client with retry logic
            self.master_client = redis.Redis(
                host=self._master_host,
                port=self._master_port,
                password=self.password,
                socket_timeout=self.socket_timeout,
                socket_connect_timeout=self.socket_connect_timeout,
                retry_on_timeout=self.retry_on_timeout,
                retry=Retry(ExponentialBackoff(), 3),
                max_connections=self.max_connections,
                health_check_interval=self.health_check_interval
            )

            # Test master connection
            await asyncio.get_event_loop().run_in_executor(
                None, self.master_client.ping
            )

            # Create replica client (for read operations)
            self.replica_client = await asyncio.get_event_loop().run_in_executor(
                None, self.sentinel.slave_for, self.master_name,
                socket_timeout=self.socket_timeout,
                socket_connect_timeout=self.socket_connect_timeout,
                password=self.password,
                retry_on_timeout=self.retry_on_timeout
            )

            logger.info("Redis clients created successfully",
                       master=f"{self._master_host}:{self._master_port}")

        except Exception as e:
            logger.error("Failed to create Redis clients", error=str(e))
            raise

    async def _health_monitor(self):
        """Background health monitoring task"""
        while self._running:
            try:
                current_time = time.time()

                # Check if it's time for health check
                if current_time - self._last_health_check >= self.health_check_interval:
                    await self._perform_health_check()
                    self._last_health_check = current_time

                await asyncio.sleep(5)  # Check every 5 seconds

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Error in health monitor", error=str(e))
                await asyncio.sleep(5)

    async def _perform_health_check(self):
        """Perform health check on Redis connections"""
        try:
            # Check master connection
            if self.master_client:
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        None, self.master_client.ping
                    )
                except Exception as e:
                    logger.warning("Master ping failed, attempting reconnection", error=str(e))
                    await self._discover_master()

            # Check replica connection
            if self.replica_client:
                try:
                    await asyncio.get_event_loop().run_in_executor(
                        None, self.replica_client.ping
                    )
                except Exception as e:
                    logger.warning("Replica ping failed", error=str(e))

        except Exception as e:
            logger.error("Health check failed", error=str(e))

    # Redis command wrappers with automatic failover

    async def get(self, key: str, use_replica: bool = True) -> Optional[str]:
        """Get value from Redis (preferably from replica for read scalability)"""
        client = self.replica_client if use_replica and self.replica_client else self.master_client

        if not client:
            raise Exception("No Redis client available")

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, client.get, key
            )
            return result.decode('utf-8') if result else None

        except Exception as e:
            # Fallback to master if replica fails
            if use_replica and self.master_client:
                logger.warning("Replica get failed, falling back to master", error=str(e))
                return await self.get(key, use_replica=False)
            else:
                logger.error("Redis get failed", key=key, error=str(e))
                raise

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        """Set value in Redis (always uses master)"""
        if not self.master_client:
            raise Exception("No master client available")

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, self.master_client.set, key, value, ex
            )
            return bool(result)

        except Exception as e:
            logger.error("Redis set failed", key=key, error=str(e))
            raise

    async def delete(self, *keys: str) -> int:
        """Delete keys from Redis (always uses master)"""
        if not self.master_client:
            raise Exception("No master client available")

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, self.master_client.delete, *keys
            )
            return int(result)

        except Exception as e:
            logger.error("Redis delete failed", keys=keys, error=str(e))
            raise

    async def exists(self, *keys: str, use_replica: bool = True) -> int:
        """Check if keys exist in Redis"""
        client = self.replica_client if use_replica and self.replica_client else self.master_client

        if not client:
            raise Exception("No Redis client available")

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, client.exists, *keys
            )
            return int(result)

        except Exception as e:
            # Fallback to master if replica fails
            if use_replica and self.master_client:
                logger.warning("Replica exists failed, falling back to master", error=str(e))
                return await self.exists(*keys, use_replica=False)
            else:
                logger.error("Redis exists failed", keys=keys, error=str(e))
                raise

    async def expire(self, key: str, time: int) -> bool:
        """Set expiration time for a key (always uses master)"""
        if not self.master_client:
            raise Exception("No master client available")

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, self.master_client.expire, key, time
            )
            return bool(result)

        except Exception as e:
            logger.error("Redis expire failed", key=key, error=str(e))
            raise

    async def hget(self, name: str, key: str, use_replica: bool = True) -> Optional[str]:
        """Get hash field value"""
        client = self.replica_client if use_replica and self.replica_client else self.master_client

        if not client:
            raise Exception("No Redis client available")

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, client.hget, name, key
            )
            return result.decode('utf-8') if result else None

        except Exception as e:
            if use_replica and self.master_client:
                logger.warning("Replica hget failed, falling back to master", error=str(e))
                return await self.hget(name, key, use_replica=False)
            else:
                logger.error("Redis hget failed", name=name, key=key, error=str(e))
                raise

    async def hset(self, name: str, key: str, value: str) -> bool:
        """Set hash field value (always uses master)"""
        if not self.master_client:
            raise Exception("No master client available")

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, self.master_client.hset, name, key, value
            )
            return bool(result)

        except Exception as e:
            logger.error("Redis hset failed", name=name, key=key, error=str(e))
            raise

    async def pipeline(self):
        """Create a Redis pipeline for batch operations"""
        if not self.master_client:
            raise Exception("No master client available")

        return self.master_client.pipeline()

    async def get_connection_info(self) -> Dict[str, Any]:
        """Get current connection information"""
        return {
            'connected': self._connected,
            'master_host': self._master_host,
            'master_port': self._master_port,
            'sentinel_hosts': self.sentinel_hosts,
            'master_name': self.master_name,
            'health_check_interval': self.health_check_interval
        }

# Global HA client instance
_redis_ha_client: Optional[RedisHAClient] = None

async def get_redis_ha_client() -> RedisHAClient:
    """Get or create Redis HA client instance"""
    global _redis_ha_client

    if _redis_ha_client is None or not _redis_ha_client._connected:
        # Default sentinel configuration
        sentinel_hosts = [
            ('redis-sentinel-1', 26379),
            ('redis-sentinel-2', 26379),
            ('redis-sentinel-3', 26379)
        ]

        _redis_ha_client = RedisHAClient(
            sentinel_hosts=sentinel_hosts,
            master_name='oms-redis-master',
            password=None,  # Set from environment in production
            socket_timeout=5.0,
            health_check_interval=30
        )

        success = await _redis_ha_client.connect()
        if not success:
            raise Exception("Failed to connect to Redis HA cluster")

    return _redis_ha_client

async def close_redis_ha_client():
    """Close Redis HA client connection"""
    global _redis_ha_client

    if _redis_ha_client:
        await _redis_ha_client.disconnect()
        _redis_ha_client = None
