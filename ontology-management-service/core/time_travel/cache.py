"""
Time Travel Query Cache with Redis Integration
Provides distributed caching for temporal queries
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import json
import hashlib
import redis.asyncio as redis

from shared.cache.smart_cache import SmartCache
from .models import TemporalQueryResult, TemporalResourceVersion
from common_logging.setup import get_logger

logger = get_logger(__name__)


class TemporalQueryCache:
    """
    Distributed cache for temporal queries using Redis/SmartCache
    """
    
    def __init__(
        self,
        redis_client: Optional[redis.Redis] = None,
        smart_cache: Optional[SmartCache] = None,
        ttl_seconds: int = 3600,
        max_memory_items: int = 1000
    ):
        self.redis_client = redis_client
        self.smart_cache = smart_cache
        self.ttl_seconds = ttl_seconds
        self.max_memory_items = max_memory_items
        
        # Local LRU cache for hot data
        self._local_cache: Dict[str, Dict[str, Any]] = {}
        self._access_order: List[str] = []
        
    def _generate_cache_key(
        self,
        query_type: str,
        resource_type: str,
        resource_id: Optional[str],
        branch: str,
        temporal_params: Dict[str, Any]
    ) -> str:
        """Generate deterministic cache key for temporal query"""
        key_parts = [
            "temporal",
            query_type,
            resource_type,
            resource_id or "all",
            branch
        ]
        
        # Add temporal parameters
        param_str = json.dumps(temporal_params, sort_keys=True)
        param_hash = hashlib.md5(param_str.encode()).hexdigest()[:8]
        key_parts.append(param_hash)
        
        return ":".join(key_parts)
    
    async def get_cached_result(
        self,
        cache_key: str
    ) -> Optional[TemporalQueryResult]:
        """Get cached temporal query result"""
        # Check local cache first
        if cache_key in self._local_cache:
            self._update_access_order(cache_key)
            logger.debug(f"Local cache hit for {cache_key}")
            return self._deserialize_result(self._local_cache[cache_key])
        
        # Check SmartCache (3-tier)
        if self.smart_cache:
            cached_data = await self.smart_cache.get(cache_key)
            if cached_data:
                # Update local cache
                self._update_local_cache(cache_key, cached_data)
                logger.debug(f"SmartCache hit for {cache_key}")
                return self._deserialize_result(cached_data)
        
        # Fallback to Redis
        elif self.redis_client:
            try:
                cached_json = await self.redis_client.get(cache_key)
                if cached_json:
                    cached_data = json.loads(cached_json)
                    self._update_local_cache(cache_key, cached_data)
                    logger.debug(f"Redis cache hit for {cache_key}")
                    return self._deserialize_result(cached_data)
            except Exception as e:
                logger.error(f"Redis cache get error: {e}")
        
        return None
    
    async def cache_result(
        self,
        cache_key: str,
        result: TemporalQueryResult,
        ttl_override: Optional[int] = None
    ):
        """Cache temporal query result"""
        ttl = ttl_override or self.ttl_seconds
        
        # Serialize result
        cached_data = self._serialize_result(result)
        
        # Update local cache
        self._update_local_cache(cache_key, cached_data)
        
        # Store in distributed cache
        if self.smart_cache:
            await self.smart_cache.set(
                cache_key,
                cached_data,
                ttl=ttl
            )
        elif self.redis_client:
            try:
                await self.redis_client.setex(
                    cache_key,
                    ttl,
                    json.dumps(cached_data)
                )
            except Exception as e:
                logger.error(f"Redis cache set error: {e}")
    
    async def invalidate_resource(
        self,
        resource_type: str,
        resource_id: str,
        branch: str
    ):
        """Invalidate all cached queries for a resource"""
        pattern = f"temporal:*:{resource_type}:{resource_id}:{branch}:*"
        
        # Clear from local cache
        keys_to_remove = [
            k for k in self._local_cache
            if self._matches_pattern(k, pattern)
        ]
        for key in keys_to_remove:
            del self._local_cache[key]
            if key in self._access_order:
                self._access_order.remove(key)
        
        # Clear from distributed cache
        if self.smart_cache:
            # SmartCache handles pattern-based invalidation
            await self.smart_cache.delete_pattern(pattern)
        elif self.redis_client:
            try:
                # Use SCAN to find matching keys
                cursor = 0
                while True:
                    cursor, keys = await self.redis_client.scan(
                        cursor, match=pattern, count=100
                    )
                    if keys:
                        await self.redis_client.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.error(f"Redis invalidation error: {e}")
    
    async def invalidate_branch(self, branch: str):
        """Invalidate all cached queries for a branch"""
        pattern = f"temporal:*:*:*:{branch}:*"
        
        # Clear local cache
        keys_to_remove = [
            k for k in self._local_cache
            if self._matches_pattern(k, pattern)
        ]
        for key in keys_to_remove:
            del self._local_cache[key]
            if key in self._access_order:
                self._access_order.remove(key)
        
        # Clear distributed cache
        if self.smart_cache:
            await self.smart_cache.delete_pattern(pattern)
        elif self.redis_client:
            try:
                cursor = 0
                while True:
                    cursor, keys = await self.redis_client.scan(
                        cursor, match=pattern, count=100
                    )
                    if keys:
                        await self.redis_client.delete(*keys)
                    if cursor == 0:
                        break
            except Exception as e:
                logger.error(f"Redis branch invalidation error: {e}")
    
    def _update_local_cache(self, key: str, data: Dict[str, Any]):
        """Update local LRU cache"""
        # Evict if at capacity
        if len(self._local_cache) >= self.max_memory_items:
            if self._access_order:
                oldest_key = self._access_order.pop(0)
                del self._local_cache[oldest_key]
        
        self._local_cache[key] = data
        self._update_access_order(key)
    
    def _update_access_order(self, key: str):
        """Update LRU access order"""
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)
    
    def _matches_pattern(self, key: str, pattern: str) -> bool:
        """Check if key matches wildcard pattern"""
        import fnmatch
        return fnmatch.fnmatch(key, pattern)
    
    def _serialize_result(self, result: TemporalQueryResult) -> Dict[str, Any]:
        """Serialize temporal query result for caching"""
        return {
            "resources": [
                {
                    "resource_type": r.resource_type,
                    "resource_id": r.resource_id,
                    "branch": r.branch,
                    "version": r.version,
                    "commit_hash": r.commit_hash,
                    "valid_time": r.valid_time.isoformat(),
                    "content": r.content,
                    "modified_by": r.modified_by,
                    "change_type": r.change_type,
                    "change_summary": r.change_summary,
                    "next_version": r.next_version,
                    "previous_version": r.previous_version,
                    "version_duration": r.version_duration
                }
                for r in result.resources
            ],
            "total_count": result.total_count,
            "has_more": result.has_more,
            "execution_time_ms": result.execution_time_ms,
            "time_range_covered": result.time_range_covered,
            "versions_scanned": result.versions_scanned,
            "cache_hit": True,  # Mark as cached
            "cached_at": datetime.utcnow().isoformat()
        }
    
    def _deserialize_result(self, data: Dict[str, Any]) -> TemporalQueryResult:
        """Deserialize cached temporal query result"""
        # Convert resources
        resources = []
        for r_data in data.get("resources", []):
            resources.append(TemporalResourceVersion(
                resource_type=r_data["resource_type"],
                resource_id=r_data["resource_id"],
                branch=r_data["branch"],
                version=r_data["version"],
                commit_hash=r_data["commit_hash"],
                valid_time=datetime.fromisoformat(r_data["valid_time"]),
                content=r_data["content"],
                modified_by=r_data["modified_by"],
                change_type=r_data["change_type"],
                change_summary=r_data.get("change_summary"),
                next_version=r_data.get("next_version"),
                previous_version=r_data.get("previous_version"),
                version_duration=r_data.get("version_duration")
            ))
        
        # Create dummy query object (not used for cached results)
        from .models import TemporalResourceQuery, TemporalQuery, TemporalOperator
        dummy_query = TemporalResourceQuery(
            resource_type="cached",
            branch="cached",
            temporal=TemporalQuery(operator=TemporalOperator.AS_OF)
        )
        
        return TemporalQueryResult(
            query=dummy_query,
            execution_time_ms=data["execution_time_ms"],
            resources=resources,
            total_count=data["total_count"],
            has_more=data["has_more"],
            time_range_covered=data.get("time_range_covered"),
            versions_scanned=data.get("versions_scanned", 0),
            cache_hit=True,
            cacheable=True
        )
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        stats = {
            "local_cache_size": len(self._local_cache),
            "local_cache_keys": len(self._access_order),
            "max_memory_items": self.max_memory_items,
            "ttl_seconds": self.ttl_seconds
        }
        
        if self.redis_client:
            try:
                info = await self.redis_client.info()
                stats["redis_used_memory"] = info.get("used_memory_human", "N/A")
                stats["redis_connected_clients"] = info.get("connected_clients", 0)
            except Exception as e:
                stats["redis_error"] = str(e)
        
        return stats