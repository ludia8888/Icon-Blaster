"""
Enterprise-grade DataLoader implementation for GraphQL
Prevents N+1 queries with batching and caching
"""
import asyncio
from collections import defaultdict
from typing import Dict, List, Optional, Any, TypeVar, Generic, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import redis.asyncio as redis
from aiodataloader import DataLoader

from utils.logger import get_logger

logger = get_logger(__name__)

T = TypeVar('T')
K = TypeVar('K')


@dataclass
class LoaderConfig:
    """Configuration for DataLoader behavior"""
    batch_size: int = 100
    cache_ttl: int = 300  # 5 minutes
    max_batch_wait: float = 0.016  # 16ms (1 frame at 60fps)
    cache_enabled: bool = True
    cache_prefix: str = ""


class MetricsCollector:
    """Collects performance metrics for DataLoader operations"""
    
    def __init__(self):
        self.batch_counts: List[int] = []
        self.load_times: List[float] = []
        self.cache_hits: int = 0
        self.cache_misses: int = 0
        self.total_loads: int = 0
    
    def record_batch(self, size: int, duration: float):
        """Record a batch operation"""
        self.batch_counts.append(size)
        self.load_times.append(duration)
        self.total_loads += size
    
    def record_cache_hit(self):
        """Record a cache hit"""
        self.cache_hits += 1
    
    def record_cache_miss(self):
        """Record a cache miss"""
        self.cache_misses += 1
    
    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate"""
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0
    
    @property
    def avg_batch_size(self) -> float:
        """Calculate average batch size"""
        return sum(self.batch_counts) / len(self.batch_counts) if self.batch_counts else 0.0
    
    @property
    def avg_load_time(self) -> float:
        """Calculate average load time"""
        return sum(self.load_times) / len(self.load_times) if self.load_times else 0.0


class RedisCache:
    """Redis-based cache for DataLoader"""
    
    def __init__(self, redis_client: redis.Redis, prefix: str, ttl: int):
        self.redis = redis_client
        self.prefix = prefix
        self.ttl = ttl
    
    async def get_many(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple values from cache"""
        if not keys:
            return {}
        
        # Build Redis keys
        redis_keys = [f"{self.prefix}:{key}" for key in keys]
        
        # Get values
        values = await self.redis.mget(redis_keys)
        
        # Build result dict
        result = {}
        for key, value in zip(keys, values):
            if value is not None:
                import json
                result[key] = json.loads(value)
        
        return result
    
    async def set_many(self, items: Dict[str, Any]):
        """Set multiple values in cache"""
        if not items:
            return
        
        # Build pipeline
        pipe = self.redis.pipeline()
        
        for key, value in items.items():
            import json
            redis_key = f"{self.prefix}:{key}"
            pipe.setex(redis_key, self.ttl, json.dumps(value))
        
        await pipe.execute()


class EnterpriseDataLoader(Generic[K, T]):
    """
    Enterprise-grade DataLoader with:
    - Batching to prevent N+1 queries
    - Redis caching with TTL
    - Metrics collection
    - Error handling with partial results
    - Configurable behavior
    """
    
    def __init__(
        self,
        batch_fn: Callable[[List[K]], List[Optional[T]]],
        config: LoaderConfig,
        redis_client: Optional[redis.Redis] = None,
        key_fn: Optional[Callable[[K], str]] = None
    ):
        self.batch_fn = batch_fn
        self.config = config
        self.metrics = MetricsCollector()
        self.key_fn = key_fn or str
        
        # Create underlying DataLoader
        self._loader = DataLoader(
            self._batch_load_fn,
            max_batch_size=config.batch_size
        )
        
        # Setup Redis cache if enabled
        self.cache: Optional[RedisCache] = None
        if config.cache_enabled and redis_client:
            self.cache = RedisCache(
                redis_client,
                config.cache_prefix,
                config.cache_ttl
            )
    
    async def _batch_load_fn(self, keys: List[K]) -> List[Optional[T]]:
        """Internal batch function with caching and metrics"""
        start_time = asyncio.get_event_loop().time()
        
        # Convert keys to strings for caching
        key_strings = [self.key_fn(k) for k in keys]
        key_map = dict(zip(key_strings, keys))
        
        # Check cache first
        cached_results: Dict[str, T] = {}
        uncached_keys: List[K] = []
        
        if self.cache:
            cached_results = await self.cache.get_many(key_strings)
            
            # Track metrics
            for key_str in key_strings:
                if key_str in cached_results:
                    self.metrics.record_cache_hit()
                else:
                    self.metrics.record_cache_miss()
                    uncached_keys.append(key_map[key_str])
        else:
            uncached_keys = keys
        
        # Load uncached data
        fresh_results: Dict[str, T] = {}
        if uncached_keys:
            try:
                # Call the batch function
                loaded_values = await self.batch_fn(uncached_keys)
                
                # Map results
                for key, value in zip(uncached_keys, loaded_values):
                    if value is not None:
                        key_str = self.key_fn(key)
                        fresh_results[key_str] = value
                
                # Cache fresh results
                if self.cache and fresh_results:
                    await self.cache.set_many(fresh_results)
                    
            except Exception as e:
                logger.error(f"Batch load error in {self.config.cache_prefix}: {e}")
                # Return partial results rather than failing completely
        
        # Combine results in correct order
        results = []
        for key_str in key_strings:
            value = cached_results.get(key_str) or fresh_results.get(key_str)
            results.append(value)
        
        # Record metrics
        duration = asyncio.get_event_loop().time() - start_time
        self.metrics.record_batch(len(keys), duration)
        
        if duration > 0.1:  # Log slow queries
            logger.warning(
                f"Slow batch load in {self.config.cache_prefix}: "
                f"{len(keys)} keys in {duration:.3f}s"
            )
        
        return results
    
    async def load(self, key: K) -> Optional[T]:
        """Load a single value"""
        return await self._loader.load(key)
    
    async def load_many(self, keys: List[K]) -> List[Optional[T]]:
        """Load multiple values"""
        return await self._loader.load_many(keys)
    
    def clear(self, key: K):
        """Clear a cached value"""
        self._loader.clear(key)
    
    def clear_all(self):
        """Clear all cached values"""
        self._loader.clear_all()
    
    def prime(self, key: K, value: T):
        """Prime the cache with a known value"""
        self._loader.prime(key, value)


