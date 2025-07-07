"""
Rate limiting coordinator - Facade for rate limiting components
"""
import asyncio
from typing import Dict, Optional, Any, List
from datetime import datetime, timedelta
import logging

from .models import (
    RateLimitConfig, RateLimitResult, RateLimitScope,
    RateLimitAlgorithm, RateLimitKey, RateLimitMetrics
)
from .strategies.sliding_window import SlidingWindowStrategy
from .strategies.token_bucket import TokenBucketStrategy
from .strategies.leaky_bucket import LeakyBucketStrategy
from .adaptive import AdaptiveRateLimiter
from .limiter import RateLimiter
from ..common.redis_utils import RedisClient, RedisKeyPatterns
from ..common.metrics import MetricsCollector

logger = logging.getLogger(__name__)


class RateLimitCoordinator:
    """
    Facade for coordinating rate limiting components
    """
    
    def __init__(self, default_config: Optional[RateLimitConfig] = None):
        self.default_config = default_config or RateLimitConfig()
        
        # Components
        self.limiter = RateLimiter()
        self.adaptive = AdaptiveRateLimiter()
        self.metrics_collector = MetricsCollector("rate_limiting")
        
        # Strategy instances
        self._strategies: Dict[RateLimitAlgorithm, Any] = {}
        self._init_strategies()
        
        # Metrics tracking
        self._metrics: Dict[str, RateLimitMetrics] = {}
        
        # Configuration cache
        self._endpoint_configs: Dict[str, RateLimitConfig] = {}
    
    def _init_strategies(self):
        """Initialize rate limiting strategies"""
        self._strategies[RateLimitAlgorithm.SLIDING_WINDOW] = SlidingWindowStrategy(self.default_config)
        self._strategies[RateLimitAlgorithm.TOKEN_BUCKET] = TokenBucketStrategy(self.default_config)
        self._strategies[RateLimitAlgorithm.LEAKY_BUCKET] = LeakyBucketStrategy(self.default_config)
    
    def configure_endpoint(self, endpoint: str, config: RateLimitConfig):
        """Configure rate limiting for specific endpoint"""
        self._endpoint_configs[endpoint] = config
        # Reinitialize strategies for this config
        if config.algorithm not in self._strategies:
            if config.algorithm == RateLimitAlgorithm.SLIDING_WINDOW:
                self._strategies[config.algorithm] = SlidingWindowStrategy(config)
            elif config.algorithm == RateLimitAlgorithm.TOKEN_BUCKET:
                self._strategies[config.algorithm] = TokenBucketStrategy(config)
            elif config.algorithm == RateLimitAlgorithm.LEAKY_BUCKET:
                self._strategies[config.algorithm] = LeakyBucketStrategy(config)
    
    async def check_rate_limit(
        self,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        endpoint: Optional[str] = None,
        scope: Optional[RateLimitScope] = None
    ) -> Dict[str, Any]:
        """
        Check rate limit for request (called by middleware coordinator)
        """
        try:
            # Determine configuration
            config = self._get_config(endpoint)
            
            # Determine scope and key
            if scope is None:
                scope = config.scope
            
            key = self._create_key(scope, user_id, ip_address, endpoint)
            
            # Check with appropriate algorithm
            if config.adaptive_enabled:
                result = await self._check_adaptive(key, config)
            else:
                result = await self._check_standard(key, config)
            
            # Update metrics
            self._update_metrics(key, result)
            
            # Record in monitoring
            self.metrics_collector.increment_counter(
                "rate_limit_checks_total",
                labels={
                    "scope": scope.value,
                    "endpoint": endpoint or "global",
                    "allowed": str(result.allowed).lower()
                }
            )
            
            return {
                "allowed": result.allowed,
                "limit": result.limit,
                "remaining": result.remaining,
                "reset_at": result.reset_at.isoformat(),
                "retry_after": result.retry_after,
                "headers": result.headers
            }
            
        except Exception as e:
            logger.error(f"Rate limit check failed: {str(e)}")
            # Fail open - allow request on error
            return {
                "allowed": True,
                "error": str(e)
            }
    
    async def _check_standard(
        self,
        key: RateLimitKey,
        config: RateLimitConfig
    ) -> RateLimitResult:
        """Standard rate limit check"""
        strategy = self._strategies.get(config.algorithm)
        if not strategy:
            strategy = self._strategies[RateLimitAlgorithm.SLIDING_WINDOW]
        
        # Get state from Redis
        state = await self._get_state(key)
        
        # Check limit
        result, new_state = await strategy.check_limit(key, state)
        
        # Consume if checking only (not consuming)
        if result.allowed:
            success, final_state = await strategy.consume(key, 1, new_state)
            if success:
                await self._save_state(key, final_state)
            else:
                result.allowed = False
        
        return result
    
    async def _check_adaptive(
        self,
        key: RateLimitKey,
        config: RateLimitConfig
    ) -> RateLimitResult:
        """Adaptive rate limit check"""
        # Get current system load
        load_factor = await self._get_system_load()
        
        # Adjust limits based on load
        adjusted_config = self.adaptive.adjust_limits(config, load_factor)
        
        # Use adjusted config for check
        return await self._check_standard(key, adjusted_config)
    
    def _create_key(
        self,
        scope: RateLimitScope,
        user_id: Optional[str],
        ip_address: Optional[str],
        endpoint: Optional[str]
    ) -> RateLimitKey:
        """Create rate limit key"""
        if scope == RateLimitScope.USER and user_id:
            return RateLimitKey(scope, user_id, endpoint)
        elif scope == RateLimitScope.IP and ip_address:
            return RateLimitKey(scope, ip_address, endpoint)
        elif scope == RateLimitScope.ENDPOINT and endpoint:
            return RateLimitKey(scope, endpoint)
        elif scope == RateLimitScope.COMBINED:
            identifier = f"{user_id or 'anonymous'}:{ip_address or 'unknown'}"
            return RateLimitKey(scope, identifier, endpoint)
        else:
            return RateLimitKey(RateLimitScope.GLOBAL, "global", endpoint)
    
    def _get_config(self, endpoint: Optional[str]) -> RateLimitConfig:
        """Get configuration for endpoint"""
        if endpoint and endpoint in self._endpoint_configs:
            return self._endpoint_configs[endpoint]
        return self.default_config
    
    async def _get_state(self, key: RateLimitKey) -> Optional[RateLimitState]:
        """Get rate limit state from Redis"""
        async with RedisClient() as client:
            redis_key = self._get_redis_key(key)
            data = await client.get_json(redis_key)
            
            if data:
                from .models import RateLimitState
                return RateLimitState.from_dict(data)
            
            return None
    
    async def _save_state(self, key: RateLimitKey, state: RateLimitState):
        """Save rate limit state to Redis"""
        async with RedisClient() as client:
            redis_key = self._get_redis_key(key)
            await client.set_json(
                redis_key,
                state.to_dict(),
                expire=timedelta(seconds=self.default_config.window_seconds * 2)
            )
    
    def _get_redis_key(self, key: RateLimitKey) -> str:
        """Get Redis key for rate limit"""
        if key.scope == RateLimitScope.USER:
            return RedisKeyPatterns.RATE_LIMIT_USER.format(
                user_id=key.identifier,
                endpoint=key.endpoint or "global"
            )
        elif key.scope == RateLimitScope.IP:
            return RedisKeyPatterns.RATE_LIMIT_IP.format(
                ip=key.identifier,
                endpoint=key.endpoint or "global"
            )
        else:
            return RedisKeyPatterns.RATE_LIMIT_GLOBAL.format(
                endpoint=key.endpoint or "global"
            )
    
    async def _get_system_load(self) -> float:
        """Get current system load factor"""
        try:
            # This would check actual system metrics
            # For now, return a simulated value
            import random
            return random.uniform(0.5, 1.5)
        except Exception:
            return 1.0
    
    def _update_metrics(self, key: RateLimitKey, result: RateLimitResult):
        """Update rate limit metrics"""
        metric_key = key.to_string()
        
        if metric_key not in self._metrics:
            self._metrics[metric_key] = RateLimitMetrics()
        
        metrics = self._metrics[metric_key]
        metrics.record_request(result.allowed)
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get rate limiting statistics"""
        total_metrics = RateLimitMetrics()
        
        for metrics in self._metrics.values():
            total_metrics.total_requests += metrics.total_requests
            total_metrics.allowed_requests += metrics.allowed_requests
            total_metrics.denied_requests += metrics.denied_requests
        
        total_metrics.unique_identifiers = len(self._metrics)
        
        return {
            "total_requests": total_metrics.total_requests,
            "allowed_requests": total_metrics.allowed_requests,
            "denied_requests": total_metrics.denied_requests,
            "denial_rate": total_metrics.denial_rate,
            "unique_identifiers": total_metrics.unique_identifiers,
            "endpoint_configs": len(self._endpoint_configs),
            "active_algorithms": list(self._strategies.keys())
        }
    
    async def reset_limits(self, identifier: Optional[str] = None):
        """Reset rate limits"""
        if identifier:
            # Reset specific identifier
            for scope in RateLimitScope:
                for endpoint in list(self._endpoint_configs.keys()) + [None]:
                    key = RateLimitKey(scope, identifier, endpoint)
                    await self._reset_key(key)
        else:
            # Reset all limits
            async with RedisClient() as client:
                await client.delete_keys("ratelimit:*")
            self._metrics.clear()
    
    async def _reset_key(self, key: RateLimitKey):
        """Reset specific rate limit key"""
        async with RedisClient() as client:
            redis_key = self._get_redis_key(key)
            await client.client.delete(redis_key)
        
        # Reset in strategies
        for strategy in self._strategies.values():
            await strategy.reset(key)