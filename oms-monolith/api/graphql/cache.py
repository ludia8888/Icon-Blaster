"""
Enterprise GraphQL Caching Strategy
Multi-layer caching with intelligent invalidation
"""
import hashlib
import json
from typing import Any, Dict, List, Optional, Set, Union
from datetime import datetime, timedelta
from enum import Enum
import asyncio

import redis.asyncio as redis
from pydantic import BaseModel

from utils.logger import get_logger

logger = get_logger(__name__)


class CacheLevel(str, Enum):
    """Cache levels for different data volatility"""
    STATIC = "static"      # Rarely changes (schemas, types) - 1 hour
    NORMAL = "normal"      # Regular data - 5 minutes
    VOLATILE = "volatile"  # Frequently changing - 1 minute
    REALTIME = "realtime"  # No caching


class CacheStrategy(str, Enum):
    """Cache invalidation strategies"""
    TTL = "ttl"                    # Time-based expiration
    EVENT_BASED = "event_based"    # Invalidate on events
    WRITE_THROUGH = "write_through" # Update cache on writes
    LAZY = "lazy"                  # Invalidate on next read


class CacheKeyBuilder:
    """Builds consistent cache keys for GraphQL queries"""
    
    @staticmethod
    def build_query_key(
        query_name: str,
        variables: Dict[str, Any],
        fields: Optional[List[str]] = None
    ) -> str:
        """Build a cache key for a GraphQL query"""
        # Sort variables for consistency
        sorted_vars = json.dumps(variables, sort_keys=True)
        
        # Include requested fields if specified
        if fields:
            fields_str = ",".join(sorted(fields))
            key_data = f"{query_name}:{sorted_vars}:{fields_str}"
        else:
            key_data = f"{query_name}:{sorted_vars}"
        
        # Hash for shorter keys
        key_hash = hashlib.md5(key_data.encode()).hexdigest()[:12]
        return f"gql:query:{query_name}:{key_hash}"
    
    @staticmethod
    def build_entity_key(entity_type: str, entity_id: str) -> str:
        """Build a cache key for an entity"""
        return f"gql:entity:{entity_type}:{entity_id}"
    
    @staticmethod
    def build_list_key(
        entity_type: str,
        filters: Optional[Dict[str, Any]] = None,
        pagination: Optional[Dict[str, int]] = None
    ) -> str:
        """Build a cache key for a list query"""
        filter_str = json.dumps(filters or {}, sort_keys=True)
        page_str = json.dumps(pagination or {}, sort_keys=True)
        
        key_data = f"{entity_type}:{filter_str}:{page_str}"
        key_hash = hashlib.md5(key_data.encode()).hexdigest()[:12]
        return f"gql:list:{entity_type}:{key_hash}"


class CacheMetadata(BaseModel):
    """Metadata stored with cached values"""
    cached_at: datetime
    expires_at: datetime
    cache_level: CacheLevel
    version: int = 1
    tags: List[str] = []
    hit_count: int = 0


