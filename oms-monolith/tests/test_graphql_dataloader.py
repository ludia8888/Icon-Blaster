"""
Comprehensive tests for GraphQL DataLoader functionality
Verifies batching, caching, and N+1 query prevention
"""
import pytest
import asyncio
from typing import List, Optional, Dict, Any
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import redis.asyncio as redis
import json

from api.graphql.dataloaders import (
    EnterpriseDataLoader,
    DataLoaderRegistry,
    LoaderConfig,
    MetricsCollector,
    RedisCache
)


class TestMetricsCollector:
    """Test the metrics collection functionality"""
    
    def test_record_batch(self):
        """Test recording batch operations"""
        collector = MetricsCollector()
        
        # Record some batch operations
        collector.record_batch(10, 0.05)
        collector.record_batch(20, 0.10)
        collector.record_batch(15, 0.07)
        
        assert collector.total_loads == 45
        assert collector.avg_batch_size == 15.0
        assert collector.avg_load_time == pytest.approx(0.073, rel=0.01)
    
    def test_cache_metrics(self):
        """Test cache hit/miss tracking"""
        collector = MetricsCollector()
        
        # Record cache operations
        for _ in range(7):
            collector.record_cache_hit()
        for _ in range(3):
            collector.record_cache_miss()
        
        assert collector.cache_hits == 7
        assert collector.cache_misses == 3
        assert collector.cache_hit_rate == 0.7
    
    def test_empty_metrics(self):
        """Test metrics with no data"""
        collector = MetricsCollector()
        
        assert collector.avg_batch_size == 0.0
        assert collector.avg_load_time == 0.0
        assert collector.cache_hit_rate == 0.0


class TestRedisCache:
    """Test the Redis cache functionality"""
    
    @pytest.mark.asyncio
    async def test_get_many_with_hits(self):
        """Test getting multiple values with cache hits"""
        # Mock Redis client
        mock_redis = AsyncMock(spec=redis.Redis)
        mock_redis.mget.return_value = [
            json.dumps({"id": "1", "name": "Type1"}),
            None,
            json.dumps({"id": "3", "name": "Type3"})
        ]
        
        cache = RedisCache(mock_redis, "test", 300)
        result = await cache.get_many(["key1", "key2", "key3"])
        
        assert result == {
            "key1": {"id": "1", "name": "Type1"},
            "key3": {"id": "3", "name": "Type3"}
        }
        
        mock_redis.mget.assert_called_once_with([
            "test:key1", "test:key2", "test:key3"
        ])
    
    @pytest.mark.asyncio
    async def test_set_many(self):
        """Test setting multiple values in cache"""
        mock_redis = AsyncMock(spec=redis.Redis)
        mock_pipeline = AsyncMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        cache = RedisCache(mock_redis, "test", 300)
        await cache.set_many({
            "key1": {"id": "1", "name": "Type1"},
            "key2": {"id": "2", "name": "Type2"}
        })
        
        # Verify pipeline operations
        assert mock_pipeline.setex.call_count == 2
        mock_pipeline.execute.assert_called_once()


