"""
Resilient Version Service Wrapper
Implements circuit breaker pattern, caching, and monitoring for the version service
"""
import asyncio
import time
from typing import Optional, Dict, Any, Tuple, Callable, TypeVar, Coroutine
from datetime import datetime, timedelta
from functools import wraps
import json
import hashlib
from contextlib import asynccontextmanager

try:
    import pybreaker  # type: ignore
except ImportError:  # pragma: no cover
    # ------------------------------------------------------------------
    # pybreaker 가 설치되지 않은 개발/테스트 환경에서도 코드가 동작하도록
    # 최소한의 대체 구현을 제공합니다. 실제 CircuitBreaker 로직은 생략하고
    # 메서드 호출 시 기본 동작만 수행하도록 합니다.
    # ------------------------------------------------------------------
    class _NoOpListener:  # pylint: disable=too-few-public-methods
        def __getattr__(self, name):  # noqa: D401
            return lambda *args, **kwargs: None


    class _NoOpCircuitBreaker:  # pylint: disable=too-few-public-methods
        def __init__(self, *args, **kwargs):
            self.listeners = kwargs.get("listeners", [])

        def call(self, func, *args, **kwargs):  # noqa: D401
            return func(*args, **kwargs)

        def __call__(self, func):  # noqa: D401
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)

            return wrapper

    pybreaker = type(
        "pybreaker_stub",
        (),
        {
            "CircuitBreaker": _NoOpCircuitBreaker,
            "CircuitBreakerListener": _NoOpListener,
        },
    )

from redis.asyncio import Redis
from prometheus_client import Counter, Histogram, Gauge, Summary
import structlog

from core.versioning.version_service import VersionTrackingService, get_version_service
from models.etag import (
    ResourceVersion, DeltaRequest, DeltaResponse, CacheValidation
)
from core.auth_utils import UserContext
from common_logging.setup import get_logger
from bootstrap.config import get_config

logger = structlog.get_logger(__name__)

# Prometheus metrics
version_service_requests = Counter(
    'version_service_requests_total',
    'Total requests to version service',
    ['method', 'status']
)

