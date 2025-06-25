"""
Enterprise-grade distributed rate limiting with multiple algorithms.

Supports:
- Sliding window algorithm
- Token bucket algorithm
- Leaky bucket algorithm
- Distributed rate limiting with Redis
- Per-user, per-IP, and per-endpoint limits
- Adaptive rate limiting based on system load
"""

import asyncio
import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, Callable
import redis.asyncio as redis
from contextvars import ContextVar
import json
import hashlib
from functools import wraps
import logging

logger = logging.getLogger(__name__)

# Context variable for request metadata
request_context: ContextVar[Dict[str, Any]] = ContextVar('request_context', default={})


class RateLimitAlgorithm(Enum):
    """Rate limiting algorithms."""
    SLIDING_WINDOW = "sliding_window"
    TOKEN_BUCKET = "token_bucket"
    LEAKY_BUCKET = "leaky_bucket"
    ADAPTIVE = "adaptive"


class RateLimitScope(Enum):
    """Rate limit scopes."""
    GLOBAL = "global"
    USER = "user"
    IP = "ip"
    ENDPOINT = "endpoint"
    COMBINED = "combined"


@dataclass
class RateLimitConfig:
    """Rate limit configuration."""
    algorithm: RateLimitAlgorithm
    scope: RateLimitScope
    limit: int
    window_seconds: int
    burst_size: Optional[int] = None
    leak_rate: Optional[float] = None
    adaptive_threshold: Optional[float] = None
    redis_ttl: int = 3600
    
    def __post_init__(self):
        if self.algorithm == RateLimitAlgorithm.TOKEN_BUCKET and not self.burst_size:
            self.burst_size = self.limit * 2
        if self.algorithm == RateLimitAlgorithm.LEAKY_BUCKET and not self.leak_rate:
            self.leak_rate = self.limit / self.window_seconds


@dataclass
class RateLimitResult:
    """Rate limit check result."""
    allowed: bool
    remaining: int
    reset_at: datetime
    retry_after: Optional[int] = None
    headers: Dict[str, str] = field(default_factory=dict)
    
    def __post_init__(self):
        self.headers = {
            "X-RateLimit-Limit": str(self.remaining + (1 if self.allowed else 0)),
            "X-RateLimit-Remaining": str(self.remaining),
            "X-RateLimit-Reset": str(int(self.reset_at.timestamp())),
        }
        if self.retry_after:
            self.headers["Retry-After"] = str(self.retry_after)


class RateLimitStrategy(ABC):
    """Base rate limit strategy."""
    
    @abstractmethod
    async def check_limit(
        self, 
        key: str, 
        config: RateLimitConfig,
        redis_client: Optional[redis.Redis] = None
    ) -> RateLimitResult:
        """Check if request is within rate limit."""
        pass
    
    @abstractmethod
    async def reset(self, key: str, redis_client: Optional[redis.Redis] = None):
        """Reset rate limit for key."""
        pass


