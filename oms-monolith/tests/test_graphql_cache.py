"""
Comprehensive tests for GraphQL caching functionality
Verifies multi-level caching, invalidation, and performance
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Set
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import redis.asyncio as redis
import json

from api.graphql.cache import (
    GraphQLCache,
    CacheLevel,
    CacheStrategy,
    CacheKeyBuilder,
    CacheMetadata,
    InvalidationTracker,
    CacheMiddleware,
    cache_warmup
)


class TestCacheKeyBuilder:
    """Test cache key generation"""
    
    def test_query_key_basic(self):
        """Test basic query key generation"""
        key = CacheKeyBuilder.build_query_key(
            "getObjectTypes",
            {"branch": "main", "limit": 10}
        )
        
        assert key.startswith("gql:query:getObjectTypes:")
        assert len(key.split(":")) == 4
        
        # Same inputs should generate same key
        key2 = CacheKeyBuilder.build_query_key(
            "getObjectTypes",
            {"limit": 10, "branch": "main"}  # Different order
        )
        assert key == key2
    
    def test_query_key_with_fields(self):
        """Test query key with field selection"""
        key1 = CacheKeyBuilder.build_query_key(
            "getObjectTypes",
            {"branch": "main"},
            ["id", "name", "properties"]
        )
        
        key2 = CacheKeyBuilder.build_query_key(
            "getObjectTypes",
            {"branch": "main"},
            ["properties", "name", "id"]  # Different order
        )
        
        # Should be same regardless of field order
        assert key1 == key2
        
        # Different fields should generate different key
        key3 = CacheKeyBuilder.build_query_key(
            "getObjectTypes",
            {"branch": "main"},
            ["id", "name"]  # Missing properties
        )
        assert key1 != key3
    
    def test_entity_key(self):
        """Test entity key generation"""
        key = CacheKeyBuilder.build_entity_key("ObjectType", "User")
        assert key == "gql:entity:ObjectType:User"
    
    def test_list_key(self):
        """Test list query key generation"""
        key = CacheKeyBuilder.build_list_key(
            "ObjectType",
            {"status": "active", "type": "entity"},
            {"limit": 10, "offset": 0}
        )
        
        assert key.startswith("gql:list:ObjectType:")
        
        # Empty filters should work
        key2 = CacheKeyBuilder.build_list_key("ObjectType")
        assert key2.startswith("gql:list:ObjectType:")


class TestInvalidationTracker:
    """Test cache dependency tracking and invalidation"""
    
    @pytest.mark.asyncio
    async def test_add_dependency(self):
        """Test adding cache dependencies"""
        mock_redis = AsyncMock(spec=redis.Redis)
        tracker = InvalidationTracker(mock_redis)
        
        await tracker.add_dependency(
            "gql:query:getUser:123",
            "User",
            "user-1"
        )
        
        mock_redis.sadd.assert_called_once_with(
            "gql:deps:User:user-1",
            "gql:query:getUser:123"
        )
        mock_redis.expire.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_dependent_keys(self):
        """Test retrieving dependent cache keys"""
        mock_redis = AsyncMock(spec=redis.Redis)
        mock_redis.smembers.return_value = {
            b"gql:query:getUser:123",
            b"gql:list:users:abc"
        }
        
        tracker = InvalidationTracker(mock_redis)
        keys = await tracker.get_dependent_keys("User", "user-1")
        
        assert len(keys) == 2
        assert b"gql:query:getUser:123" in keys
        assert b"gql:list:users:abc" in keys
    
    @pytest.mark.asyncio
    async def test_invalidate_entity(self):
        """Test invalidating all dependent cache entries"""
        mock_redis = AsyncMock(spec=redis.Redis)
        mock_redis.smembers.return_value = {
            b"gql:query:getUser:123",
            b"gql:list:users:abc"
        }
        
        tracker = InvalidationTracker(mock_redis)
        count = await tracker.invalidate_entity("User", "user-1")
        
        assert count == 2
        
        # Should delete cache entries and dependency tracking
        assert mock_redis.delete.call_count == 2
        
        # First call deletes cache entries
        first_call_args = mock_redis.delete.call_args_list[0][0]
        assert b"gql:query:getUser:123" in first_call_args
        assert b"gql:list:users:abc" in first_call_args
        
        # Second call deletes dependency key
        second_call_args = mock_redis.delete.call_args_list[1][0]
        assert second_call_args[0] == "gql:deps:User:user-1"


class TestGraphQLCache:
    """Test the main GraphQL cache functionality"""
    
    @pytest.mark.asyncio
    async def test_get_and_set(self):
        """Test basic get and set operations"""
        mock_redis = AsyncMock(spec=redis.Redis)
        mock_redis.get.return_value = None  # Cache miss
        
        cache = GraphQLCache(mock_redis)
        
        # Test cache miss
        result = await cache.get("test_key", CacheLevel.NORMAL)
        assert result is None
        
        # Test set
        test_data = {"id": "1", "name": "Test"}
        await cache.set("test_key", test_data, CacheLevel.NORMAL)
        
        # Verify Redis operations
        mock_redis.get.assert_called_once()
        mock_redis.setex.assert_called_once()
        
        # Check TTL is correct for NORMAL level (5 minutes)
        call_args = mock_redis.setex.call_args
        assert call_args[0][1] == 300  # 5 minutes
    
    @pytest.mark.asyncio
    async def test_cache_levels(self):
        """Test different cache levels have correct TTLs"""
        mock_redis = AsyncMock(spec=redis.Redis)
        cache = GraphQLCache(mock_redis)
        
        test_data = {"test": "data"}
        
        # Test each cache level
        await cache.set("key1", test_data, CacheLevel.STATIC)
        await cache.set("key2", test_data, CacheLevel.NORMAL)
        await cache.set("key3", test_data, CacheLevel.VOLATILE)
        await cache.set("key4", test_data, CacheLevel.REALTIME)
        
        # Check TTLs
        calls = mock_redis.setex.call_args_list
        assert calls[0][0][1] == 3600  # STATIC: 1 hour
        assert calls[1][0][1] == 300   # NORMAL: 5 minutes
        assert calls[2][0][1] == 60    # VOLATILE: 1 minute
        
        # REALTIME should not cache
        assert len(calls) == 3  # Only 3 calls, not 4
    
    @pytest.mark.asyncio
    async def test_cache_with_dependencies(self):
        """Test caching with dependency tracking"""
        mock_redis = AsyncMock(spec=redis.Redis)
        cache = GraphQLCache(mock_redis)
        
        # Set with dependencies
        await cache.set(
            "query_key",
            {"user": {"id": "1", "name": "Test"}},
            CacheLevel.NORMAL,
            dependencies=[("User", "1")]
        )
        
        # Should track dependencies
        mock_redis.sadd.assert_called_once_with(
            "gql:deps:User:1",
            "gql:cache:query_key"
        )
    
    @pytest.mark.asyncio
    async def test_invalidate_pattern(self):
        """Test pattern-based cache invalidation"""
        mock_redis = AsyncMock(spec=redis.Redis)
        mock_redis.keys.return_value = [
            b"gql:cache:users:1",
            b"gql:cache:users:2",
            b"gql:cache:users:list"
        ]
        
        cache = GraphQLCache(mock_redis)
        count = await cache.invalidate_pattern("users:*")
        
        assert count == 3
        mock_redis.delete.assert_called_once()
        
        # Check all keys were passed to delete
        delete_args = mock_redis.delete.call_args[0]
        assert len(delete_args) == 3
    
    @pytest.mark.asyncio
    async def test_cache_hit_metrics(self):
        """Test cache hit/miss metrics tracking"""
        mock_redis = AsyncMock(spec=redis.Redis)
        cache = GraphQLCache(mock_redis)
        
        # Simulate cache hit
        mock_redis.get.return_value = json.dumps({
            "value": {"test": "data"},
            "metadata": {
                "cached_at": datetime.utcnow().isoformat(),
                "expires_at": (datetime.utcnow() + timedelta(minutes=5)).isoformat(),
                "cache_level": "normal",
                "version": 1,
                "tags": [],
                "hit_count": 5
            }
        })
        
        result = await cache.get("test_key", CacheLevel.NORMAL)
        assert result["test"] == "data"
        
        # Metrics should be updated
        assert cache.metrics["hits"] == 1
        assert cache.metrics["misses"] == 0
        
        # Test cache miss
        mock_redis.get.return_value = None
        result = await cache.get("miss_key", CacheLevel.NORMAL)
        assert result is None
        
        assert cache.metrics["hits"] == 1
        assert cache.metrics["misses"] == 1


class TestCacheMiddleware:
    """Test GraphQL cache middleware"""
    
    @pytest.mark.asyncio
    async def test_middleware_caching(self):
        """Test that middleware caches query results"""
        mock_redis = AsyncMock(spec=redis.Redis)
        mock_redis.get.return_value = None  # Cache miss
        
        cache = GraphQLCache(mock_redis)
        middleware = CacheMiddleware(cache)
        
        # Mock GraphQL context
        mock_info = Mock()
        mock_info.context = {
            "cache": cache,
            "cache_hints": {
                "level": CacheLevel.NORMAL,
                "key": "test_query"
            }
        }
        
        # Mock resolver
        async def mock_resolver(*args):
            return {"data": "test_result"}
        
        # Execute with middleware
        result = await middleware.resolve(
            lambda: mock_resolver(),
            mock_info,
            None
        )
        
        assert result["data"] == "test_result"
        
        # Should have cached the result
        mock_redis.setex.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_middleware_cache_bypass(self):
        """Test middleware bypasses cache for mutations"""
        mock_redis = AsyncMock(spec=redis.Redis)
        cache = GraphQLCache(mock_redis)
        middleware = CacheMiddleware(cache)
        
        # Mock GraphQL context for mutation
        mock_info = Mock()
        mock_info.context = {
            "cache": cache,
            "is_mutation": True
        }
        
        # Mock resolver
        async def mock_resolver(*args):
            return {"data": "mutation_result"}
        
        # Execute
        result = await middleware.resolve(
            lambda: mock_resolver(),
            mock_info,
            None
        )
        
        # Should not cache mutations
        mock_redis.setex.assert_not_called()


class TestCacheWarmup:
    """Test cache warming functionality"""
    
    @pytest.mark.asyncio
    async def test_warmup_common_queries(self):
        """Test warming cache with common queries"""
        mock_redis = AsyncMock(spec=redis.Redis)
        cache = GraphQLCache(mock_redis)
        
        # Mock query executor
        mock_executor = AsyncMock()
        mock_executor.return_value = {
            "data": {"objectTypes": [{"id": "1"}]}
        }
        
        # Define warmup queries
        queries = [
            {
                "query": "{ objectTypes { id name } }",
                "variables": {"branch": "main"},
                "cache_level": CacheLevel.STATIC
            }
        ]
        
        await cache_warmup(
            cache,
            queries,
            mock_executor
        )
        
        # Should execute query and cache result
        mock_executor.assert_called_once()
        mock_redis.setex.assert_called()
    
    @pytest.mark.asyncio
    async def test_warmup_error_handling(self):
        """Test warmup handles errors gracefully"""
        mock_redis = AsyncMock(spec=redis.Redis)
        cache = GraphQLCache(mock_redis)
        
        # Mock executor that fails
        mock_executor = AsyncMock()
        mock_executor.side_effect = Exception("Query failed")
        
        queries = [{"query": "{ failing }"}]
        
        # Should not raise exception
        await cache_warmup(cache, queries, mock_executor)
        
        # Should not cache failed queries
        mock_redis.setex.assert_not_called()


class TestCacheIntegration:
    """Test cache integration with GraphQL operations"""
    
    @pytest.mark.asyncio
    async def test_query_result_caching(self):
        """Test full query result caching flow"""
        mock_redis = AsyncMock(spec=redis.Redis)
        cache = GraphQLCache(mock_redis)
        
        # Simulate GraphQL query execution
        query_key = CacheKeyBuilder.build_query_key(
            "objectTypes",
            {"branch": "main", "limit": 10},
            ["id", "name", "properties"]
        )
        
        # First execution - cache miss
        mock_redis.get.return_value = None
        result = await cache.get(query_key, CacheLevel.NORMAL)
        assert result is None
        
        # Store result
        query_result = {
            "data": {
                "objectTypes": [
                    {"id": "1", "name": "User"},
                    {"id": "2", "name": "Post"}
                ]
            }
        }
        
        await cache.set(
            query_key,
            query_result,
            CacheLevel.NORMAL,
            dependencies=[
                ("ObjectType", "User"),
                ("ObjectType", "Post")
            ]
        )
        
        # Verify stored with dependencies
        assert mock_redis.sadd.call_count == 2
        
        # Invalidate one object
        await cache.invalidation_tracker.invalidate_entity("ObjectType", "User")
        
        # Should have deleted the query cache
        mock_redis.delete.assert_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])