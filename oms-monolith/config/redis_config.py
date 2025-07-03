"""
Redis configuration for graph analysis caching.
Provides production-ready Redis setup with clustering support.
"""
import os
from typing import Optional, Dict, Any
from dataclasses import dataclass
import redis.asyncio as redis
from redis.asyncio.cluster import RedisCluster
from redis.asyncio.sentinel import Sentinel

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RedisConfig:
    """Redis configuration for various deployment modes."""
    # Connection settings
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    username: Optional[str] = None
    
    # SSL/TLS settings
    ssl: bool = False
    ssl_cert_reqs: str = "required"
    ssl_ca_certs: Optional[str] = None
    ssl_certfile: Optional[str] = None
    ssl_keyfile: Optional[str] = None
    
    # Connection pool settings
    max_connections: int = 50
    retry_on_timeout: bool = True
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    
    # Cluster settings
    cluster_mode: bool = False
    cluster_nodes: Optional[list] = None
    
    # Sentinel settings  
    sentinel_mode: bool = False
    sentinel_service: str = "mymaster"
    sentinel_nodes: Optional[list] = None
    
    # Graph-specific settings
    graph_cache_prefix: str = "graph:"
    default_ttl: int = 1800  # 30 minutes
    max_key_length: int = 250
    
    @classmethod
    def from_env(cls) -> 'RedisConfig':
        """Create Redis config from environment variables."""
        return cls(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")),
            password=os.getenv("REDIS_PASSWORD"),
            username=os.getenv("REDIS_USERNAME"),
            
            ssl=os.getenv("REDIS_SSL", "false").lower() == "true",
            ssl_ca_certs=os.getenv("REDIS_SSL_CA_CERTS"),
            ssl_certfile=os.getenv("REDIS_SSL_CERTFILE"),
            ssl_keyfile=os.getenv("REDIS_SSL_KEYFILE"),
            
            max_connections=int(os.getenv("REDIS_MAX_CONNECTIONS", "50")),
            socket_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT", "5.0")),
            socket_connect_timeout=float(os.getenv("REDIS_CONNECT_TIMEOUT", "5.0")),
            
            cluster_mode=os.getenv("REDIS_CLUSTER_MODE", "false").lower() == "true",
            sentinel_mode=os.getenv("REDIS_SENTINEL_MODE", "false").lower() == "true",
            sentinel_service=os.getenv("REDIS_SENTINEL_SERVICE", "mymaster"),
            
            graph_cache_prefix=os.getenv("GRAPH_CACHE_PREFIX", "graph:"),
            default_ttl=int(os.getenv("GRAPH_CACHE_TTL", "1800"))
        )


