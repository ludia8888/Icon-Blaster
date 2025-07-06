"""Circuit Breaker Provider"""
from typing import Optional
import redis.asyncio as redis
from middleware.circuit_breaker import CircuitBreakerGroup, CircuitConfig
from bootstrap.providers.redis_provider import RedisProvider

class CircuitBreakerProvider:
    """Provides and manages the CircuitBreakerGroup."""

    def __init__(self, redis_provider: RedisProvider):
        self._redis_provider = redis_provider
        self._redis_client: Optional[redis.Redis] = None
        self._circuit_breaker_group: Optional[CircuitBreakerGroup] = None

    async def provide(self) -> CircuitBreakerGroup:
        """
        Provides a singleton instance of the CircuitBreakerGroup.
        Initializes the group on first call.
        """
        if self._circuit_breaker_group is None:
            self._redis_client = await self._redis_provider.provide()
            self._circuit_breaker_group = CircuitBreakerGroup(redis_client=self._redis_client)
            self._register_circuits()
        return self._circuit_breaker_group

    def _register_circuits(self):
        """
        Registers all necessary circuit breakers for external services.
        Configurations should be loaded from a config file or environment variables.
        """
        if not self._circuit_breaker_group:
            return

        # Example configuration for user-service
        user_service_config = CircuitConfig(
            name="user-service",
            failure_threshold=5,
            success_threshold=3,
            timeout_seconds=60,
            half_open_max_calls=3
        )
        self._circuit_breaker_group.add_breaker(user_service_config)

        # Add other circuit configurations here (e.g., for audit-service)
        # audit_service_config = CircuitConfig(name="audit-service", ...)
        # self._circuit_breaker_group.add_breaker(audit_service_config)


    async def shutdown(self):
        """Gracefully shuts down the provider."""
        # The circuit breaker group itself does not have a shutdown method.
        # Redis client shutdown is handled by the RedisProvider.
        pass 