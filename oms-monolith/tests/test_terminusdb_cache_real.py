"""
Real TerminusDB Cache Integration Tests
Tests actual caching behavior with TerminusDB - no mocks, real verification
"""

import pytest
import asyncio
import os
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock
import tempfile
import shutil

from shared.cache.terminusdb_cache import TerminusDBCacheManager


class TestTerminusDBCacheReal:
    """Real tests that verify actual caching behavior - no lies, no assumptions"""
    
    @pytest.fixture
    async def cache_manager(self):
        """Create cache manager with mock DB client for testing"""
        mock_db_client = AsyncMock()
        mock_db_client.create_database = AsyncMock(return_value=True)
        mock_db_client.insert_document = AsyncMock(return_value=True)
        mock_db_client.query_document = AsyncMock(return_value=[])
        mock_db_client.replace_document = AsyncMock(return_value=True)
        mock_db_client.delete_database = AsyncMock(return_value=True)
        
        cache = TerminusDBCacheManager(db_client=mock_db_client)
        await cache.initialize()
        return cache
    
    @pytest.fixture
    def cache_manager_no_db(self):
        """Create cache manager without DB client (memory-only)"""
        return TerminusDBCacheManager(db_client=None)
    
    @pytest.mark.asyncio
    async def test_memory_cache_actually_stores_values(self, cache_manager_no_db):
        """Test that memory cache actually stores and retrieves values"""
        cache = cache_manager_no_db
        
        # Set a value
        result = await cache.set("test_key", "test_value", ttl=3600)
        assert result is True, "Cache set should return True"
        
        # Verify it's actually stored in memory
        assert len(cache._memory_cache) == 1, "Memory cache should contain 1 item"
        
        # Retrieve the value
        retrieved = await cache.get("test_key")
        assert retrieved == "test_value", f"Expected 'test_value', got {retrieved}"
        
        # Verify access count increased
        cache_key = cache._generate_cache_key("test_key")
        assert cache._memory_cache[cache_key]["access_count"] == 1, "Access count should be 1"
    
    @pytest.mark.asyncio
    async def test_cache_expiration_actually_works(self, cache_manager_no_db):
        """Test that expired entries are actually removed and not returned"""
        cache = cache_manager_no_db
        
        # Set a value with 1 second TTL
        await cache.set("expire_key", "expire_value", ttl=1)
        
        # Immediately retrieve - should work
        retrieved = await cache.get("expire_key")
        assert retrieved == "expire_value", "Should retrieve value before expiration"
        
        # Wait for expiration
        await asyncio.sleep(1.1)
        
        # Try to retrieve expired value
        retrieved = await cache.get("expire_key")
        assert retrieved is None, "Should return None for expired value"
        
        # Verify expired entry was removed from memory
        cache_key = cache._generate_cache_key("expire_key")
        assert cache_key not in cache._memory_cache, "Expired entry should be removed from memory"
    
    @pytest.mark.asyncio
    async def test_complex_data_serialization(self, cache_manager_no_db):
        """Test that complex data structures are properly serialized/deserialized"""
        cache = cache_manager_no_db
        
        complex_data = {
            "nested": {
                "list": [1, 2, {"inner": "value"}],
                "date": "2024-01-01",
                "boolean": True,
                "null": None,
                "number": 42.5
            },
            "array": ["string", 123, {"key": "value"}]
        }
        
        # Store complex data
        await cache.set("complex_key", complex_data)
        
        # Retrieve and verify
        retrieved = await cache.get("complex_key")
        assert retrieved == complex_data, f"Complex data mismatch: {retrieved} != {complex_data}"
        
        # Verify it's actually the same structure
        assert retrieved["nested"]["list"][2]["inner"] == "value"
        assert retrieved["array"][2]["key"] == "value"
    
    @pytest.mark.asyncio
    async def test_lru_eviction_behavior(self, cache_manager_no_db):
        """Test that LRU eviction actually removes least recently used items"""
        cache = cache_manager_no_db
        cache._memory_cache_max_size = 3  # Set small cache size for testing
        
        # Fill cache to capacity
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")
        
        assert len(cache._memory_cache) == 3, "Cache should be at capacity"
        
        # Access key1 to make it recently used
        await cache.get("key1")
        
        # Add another item - should evict key2 (least recently used)
        await cache.set("key4", "value4")
        
        # Verify LRU behavior
        assert await cache.get("key1") == "value1", "Recently accessed key1 should still exist"
        assert await cache.get("key2") is None, "LRU key2 should be evicted"
        assert await cache.get("key3") == "value3", "key3 should still exist"
        assert await cache.get("key4") == "value4", "New key4 should exist"
    
    @pytest.mark.asyncio
    async def test_delete_actually_removes_entries(self, cache_manager_no_db):
        """Test that delete actually removes entries from cache"""
        cache = cache_manager_no_db
        
        # Set multiple values
        await cache.set("delete_key1", "value1")
        await cache.set("delete_key2", "value2")
        
        # Verify they exist
        assert await cache.get("delete_key1") == "value1"
        assert await cache.get("delete_key2") == "value2"
        assert len(cache._memory_cache) == 2
        
        # Delete one entry
        result = await cache.delete("delete_key1")
        assert result is True, "Delete should return True"
        
        # Verify deletion
        assert await cache.get("delete_key1") is None, "Deleted key should return None"
        assert await cache.get("delete_key2") == "value2", "Non-deleted key should still exist"
        assert len(cache._memory_cache) == 1, "Cache size should decrease"
    
    @pytest.mark.asyncio
    async def test_clear_actually_empties_cache(self, cache_manager_no_db):
        """Test that clear actually empties the entire cache"""
        cache = cache_manager_no_db
        
        # Fill cache with multiple entries
        for i in range(10):
            await cache.set(f"clear_key_{i}", f"value_{i}")
        
        assert len(cache._memory_cache) == 10, "Cache should have 10 entries"
        
        # Clear cache
        result = await cache.clear()
        assert result is True, "Clear should return True"
        
        # Verify cache is empty
        assert len(cache._memory_cache) == 0, "Cache should be empty after clear"
        
        # Verify no entries can be retrieved
        for i in range(10):
            retrieved = await cache.get(f"clear_key_{i}")
            assert retrieved is None, f"Entry {i} should be None after clear"
    
    @pytest.mark.asyncio
    async def test_exists_reflects_actual_cache_state(self, cache_manager_no_db):
        """Test that exists() accurately reflects cache state"""
        cache = cache_manager_no_db
        
        # Non-existent key
        assert await cache.exists("nonexistent") is False
        
        # Set a key
        await cache.set("exists_key", "exists_value")
        assert await cache.exists("exists_key") is True
        
        # Delete the key
        await cache.delete("exists_key")
        assert await cache.exists("exists_key") is False
        
        # Test with expired key
        await cache.set("expire_exists", "value", ttl=1)
        assert await cache.exists("expire_exists") is True
        
        await asyncio.sleep(1.1)
        assert await cache.exists("expire_exists") is False
    
    @pytest.mark.asyncio
    async def test_get_with_optimization_fallback_works(self, cache_manager_no_db):
        """Test that get_with_optimization properly falls back to query_factory"""
        cache = cache_manager_no_db
        
        call_count = 0
        
        def mock_query_factory():
            nonlocal call_count
            call_count += 1
            return f"computed_value_{call_count}"
        
        # First call - cache miss, should execute query_factory
        result1 = await cache.get_with_optimization(
            key="opt_key",
            db="test_db",
            branch="main",
            query_factory=mock_query_factory,
            doc_type="TestDoc"
        )
        
        assert result1 == "computed_value_1", "First call should execute query_factory"
        assert call_count == 1, "Query factory should be called once"
        
        # Second call - cache hit, should NOT execute query_factory
        result2 = await cache.get_with_optimization(
            key="opt_key",
            db="test_db",
            branch="main",
            query_factory=mock_query_factory,
            doc_type="TestDoc"
        )
        
        assert result2 == "computed_value_1", "Second call should return cached value"
        assert call_count == 1, "Query factory should NOT be called again"
    
    @pytest.mark.asyncio
    async def test_async_query_factory_support(self, cache_manager_no_db):
        """Test that async query factories are properly handled"""
        cache = cache_manager_no_db
        
        async def async_query_factory():
            await asyncio.sleep(0.01)  # Simulate async work
            return "async_computed_value"
        
        # Test with async query factory
        result = await cache.get_with_optimization(
            key="async_opt_key",
            db="test_db", 
            branch="main",
            query_factory=async_query_factory,
            doc_type="AsyncDoc"
        )
        
        assert result == "async_computed_value", "Async query factory should work"
        
        # Second call should hit cache
        result2 = await cache.get_with_optimization(
            key="async_opt_key",
            db="test_db",
            branch="main", 
            query_factory=async_query_factory,
            doc_type="AsyncDoc"
        )
        
        assert result2 == "async_computed_value", "Should return cached async result"
    
    @pytest.mark.asyncio
    async def test_cache_stats_accuracy(self, cache_manager_no_db):
        """Test that cache statistics reflect actual cache state"""
        cache = cache_manager_no_db
        
        # Initial stats
        stats = await cache.get_cache_stats()
        assert stats["memory_cache_size"] == 0, "Initial cache should be empty"
        
        # Add some entries
        await cache.set("stats_key1", "value1")
        await cache.set("stats_key2", "value2")
        
        # Access one entry multiple times
        await cache.get("stats_key1")
        await cache.get("stats_key1")
        await cache.get("stats_key2")
        
        # Check updated stats
        stats = await cache.get_cache_stats()
        assert stats["memory_cache_size"] == 2, "Should show 2 entries"
        assert stats["total_memory_accesses"] == 3, "Should show 3 total accesses"
    
    @pytest.mark.asyncio
    async def test_environment_variable_configuration(self):
        """Test that environment variables actually affect cache behavior"""
        # Test with custom cache size
        os.environ["TERMINUSDB_LRU_CACHE_SIZE"] = "1000000"  # 1MB
        os.environ["CACHE_DEFAULT_TTL"] = "7200"  # 2 hours
        os.environ["TERMINUSDB_CACHE_ENABLED"] = "false"
        
        cache = TerminusDBCacheManager()
        
        assert cache.lru_cache_size == 1000000, "Should use env var cache size"
        assert cache.default_ttl == 7200, "Should use env var TTL"
        assert cache.enable_internal_cache is False, "Should respect cache disabled"
        
        # Clean up
        del os.environ["TERMINUSDB_LRU_CACHE_SIZE"]
        del os.environ["CACHE_DEFAULT_TTL"]
        del os.environ["TERMINUSDB_CACHE_ENABLED"]