class SlidingWindowStrategy(RateLimitStrategy):
    """Sliding window rate limiting strategy."""
    
    def __init__(self):
        self.local_storage: Dict[str, deque] = defaultdict(deque)
    
    async def check_limit(
        self, 
        key: str, 
        config: RateLimitConfig,
        redis_client: Optional[redis.Redis] = None
    ) -> RateLimitResult:
        """Check rate limit using sliding window algorithm."""
        current_time = time.time()
        window_start = current_time - config.window_seconds
        
        if redis_client:
            return await self._check_distributed(key, config, redis_client, current_time, window_start)
        else:
            return await self._check_local(key, config, current_time, window_start)
    
    async def _check_local(
        self, 
        key: str, 
        config: RateLimitConfig,
        current_time: float,
        window_start: float
    ) -> RateLimitResult:
        """Check rate limit using local storage."""
        # Clean old entries
        requests = self.local_storage[key]
        while requests and requests[0] < window_start:
            requests.popleft()
        
        # Check limit
        if len(requests) >= config.limit:
            oldest_request = requests[0] if requests else current_time
            reset_at = datetime.fromtimestamp(oldest_request + config.window_seconds)
            retry_after = int(reset_at.timestamp() - current_time)
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=reset_at,
                retry_after=retry_after
            )
        
        # Add request
        requests.append(current_time)
        reset_at = datetime.fromtimestamp(current_time + config.window_seconds)
        return RateLimitResult(
            allowed=True,
            remaining=config.limit - len(requests),
            reset_at=reset_at
        )
    
    async def _check_distributed(
        self, 
        key: str, 
        config: RateLimitConfig,
        redis_client: redis.Redis,
        current_time: float,
        window_start: float
    ) -> RateLimitResult:
        """Check rate limit using Redis."""
        redis_key = f"rate_limit:sliding:{key}"
        
        # Lua script for atomic sliding window check
        lua_script = """
        local key = KEYS[1]
        local window_start = tonumber(ARGV[1])
        local current_time = tonumber(ARGV[2])
        local limit = tonumber(ARGV[3])
        local window_seconds = tonumber(ARGV[4])
        local ttl = tonumber(ARGV[5])
        
        -- Remove old entries
        redis.call('ZREMRANGEBYSCORE', key, 0, window_start)
        
        -- Count current requests
        local count = redis.call('ZCARD', key)
        
        if count >= limit then
            -- Get oldest request time
            local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
            if #oldest > 0 then
                return {0, count, oldest[2]}
            else
                return {0, count, current_time}
            end
        else
            -- Add new request
            redis.call('ZADD', key, current_time, current_time)
            redis.call('EXPIRE', key, ttl)
            return {1, limit - count - 1, current_time + window_seconds}
        end
        """
        
        result = await redis_client.eval(
            lua_script,
            1,
            redis_key,
            str(window_start),
            str(current_time),
            str(config.limit),
            str(config.window_seconds),
            str(config.redis_ttl)
        )
        
        allowed, remaining, reset_timestamp = result
        reset_at = datetime.fromtimestamp(float(reset_timestamp))
        retry_after = None
        
        if not allowed:
            retry_after = int(float(reset_timestamp) + config.window_seconds - current_time)
        
        return RateLimitResult(
            allowed=bool(allowed),
            remaining=int(remaining),
            reset_at=reset_at,
            retry_after=retry_after
        )
    
    async def reset(self, key: str, redis_client: Optional[redis.Redis] = None):
        """Reset rate limit for key."""
        if redis_client:
            redis_key = f"rate_limit:sliding:{key}"
            await redis_client.delete(redis_key)
        else:
            self.local_storage.pop(key, None)


