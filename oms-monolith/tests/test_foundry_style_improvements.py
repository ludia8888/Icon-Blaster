"""
Tests for Foundry-style Schema Freeze improvements
Validates granular locking, better UX, and minimal scope locking
"""
import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from core.branch.lock_manager import BranchLockManager, LockConflictError
from models.branch_state import (
    BranchState, BranchLock, BranchStateInfo,
    LockType, LockScope
)
from middleware.schema_freeze_middleware import SchemaFreezeMiddleware


class TestFoundryStyleLocking:
    """Test Foundry-style granular locking improvements"""
    
    @pytest.fixture
    def lock_manager(self):
        """Create a lock manager for testing"""
        return BranchLockManager()
    
    @pytest.mark.asyncio
    async def test_foundry_style_resource_type_locking(self, lock_manager):
        """Test that default locking is resource-type specific, not full branch"""
        # Test new lock_for_indexing with default (Foundry-style) behavior
        lock_ids = await lock_manager.lock_for_indexing(
            branch_name="feature/user-schema",
            locked_by="funnel-service",
            resource_types=["object_type", "link_type"]  # Specific types only
        )
        
        # Should return multiple lock IDs (one per resource type)
        assert isinstance(lock_ids, list)
        assert len(lock_ids) == 2
        
        # Get branch state
        branch_state = await lock_manager.get_branch_state("feature/user-schema")
        
        # Branch should remain ACTIVE (not LOCKED_FOR_WRITE)
        assert branch_state.current_state == BranchState.ACTIVE
        
        # Should have 2 active locks with RESOURCE_TYPE scope
        active_locks = [lock for lock in branch_state.active_locks if lock.is_active]
        assert len(active_locks) == 2
        
        for lock in active_locks:
            assert lock.lock_scope == LockScope.RESOURCE_TYPE
            assert lock.lock_type == LockType.INDEXING
            assert lock.resource_type in ["object_type", "link_type"]
    
    @pytest.mark.asyncio
    async def test_partial_indexing_completion(self, lock_manager):
        """Test that partial indexing completion works correctly"""
        # Start indexing multiple resource types
        lock_ids = await lock_manager.lock_for_indexing(
            branch_name="feature/mixed-schema",
            resource_types=["object_type", "link_type", "action_type"]
        )
        
        assert len(lock_ids) == 3
        
        # Complete indexing for just object_type
        success = await lock_manager.complete_indexing(
            branch_name="feature/mixed-schema",
            resource_types=["object_type"]
        )
        
        assert success
        
        # Check that only object_type lock is released
        branch_state = await lock_manager.get_branch_state("feature/mixed-schema")
        active_locks = [lock for lock in branch_state.active_locks if lock.is_active]
        
        # Should have 2 remaining locks
        assert len(active_locks) == 2
        
        locked_types = {lock.resource_type for lock in active_locks}
        assert locked_types == {"link_type", "action_type"}
        assert "object_type" not in locked_types
        
        # Branch should still be ACTIVE (not READY yet)
        assert branch_state.current_state == BranchState.ACTIVE
    
    @pytest.mark.asyncio
    async def test_force_branch_lock_legacy_mode(self, lock_manager):
        """Test that force_branch_lock=True still works for legacy behavior"""
        # Use legacy mode with force_branch_lock=True
        lock_ids = await lock_manager.lock_for_indexing(
            branch_name="legacy-branch",
            force_branch_lock=True,
            reason="Emergency full branch lock"
        )
        
        # Should return one lock ID for full branch
        assert len(lock_ids) == 1
        
        # Get branch state
        branch_state = await lock_manager.get_branch_state("legacy-branch")
        
        # Branch should be LOCKED_FOR_WRITE (legacy behavior)
        assert branch_state.current_state == BranchState.LOCKED_FOR_WRITE
        
        # Should have 1 active lock with BRANCH scope
        active_locks = [lock for lock in branch_state.active_locks if lock.is_active]
        assert len(active_locks) == 1
        assert active_locks[0].lock_scope == LockScope.BRANCH
    
    @pytest.mark.asyncio
    async def test_auto_detect_resource_types(self, lock_manager):
        """Test that resource types are auto-detected when not specified"""
        # Don't specify resource_types - should auto-detect
        lock_ids = await lock_manager.lock_for_indexing(
            branch_name="feature/object-changes"  # Branch name hints at object_type
        )
        
        # Should detect and lock at least one resource type
        assert len(lock_ids) >= 1
        
        branch_state = await lock_manager.get_branch_state("feature/object-changes")
        active_locks = [lock for lock in branch_state.active_locks if lock.is_active]
        
        # Should have resource-type locks, not branch lock
        for lock in active_locks:
            assert lock.lock_scope == LockScope.RESOURCE_TYPE
            assert lock.resource_type is not None