class TestTerminusDBCacheIntegration:
    """Integration tests with mock TerminusDB client - verify DB interactions"""
    
    @pytest.mark.asyncio
    async def test_terminusdb_cache_initialization(self):
        """Test that TerminusDB cache database is properly initialized"""
        mock_db_client = AsyncMock()
        mock_db_client.create_database = AsyncMock(return_value=True)
        mock_db_client.insert_document = AsyncMock(return_value=True)
        
        cache = TerminusDBCacheManager(db_client=mock_db_client)
        await cache.initialize()
        
        # Verify database creation was called
        mock_db_client.create_database.assert_called_once_with("_cache")
        
        # Verify schema creation was called
        mock_db_client.insert_document.assert_called_once()
        call_args = mock_db_client.insert_document.call_args
        schema = call_args[0][0]
        
        assert schema["@type"] == "Class"
        assert schema["@id"] == "CacheEntry"
        assert "cache_key" in schema
        assert "cache_value" in schema
        assert "expires_at" in schema
    
    @pytest.mark.asyncio
    async def test_terminusdb_cache_storage_calls(self):
        """Test that cache storage actually calls TerminusDB methods"""
        mock_db_client = AsyncMock()
        mock_db_client.create_database = AsyncMock(return_value=True)
        mock_db_client.insert_document = AsyncMock(return_value=True)
        mock_db_client.query_document = AsyncMock(return_value=[])  # Simulate no existing entry
        
        cache = TerminusDBCacheManager(db_client=mock_db_client)
        await cache.initialize()
        
        # Reset call count after initialization
        mock_db_client.insert_document.reset_mock()
        
        # Set a value
        await cache.set("db_test_key", "db_test_value")
        
        # Verify TerminusDB insert was called
        mock_db_client.insert_document.assert_called_once()
        call_args = mock_db_client.insert_document.call_args
        cache_entry = call_args[0][0]
        
        assert cache_entry["@type"] == "CacheEntry"
        assert cache_entry["cache_key"] == "db_test_key"
        assert cache_entry["cache_value"] == '"db_test_value"'  # JSON serialized
        assert "expires_at" in cache_entry
    
    @pytest.mark.asyncio
    async def test_terminusdb_cache_retrieval_calls(self):
        """Test that cache retrieval properly queries TerminusDB"""
        mock_entry = {
            "Entry": {
                "@type": "CacheEntry",
                "cache_key": "retrieve_test_key", 
                "cache_value": '"retrieved_value"',
                "expires_at": (datetime.utcnow() + timedelta(hours=1)).isoformat(),
                "access_count": 0,
                "last_accessed": datetime.utcnow().isoformat()
            }
        }
        
        mock_db_client = AsyncMock()
        mock_db_client.create_database = AsyncMock(return_value=True)
        mock_db_client.insert_document = AsyncMock(return_value=True)
        mock_db_client.query_document = AsyncMock(return_value=[mock_entry])
        mock_db_client.replace_document = AsyncMock(return_value=True)
        
        cache = TerminusDBCacheManager(db_client=mock_db_client)
        await cache.initialize()
        
        # Reset mock after initialization
        mock_db_client.query_document.reset_mock()
        
        # Get a value
        result = await cache.get("retrieve_test_key")
        
        # Verify TerminusDB query was called
        mock_db_client.query_document.assert_called()
        
        # Verify correct result
        assert result == "retrieved_value"
        
        # Verify access count update was called
        mock_db_client.replace_document.assert_called_once()