class TokenBucketStrategy(RateLimitStrategy):
    """Token bucket rate limiting strategy."""
    
    def __init__(self):
        self.local_buckets: Dict[str, Tuple[float, float, float]] = {}
    
    async def check_limit(
        self, 
        key: str, 
        config: RateLimitConfig,
        redis_client: Optional[redis.Redis] = None
    ) -> RateLimitResult:
        """Check rate limit using token bucket algorithm."""
        current_time = time.time()
        refill_rate = config.limit / config.window_seconds
        bucket_size = config.burst_size or config.limit
        
        if redis_client:
            return await self._check_distributed(key, config, redis_client, current_time, refill_rate, bucket_size)
        else:
            return await self._check_local(key, config, current_time, refill_rate, bucket_size)
    
    async def _check_local(
        self, 
        key: str, 
        config: RateLimitConfig,
        current_time: float,
        refill_rate: float,
        bucket_size: float
    ) -> RateLimitResult:
        """Check rate limit using local storage."""
        if key not in self.local_buckets:
            self.local_buckets[key] = (bucket_size, current_time, bucket_size)
        
        tokens, last_refill, capacity = self.local_buckets[key]
        
        # Refill tokens
        time_passed = current_time - last_refill
        tokens = min(capacity, tokens + time_passed * refill_rate)
        
        if tokens >= 1:
            # Consume token
            tokens -= 1
            self.local_buckets[key] = (tokens, current_time, capacity)
            
            # Calculate reset time
            tokens_needed = capacity - tokens
            reset_seconds = tokens_needed / refill_rate
            reset_at = datetime.fromtimestamp(current_time + reset_seconds)
            
            return RateLimitResult(
                allowed=True,
                remaining=int(tokens),
                reset_at=reset_at
            )
        else:
            # Calculate retry after
            retry_after = int((1 - tokens) / refill_rate)
            reset_at = datetime.fromtimestamp(current_time + retry_after)
            
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=reset_at,
                retry_after=retry_after
            )
    
    async def _check_distributed(
        self, 
        key: str, 
        config: RateLimitConfig,
        redis_client: redis.Redis,
        current_time: float,
        refill_rate: float,
        bucket_size: float
    ) -> RateLimitResult:
        """Check rate limit using Redis."""
        redis_key = f"rate_limit:token:{key}"
        
        # Lua script for atomic token bucket check
        lua_script = """
        local key = KEYS[1]
        local current_time = tonumber(ARGV[1])
        local refill_rate = tonumber(ARGV[2])
        local bucket_size = tonumber(ARGV[3])
        local ttl = tonumber(ARGV[4])
        
        -- Get current state
        local state = redis.call('HMGET', key, 'tokens', 'last_refill')
        local tokens = tonumber(state[1]) or bucket_size
        local last_refill = tonumber(state[2]) or current_time
        
        -- Refill tokens
        local time_passed = current_time - last_refill
        tokens = math.min(bucket_size, tokens + time_passed * refill_rate)
        
        if tokens >= 1 then
            -- Consume token
            tokens = tokens - 1
            redis.call('HMSET', key, 'tokens', tokens, 'last_refill', current_time)
            redis.call('EXPIRE', key, ttl)
            
            -- Calculate reset time
            local tokens_needed = bucket_size - tokens
            local reset_seconds = tokens_needed / refill_rate
            
            return {1, math.floor(tokens), current_time + reset_seconds}
        else
            -- Update last refill time
            redis.call('HMSET', key, 'tokens', tokens, 'last_refill', current_time)
            redis.call('EXPIRE', key, ttl)
            
            -- Calculate retry after
            local retry_after = (1 - tokens) / refill_rate
            
            return {0, 0, current_time + retry_after, retry_after}
        end
        """
        
        result = await redis_client.eval(
            lua_script,
            1,
            redis_key,
            str(current_time),
            str(refill_rate),
            str(bucket_size),
            str(config.redis_ttl)
        )
        
        allowed, remaining, reset_timestamp = result[:3]
        retry_after = int(result[3]) if len(result) > 3 else None
        
        reset_at = datetime.fromtimestamp(float(reset_timestamp))
        
        return RateLimitResult(
            allowed=bool(allowed),
            remaining=int(remaining),
            reset_at=reset_at,
            retry_after=retry_after
        )
    
    async def reset(self, key: str, redis_client: Optional[redis.Redis] = None):
        """Reset rate limit for key."""
        if redis_client:
            redis_key = f"rate_limit:token:{key}"
            await redis_client.delete(redis_key)
        else:
            self.local_buckets.pop(key, None)


