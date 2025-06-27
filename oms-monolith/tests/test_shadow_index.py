"""
Tests for Shadow Index + Switch pattern
Validates near-zero downtime indexing with atomic switch
"""
import pytest
import asyncio
import os
import tempfile
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from core.shadow_index.manager import ShadowIndexManager, ShadowIndexConflictError
from models.shadow_index import (
    ShadowIndexInfo, ShadowIndexState, IndexType, SwitchRequest, SwitchResult,
    estimate_switch_duration
)


class TestShadowIndexManager:
    """Test Shadow Index Manager functionality"""
    
    @pytest.fixture
    def temp_index_dir(self):
        """Create temporary directory for index testing"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.fixture
    def shadow_manager(self, temp_index_dir):
        """Create shadow index manager for testing"""
        return ShadowIndexManager(index_base_path=temp_index_dir)
    
    @pytest.mark.asyncio
    async def test_start_shadow_build(self, shadow_manager):
        """Test starting a shadow index build"""
        shadow_id = await shadow_manager.start_shadow_build(
            branch_name="feature/test-branch",
            index_type=IndexType.SEARCH_INDEX,
            resource_types=["object_type", "link_type"],
            service_name="funnel-service"
        )
        
        assert shadow_id is not None
        
        # Get shadow status
        shadow_info = await shadow_manager.get_shadow_status(shadow_id)
        assert shadow_info is not None
        assert shadow_info.state == ShadowIndexState.BUILDING
        assert shadow_info.branch_name == "feature/test-branch"
        assert shadow_info.index_type == IndexType.SEARCH_INDEX
        assert shadow_info.resource_types == ["object_type", "link_type"]
        assert shadow_info.service_name == "funnel-service"
    
    @pytest.mark.asyncio
    async def test_prevent_duplicate_shadow_builds(self, shadow_manager):
        """Test that duplicate shadow builds for same branch/type are prevented"""
        # Start first shadow build
        shadow_id1 = await shadow_manager.start_shadow_build(
            branch_name="feature/test-branch",
            index_type=IndexType.SEARCH_INDEX,
            resource_types=["object_type"],
            service_name="funnel-service"
        )
        
        # Try to start second shadow build for same branch/type
        with pytest.raises(ShadowIndexConflictError):
            await shadow_manager.start_shadow_build(
                branch_name="feature/test-branch",
                index_type=IndexType.SEARCH_INDEX,
                resource_types=["link_type"],
                service_name="funnel-service"
            )
        
        # But different index type should work
        shadow_id2 = await shadow_manager.start_shadow_build(
            branch_name="feature/test-branch",
            index_type=IndexType.GRAPH_INDEX,
            resource_types=["object_type"],
            service_name="funnel-service"
        )
        
        assert shadow_id1 != shadow_id2
    
    @pytest.mark.asyncio
    async def test_update_build_progress(self, shadow_manager):
        """Test updating build progress"""
        # Start shadow build
        shadow_id = await shadow_manager.start_shadow_build(
            branch_name="feature/progress-test",
            index_type=IndexType.SEARCH_INDEX,
            resource_types=["object_type"],
            service_name="funnel-service"
        )
        
        # Update progress
        success = await shadow_manager.update_build_progress(
            shadow_index_id=shadow_id,
            progress_percent=25,
            estimated_completion_seconds=1800,
            record_count=500,
            service_name="funnel-service"
        )
        
        assert success == True
        
        # Check updated progress
        shadow_info = await shadow_manager.get_shadow_status(shadow_id)
        assert shadow_info.build_progress_percent == 25
        assert shadow_info.estimated_completion_seconds == 1800
        assert shadow_info.record_count == 500
    
    @pytest.mark.asyncio
    async def test_complete_shadow_build(self, shadow_manager, temp_index_dir):
        """Test completing a shadow build"""
        # Start shadow build
        shadow_id = await shadow_manager.start_shadow_build(
            branch_name="feature/complete-test",
            index_type=IndexType.SEARCH_INDEX,
            resource_types=["object_type"],
            service_name="funnel-service"
        )
        
        # Create mock shadow index files
        shadow_info = await shadow_manager.get_shadow_status(shadow_id)
        shadow_path = Path(shadow_info.shadow_index_path)
        shadow_path.mkdir(parents=True, exist_ok=True)
        (shadow_path / "index.dat").write_text("mock index data")
        
        # Complete build
        success = await shadow_manager.complete_shadow_build(
            shadow_index_id=shadow_id,
            index_size_bytes=1024 * 1024,  # 1MB
            record_count=1000,
            service_name="funnel-service"
        )
        
        assert success == True
        
        # Check completion
        shadow_info = await shadow_manager.get_shadow_status(shadow_id)
        assert shadow_info.state == ShadowIndexState.BUILT
        assert shadow_info.index_size_bytes == 1024 * 1024
        assert shadow_info.record_count == 1000
        assert shadow_info.build_progress_percent == 100
        assert shadow_info.completed_at is not None
    
    @pytest.mark.asyncio
    async def test_atomic_switch_success(self, shadow_manager, temp_index_dir):
        """Test successful atomic switch from shadow to primary"""
        # Start and complete shadow build
        shadow_id = await shadow_manager.start_shadow_build(
            branch_name="feature/switch-test",
            index_type=IndexType.SEARCH_INDEX,
            resource_types=["object_type"],
            service_name="funnel-service"
        )
        
        # Create mock shadow index
        shadow_info = await shadow_manager.get_shadow_status(shadow_id)
        shadow_path = Path(shadow_info.shadow_index_path)
        shadow_path.mkdir(parents=True, exist_ok=True)
        (shadow_path / "index.dat").write_text("new index data")
        
        # Complete build
        await shadow_manager.complete_shadow_build(
            shadow_index_id=shadow_id,
            index_size_bytes=2048,
            record_count=100,
            service_name="funnel-service"
        )
        
        # Create switch request
        switch_request = SwitchRequest(
            shadow_index_id=shadow_id,
            force_switch=False,
            validation_checks=["RECORD_COUNT_VALIDATION"],
            backup_current=True,
            switch_timeout_seconds=10
        )
        
        # Perform atomic switch
        switch_result = await shadow_manager.request_atomic_switch(
            shadow_index_id=shadow_id,
            request=switch_request,
            service_name="funnel-service"
        )
        
        # Verify switch success
        assert switch_result.success == True
        assert switch_result.switch_duration_ms >= 0  # Can be 0 for very fast operations
        assert switch_result.validation_passed == True
        assert switch_result.verification_passed == True
        
        # Check shadow state
        shadow_info = await shadow_manager.get_shadow_status(shadow_id)
        assert shadow_info.state == ShadowIndexState.ACTIVE
        assert shadow_info.switched_at is not None
        
        # Verify current index exists and contains new data
        current_path = Path(shadow_info.current_index_path)
        assert current_path.exists()
        assert (current_path / "index.dat").read_text() == "new index data"
    
    @pytest.mark.asyncio
    async def test_switch_validation_failure(self, shadow_manager, temp_index_dir):
        """Test switch validation failure"""
        # Start and complete shadow build with no records
        shadow_id = await shadow_manager.start_shadow_build(
            branch_name="feature/validation-fail",
            index_type=IndexType.SEARCH_INDEX,
            resource_types=["object_type"],
            service_name="funnel-service"
        )
        
        # Create empty shadow index
        shadow_info = await shadow_manager.get_shadow_status(shadow_id)
        shadow_path = Path(shadow_info.shadow_index_path)
        shadow_path.mkdir(parents=True, exist_ok=True)
        
        # Complete build with 0 records (should fail validation)
        await shadow_manager.complete_shadow_build(
            shadow_index_id=shadow_id,
            index_size_bytes=100,
            record_count=0,
            service_name="funnel-service"
        )
        
        # Create switch request with validation
        switch_request = SwitchRequest(
            shadow_index_id=shadow_id,
            force_switch=False,
            validation_checks=["RECORD_COUNT_VALIDATION"],
            backup_current=True,
            switch_timeout_seconds=10
        )
        
        # Perform atomic switch (should fail validation)
        switch_result = await shadow_manager.request_atomic_switch(
            shadow_index_id=shadow_id,
            request=switch_request,
            service_name="funnel-service"
        )
        
        # Verify validation failed
        assert switch_result.success == False
        assert switch_result.validation_passed == False
        assert "no records" in switch_result.validation_errors[0].lower()
        
        # Shadow should still be in BUILT state
        shadow_info = await shadow_manager.get_shadow_status(shadow_id)
        assert shadow_info.state == ShadowIndexState.BUILT
    
    @pytest.mark.asyncio
    async def test_force_switch_bypasses_validation(self, shadow_manager, temp_index_dir):
        """Test that force switch bypasses validation"""
        # Start and complete shadow build with no records
        shadow_id = await shadow_manager.start_shadow_build(
            branch_name="feature/force-switch",
            index_type=IndexType.SEARCH_INDEX,
            resource_types=["object_type"],
            service_name="funnel-service"
        )
        
        # Create shadow index
        shadow_info = await shadow_manager.get_shadow_status(shadow_id)
        shadow_path = Path(shadow_info.shadow_index_path)
        shadow_path.mkdir(parents=True, exist_ok=True)
        (shadow_path / "index.dat").write_text("forced index")
        
        # Complete build with 0 records
        await shadow_manager.complete_shadow_build(
            shadow_index_id=shadow_id,
            index_size_bytes=100,
            record_count=0,
            service_name="funnel-service"
        )
        
        # Create switch request with force
        switch_request = SwitchRequest(
            shadow_index_id=shadow_id,
            force_switch=True,  # Force switch despite validation failures
            validation_checks=["RECORD_COUNT_VALIDATION"],
            backup_current=True,
            switch_timeout_seconds=10
        )
        
        # Perform atomic switch (should succeed despite validation failure)
        switch_result = await shadow_manager.request_atomic_switch(
            shadow_index_id=shadow_id,
            request=switch_request,
            service_name="funnel-service"
        )
        
        # Verify switch succeeded despite validation failure
        assert switch_result.success == True
        assert switch_result.validation_passed == False  # Validation failed
        # But switch proceeded anyway due to force_switch=True
        
        # Shadow should be in ACTIVE state
        shadow_info = await shadow_manager.get_shadow_status(shadow_id)
        assert shadow_info.state == ShadowIndexState.ACTIVE
    
    @pytest.mark.asyncio
    async def test_cancel_shadow_build(self, shadow_manager):
        """Test cancelling a shadow build"""
        # Start shadow build
        shadow_id = await shadow_manager.start_shadow_build(
            branch_name="feature/cancel-test",
            index_type=IndexType.SEARCH_INDEX,
            resource_types=["object_type"],
            service_name="funnel-service"
        )
        
        # Cancel build
        success = await shadow_manager.cancel_shadow_build(
            shadow_index_id=shadow_id,
            service_name="admin",
            reason="Testing cancellation"
        )
        
        assert success == True
        
        # Check cancellation
        shadow_info = await shadow_manager.get_shadow_status(shadow_id)
        assert shadow_info.state == ShadowIndexState.CANCELLED
    
    @pytest.mark.asyncio
    async def test_list_active_shadows(self, shadow_manager):
        """Test listing active shadow indexes"""
        # Start multiple shadow builds
        shadow_id1 = await shadow_manager.start_shadow_build(
            branch_name="feature/list-test-1",
            index_type=IndexType.SEARCH_INDEX,
            resource_types=["object_type"],
            service_name="funnel-service"
        )
        
        shadow_id2 = await shadow_manager.start_shadow_build(
            branch_name="feature/list-test-2",
            index_type=IndexType.GRAPH_INDEX,
            resource_types=["link_type"],
            service_name="funnel-service"
        )
        
        # List all shadows
        all_shadows = await shadow_manager.list_active_shadows()
        assert len(all_shadows) >= 2
        
        shadow_ids = [s.id for s in all_shadows]
        assert shadow_id1 in shadow_ids
        assert shadow_id2 in shadow_ids
        
        # List shadows for specific branch
        branch_shadows = await shadow_manager.list_active_shadows("feature/list-test-1")
        assert len(branch_shadows) == 1
        assert branch_shadows[0].id == shadow_id1


class TestShadowIndexUtilities:
    """Test Shadow Index utility functions"""
    
    def test_estimate_switch_duration(self):
        """Test switch duration estimation"""
        # Small index with atomic rename (fastest)
        duration = estimate_switch_duration(1024 * 1024, "ATOMIC_RENAME")  # 1MB
        assert 1 <= duration <= 3
        
        # Large index with atomic rename (still fast)
        duration = estimate_switch_duration(1024 * 1024 * 1024, "ATOMIC_RENAME")  # 1GB
        assert duration == 3  # Capped at 3 seconds
        
        # Small index with copy strategy (slower)
        duration = estimate_switch_duration(1024 * 1024, "COPY_AND_REPLACE")  # 1MB
        assert 5 <= duration <= 30
        
        # No size provided
        duration = estimate_switch_duration(None, "ATOMIC_RENAME")
        assert duration == 5  # Default


class TestShadowIndexIntegration:
    """Integration tests for Shadow Index with lock manager"""
    
    @pytest.mark.asyncio
    async def test_shadow_index_requires_minimal_lock(self, temp_index_dir_integration):
        """Test that shadow index only requires lock during switch"""
        shadow_manager = ShadowIndexManager(index_base_path=temp_index_dir_integration)
        
        # Start shadow build (no lock required)
        shadow_id = await shadow_manager.start_shadow_build(
            branch_name="feature/minimal-lock-test",
            index_type=IndexType.SEARCH_INDEX,
            resource_types=["object_type"],
            service_name="funnel-service"
        )
        
        # Update progress (no lock required)
        await shadow_manager.update_build_progress(
            shadow_index_id=shadow_id,
            progress_percent=50,
            service_name="funnel-service"
        )
        
        # Complete build (no lock required)
        shadow_info = await shadow_manager.get_shadow_status(shadow_id)
        shadow_path = Path(shadow_info.shadow_index_path)
        shadow_path.mkdir(parents=True, exist_ok=True)
        (shadow_path / "index.dat").write_text("test data")
        
        await shadow_manager.complete_shadow_build(
            shadow_index_id=shadow_id,
            index_size_bytes=1024,
            record_count=100,
            service_name="funnel-service"
        )
        
        # Switch requires lock (but very brief)
        switch_request = SwitchRequest(
            shadow_index_id=shadow_id,
            force_switch=False,
            switch_timeout_seconds=5  # Very short timeout
        )
        
        start_time = datetime.now(timezone.utc)
        
        # Mock the lock manager to track lock duration
        with patch('core.shadow_index.manager.get_lock_manager') as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.acquire_lock = AsyncMock(return_value="test-lock-id")
            mock_manager.release_lock = AsyncMock(return_value=True)
            mock_get_manager.return_value = mock_manager
            
            switch_result = await shadow_manager.request_atomic_switch(
                shadow_index_id=shadow_id,
                request=switch_request,
                service_name="funnel-service"
            )
        
        end_time = datetime.now(timezone.utc)
        total_duration = (end_time - start_time).total_seconds()
        
        # Verify switch was fast (< 10 seconds)
        assert total_duration < 10
        assert switch_result.success == True
        assert switch_result.switch_duration_ms < 10000  # < 10 seconds
        
        # Verify lock was acquired and released
        mock_manager.acquire_lock.assert_called_once()
        mock_manager.release_lock.assert_called_once()
    
    @pytest.fixture
    def temp_index_dir_integration(self):
        """Create temporary directory for integration testing"""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_concurrent_development_during_shadow_build(self, temp_index_dir_integration):
        """Test that development can continue during shadow index building"""
        from core.branch.lock_manager import BranchLockManager
        
        lock_manager = BranchLockManager()
        shadow_manager = ShadowIndexManager(index_base_path=temp_index_dir_integration)
        
        branch_name = "feature/concurrent-development"
        
        # Start shadow build (background, no locks)
        shadow_id = await shadow_manager.start_shadow_build(
            branch_name=branch_name,
            index_type=IndexType.SEARCH_INDEX,
            resource_types=["object_type"],
            service_name="funnel-service"
        )
        
        # While shadow is building, developers should be able to work
        # (This simulates normal development continuing during background indexing)
        
        # Check write permissions (should be allowed during shadow build)
        can_write, reason = await lock_manager.check_write_permission(
            branch_name=branch_name,
            action="write",
            resource_type="object_type"
        )
        
        # Should be able to write during shadow build
        assert can_write == True
        
        # Simulate more development work
        can_write_link, reason = await lock_manager.check_write_permission(
            branch_name=branch_name,
            action="write", 
            resource_type="link_type"
        )
        
        assert can_write_link == True
        
        # Complete shadow build
        shadow_info = await shadow_manager.get_shadow_status(shadow_id)
        shadow_path = Path(shadow_info.shadow_index_path)
        shadow_path.mkdir(parents=True, exist_ok=True)
        (shadow_path / "index.dat").write_text("test data")
        
        await shadow_manager.complete_shadow_build(
            shadow_index_id=shadow_id,
            index_size_bytes=1024,
            record_count=100,
            service_name="funnel-service"
        )
        
        # Even after build completion, should still be able to work
        # (Only switch operation requires brief lock)
        can_write_after, reason = await lock_manager.check_write_permission(
            branch_name=branch_name,
            action="write",
            resource_type="object_type"
        )
        
        assert can_write_after == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])