class RedisConnectionManager:
    """
    Manages Redis connections with support for various deployment modes.
    """
    
    def __init__(self, config: RedisConfig):
        self.config = config
        self._client: Optional[redis.Redis] = None
        self._cluster: Optional[RedisCluster] = None
        self._sentinel: Optional[Sentinel] = None
    
    async def get_client(self) -> redis.Redis:
        """Get Redis client based on configuration."""
        if self.config.cluster_mode:
            return await self._get_cluster_client()
        elif self.config.sentinel_mode:
            return await self._get_sentinel_client()
        else:
            return await self._get_single_client()
    
    async def _get_single_client(self) -> redis.Redis:
        """Get single Redis instance client."""
        if self._client is None:
            connection_kwargs = {
                "host": self.config.host,
                "port": self.config.port,
                "db": self.config.db,
                "password": self.config.password,
                "username": self.config.username,
                "max_connections": self.config.max_connections,
                "retry_on_timeout": self.config.retry_on_timeout,
                "socket_timeout": self.config.socket_timeout,
                "socket_connect_timeout": self.config.socket_connect_timeout,
                "decode_responses": True
            }
            
            # Add SSL configuration if enabled
            if self.config.ssl:
                connection_kwargs.update({
                    "ssl": True,
                    "ssl_cert_reqs": self.config.ssl_cert_reqs,
                    "ssl_ca_certs": self.config.ssl_ca_certs,
                    "ssl_certfile": self.config.ssl_certfile,
                    "ssl_keyfile": self.config.ssl_keyfile
                })
            
            self._client = redis.Redis(**connection_kwargs)
            
            # Test connection
            try:
                await self._client.ping()
                logger.info(f"Connected to Redis at {self.config.host}:{self.config.port}")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                raise
        
        return self._client
    
    async def _get_cluster_client(self) -> RedisCluster:
        """Get Redis cluster client."""
        if self._cluster is None:
            if not self.config.cluster_nodes:
                raise ValueError("Cluster nodes must be specified for cluster mode")
            
            startup_nodes = [
                {"host": node["host"], "port": node["port"]} 
                for node in self.config.cluster_nodes
            ]
            
            cluster_kwargs = {
                "startup_nodes": startup_nodes,
                "password": self.config.password,
                "username": self.config.username,
                "max_connections": self.config.max_connections,
                "socket_timeout": self.config.socket_timeout,
                "socket_connect_timeout": self.config.socket_connect_timeout,
                "decode_responses": True,
                "skip_full_coverage_check": True  # For development
            }
            
            if self.config.ssl:
                cluster_kwargs.update({
                    "ssl": True,
                    "ssl_cert_reqs": self.config.ssl_cert_reqs,
                    "ssl_ca_certs": self.config.ssl_ca_certs,
                    "ssl_certfile": self.config.ssl_certfile,
                    "ssl_keyfile": self.config.ssl_keyfile
                })
            
            self._cluster = RedisCluster(**cluster_kwargs)
            
            try:
                await self._cluster.ping()
                logger.info(f"Connected to Redis cluster with {len(startup_nodes)} nodes")
            except Exception as e:
                logger.error(f"Failed to connect to Redis cluster: {e}")
                raise
        
        return self._cluster
    
    async def _get_sentinel_client(self) -> redis.Redis:
        """Get Redis client through Sentinel."""
        if self._sentinel is None:
            if not self.config.sentinel_nodes:
                raise ValueError("Sentinel nodes must be specified for sentinel mode")
            
            sentinel_kwargs = {
                "socket_timeout": self.config.socket_timeout,
                "socket_connect_timeout": self.config.socket_connect_timeout
            }
            
            if self.config.ssl:
                sentinel_kwargs.update({
                    "ssl": True,
                    "ssl_cert_reqs": self.config.ssl_cert_reqs,
                    "ssl_ca_certs": self.config.ssl_ca_certs,
                    "ssl_certfile": self.config.ssl_certfile,
                    "ssl_keyfile": self.config.ssl_keyfile
                })
            
            self._sentinel = Sentinel(
                [(node["host"], node["port"]) for node in self.config.sentinel_nodes],
                sentinel_kwargs=sentinel_kwargs
            )
            
            logger.info(f"Connected to Redis via Sentinel with service: {self.config.sentinel_service}")
        
        # Get master connection
        master = self._sentinel.master_for(
            self.config.sentinel_service,
            password=self.config.password,
            username=self.config.username,
            db=self.config.db,
            decode_responses=True
        )
        
        return master
    
    async def close(self):
        """Close all Redis connections."""
        if self._client:
            await self._client.close()
            self._client = None
        
        if self._cluster:
            await self._cluster.close()
            self._cluster = None
        
        if self._sentinel:
            # Sentinel doesn't need explicit closing
            self._sentinel = None
        
        logger.info("Redis connections closed")
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform Redis health check."""
        try:
            client = await self.get_client()
            
            # Basic connectivity
            ping_result = await client.ping()
            
            # Get info
            info = await client.info()
            
            # Test read/write
            test_key = f"{self.config.graph_cache_prefix}health_check"
            await client.set(test_key, "ok", ex=60)
            test_value = await client.get(test_key)
            await client.delete(test_key)
            
            return {
                "status": "healthy",
                "ping": ping_result,
                "read_write_test": test_value == "ok",
                "redis_version": info.get("redis_version"),
                "connected_clients": info.get("connected_clients"),
                "used_memory_human": info.get("used_memory_human"),
                "keyspace": {k: v for k, v in info.items() if k.startswith("db")},
                "mode": "cluster" if self.config.cluster_mode else "sentinel" if self.config.sentinel_mode else "standalone"
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "mode": "cluster" if self.config.cluster_mode else "sentinel" if self.config.sentinel_mode else "standalone"
            }


# Global Redis connection manager instance
_redis_manager: Optional[RedisConnectionManager] = None

async def get_redis_client() -> redis.Redis:
    """Get global Redis client instance."""
    global _redis_manager
    
    if _redis_manager is None:
        config = RedisConfig.from_env()
        _redis_manager = RedisConnectionManager(config)
    
    return await _redis_manager.get_client()

async def close_redis_connections():
    """Close global Redis connections."""
    global _redis_manager
    
    if _redis_manager:
        await _redis_manager.close()
        _redis_manager = None

async def redis_health_check() -> Dict[str, Any]:
    """Perform Redis health check."""
    global _redis_manager
    
    if _redis_manager is None:
        config = RedisConfig.from_env()
        _redis_manager = RedisConnectionManager(config)
    
    return await _redis_manager.health_check()