class InvalidationTracker:
    """Tracks cache dependencies for smart invalidation"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.prefix = "gql:deps"
    
    async def add_dependency(self, cache_key: str, entity_type: str, entity_id: str):
        """Add a dependency between a cache key and an entity"""
        dep_key = f"{self.prefix}:{entity_type}:{entity_id}"
        await self.redis.sadd(dep_key, cache_key)
        
        # Set expiration on dependency tracking
        await self.redis.expire(dep_key, 3600)  # 1 hour
    
    async def get_dependent_keys(self, entity_type: str, entity_id: str) -> Set[str]:
        """Get all cache keys that depend on an entity"""
        dep_key = f"{self.prefix}:{entity_type}:{entity_id}"
        keys = await self.redis.smembers(dep_key)
        return set(keys) if keys else set()
    
    async def invalidate_entity(self, entity_type: str, entity_id: str) -> int:
        """Invalidate all cache entries that depend on an entity"""
        dependent_keys = await self.get_dependent_keys(entity_type, entity_id)
        
        if dependent_keys:
            # Delete all dependent cache entries
            await self.redis.delete(*dependent_keys)
            
            # Clean up dependency tracking
            dep_key = f"{self.prefix}:{entity_type}:{entity_id}"
            await self.redis.delete(dep_key)
            
            logger.info(
                f"Invalidated {len(dependent_keys)} cache entries "
                f"for {entity_type}:{entity_id}"
            )
        
        return len(dependent_keys)


class GraphQLCache:
    """
    Enterprise-grade caching for GraphQL with:
    - Multi-level TTL strategies
    - Smart invalidation
    - Partial query caching
    - Metrics and monitoring
    """
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.invalidation_tracker = InvalidationTracker(redis_client)
        
        # TTL configurations by cache level
        self.ttl_config = {
            CacheLevel.STATIC: 3600,     # 1 hour
            CacheLevel.NORMAL: 300,      # 5 minutes
            CacheLevel.VOLATILE: 60,     # 1 minute
            CacheLevel.REALTIME: 0       # No caching
        }
        
        # Metrics
        self._metrics = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "invalidations": 0
        }
    
    async def get(
        self,
        key: str,
        include_metadata: bool = False
    ) -> Optional[Union[Any, tuple[Any, CacheMetadata]]]:
        """Get a value from cache"""
        # Get value and metadata
        data = await self.redis.hgetall(key)
        
        if not data:
            self._metrics["misses"] += 1
            return None
        
        # Parse stored data
        value = json.loads(data.get("value", "null"))
        
        if value is None:
            self._metrics["misses"] += 1
            return None
        
        # Check expiration
        metadata = CacheMetadata.parse_raw(data.get("metadata", "{}"))
        if datetime.utcnow() > metadata.expires_at:
            await self.redis.delete(key)
            self._metrics["misses"] += 1
            return None
        
        # Update hit count
        metadata.hit_count += 1
        await self.redis.hset(key, "metadata", metadata.json())
        
        self._metrics["hits"] += 1
        
        if include_metadata:
            return value, metadata
        return value
    
    async def set(
        self,
        key: str,
        value: Any,
        cache_level: CacheLevel = CacheLevel.NORMAL,
        dependencies: Optional[List[tuple[str, str]]] = None,
        tags: Optional[List[str]] = None
    ):
        """Set a value in cache with metadata"""
        if cache_level == CacheLevel.REALTIME:
            return  # Don't cache realtime data
        
        ttl = self.ttl_config[cache_level]
        now = datetime.utcnow()
        
        # Create metadata
        metadata = CacheMetadata(
            cached_at=now,
            expires_at=now + timedelta(seconds=ttl),
            cache_level=cache_level,
            tags=tags or []
        )
        
        # Store value and metadata
        await self.redis.hset(key, mapping={
            "value": json.dumps(value),
            "metadata": metadata.json()
        })
        await self.redis.expire(key, ttl)
        
        # Track dependencies
        if dependencies:
            for entity_type, entity_id in dependencies:
                await self.invalidation_tracker.add_dependency(key, entity_type, entity_id)
        
        self._metrics["sets"] += 1
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching a pattern"""
        cursor = 0
        count = 0
        
        while True:
            cursor, keys = await self.redis.scan(
                cursor, match=pattern, count=100
            )
            
            if keys:
                await self.redis.delete(*keys)
                count += len(keys)
            
            if cursor == 0:
                break
        
        self._metrics["invalidations"] += count
        logger.info(f"Invalidated {count} cache entries matching pattern: {pattern}")
        return count
    
    async def invalidate_by_tags(self, tags: List[str]) -> int:
        """Invalidate all cache entries with specific tags"""
        # This would require maintaining a tag index
        # For now, scan through all keys (not ideal for production)
        pattern = "gql:*"
        cursor = 0
        count = 0
        
        while True:
            cursor, keys = await self.redis.scan(
                cursor, match=pattern, count=100
            )
            
            for key in keys:
                data = await self.redis.hget(key, "metadata")
                if data:
                    metadata = CacheMetadata.parse_raw(data)
                    if any(tag in metadata.tags for tag in tags):
                        await self.redis.delete(key)
                        count += 1
            
            if cursor == 0:
                break
        
        self._metrics["invalidations"] += count
        return count
    
    async def warmup(self, queries: List[Dict[str, Any]]):
        """Warmup cache with predefined queries"""
        logger.info(f"Warming up cache with {len(queries)} queries")
        
        tasks = []
        for query_config in queries:
            # This would execute the query and cache the result
            # Implementation depends on GraphQL execution context
            pass
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get cache metrics"""
        total = self._metrics["hits"] + self._metrics["misses"]
        hit_rate = self._metrics["hits"] / total if total > 0 else 0.0
        
        return {
            **self._metrics,
            "hit_rate": hit_rate,
            "total_requests": total
        }
    
    async def clear_all(self):
        """Clear all cache entries (use with caution)"""
        pattern = "gql:*"
        cursor = 0
        count = 0
        
        while True:
            cursor, keys = await self.redis.scan(
                cursor, match=pattern, count=100
            )
            
            if keys:
                await self.redis.delete(*keys)
                count += len(keys)
            
            if cursor == 0:
                break
        
        logger.warning(f"Cleared {count} cache entries")
        return count


class CacheMiddleware:
    """
    GraphQL middleware for automatic caching
    Intercepts queries and caches results based on configuration
    """
    
    def __init__(self, cache: GraphQLCache):
        self.cache = cache
        
        # Define caching rules for different query types
        self.cache_rules = {
            # Query name -> (cache_level, extract_dependencies_fn)
            "objectTypes": (CacheLevel.NORMAL, self._extract_object_type_deps),
            "objectType": (CacheLevel.NORMAL, self._extract_single_entity_dep),
            "branches": (CacheLevel.VOLATILE, None),
            "schemaHistory": (CacheLevel.STATIC, None),
        }
    
    async def resolve(self, next_resolver, root, info, **args):
        """Middleware resolution with caching"""
        # Only cache queries, not mutations or subscriptions
        if info.operation.operation != "query":
            return await next_resolver(root, info, **args)
        
        # Get field name
        field_name = info.field_name
        
        # Check if this query should be cached
        if field_name not in self.cache_rules:
            return await next_resolver(root, info, **args)
        
        cache_level, dep_extractor = self.cache_rules[field_name]
        
        # Build cache key
        cache_key = CacheKeyBuilder.build_query_key(
            field_name,
            args,
            self._get_selected_fields(info)
        )
        
        # Try to get from cache
        cached_value = await self.cache.get(cache_key)
        if cached_value is not None:
            return cached_value
        
        # Execute resolver
        result = await next_resolver(root, info, **args)
        
        # Extract dependencies if configured
        dependencies = None
        if dep_extractor and result:
            dependencies = dep_extractor(result)
        
        # Cache the result
        await self.cache.set(
            cache_key,
            result,
            cache_level=cache_level,
            dependencies=dependencies
        )
        
        return result
    
    def _get_selected_fields(self, info) -> List[str]:
        """Extract selected fields from GraphQL query"""
        # This is a simplified version
        # Real implementation would parse the selection set
        return []
    
    def _extract_object_type_deps(self, result) -> List[tuple[str, str]]:
        """Extract object type dependencies from result"""
        deps = []
        if isinstance(result, list):
            for item in result:
                if hasattr(item, 'id'):
                    deps.append(("object_type", item.id))
        elif hasattr(result, 'id'):
            deps.append(("object_type", result.id))
        return deps
    
    def _extract_single_entity_dep(self, result) -> List[tuple[str, str]]:
        """Extract single entity dependency"""
        if hasattr(result, 'id') and hasattr(result, '__class__'):
            entity_type = result.__class__.__name__.lower()
            return [(entity_type, result.id)]
        return []