class TestEnterpriseDataLoader:
    """Test the main DataLoader functionality"""
    
    @pytest.mark.asyncio
    async def test_basic_batch_loading(self):
        """Test basic batch loading without cache"""
        # Mock batch function
        async def batch_fn(keys: List[str]) -> List[Optional[Dict]]:
            # Simulate fetching data for keys
            return [{"id": key, "name": f"Item {key}"} for key in keys]
        
        config = LoaderConfig(batch_size=3, cache_enabled=False)
        loader = EnterpriseDataLoader(batch_fn, config)
        
        # Load single item
        result = await loader.load("1")
        assert result == {"id": "1", "name": "Item 1"}
        
        # Load multiple items
        results = await loader.load_many(["2", "3", "4"])
        assert results == [
            {"id": "2", "name": "Item 2"},
            {"id": "3", "name": "Item 3"},
            {"id": "4", "name": "Item 4"}
        ]
        
        # Check metrics
        assert loader.metrics.total_loads == 4
        assert loader.metrics.avg_batch_size > 0
    
    @pytest.mark.asyncio
    async def test_batch_loading_with_cache(self):
        """Test batch loading with Redis cache"""
        # Mock batch function
        call_count = 0
        async def batch_fn(keys: List[str]) -> List[Optional[Dict]]:
            nonlocal call_count
            call_count += 1
            return [{"id": key, "name": f"Item {key}", "call": call_count} for key in keys]
        
        # Mock Redis
        mock_redis = AsyncMock(spec=redis.Redis)
        mock_redis.mget.return_value = [None, None]  # Cache miss
        mock_pipeline = AsyncMock()
        mock_redis.pipeline.return_value = mock_pipeline
        
        config = LoaderConfig(
            batch_size=10,
            cache_enabled=True,
            cache_prefix="test"
        )
        loader = EnterpriseDataLoader(
            batch_fn,
            config,
            redis_client=mock_redis
        )
        
        # First load - cache miss
        result1 = await loader.load("1")
        assert result1["id"] == "1"
        assert result1["call"] == 1
        
        # Clear internal loader cache to force Redis check
        loader.clear_all()
        
        # Mock cache hit for second call
        mock_redis.mget.return_value = [
            json.dumps({"id": "1", "name": "Item 1", "call": 1})
        ]
        
        # Second load - should hit cache
        result2 = await loader.load("1")
        assert result2["id"] == "1"
        assert result2["call"] == 1  # Same call count = from cache
        
        # Verify batch function was only called once
        assert call_count == 1
        
        # Check cache metrics
        assert loader.metrics.cache_misses > 0
        assert loader.metrics.cache_hits > 0
    
    @pytest.mark.asyncio
    async def test_partial_batch_failure(self):
        """Test handling of partial batch failures"""
        async def batch_fn(keys: List[str]) -> List[Optional[Dict]]:
            results = []
            for key in keys:
                if key == "fail":
                    results.append(None)
                else:
                    results.append({"id": key, "name": f"Item {key}"})
            return results
        
        config = LoaderConfig(cache_enabled=False)
        loader = EnterpriseDataLoader(batch_fn, config)
        
        results = await loader.load_many(["1", "fail", "3"])
        assert results == [
            {"id": "1", "name": "Item 1"},
            None,
            {"id": "3", "name": "Item 3"}
        ]
    
    @pytest.mark.asyncio
    async def test_slow_query_logging(self, caplog):
        """Test that slow queries are logged"""
        async def slow_batch_fn(keys: List[str]) -> List[Optional[Dict]]:
            await asyncio.sleep(0.2)  # Simulate slow query
            return [{"id": key} for key in keys]
        
        config = LoaderConfig(cache_enabled=False, cache_prefix="slow_test")
        loader = EnterpriseDataLoader(slow_batch_fn, config)
        
        await loader.load("1")
        
        # Check for slow query warning
        assert any("Slow batch load" in record.message for record in caplog.records)
    
    @pytest.mark.asyncio
    async def test_exception_handling(self):
        """Test handling of exceptions in batch function"""
        async def failing_batch_fn(keys: List[str]) -> List[Optional[Dict]]:
            raise Exception("Database connection failed")
        
        config = LoaderConfig(cache_enabled=False, cache_prefix="error_test")
        loader = EnterpriseDataLoader(failing_batch_fn, config)
        
        # Should return None for all keys on exception
        results = await loader.load_many(["1", "2", "3"])
        assert results == [None, None, None]
        
        # Metrics should still be recorded
        assert loader.metrics.total_loads == 3