class LeakyBucketStrategy(RateLimitStrategy):
    """Leaky bucket rate limiting strategy."""
    
    def __init__(self):
        self.local_buckets: Dict[str, Tuple[float, float]] = {}
        self.leak_tasks: Dict[str, asyncio.Task] = {}
    
    async def check_limit(
        self, 
        key: str, 
        config: RateLimitConfig,
        redis_client: Optional[redis.Redis] = None
    ) -> RateLimitResult:
        """Check rate limit using leaky bucket algorithm."""
        current_time = time.time()
        leak_rate = config.leak_rate or (config.limit / config.window_seconds)
        bucket_size = config.limit
        
        if redis_client:
            return await self._check_distributed(key, config, redis_client, current_time, leak_rate, bucket_size)
        else:
            return await self._check_local(key, config, current_time, leak_rate, bucket_size)
    
    async def _check_local(
        self, 
        key: str, 
        config: RateLimitConfig,
        current_time: float,
        leak_rate: float,
        bucket_size: float
    ) -> RateLimitResult:
        """Check rate limit using local storage."""
        if key not in self.local_buckets:
            self.local_buckets[key] = (0.0, current_time)
        
        water_level, last_leak = self.local_buckets[key]
        
        # Leak water
        time_passed = current_time - last_leak
        water_level = max(0, water_level - time_passed * leak_rate)
        
        if water_level < bucket_size:
            # Add water (request)
            water_level += 1
            self.local_buckets[key] = (water_level, current_time)
            
            # Start leak task if not running
            if key not in self.leak_tasks or self.leak_tasks[key].done():
                self.leak_tasks[key] = asyncio.create_task(self._leak_bucket(key, leak_rate))
            
            # Calculate reset time
            reset_seconds = water_level / leak_rate
            reset_at = datetime.fromtimestamp(current_time + reset_seconds)
            
            return RateLimitResult(
                allowed=True,
                remaining=int(bucket_size - water_level),
                reset_at=reset_at
            )
        else:
            # Bucket full
            retry_after = int((water_level - bucket_size + 1) / leak_rate)
            reset_at = datetime.fromtimestamp(current_time + water_level / leak_rate)
            
            return RateLimitResult(
                allowed=False,
                remaining=0,
                reset_at=reset_at,
                retry_after=retry_after
            )
    
    async def _leak_bucket(self, key: str, leak_rate: float):
        """Background task to leak bucket."""
        while key in self.local_buckets:
            await asyncio.sleep(1 / leak_rate)
            if key in self.local_buckets:
                water_level, _ = self.local_buckets[key]
                water_level = max(0, water_level - 1)
                if water_level > 0:
                    self.local_buckets[key] = (water_level, time.time())
                else:
                    self.local_buckets.pop(key, None)
                    break
    
    async def _check_distributed(
        self, 
        key: str, 
        config: RateLimitConfig,
        redis_client: redis.Redis,
        current_time: float,
        leak_rate: float,
        bucket_size: float
    ) -> RateLimitResult:
        """Check rate limit using Redis."""
        redis_key = f"rate_limit:leaky:{key}"
        
        # Lua script for atomic leaky bucket check
        lua_script = """
        local key = KEYS[1]
        local current_time = tonumber(ARGV[1])
        local leak_rate = tonumber(ARGV[2])
        local bucket_size = tonumber(ARGV[3])
        local ttl = tonumber(ARGV[4])
        
        -- Get current state
        local state = redis.call('HMGET', key, 'water_level', 'last_leak')
        local water_level = tonumber(state[1]) or 0
        local last_leak = tonumber(state[2]) or current_time
        
        -- Leak water
        local time_passed = current_time - last_leak
        water_level = math.max(0, water_level - time_passed * leak_rate)
        
        if water_level < bucket_size then
            -- Add water (request)
            water_level = water_level + 1
            redis.call('HMSET', key, 'water_level', water_level, 'last_leak', current_time)
            redis.call('EXPIRE', key, ttl)
            
            -- Calculate reset time
            local reset_seconds = water_level / leak_rate
            
            return {1, math.floor(bucket_size - water_level), current_time + reset_seconds}
        else
            -- Update last leak time
            redis.call('HMSET', key, 'water_level', water_level, 'last_leak', current_time)
            redis.call('EXPIRE', key, ttl)
            
            -- Calculate retry after
            local retry_after = (water_level - bucket_size + 1) / leak_rate
            
            return {0, 0, current_time + water_level / leak_rate, retry_after}
        end
        """
        
        result = await redis_client.eval(
            lua_script,
            1,
            redis_key,
            str(current_time),
            str(leak_rate),
            str(bucket_size),
            str(config.redis_ttl)
        )
        
        allowed, remaining, reset_timestamp = result[:3]
        retry_after = int(result[3]) if len(result) > 3 else None
        
        reset_at = datetime.fromtimestamp(float(reset_timestamp))
        
        return RateLimitResult(
            allowed=bool(allowed),
            remaining=int(remaining),
            reset_at=reset_at,
            retry_after=retry_after
        )
    
    async def reset(self, key: str, redis_client: Optional[redis.Redis] = None):
        """Reset rate limit for key."""
        if redis_client:
            redis_key = f"rate_limit:leaky:{key}"
            await redis_client.delete(redis_key)
        else:
            self.local_buckets.pop(key, None)
            if key in self.leak_tasks:
                self.leak_tasks[key].cancel()
                self.leak_tasks.pop(key, None)


