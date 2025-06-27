"""
Integration test between TerminusDBCacheManager and BranchService
Tests that the real cache properly replaces the dummy SmartCacheManager
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, Mock
from shared.cache.terminusdb_cache import TerminusDBCacheManager
from shared.cache.smart_cache import SmartCacheManager


class TestCacheIntegrationWithBranchService:
    """Test cache integration with services that previously used dummy cache"""
    
    @pytest.mark.asyncio
    async def test_terminusdb_cache_provides_missing_methods(self):
        """Test that TerminusDBCacheManager provides methods that SmartCacheManager lacks"""
        mock_db_client = AsyncMock()
        mock_db_client.create_database = AsyncMock(return_value=True)
        mock_db_client.insert_document = AsyncMock(return_value=True)
        mock_db_client.query_document = AsyncMock(return_value=[])
        
        terminusdb_cache = TerminusDBCacheManager(db_client=mock_db_client)
        await terminusdb_cache.initialize()
        
        smart_cache = SmartCacheManager()
        
        # Methods that SmartCacheManager lacks but BranchService needs
        assert hasattr(terminusdb_cache, 'get_with_optimization')
        assert hasattr(terminusdb_cache, 'warm_cache_for_branch')
        
        assert not hasattr(smart_cache, 'get_with_optimization')
        assert not hasattr(smart_cache, 'warm_cache_for_branch')
        
        # Verify the methods actually work
        result = await terminusdb_cache.get_with_optimization(
            key="test_key",
            db="test_db",
            branch="main",
            query_factory=lambda: "factory_result",
            doc_type="TestDoc"
        )
        assert result == "factory_result"
        
        warm_results = await terminusdb_cache.warm_cache_for_branch(
            db="test_db",
            branch="main",
            doc_types=["Branch", "ChangeProposal"]
        )
        assert isinstance(warm_results, dict)
    
    @pytest.mark.asyncio 
    async def test_cache_replacement_compatibility(self):
        """Test that TerminusDBCacheManager can be a drop-in replacement"""
        mock_db_client = AsyncMock()
        mock_db_client.create_database = AsyncMock(return_value=True)
        mock_db_client.insert_document = AsyncMock(return_value=True)
        
        # Test all basic cache operations that both should support
        terminusdb_cache = TerminusDBCacheManager(db_client=mock_db_client)
        await terminusdb_cache.initialize()
        
        smart_cache = SmartCacheManager()
        
        # Basic operations both should have
        assert hasattr(terminusdb_cache, 'get')
        assert hasattr(terminusdb_cache, 'set') 
        assert hasattr(terminusdb_cache, 'delete')
        assert hasattr(terminusdb_cache, 'clear')
        assert hasattr(terminusdb_cache, 'exists')
        
        assert hasattr(smart_cache, 'get')
        assert hasattr(smart_cache, 'set')
        assert hasattr(smart_cache, 'delete')
        assert hasattr(smart_cache, 'clear')
        assert hasattr(smart_cache, 'exists')
        
        # Test that TerminusDB cache actually works vs dummy
        await terminusdb_cache.set("test", "value")
        assert await terminusdb_cache.get("test") == "value"
        assert await terminusdb_cache.exists("test") is True
        
        # Smart cache should return None/False
        smart_cache.set("test", "value")  # Not async
        assert smart_cache.get("test") is None
        assert smart_cache.exists("test") is False
    
    @pytest.mark.asyncio
    async def test_branch_service_style_usage(self):
        """Test TerminusDB cache with BranchService-style usage patterns"""
        mock_db_client = AsyncMock()
        mock_db_client.create_database = AsyncMock(return_value=True)
        mock_db_client.insert_document = AsyncMock(return_value=True)
        mock_db_client.query_document = AsyncMock(return_value=[])
        
        cache = TerminusDBCacheManager(db_client=mock_db_client)
        await cache.initialize()
        
        # Simulate BranchService._branch_exists usage
        cache_key = "branch_exists:feature/new-feature"
        
        call_count = 0
        def mock_check_branch_exists():
            nonlocal call_count
            call_count += 1
            return True  # Branch exists
        
        # First call - cache miss
        result1 = await cache.get_with_optimization(
            key=cache_key,
            db="oms",
            branch="_system",
            query_factory=mock_check_branch_exists,
            doc_type="Branch"
        )
        
        assert result1 is True
        assert call_count == 1, "Should call query factory on cache miss"
        
        # Second call - cache hit
        result2 = await cache.get_with_optimization(
            key=cache_key,
            db="oms",
            branch="_system", 
            query_factory=mock_check_branch_exists,
            doc_type="Branch"
        )
        
        assert result2 is True
        assert call_count == 1, "Should NOT call query factory on cache hit"
    
    @pytest.mark.asyncio
    async def test_cache_warming_for_branch_service(self):
        """Test cache warming functionality for BranchService"""
        # Mock TerminusDB responses for branch documents
        mock_branch_docs = [
            {"@id": "branch_main", "@type": "Branch", "name": "main"},
            {"@id": "branch_feature", "@type": "Branch", "name": "feature/test"}
        ]
        mock_proposal_docs = [
            {"@id": "proposal_1", "@type": "ChangeProposal", "status": "pending"}
        ]
        
        mock_db_client = AsyncMock()
        mock_db_client.create_database = AsyncMock(return_value=True)
        mock_db_client.insert_document = AsyncMock(return_value=True)
        
        # Mock query responses for different document types
        def mock_query_side_effect(*args, **kwargs):
            query = args[0]
            if "Branch" in str(query):
                return mock_branch_docs  # Return docs directly, not wrapped
            elif "ChangeProposal" in str(query):
                return mock_proposal_docs  # Return docs directly, not wrapped
            return []
        
        mock_db_client.query_document = AsyncMock(side_effect=mock_query_side_effect)
        
        cache = TerminusDBCacheManager(db_client=mock_db_client)
        await cache.initialize()
        
        # Warm cache for branch-related documents
        results = await cache.warm_cache_for_branch(
            db="oms",
            branch="main",
            doc_types=["Branch", "ChangeProposal", "MergeCommit"]
        )
        
        # Verify warming results
        assert results["Branch"] == 2, "Should warm 2 Branch documents"
        assert results["ChangeProposal"] == 1, "Should warm 1 ChangeProposal document"
        assert results["MergeCommit"] == 0, "Should warm 0 MergeCommit documents (none exist)"
        
        # Verify documents were actually cached
        branch_cache_key = "oms:main:Branch:branch_main"
        cached_branch = await cache.get(branch_cache_key)
        # The cached value should be the original doc from the mock
        assert cached_branch == mock_branch_docs[0]
    
    @pytest.mark.asyncio
    async def test_async_query_factory_with_branch_service_pattern(self):
        """Test async query factory pattern that BranchService might use"""
        mock_db_client = AsyncMock()
        mock_db_client.create_database = AsyncMock(return_value=True)
        mock_db_client.insert_document = AsyncMock(return_value=True)
        mock_db_client.query_document = AsyncMock(return_value=[])
        
        cache = TerminusDBCacheManager(db_client=mock_db_client)
        await cache.initialize()
        
        # Simulate an async database query that BranchService might use
        async def mock_async_branch_query():
            await asyncio.sleep(0.01)  # Simulate DB query delay
            return {
                "branch_id": "feature/async-test",
                "created_at": "2024-01-01T00:00:00Z",
                "parent": "main"
            }
        
        # Test caching with async query factory
        cache_key = "branch_data:feature/async-test"
        
        # First call
        start_time = asyncio.get_event_loop().time()
        result1 = await cache.get_with_optimization(
            key=cache_key,
            db="oms",
            branch="_system",
            query_factory=mock_async_branch_query,
            doc_type="Branch"
        )
        first_call_time = asyncio.get_event_loop().time() - start_time
        
        # Second call (should be cached)
        start_time = asyncio.get_event_loop().time()
        result2 = await cache.get_with_optimization(
            key=cache_key,
            db="oms", 
            branch="_system",
            query_factory=mock_async_branch_query,
            doc_type="Branch"
        )
        second_call_time = asyncio.get_event_loop().time() - start_time
        
        # Verify results are the same
        assert result1 == result2
        assert result1["branch_id"] == "feature/async-test"
        
        # Verify second call was faster (cached)
        assert second_call_time < first_call_time, "Cached call should be faster"
        assert second_call_time < 0.005, "Cached call should be very fast"
    
    @pytest.mark.asyncio
    async def test_error_handling_in_cache_integration(self):
        """Test error handling when integrating with BranchService patterns"""
        mock_db_client = AsyncMock()
        mock_db_client.create_database = AsyncMock(return_value=True)
        mock_db_client.insert_document = AsyncMock(return_value=True)
        mock_db_client.query_document = AsyncMock(return_value=[])
        
        cache = TerminusDBCacheManager(db_client=mock_db_client)
        await cache.initialize()
        
        # Test query factory that raises an exception
        def failing_query_factory():
            raise Exception("Database connection failed")
        
        # Should propagate the exception
        with pytest.raises(Exception, match="Database connection failed"):
            await cache.get_with_optimization(
                key="failing_key",
                db="oms",
                branch="main",
                query_factory=failing_query_factory,
                doc_type="Branch"
            )
        
        # Verify cache doesn't store failed results
        assert await cache.get("failing_key") is None
    
    def test_cache_configuration_compatibility(self):
        """Test that cache respects TerminusDB configuration"""
        import os
        
        # Set environment variables that BranchService comments reference
        original_cache_size = os.environ.get("TERMINUSDB_LRU_CACHE_SIZE")
        original_cache_enabled = os.environ.get("TERMINUSDB_CACHE_ENABLED")
        
        try:
            os.environ["TERMINUSDB_LRU_CACHE_SIZE"] = "1000000000"  # 1GB
            os.environ["TERMINUSDB_CACHE_ENABLED"] = "true"
            
            cache = TerminusDBCacheManager()
            
            assert cache.lru_cache_size == 1000000000
            assert cache.enable_internal_cache is True
            
        finally:
            # Restore original values
            if original_cache_size:
                os.environ["TERMINUSDB_LRU_CACHE_SIZE"] = original_cache_size
            else:
                os.environ.pop("TERMINUSDB_LRU_CACHE_SIZE", None)
                
            if original_cache_enabled:
                os.environ["TERMINUSDB_CACHE_ENABLED"] = original_cache_enabled
            else:
                os.environ.pop("TERMINUSDB_CACHE_ENABLED", None)


class TestSmartCacheVsTerminusDBCache:
    """Direct comparison tests between dummy and real cache"""
    
    @pytest.mark.asyncio
    async def test_behavior_difference_verification(self):
        """Verify that the behaviors are actually different - no lies about testing"""
        mock_db_client = AsyncMock()
        mock_db_client.create_database = AsyncMock(return_value=True)
        mock_db_client.insert_document = AsyncMock(return_value=True)
        mock_db_client.query_document = AsyncMock(return_value=[])
        
        real_cache = TerminusDBCacheManager(db_client=mock_db_client)
        await real_cache.initialize()
        
        dummy_cache = SmartCacheManager()
        
        # Set the same value in both
        await real_cache.set("comparison_key", "test_value")
        dummy_cache.set("comparison_key", "test_value")  # Not async
        
        # Verify different behaviors
        real_result = await real_cache.get("comparison_key")
        dummy_result = dummy_cache.get("comparison_key")
        
        assert real_result == "test_value", "Real cache should store and retrieve values"
        assert dummy_result is None, "Dummy cache should always return None"
        
        # Verify exists behavior
        real_exists = await real_cache.exists("comparison_key")
        dummy_exists = dummy_cache.exists("comparison_key")
        
        assert real_exists is True, "Real cache should report existing keys"
        assert dummy_exists is False, "Dummy cache should always report False"
        
        print("✅ VERIFIED: TerminusDBCacheManager actually caches, SmartCacheManager does not")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])