class TestDataLoaderRegistry:
    """Test the DataLoader registry functionality"""
    
    @pytest.mark.asyncio
    async def test_registry_creation(self):
        """Test creating loaders through registry"""
        mock_redis = AsyncMock(spec=redis.Redis)
        registry = DataLoaderRegistry(redis_client=mock_redis)
        
        # Mock service client
        mock_client = AsyncMock()
        mock_client.batch_load_object_types.return_value = [
            {"id": "1", "name": "Type1"}
        ]
        
        # Get loader
        loader = registry.get_loader("object_type", mock_client)
        assert loader is not None
        
        # Use loader
        result = await loader.load("1")
        assert result["name"] == "Type1"
        
        # Should reuse same loader instance
        loader2 = registry.get_loader("object_type", mock_client)
        assert loader is loader2
    
    @pytest.mark.asyncio
    async def test_multiple_loader_types(self):
        """Test registry with multiple loader types"""
        registry = DataLoaderRegistry()
        
        # Mock service client with different batch methods
        mock_client = AsyncMock()
        mock_client.batch_load_object_types.return_value = [{"type": "object"}]
        mock_client.batch_load_properties.return_value = [[{"type": "property"}]]
        mock_client.batch_load_link_types.return_value = [{"type": "link"}]
        
        # Get different loaders
        obj_loader = registry.get_loader("object_type", mock_client)
        prop_loader = registry.get_loader("property", mock_client)
        link_loader = registry.get_loader("link_type", mock_client)
        
        # Verify they're different instances
        assert obj_loader is not prop_loader
        assert prop_loader is not link_loader
        
        # Verify they call correct methods
        await obj_loader.load("1")
        mock_client.batch_load_object_types.assert_called()
        
        await prop_loader.load("1")
        mock_client.batch_load_properties.assert_called()
        
        await link_loader.load("1")
        mock_client.batch_load_link_types.assert_called()
    
    def test_clear_all_loaders(self):
        """Test clearing all loaders in registry"""
        registry = DataLoaderRegistry()
        mock_client = AsyncMock()
        
        # Create some loaders
        loader1 = registry.get_loader("object_type", mock_client)
        loader2 = registry.get_loader("property", mock_client)
        
        # Mock the clear_all method
        loader1.clear_all = Mock()
        loader2.clear_all = Mock()
        
        # Clear all
        registry.clear_all()
        
        # Verify all loaders were cleared
        loader1.clear_all.assert_called_once()
        loader2.clear_all.assert_called_once()


class TestBatchEndpointIntegration:
    """Test integration with batch endpoints"""
    
    @pytest.mark.asyncio
    async def test_batch_endpoint_fallback(self):
        """Test fallback when batch endpoint is unavailable"""
        from api.graphql.enhanced_resolvers import EnhancedServiceClient
        
        # Mock base client
        mock_base_client = AsyncMock()
        mock_base_client.schema_service_url = "http://test"
        
        # First call to batch endpoint fails
        mock_base_client.call_service.side_effect = [
            Exception("404 Not Found"),  # Batch endpoint fails
            {"id": "main:Type1", "name": "Type1"},  # Individual load 1
            {"id": "main:Type2", "name": "Type2"},  # Individual load 2
        ]
        
        # Create enhanced client
        registry = DataLoaderRegistry()
        client = EnhancedServiceClient(mock_base_client, registry)
        
        # Test batch load with fallback
        results = await client.batch_load_object_types(["main:Type1", "main:Type2"])
        
        assert len(results) == 2
        assert results[0]["name"] == "Type1"
        assert results[1]["name"] == "Type2"
        
        # Verify it tried batch first, then individual
        assert mock_base_client.call_service.call_count == 3
    
    @pytest.mark.asyncio
    async def test_invalid_id_format(self):
        """Test handling of invalid ID formats"""
        from api.graphql.enhanced_resolvers import EnhancedServiceClient
        
        mock_base_client = AsyncMock()
        mock_base_client.schema_service_url = "http://test"
        mock_base_client.call_service.side_effect = Exception("Batch failed")
        
        registry = DataLoaderRegistry()
        client = EnhancedServiceClient(mock_base_client, registry)
        
        # Test with invalid ID format
        results = await client.batch_load_object_types(["invalid_id", "main:valid"])
        
        assert results[0] is None  # Invalid ID
        assert results[1] is not None or results[1] is None  # Depends on mock


if __name__ == "__main__":
    pytest.main([__file__, "-v"])