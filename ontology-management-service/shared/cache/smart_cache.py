"""
Smart Cache Manager with Redis backend and intelligent tiered storage.
Provides high-performance caching for graph analysis operations.
"""
import json
import gzip
import hashlib
import asyncio
from typing import Any, Optional, Dict, List, Union
from datetime import datetime, timedelta
import pickle
from cachetools import TTLCache

import redis.asyncio as redis
from database.clients.terminus_db import TerminusDBClient
from middleware.common.metrics import get_metrics_collector
from common_logging.setup import get_logger
from core.validation.ports import CachePort

logger = get_logger(__name__)

# Metrics
metrics_collector = get_metrics_collector("smart_cache")

# Helper functions for metrics
def increment_cache_operations(operation: str, tier: str):
    metrics_collector.increment_counter("cache_operations_total", 1, {"operation": operation, "tier": tier})

def observe_cache_latency(operation: str, tier: str, duration: float):
    metrics_collector.observe_histogram("cache_operation_duration_seconds", duration, {"operation": operation, "tier": tier})

def set_cache_memory_usage(tier: str, bytes_used: float):
    metrics_collector.set_gauge("cache_memory_bytes", bytes_used, {"tier": tier})

def set_cache_hit_ratio(tier: str, ratio: float):
    metrics_collector.set_gauge("cache_hit_ratio", ratio, {"tier": tier})


class CacheMetrics:
    """Cache metrics collector."""
    
    def __init__(self):
        self.reset()
    
    def reset(self):
        """Reset all metrics."""
        self.local_hits = 0
        self.local_misses = 0
        self.redis_hits = 0
        self.redis_misses = 0
        self.terminus_hits = 0
        self.terminus_misses = 0
        self.evictions = 0
        self.errors = 0
    
    def record_hit(self, tier: str):
        """Record cache hit."""
        increment_cache_operations("hit", tier)
        if tier == "local":
            self.local_hits += 1
        elif tier == "redis":
            self.redis_hits += 1
        elif tier == "terminus":
            self.terminus_hits += 1
    
    def record_miss(self, tier: str):
        """Record cache miss."""
        increment_cache_operations("miss", tier)
        if tier == "local":
            self.local_misses += 1
        elif tier == "redis":
            self.redis_misses += 1
        elif tier == "terminus":
            self.terminus_misses += 1
    
    def record_set(self, tier: str):
        """Record cache set operation."""
        increment_cache_operations("set", tier)
    
    def record_eviction(self):
        """Record cache eviction."""
        increment_cache_operations("eviction", "local")
        self.evictions += 1
    
    def record_error(self):
        """Record cache error."""
        increment_cache_operations("error", "unknown")
        self.errors += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        total_local = self.local_hits + self.local_misses
        total_redis = self.redis_hits + self.redis_misses
        total_terminus = self.terminus_hits + self.terminus_misses
        
        local_hit_ratio = self.local_hits / total_local if total_local > 0 else 0
        redis_hit_ratio = self.redis_hits / total_redis if total_redis > 0 else 0
        terminus_hit_ratio = self.terminus_hits / total_terminus if total_terminus > 0 else 0
        
        # Update Prometheus metrics
        set_cache_hit_ratio("local", local_hit_ratio)
        set_cache_hit_ratio("redis", redis_hit_ratio)
        set_cache_hit_ratio("terminus", terminus_hit_ratio)
        
        return {
            "local": {
                "hits": self.local_hits,
                "misses": self.local_misses,
                "hit_ratio": local_hit_ratio
            },
            "redis": {
                "hits": self.redis_hits,
                "misses": self.redis_misses,
                "hit_ratio": redis_hit_ratio
            },
            "terminus": {
                "hits": self.terminus_hits,
                "misses": self.terminus_misses,
                "hit_ratio": terminus_hit_ratio
            },
            "evictions": self.evictions,
            "errors": self.errors
        }


