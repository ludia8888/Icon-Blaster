"""
Provider for the Redis client.
"""
import redis.asyncio as redis
from bootstrap.config import get_config
from .base import Provider
from common_logging.setup import get_logger

logger = get_logger(__name__)

class RedisProvider(Provider[redis.Redis]):
    """
    Provides a Redis client based on the application configuration.
    Connects to a single Redis instance.
    """
    def __init__(self):
        self._config = get_config().redis
        self._client: redis.Redis | None = None

    async def provide(self) -> redis.Redis:
        """Create and return a Redis client instance."""
        if self._client:
            return self._client

        # Construct the URL from config, including password if it exists
        redis_url = f"redis://{':'+self._config.password+'@' if self._config.password else ''}{self._config.host}:{self._config.port}/{self._config.db}"
        
        try:
            client = redis.from_url(
                redis_url,
                decode_responses=True,
                max_connections=self._config.max_connections,
                socket_timeout=self._config.socket_timeout
            )
            await client.ping()
            logger.info(f"Successfully connected to Redis at {self._config.host}:{self._config.port}")
            self._client = client
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
        
        return self._client

    async def shutdown(self) -> None:
        """Close the Redis client connection."""
        if self._client:
            await self._client.close()
            logger.info("Redis connection closed.") 