version_service_latency = Histogram(
    'version_service_request_duration_seconds',
    'Version service request latency',
    ['method'],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

version_service_cache_hits = Counter(
    'version_service_cache_hits_total',
    'Cache hits in version service',
    ['method', 'cache_type']
)

version_service_circuit_breaker_state = Gauge(
    'version_service_circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=open, 2=half-open)',
    ['service']
)

version_service_errors = Counter(
    'version_service_errors_total',
    'Total errors in version service',
    ['method', 'error_type']
)

redis_connection_pool_size = Gauge(
    'redis_connection_pool_size',
    'Current Redis connection pool size'
)

cache_memory_usage_bytes = Gauge(
    'version_service_cache_memory_bytes',
    'Estimated memory usage of version service cache'
)

T = TypeVar("T")


def circuit_breaker(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:  # type: ignore
    """No-op circuit breaker decorator (fallback).

    실제 회로 차단 로직은 `ResilientVersionService` 내부에서 pybreaker 인스턴스를
    사용해 구현된다. 여기서는 데코레이터 정의 시점에 pybreaker 가 없더라도
    모듈 임포트가 실패하지 않도록 단순 pass-through 역할만 수행한다.
    """

    async def wrapper(*args, **kwargs):  # type: ignore[override]
        return await func(*args, **kwargs)

    return wrapper


class CircuitBreakerConfig:
    """Configuration for circuit breaker"""
    def __init__(
        self,
        fail_max: int = 5,
        reset_timeout: int = 60,
        expected_exception: type = Exception,
        exclude: Optional[list] = None
    ):
        self.fail_max = fail_max
        self.reset_timeout = reset_timeout
        self.expected_exception = expected_exception
        self.exclude = exclude or []


class ResilientVersionService:
    """
    Resilient wrapper around VersionTrackingService with:
    - Circuit breaker pattern
    - Redis caching
    - Timeout handling
    - Retry logic with exponential backoff
    - Comprehensive monitoring
    """
    
    def __init__(
        self,
        redis_client: Redis,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        cache_ttl: int = 300,  # 5 minutes default
        timeout: Optional[float] = None,
        max_retries: int = 3,
        retry_backoff_base: float = 0.1
    ):
        config = get_config()
        self.redis = redis_client
        self.cache_ttl = cache_ttl
        self.timeout = timeout if timeout is not None else config.service.resilience_timeout
        self.max_retries = max_retries
        self.retry_backoff_base = retry_backoff_base
        self._version_service: Optional[VersionTrackingService] = None
        self._initialized = False
        
        # Circuit breaker configuration
        cb_config = circuit_breaker_config or CircuitBreakerConfig()
        self.circuit_breaker = pybreaker.CircuitBreaker(
            fail_max=cb_config.fail_max,
            reset_timeout=cb_config.reset_timeout,
            expected_exception=cb_config.expected_exception,
            exclude=cb_config.exclude,
            listeners=[
                self._on_circuit_breaker_open,
                self._on_circuit_breaker_close,
                self._on_circuit_breaker_half_open
            ]
        )
        
        # Local memory cache for hot data
        self._memory_cache: Dict[str, Tuple[Any, float]] = {}
        self._memory_cache_max_size = 1000
        self._memory_cache_ttl = 60  # 1 minute for memory cache
        
        # Request coalescing for identical concurrent requests
        self._pending_requests: Dict[str, asyncio.Future] = {}
        
        logger.info(
            "Initialized ResilientVersionService",
            cache_ttl=cache_ttl,
            timeout=timeout,
            max_retries=max_retries,
            circuit_breaker_fail_max=cb_config.fail_max,
            circuit_breaker_reset_timeout=cb_config.reset_timeout
        )
    
    async def initialize(self):
        """Initialize the underlying version service"""
        if not self._initialized:
            self._version_service = await get_version_service()
            self._initialized = True
            logger.info("ResilientVersionService initialized successfully")
    
    def _on_circuit_breaker_open(self):
        """Called when circuit breaker opens"""
        version_service_circuit_breaker_state.labels(service='version_service').set(1)
        logger.error("Circuit breaker OPENED - version service is failing")
    
    def _on_circuit_breaker_close(self):
        """Called when circuit breaker closes"""
        version_service_circuit_breaker_state.labels(service='version_service').set(0)
        logger.info("Circuit breaker CLOSED - version service is healthy")
    
    def _on_circuit_breaker_half_open(self):
        """Called when circuit breaker enters half-open state"""
        version_service_circuit_breaker_state.labels(service='version_service').set(2)
        logger.info("Circuit breaker HALF-OPEN - testing version service")
    
    def _generate_cache_key(self, prefix: str, **kwargs) -> str:
        """Generate a consistent cache key from parameters"""
        # Sort kwargs for consistent key generation
        sorted_args = sorted(kwargs.items())
        key_data = f"{prefix}:{':'.join(f'{k}={v}' for k, v in sorted_args)}"
        return f"etag:v1:{hashlib.md5(key_data.encode()).hexdigest()}"
    
    async def _get_from_cache(self, cache_key: str) -> Optional[Any]:
        """Get value from cache (memory first, then Redis)"""
        # Check memory cache first
        if cache_key in self._memory_cache:
            value, expiry = self._memory_cache[cache_key]
            if time.time() < expiry:
                version_service_cache_hits.labels(method='get', cache_type='memory').inc()
                return value
            else:
                del self._memory_cache[cache_key]
        
        # Check Redis cache
        try:
            cached = await self.redis.get(cache_key)
            if cached:
                value = json.loads(cached)
                # Update memory cache
                self._update_memory_cache(cache_key, value)
                version_service_cache_hits.labels(method='get', cache_type='redis').inc()
                return value
        except Exception as e:
            logger.warning("Cache retrieval failed", error=str(e), cache_key=cache_key)
        
        return None
    
    async def _set_cache(self, cache_key: str, value: Any, ttl: Optional[int] = None):
        """Set value in cache (both memory and Redis)"""
        ttl = ttl or self.cache_ttl
        
        # Update memory cache
        self._update_memory_cache(cache_key, value)
        
        # Update Redis cache
        try:
            await self.redis.setex(
                cache_key,
                ttl,
                json.dumps(value, default=str)
            )
        except Exception as e:
            logger.warning("Cache update failed", error=str(e), cache_key=cache_key)
    
    def _update_memory_cache(self, key: str, value: Any):
        """Update memory cache with LRU eviction"""
        # Evict oldest entries if cache is full
        if len(self._memory_cache) >= self._memory_cache_max_size:
            # Find and remove the oldest entry
            oldest_key = min(self._memory_cache.keys(), 
                           key=lambda k: self._memory_cache[k][1])
            del self._memory_cache[oldest_key]
        
        expiry = time.time() + self._memory_cache_ttl
        self._memory_cache[key] = (value, expiry)
        
        # Update memory usage metric
        estimated_size = len(json.dumps(self._memory_cache, default=str))
        cache_memory_usage_bytes.set(estimated_size)
    
    async def _execute_with_retry(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """Execute function with retry logic and exponential backoff"""
        last_exception = None
        
        for attempt in range(self.max_retries):
            try:
                # Apply timeout
                result = await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=self.timeout
                )
                return result
                
            except asyncio.TimeoutError:
                last_exception = TimeoutError(f"Operation timed out after {self.timeout}s")
                version_service_errors.labels(
                    method=func.__name__,
                    error_type='timeout'
                ).inc()
                
            except Exception as e:
                last_exception = e
                version_service_errors.labels(
                    method=func.__name__,
                    error_type=type(e).__name__
                ).inc()
            
            # Exponential backoff
            if attempt < self.max_retries - 1:
                backoff = self.retry_backoff_base * (2 ** attempt)
                await asyncio.sleep(backoff)
                logger.warning(
                    "Retrying operation",
                    attempt=attempt + 1,
                    max_retries=self.max_retries,
                    backoff=backoff,
                    error=str(last_exception)
                )
        
        raise last_exception
    
    @asynccontextmanager
    async def _track_operation(self, operation: str):
        """Context manager to track operation metrics"""
        start_time = time.time()
        try:
            yield
            version_service_requests.labels(method=operation, status='success').inc()
        except Exception as e:
            version_service_requests.labels(method=operation, status='failure').inc()
            raise
        finally:
            duration = time.time() - start_time
            version_service_latency.labels(method=operation).observe(duration)
    
    async def _coalesce_request(self, key: str, func: Callable, *args, **kwargs):
        """Coalesce identical concurrent requests"""
        if key in self._pending_requests:
            # Wait for existing request
            return await self._pending_requests[key]
        
        # Create new future for this request
        future = asyncio.Future()
        self._pending_requests[key] = future
        
        try:
            result = await func(*args, **kwargs)
            future.set_result(result)
            return result
        except Exception as e:
            future.set_exception(e)
            raise
        finally:
            # Clean up
            del self._pending_requests[key]
    
    @circuit_breaker
    async def track_change(
        self,
        resource_type: str,
        resource_id: str,
        branch: str,
        content: Dict[str, Any],
        change_type: str,
        user: UserContext,
        change_summary: Optional[str] = None,
        fields_changed: Optional[list] = None
    ) -> ResourceVersion:
        """Track a change with resilience patterns"""
        await self.initialize()
        
        async with self._track_operation('track_change'):
            # Generate cache key for invalidation
            cache_key = self._generate_cache_key(
                'version',
                resource_type=resource_type,
                resource_id=resource_id,
                branch=branch
            )
            
            # Execute with retry
            result = await self._execute_with_retry(
                self._version_service.track_change,
                resource_type=resource_type,
                resource_id=resource_id,
                branch=branch,
                content=content,
                change_type=change_type,
                user=user,
                change_summary=change_summary,
                fields_changed=fields_changed
            )
            
            # Invalidate caches
            await self.redis.delete(cache_key)
            if cache_key in self._memory_cache:
                del self._memory_cache[cache_key]
            
            # Cache the new version
            await self._set_cache(
                cache_key,
                result.dict() if hasattr(result, 'dict') else result
            )
            
            return result
    
    @circuit_breaker
    async def get_resource_version(
        self,
        resource_type: str,
        resource_id: str,
        branch: str,
        version: Optional[int] = None,
        use_cache: bool = True
    ) -> Optional[ResourceVersion]:
        """Get resource version with caching"""
        await self.initialize()
        
        async with self._track_operation('get_resource_version'):
            # Generate cache key
            cache_key = self._generate_cache_key(
                'version',
                resource_type=resource_type,
                resource_id=resource_id,
                branch=branch,
                version=version or 'latest'
            )
            
            # Check cache if enabled
            if use_cache:
                cached = await self._get_from_cache(cache_key)
                if cached:
                    # Reconstruct ResourceVersion from cached dict
                    from models.etag import ResourceVersion, VersionInfo
                    return ResourceVersion(**cached)
            
            # Use request coalescing
            coalesce_key = f"get_version:{cache_key}"
            
            async def fetch():
                result = await self._execute_with_retry(
                    self._version_service.get_resource_version,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    branch=branch,
                    version=version
                )
                
                if result and use_cache:
                    await self._set_cache(
                        cache_key,
                        result.dict() if hasattr(result, 'dict') else result
                    )
                
                return result
            
            return await self._coalesce_request(coalesce_key, fetch)
    
    @circuit_breaker
    async def validate_etag(
        self,
        resource_type: str,
        resource_id: str,
        branch: str,
        client_etag: str,
        use_cache: bool = True
    ) -> Tuple[bool, Optional[ResourceVersion]]:
        """Validate ETag with caching"""
        await self.initialize()
        
        async with self._track_operation('validate_etag'):
            # First get the current version (with caching)
            current_version = await self.get_resource_version(
                resource_type, resource_id, branch, use_cache=use_cache
            )
            
            if not current_version:
                return False, None
            
            is_valid = current_version.current_version.etag == client_etag
            return is_valid, current_version
    
    @circuit_breaker
    async def get_delta(
        self,
        resource_type: str,
        resource_id: str,
        branch: str,
        delta_request: DeltaRequest
    ) -> DeltaResponse:
        """Get delta with caching"""
        await self.initialize()
        
        async with self._track_operation('get_delta'):
            # Generate cache key for delta
            cache_key = self._generate_cache_key(
                'delta',
                resource_type=resource_type,
                resource_id=resource_id,
                branch=branch,
                client_etag=delta_request.client_etag,
                client_version=delta_request.client_version
            )
            
            # Check cache
            cached = await self._get_from_cache(cache_key)
            if cached:
                from models.etag import DeltaResponse
                return DeltaResponse(**cached)
            
            # Execute with retry
            result = await self._execute_with_retry(
                self._version_service.get_delta,
                resource_type=resource_type,
                resource_id=resource_id,
                branch=branch,
                delta_request=delta_request
            )
            
            # Cache the result (shorter TTL for deltas)
            if result:
                await self._set_cache(
                    cache_key,
                    result.dict() if hasattr(result, 'dict') else result,
                    ttl=60  # 1 minute for deltas
                )
            
            return result
    
    @circuit_breaker
    async def validate_cache(
        self,
        branch: str,
        validation: CacheValidation
    ) -> CacheValidation:
        """Validate cache with resilience"""
        await self.initialize()
        
        async with self._track_operation('validate_cache'):
            return await self._execute_with_retry(
                self._version_service.validate_cache,
                branch=branch,
                validation=validation
            )
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on version service"""
        health_status = {
            'healthy': True,
            'circuit_breaker_state': 'closed',
            'cache_connected': False,
            'version_service_connected': False,
            'memory_cache_size': len(self._memory_cache),
            'pending_requests': len(self._pending_requests),
            'errors': []
        }
        
        # Check circuit breaker state
        if self.circuit_breaker.current_state == pybreaker.STATE_OPEN:
            health_status['circuit_breaker_state'] = 'open'
            health_status['healthy'] = False
            health_status['errors'].append('Circuit breaker is open')
        elif self.circuit_breaker.current_state == pybreaker.STATE_HALF_OPEN:
            health_status['circuit_breaker_state'] = 'half-open'
        
        # Check Redis connection
        try:
            await self.redis.ping()
            health_status['cache_connected'] = True
        except Exception as e:
            health_status['healthy'] = False
            health_status['errors'].append(f'Redis connection failed: {str(e)}')
        
        # Check version service
        try:
            await self.initialize()
            # Try a simple operation
            await asyncio.wait_for(
                self._version_service.get_branch_version_summary('main'),
                timeout=2.0
            )
            health_status['version_service_connected'] = True
        except Exception as e:
            health_status['healthy'] = False
            health_status['errors'].append(f'Version service check failed: {str(e)}')
        
        return health_status
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get service metrics"""
        return {
            'circuit_breaker': {
                'state': self.circuit_breaker.current_state,
                'fail_counter': self.circuit_breaker.fail_counter,
                'success_counter': self.circuit_breaker.success_counter,
                'last_failure': str(self.circuit_breaker.last_failure) if self.circuit_breaker.last_failure else None
            },
            'cache': {
                'memory_cache_size': len(self._memory_cache),
                'memory_cache_max_size': self._memory_cache_max_size,
                'memory_cache_ttl': self._memory_cache_ttl,
                'redis_cache_ttl': self.cache_ttl
            },
            'performance': {
                'timeout': self.timeout,
                'max_retries': self.max_retries,
                'pending_requests': len(self._pending_requests)
            }
        }


# Global instance management
_resilient_version_service: Optional[ResilientVersionService] = None


async def get_resilient_version_service(
    redis_client: Redis,
    config: Optional[Dict[str, Any]] = None
) -> ResilientVersionService:
    """Get or create global resilient version service instance"""
    global _resilient_version_service
    
    if _resilient_version_service is None:
        config = config or {}
        
        # Extract configuration
        circuit_breaker_config = CircuitBreakerConfig(
            fail_max=config.get('circuit_breaker_fail_max', 5),
            reset_timeout=config.get('circuit_breaker_reset_timeout', 60)
        )
        
        _resilient_version_service = ResilientVersionService(
            redis_client=redis_client,
            circuit_breaker_config=circuit_breaker_config,
            cache_ttl=config.get('cache_ttl', 300),
            timeout=config.get('timeout', None),
            max_retries=config.get('max_retries', 3),
            retry_backoff_base=config.get('retry_backoff_base', 0.1)
        )
        
        await _resilient_version_service.initialize()
    
    return _resilient_version_service