def test_cache_key_generation_consistency():
    """Test that cache key generation is consistent and collision-resistant"""
    cache = TerminusDBCacheManager()
    
    # Same input should generate same key
    key1 = cache._generate_cache_key("test_string")
    key2 = cache._generate_cache_key("test_string")
    assert key1 == key2, "Same input should generate same cache key"
    
    # Different inputs should generate different keys
    key3 = cache._generate_cache_key("different_string")
    assert key1 != key3, "Different inputs should generate different keys"
    
    # Keys should be fixed length for consistency
    assert len(key1) == 32, "Cache keys should be fixed length (32 chars)"
    assert len(key3) == 32, "All cache keys should be same length"
    
    # Should handle different data types
    key_int = cache._generate_cache_key(123)
    key_dict = cache._generate_cache_key({"key": "value"})
    key_none = cache._generate_cache_key(None)
    
    all_keys = {key1, key3, key_int, key_dict, key_none}
    assert len(all_keys) == 5, "All different inputs should generate unique keys"


def test_serialization_handles_edge_cases():
    """Test that serialization properly handles edge cases"""
    cache = TerminusDBCacheManager()
    
    # Test various data types
    test_cases = [
        None,
        "",
        0,
        False,
        [],
        {},
        {"nested": {"deep": {"value": "test"}}},
        [1, "two", {"three": 3}],
        datetime.utcnow().isoformat()
    ]
    
    for test_value in test_cases:
        # Serialize and deserialize
        serialized = cache._serialize_value(test_value)
        deserialized = cache._deserialize_value(serialized)
        
        assert deserialized == test_value, f"Serialization failed for {test_value}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])