class AdaptiveRateLimiter:
    """Adaptive rate limiter that adjusts limits based on system load."""
    
    def __init__(self, base_config: RateLimitConfig, metrics_callback: Optional[Callable] = None):
        self.base_config = base_config
        self.metrics_callback = metrics_callback
        self.adjustment_history: deque = deque(maxlen=100)
        self.last_adjustment = time.time()
        self.current_multiplier = 1.0
    
    async def get_adjusted_config(self) -> RateLimitConfig:
        """Get rate limit config adjusted for current system load."""
        if not self.metrics_callback:
            return self.base_config
        
        # Get system metrics
        metrics = await self.metrics_callback()
        
        # Calculate adjustment based on metrics
        cpu_load = metrics.get('cpu_percent', 0) / 100
        memory_load = metrics.get('memory_percent', 0) / 100
        error_rate = metrics.get('error_rate', 0)
        response_time = metrics.get('avg_response_time', 0)
        
        # Composite load score (0-1)
        load_score = (
            cpu_load * 0.3 +
            memory_load * 0.2 +
            min(error_rate, 1.0) * 0.3 +
            min(response_time / 1000, 1.0) * 0.2  # Normalize to seconds
        )
        
        # Calculate multiplier
        threshold = self.base_config.adaptive_threshold or 0.7
        if load_score > threshold:
            # Reduce limits under high load
            self.current_multiplier = max(0.1, 1.0 - (load_score - threshold) / (1 - threshold))
        else:
            # Gradually restore limits
            self.current_multiplier = min(1.0, self.current_multiplier + 0.01)
        
        # Record adjustment
        self.adjustment_history.append({
            'timestamp': time.time(),
            'load_score': load_score,
            'multiplier': self.current_multiplier,
            'metrics': metrics
        })
        
        # Create adjusted config
        adjusted_config = RateLimitConfig(
            algorithm=self.base_config.algorithm,
            scope=self.base_config.scope,
            limit=int(self.base_config.limit * self.current_multiplier),
            window_seconds=self.base_config.window_seconds,
            burst_size=int((self.base_config.burst_size or 0) * self.current_multiplier) if self.base_config.burst_size else None,
            leak_rate=(self.base_config.leak_rate or 0) * self.current_multiplier if self.base_config.leak_rate else None,
            redis_ttl=self.base_config.redis_ttl
        )
        
        return adjusted_config