class SmartCache(CachePort):
    """
    Enhanced caching system with Redis backend and intelligent tiered storage.
    
    Provides three-tier caching:
    1. Local in-memory cache (fastest)
    2. Redis distributed cache (fast)
    3. TerminusDB persistence cache (persistent)
    """
    
    def __init__(self, 
                 terminus_client: Optional[TerminusDBClient] = None,
                 redis_client: Optional[redis.Redis] = None,
                 namespace: str = "cache",
                 local_cache_size: int = 1000,
                 local_ttl: int = 300,
                 distributed_ttl: int = 3600,
                 persistence_ttl: int = 86400,
                 compression_enabled: bool = True,
                 compression_threshold: int = 1024,
                 serialization_format: str = "json"):
        
        self.terminus_client = terminus_client
        self.redis_client = redis_client
        self.namespace = namespace
        self.local_cache = TTLCache(maxsize=local_cache_size, ttl=local_ttl)
        self.distributed_ttl = distributed_ttl
        self.persistence_ttl = persistence_ttl
        self.compression_enabled = compression_enabled
        self.compression_threshold = compression_threshold
        self.serialization_format = serialization_format
        self.metrics = CacheMetrics()
        
        # Redis initialization
        self._redis_initialized = False
        
    async def _ensure_redis_client(self):
        """Ensure Redis client is available."""
        if not self._redis_initialized:
            if self.redis_client is None:
                # The expectation is that the redis_client is injected during initialization.
                # This method no longer attempts to create a client on its own.
                logger.warning("SmartCache: Redis client was not provided during initialization. Distributed cache is disabled.")
            
            self._redis_initialized = True
    
    def _generate_key(self, key: str) -> str:
        """Generate namespaced cache key."""
        if len(key) > 200:  # Redis key length limit consideration
            key_hash = hashlib.sha256(key.encode()).hexdigest()[:16]
            return f"{self.namespace}:{key_hash}"
        return f"{self.namespace}:{key}"
    
    def _serialize(self, value: Any) -> bytes:
        """Serialize value for storage."""
        if self.serialization_format == "json":
            try:
                serialized = json.dumps(value, ensure_ascii=False).encode('utf-8')
            except (TypeError, ValueError):
                # Fallback to pickle for non-JSON serializable objects
                serialized = pickle.dumps(value)
        else:  # pickle
            serialized = pickle.dumps(value)
        
        # Apply compression if enabled and data is large enough
        if (self.compression_enabled and 
            len(serialized) > self.compression_threshold):
            compressed = gzip.compress(serialized)
            compression_ratio = len(compressed) / len(serialized)
            
            # Only use compression if it saves significant space
            if compression_ratio < 0.8:
                return b"gzip:" + compressed
        
        return serialized
    
    def _deserialize(self, data: bytes) -> Any:
        """Deserialize value from storage."""
        if data.startswith(b"gzip:"):
            # Decompress first
            data = gzip.decompress(data[5:])
        
        if self.serialization_format == "json":
            try:
                return json.loads(data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                # Fallback to pickle
                return pickle.loads(data)
        else:  # pickle
            return pickle.loads(data)
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache using tiered lookup.
        
        Order: Local -> Redis -> TerminusDB -> None
        """
        cache_key = self._generate_key(key)
        
        # Tier 1: Local cache
        if cache_key in self.local_cache:
            self.metrics.record_hit("local")
            logger.debug(f"Cache hit (local): {key}")
            return self.local_cache[cache_key]
        else:
            self.metrics.record_miss("local")
        
        # Tier 2: Redis cache
        redis_value = await self._get_from_redis(cache_key)
        if redis_value is not None:
            self.metrics.record_hit("redis")
            # Populate local cache
            self.local_cache[cache_key] = redis_value
            logger.debug(f"Cache hit (redis): {key}")
            return redis_value
        else:
            self.metrics.record_miss("redis")
        
        # Tier 3: TerminusDB persistence cache
        if self.terminus_client:
            terminus_value = await self._get_from_terminus(cache_key)
            if terminus_value is not None:
                self.metrics.record_hit("terminus")
                # Populate both upper tiers
                self.local_cache[cache_key] = terminus_value
                await self._set_to_redis(cache_key, terminus_value, self.distributed_ttl)
                logger.debug(f"Cache hit (terminus): {key}")
                return terminus_value
            else:
                self.metrics.record_miss("terminus")
        
        logger.debug(f"Cache miss (all tiers): {key}")
        return None

    async def exists(self, key: str) -> bool:
        """Check if a key exists in any cache tier."""
        value = await self.get(key)
        return value is not None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set value in all cache tiers.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time to live in seconds (uses default if None)
        """
        cache_key = self._generate_key(key)
        local_ttl = ttl or 300
        redis_ttl = ttl or self.distributed_ttl
        terminus_ttl = ttl or self.persistence_ttl
        
        success = True
        
        # Set in local cache
        try:
            self.local_cache[cache_key] = value
            self.metrics.record_set("local")
        except Exception as e:
            logger.warning(f"Failed to set local cache for {key}: {e}")
            success = False
        
        # Set in Redis
        redis_success = await self._set_to_redis(cache_key, value, redis_ttl)
        if redis_success:
            self.metrics.record_set("redis")
        else:
            success = False
        
        # Set in TerminusDB (if enabled)
        if self.terminus_client:
            terminus_success = await self._set_to_terminus(cache_key, value, terminus_ttl)
            if terminus_success:
                self.metrics.record_set("terminus")
            else:
                success = False
        
        logger.debug(f"Cache set: {key} (success: {success})")
        return success
    
    async def delete(self, key: str) -> bool:
        """Delete value from all cache tiers."""
        cache_key = self._generate_key(key)
        success = True
        
        # Delete from local cache
        if cache_key in self.local_cache:
            del self.local_cache[cache_key]
        
        # Delete from Redis
        redis_success = await self._delete_from_redis(cache_key)
        if not redis_success:
            success = False
        
        # Delete from TerminusDB
        if self.terminus_client:
            terminus_success = await self._delete_from_terminus(cache_key)
            if not terminus_success:
                success = False
        
        logger.debug(f"Cache delete: {key} (success: {success})")
        return success
    
    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
        deleted_count = 0
        
        # Delete from local cache
        keys_to_delete = []
        for local_key in self.local_cache.keys():
            if pattern in local_key:
                keys_to_delete.append(local_key)
        
        for key in keys_to_delete:
            del self.local_cache[key]
            deleted_count += 1
        
        # Delete from Redis
        redis_deleted = await self._delete_pattern_from_redis(pattern)
        deleted_count += redis_deleted
        
        # TerminusDB pattern deletion would be complex, skip for now
        
        logger.info(f"Cache pattern delete: {pattern} ({deleted_count} keys deleted)")
        return deleted_count
    
    async def clear(self):
        """Clear all cache tiers."""
        # Clear local cache
        self.local_cache.clear()
        
        # Clear Redis (namespace only)
        await self._clear_redis_namespace()
        
        # TerminusDB clearing would be complex, skip for now
        
        logger.info("Cache cleared")
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        stats = self.metrics.get_stats()
        
        # Add memory usage information
        stats["memory"] = {
            "local_items": len(self.local_cache),
            "local_maxsize": self.local_cache.maxsize,
        }
        
        # Add Redis info if available
        if self.redis_client:
            try:
                redis_info = await self.redis_client.info("memory")
                stats["memory"]["redis_used"] = redis_info.get("used_memory_human", "unknown")
            except Exception as e:
                logger.warning(f"Failed to get Redis memory info: {e}")
        
        return stats
    
    # Redis operations
    async def _get_from_redis(self, key: str) -> Optional[Any]:
        """Get value from Redis."""
        await self._ensure_redis_client()
        if not self.redis_client:
            return None
        
        start_time = asyncio.get_event_loop().time()
        try:
            value = await self.redis_client.get(key)
            duration = asyncio.get_event_loop().time() - start_time
            # observe_cache_latency("get", "redis", duration) # TODO: Fix observe_cache_latency call
            
            if value:
                return self._deserialize(value)
            return None
        except Exception as e:
            logger.warning(f"Redis get error for {key}: {e}")
            self.metrics.record_error()
            return None
    
    async def _set_to_redis(self, key: str, value: Any, ttl: int) -> bool:
        """Set value to Redis."""
        await self._ensure_redis_client()
        if not self.redis_client:
            return False
            
        start_time = asyncio.get_event_loop().time()
        try:
            serialized_value = self._serialize(value)
            await self.redis_client.set(key, serialized_value, ex=ttl)
            duration = asyncio.get_event_loop().time() - start_time
            # observe_cache_latency("set", "redis", duration) # TODO: Fix observe_cache_latency call
            return True
        except Exception as e:
            logger.error(f"Failed to set value to Redis: {e}")
            self.metrics.record_error()
            return False
    
    async def _delete_from_redis(self, key: str) -> bool:
        """Delete value from Redis."""
        await self._ensure_redis_client()
        if not self.redis_client:
            return False
            
        start_time = asyncio.get_event_loop().time()
        try:
            await self.redis_client.delete(key)
            duration = asyncio.get_event_loop().time() - start_time
            # observe_cache_latency("delete", "redis", duration) # TODO: Fix observe_cache_latency call
            return True
        except Exception as e:
            logger.error(f"Failed to delete value from Redis: {e}")
            self.metrics.record_error()
            return False
    
    async def _delete_pattern_from_redis(self, pattern: str) -> int:
        """Delete keys matching pattern from Redis."""
        await self._ensure_redis_client()
        if not self.redis_client:
            return 0
        
        try:
            pattern_key = f"{self.namespace}:*{pattern}*"
            keys = await self.redis_client.keys(pattern_key)
            if keys:
                deleted = await self.redis_client.delete(*keys)
                return deleted
            return 0
        except Exception as e:
            logger.warning(f"Redis pattern delete error for {pattern}: {e}")
            self.metrics.record_error()
            return 0
    
    async def _clear_redis_namespace(self):
        """Clear all keys in the Redis namespace."""
        await self._ensure_redis_client()
        if not self.redis_client:
            return
        
        try:
            pattern = f"{self.namespace}:*"
            keys = await self.redis_client.keys(pattern)
            if keys:
                await self.redis_client.delete(*keys)
        except Exception as e:
            logger.warning(f"Redis namespace clear error: {e}")
            self.metrics.record_error()
    
    # TerminusDB operations (persistence tier)
    async def _get_from_terminus(self, key: str) -> Optional[Any]:
        """Get cache entry from TerminusDB."""
        if not self.terminus_client:
            return None
            
        try:
            # Use WOQL query to get cache entry
            woql_query = {
                "@type": "Select",
                "variables": ["Value"],
                "query": {
                    "@type": "Triple",
                    "subject": {"@type": "NodeValue", "node": f"cache:{key}"},
                    "predicate": {"@type": "NodeValue", "node": "value"},
                    "object": {"@type": "Variable", "name": "Value"}
                }
            }
            
            db_name = "oms"
            result = await self.terminus_client.query(db_name, woql_query)
            
            if result and result.get("bindings"):
                value_str = result["bindings"][0].get("Value", {}).get("@value")
                if value_str:
                    return self._deserialize(value_str.encode())
            return None
        except Exception as e:
            logger.warning(f"Failed to get cache from TerminusDB: {e}")
            self.metrics.record_error()
            return None
    
    async def _set_to_terminus(self, key: str, value: Any, ttl: int) -> bool:
        """Set cache entry in TerminusDB."""
        if not self.terminus_client:
            return False
        
        try:
            serialized_value = self._serialize(value)
            
            # Use WOQL to insert/update cache entry
            cache_data = {
                "key": key,
                "value": serialized_value.decode(errors='ignore'),
                "created_at": datetime.utcnow().isoformat(),
                "ttl": ttl
            }
            
            # Use WOQL query to store cache entry
            woql_query = {
                "@type": "Triple",
                "subject": {"@type": "NodeValue", "node": f"cache:{key}"},
                "predicate": {"@type": "NodeValue", "node": "rdf:type"},
                "object": {"@type": "Value", "data": {"@type": "xsd:string", "@value": "CacheEntry"}}
            }
            
            db_name = "oms"
            await self.terminus_client.query(db_name, woql_query, f"Cache set: {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to set cache to TerminusDB: {e}")
            self.metrics.record_error()
            return False
    
    async def _delete_from_terminus(self, key: str) -> bool:
        """Delete cache entry from TerminusDB."""
        if not self.terminus_client:
            return False
        
        try:
            # Use WOQL query to delete cache entry
            woql_query = {
                "@type": "DeleteTriple",
                "subject": {"@type": "NodeValue", "node": f"cache:{key}"},
                "predicate": {"@type": "Variable", "name": "predicate"},
                "object": {"@type": "Variable", "name": "object"}
            }
            
            db_name = "oms"
            await self.terminus_client.query(db_name, woql_query, f"Cache delete: {key}")
            logger.info(f"Deleted from TerminusDB cache: {key}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete cache from TerminusDB: {e}")
            self.metrics.record_error()
            return False


# Convenience aliases for backward compatibility
SmartCacheManager = SmartCache


# Factory functions for common configurations
async def create_graph_cache(terminus_client: Optional[TerminusDBClient] = None,
                           redis_client: Optional[redis.Redis] = None) -> SmartCache:
    """Create SmartCache optimized for graph operations."""
    return SmartCache(
        terminus_client=terminus_client,
        redis_client=redis_client,
        namespace="graph",
        local_cache_size=500,  # Smaller local cache for graph data
        local_ttl=300,         # 5 minutes local
        distributed_ttl=1800,  # 30 minutes Redis
        persistence_ttl=7200,  # 2 hours TerminusDB
        compression_enabled=True,
        compression_threshold=512,  # Compress smaller graph data
        serialization_format="json"
    )

async def create_path_cache(terminus_client: Optional[TerminusDBClient] = None,
                          redis_client: Optional[redis.Redis] = None) -> SmartCache:
    """Create SmartCache optimized for path query results."""
    return SmartCache(
        terminus_client=terminus_client,
        redis_client=redis_client,
        namespace="path",
        local_cache_size=1000,  # Larger local cache for paths
        local_ttl=900,          # 15 minutes local
        distributed_ttl=3600,   # 1 hour Redis
        persistence_ttl=14400,  # 4 hours TerminusDB
        compression_enabled=True,
        compression_threshold=1024,
        serialization_format="json"
    )