class TestFoundryStyleUX:
    """Test Foundry-style UX improvements"""
    
    @pytest.fixture
    def middleware(self):
        """Create middleware for testing"""
        return SchemaFreezeMiddleware(app=None)
    
    @pytest.mark.asyncio
    async def test_detailed_lock_info_response(self, middleware):
        """Test that 423 responses include detailed information"""
        # Mock lock manager
        mock_manager = AsyncMock()
        mock_manager.get_branch_state = AsyncMock()
        
        # Create a branch state with resource-type locks
        mock_lock = MagicMock()
        mock_lock.is_active = True
        mock_lock.lock_type.value = "indexing"
        mock_lock.lock_scope.value = "resource_type"
        mock_lock.resource_type = "object_type"
        mock_lock.created_at = datetime.now(timezone.utc)
        mock_lock.expires_at = datetime.now(timezone.utc).replace(second=0) + timedelta(minutes=30)
        
        mock_branch_state = MagicMock()
        mock_branch_state.active_locks = [mock_lock]
        mock_manager.get_branch_state.return_value = mock_branch_state
        
        with patch.object(middleware, 'lock_manager', mock_manager):
            # Test the detailed lock info method
            lock_info = await middleware._get_detailed_lock_info("test-branch", "object_type")
            
            # Should include detailed information
            assert lock_info["scope"] == "resource_type"
            assert lock_info["other_resources_available"] == True
            assert "object_type" in lock_info["locked_resource_types"]
            assert len(lock_info["available_resource_types"]) > 0
            assert lock_info["progress_percent"] is not None
            assert lock_info["eta_seconds"] is not None
    
    def test_user_friendly_messages(self, middleware):
        """Test that user-friendly messages are generated correctly"""
        # Test resource-type lock message
        lock_info = {
            "scope": "resource_type",
            "other_resources_available": True,
            "available_resource_types": ["link_type", "action_type"],
            "progress_percent": 65,
            "eta_seconds": 300
        }
        
        message = middleware._create_user_friendly_message(
            "feature/user-schema", "object_type", lock_info
        )
        
        # Should explain that only object_type is locked
        assert "object_type" in message
        assert "feature/user-schema" in message
        assert "other resource types are available" in message.lower()
        assert "65%" in message
        assert "5m 0s" in message  # 300 seconds = 5 minutes
    
    def test_alternative_suggestions(self, middleware):
        """Test that helpful alternatives are suggested"""
        lock_info = {
            "scope": "resource_type",
            "available_resource_types": ["link_type", "action_type"],
            "eta_seconds": 120
        }
        
        alternatives = middleware._suggest_alternatives("object_type", lock_info)
        
        # Should suggest specific alternatives
        assert any("link_type" in alt for alt in alternatives)
        assert any("action_type" in alt for alt in alternatives)
        assert any("new branch" in alt.lower() for alt in alternatives)
        assert any("wait" in alt.lower() for alt in alternatives)
        assert any("draft" in alt.lower() for alt in alternatives)


class TestFoundryStyleEfficiency:
    """Test efficiency improvements from Foundry-style changes"""
    
    @pytest.mark.asyncio
    async def test_concurrent_editing_different_resources(self):
        """Test that different resource types can be edited concurrently"""
        lock_manager = BranchLockManager()
        
        # Start indexing object_type only
        lock_ids = await lock_manager.lock_for_indexing(
            branch_name="concurrent-test",
            resource_types=["object_type"]
        )
        
        assert len(lock_ids) == 1
        
        # Should be able to acquire lock on link_type (different resource)
        link_lock_id = await lock_manager.acquire_lock(
            branch_name="concurrent-test",
            lock_type=LockType.MANUAL,
            locked_by="developer",
            lock_scope=LockScope.RESOURCE_TYPE,
            resource_type="link_type",
            reason="Editing link types"
        )
        
        assert link_lock_id is not None
        
        # Should NOT be able to acquire lock on object_type (already locked)
        with pytest.raises(LockConflictError):
            await lock_manager.acquire_lock(
                branch_name="concurrent-test",
                lock_type=LockType.MANUAL,
                locked_by="other-developer",
                lock_scope=LockScope.RESOURCE_TYPE,
                resource_type="object_type",
                reason="Conflicting edit"
            )
    
    @pytest.mark.asyncio
    async def test_productivity_metrics_simulation(self):
        """Simulate improved productivity metrics from granular locking"""
        lock_manager = BranchLockManager()
        
        # Simulate concurrent work on different resource types
        tasks = []
        
        # Developer 1: object_type work
        async def dev1_work():
            lock_ids = await lock_manager.lock_for_indexing(
                "productivity-test", resource_types=["object_type"]
            )
            return "dev1", len(lock_ids)
        
        # Developer 2: link_type work (should not be blocked)
        async def dev2_work():
            await asyncio.sleep(0.1)  # Start slightly after dev1
            lock_id = await lock_manager.acquire_lock(
                branch_name="productivity-test",
                lock_type=LockType.MANUAL,
                locked_by="dev2",
                lock_scope=LockScope.RESOURCE_TYPE,
                resource_type="link_type",
                reason="Parallel development"
            )
            return "dev2", lock_id
        
        # Developer 3: action_type work (should also not be blocked)
        async def dev3_work():
            await asyncio.sleep(0.2)  # Start after both
            lock_id = await lock_manager.acquire_lock(
                branch_name="productivity-test",
                lock_type=LockType.MANUAL,
                locked_by="dev3",
                lock_scope=LockScope.RESOURCE_TYPE,
                resource_type="action_type",
                reason="More parallel development"
            )
            return "dev3", lock_id
        
        # Run all tasks concurrently
        results = await asyncio.gather(
            dev1_work(), dev2_work(), dev3_work(),
            return_exceptions=True
        )
        
        # All should succeed (no blocking)
        for result in results:
            assert not isinstance(result, Exception)
            assert result[1] is not None  # All got lock IDs
        
        # Verify 3 different developers working simultaneously
        developer_names = [result[0] for result in results]
        assert len(set(developer_names)) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