class RateLimiter:
    """Main rate limiter class with support for multiple algorithms and scopes."""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis_client = redis_client
        self.strategies = {
            RateLimitAlgorithm.SLIDING_WINDOW: SlidingWindowStrategy(),
            RateLimitAlgorithm.TOKEN_BUCKET: TokenBucketStrategy(),
            RateLimitAlgorithm.LEAKY_BUCKET: LeakyBucketStrategy(),
        }
        self.configs: Dict[str, RateLimitConfig] = {}
        self.adaptive_limiters: Dict[str, AdaptiveRateLimiter] = {}
        self._monitoring_enabled = True
    
    def configure(
        self,
        name: str,
        config: RateLimitConfig,
        metrics_callback: Optional[Callable] = None
    ):
        """Configure a rate limit."""
        self.configs[name] = config
        
        if config.algorithm == RateLimitAlgorithm.ADAPTIVE:
            self.adaptive_limiters[name] = AdaptiveRateLimiter(config, metrics_callback)
    
    async def check_limit(
        self,
        name: str,
        scope_values: Optional[Dict[str, str]] = None
    ) -> RateLimitResult:
        """Check if request is within rate limit."""
        if name not in self.configs:
            raise ValueError(f"Rate limit '{name}' not configured")
        
        config = self.configs[name]
        
        # Handle adaptive rate limiting
        if config.algorithm == RateLimitAlgorithm.ADAPTIVE:
            if name in self.adaptive_limiters:
                config = await self.adaptive_limiters[name].get_adjusted_config()
                # Use sliding window as the underlying algorithm
                strategy = self.strategies[RateLimitAlgorithm.SLIDING_WINDOW]
            else:
                raise ValueError(f"Adaptive limiter not configured for '{name}'")
        else:
            strategy = self.strategies[config.algorithm]
        
        # Generate key based on scope
        key = self._generate_key(name, config.scope, scope_values)
        
        # Check limit
        result = await strategy.check_limit(key, config, self.redis_client)
        
        # Monitor
        if self._monitoring_enabled:
            await self._monitor_check(name, config, result)
        
        return result
    
    async def check_multiple(
        self,
        names: List[str],
        scope_values: Optional[Dict[str, str]] = None
    ) -> Dict[str, RateLimitResult]:
        """Check multiple rate limits."""
        tasks = []
        for name in names:
            tasks.append(self.check_limit(name, scope_values))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            name: result if not isinstance(result, Exception) else None
            for name, result in zip(names, results)
        }
    
    async def reset(self, name: str, scope_values: Optional[Dict[str, str]] = None):
        """Reset rate limit."""
        if name not in self.configs:
            raise ValueError(f"Rate limit '{name}' not configured")
        
        config = self.configs[name]
        strategy = self.strategies[config.algorithm]
        key = self._generate_key(name, config.scope, scope_values)
        
        await strategy.reset(key, self.redis_client)
    
    async def get_usage_stats(self, name: str) -> Dict[str, Any]:
        """Get usage statistics for a rate limit."""
        if name not in self.configs:
            raise ValueError(f"Rate limit '{name}' not configured")
        
        # Get from monitoring data if available
        stats = {
            'name': name,
            'config': self.configs[name].__dict__,
            'current_multiplier': 1.0
        }
        
        if name in self.adaptive_limiters:
            limiter = self.adaptive_limiters[name]
            stats['current_multiplier'] = limiter.current_multiplier
            stats['adjustment_history'] = list(limiter.adjustment_history)
        
        return stats
    
    def _generate_key(
        self,
        name: str,
        scope: RateLimitScope,
        scope_values: Optional[Dict[str, str]] = None
    ) -> str:
        """Generate rate limit key based on scope."""
        scope_values = scope_values or {}
        ctx = request_context.get()
        
        parts = [name]
        
        if scope == RateLimitScope.GLOBAL:
            parts.append("global")
        elif scope == RateLimitScope.USER:
            user_id = scope_values.get('user_id') or ctx.get('user_id', 'anonymous')
            parts.append(f"user:{user_id}")
        elif scope == RateLimitScope.IP:
            ip = scope_values.get('ip') or ctx.get('ip', '0.0.0.0')
            parts.append(f"ip:{ip}")
        elif scope == RateLimitScope.ENDPOINT:
            endpoint = scope_values.get('endpoint') or ctx.get('endpoint', 'unknown')
            parts.append(f"endpoint:{endpoint}")
        elif scope == RateLimitScope.COMBINED:
            user_id = scope_values.get('user_id') or ctx.get('user_id', 'anonymous')
            endpoint = scope_values.get('endpoint') or ctx.get('endpoint', 'unknown')
            parts.extend([f"user:{user_id}", f"endpoint:{endpoint}"])
        
        return ":".join(parts)
    
    async def _monitor_check(
        self,
        name: str,
        config: RateLimitConfig,
        result: RateLimitResult
    ):
        """Monitor rate limit checks."""
        # Log rate limit checks
        logger.info(
            "Rate limit check",
            extra={
                'rate_limit_name': name,
                'algorithm': config.algorithm.value,
                'scope': config.scope.value,
                'allowed': result.allowed,
                'remaining': result.remaining,
                'reset_at': result.reset_at.isoformat()
            }
        )
        
        # Emit metrics if configured
        if hasattr(self, 'metrics_client'):
            await self.metrics_client.increment(
                'rate_limit.check',
                tags={
                    'name': name,
                    'algorithm': config.algorithm.value,
                    'allowed': str(result.allowed).lower()
                }
            )


def rate_limit(
    name: str,
    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.SLIDING_WINDOW,
    scope: RateLimitScope = RateLimitScope.USER,
    limit: int = 100,
    window_seconds: int = 60,
    **kwargs
) -> Callable:
    """Decorator for rate limiting functions."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **func_kwargs):
            # Get rate limiter from context or create default
            limiter = func_kwargs.pop('_rate_limiter', None) or RateLimiter()
            
            # Configure if not already configured
            if name not in limiter.configs:
                config = RateLimitConfig(
                    algorithm=algorithm,
                    scope=scope,
                    limit=limit,
                    window_seconds=window_seconds,
                    **kwargs
                )
                limiter.configure(name, config)
            
            # Check rate limit
            result = await limiter.check_limit(name)
            
            if not result.allowed:
                raise RateLimitExceeded(
                    f"Rate limit exceeded for {name}",
                    retry_after=result.retry_after,
                    headers=result.headers
                )
            
            # Add rate limit headers to response context
            ctx = request_context.get()
            ctx['rate_limit_headers'] = result.headers
            
            # Call function
            return await func(*args, **func_kwargs)
        
        return wrapper
    return decorator


class RateLimitExceeded(Exception):
    """Rate limit exceeded exception."""
    def __init__(self, message: str, retry_after: Optional[int] = None, headers: Optional[Dict[str, str]] = None):
        super().__init__(message)
        self.retry_after = retry_after
        self.headers = headers or {}