class DataLoaderRegistry:
    """
    Central registry for all DataLoaders in the GraphQL context
    Ensures single instance per request and proper lifecycle management
    """
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis_client = redis_client
        self._loaders: Dict[str, EnterpriseDataLoader] = {}
        self._configs: Dict[str, LoaderConfig] = {
            # Define loader configurations
            "object_type": LoaderConfig(
                cache_prefix="graphql:object_type",
                batch_size=100,
                cache_ttl=300
            ),
            "property": LoaderConfig(
                cache_prefix="graphql:property",
                batch_size=200,
                cache_ttl=300
            ),
            "link_type": LoaderConfig(
                cache_prefix="graphql:link_type",
                batch_size=100,
                cache_ttl=300
            ),
            "action_type": LoaderConfig(
                cache_prefix="graphql:action_type",
                batch_size=50,
                cache_ttl=600
            ),
            "user": LoaderConfig(
                cache_prefix="graphql:user",
                batch_size=50,
                cache_ttl=3600  # 1 hour for user data
            ),
            "branch": LoaderConfig(
                cache_prefix="graphql:branch",
                batch_size=20,
                cache_ttl=60  # Short TTL for branch data
            )
        }
    
    def get_loader(
        self,
        name: str,
        batch_fn: Callable[[List[Any]], List[Optional[Any]]],
        key_fn: Optional[Callable[[Any], str]] = None
    ) -> EnterpriseDataLoader:
        """Get or create a DataLoader"""
        if name not in self._loaders:
            config = self._configs.get(name, LoaderConfig(cache_prefix=f"graphql:{name}"))
            self._loaders[name] = EnterpriseDataLoader(
                batch_fn=batch_fn,
                config=config,
                redis_client=self.redis_client,
                key_fn=key_fn
            )
        return self._loaders[name]
    
    def clear_all(self):
        """Clear all DataLoader caches"""
        for loader in self._loaders.values():
            loader.clear_all()
    
    def get_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get metrics for all loaders"""
        metrics = {}
        for name, loader in self._loaders.items():
            m = loader.metrics
            metrics[name] = {
                "total_loads": m.total_loads,
                "cache_hit_rate": m.cache_hit_rate,
                "avg_batch_size": m.avg_batch_size,
                "avg_load_time": m.avg_load_time,
                "cache_hits": m.cache_hits,
                "cache_misses": m.cache_misses
            }
        return metrics


# Example batch functions for common entities
async def batch_load_object_types(keys: List[str]) -> List[Optional[Dict[str, Any]]]:
    """Batch load object types by IDs"""
    # This would be replaced with actual database call
    # For now, showing the pattern
    logger.debug(f"Batch loading object types: {keys}")
    
    # Simulate DB call that gets all requested object types in one query
    # SELECT * FROM object_types WHERE id IN (keys)
    results = []
    for key in keys:
        # Placeholder - replace with real DB query
        results.append({"id": key, "name": f"ObjectType_{key}"})
    
    return results


async def batch_load_properties_by_object_type(
    object_type_ids: List[str]
) -> List[List[Dict[str, Any]]]:
    """Batch load properties for multiple object types"""
    logger.debug(f"Batch loading properties for object types: {object_type_ids}")
    
    # This prevents N+1 when loading properties for multiple object types
    # SELECT * FROM properties WHERE object_type_id IN (object_type_ids)
    # GROUP BY object_type_id
    
    # Placeholder implementation
    results = []
    for obj_id in object_type_ids:
        results.append([
            {"id": f"prop1_{obj_id}", "name": "property1", "object_type_id": obj_id},
            {"id": f"prop2_{obj_id}", "name": "property2", "object_type_id": obj_id}
        ])
    
    return results