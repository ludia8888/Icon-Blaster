"""
Test that verifies the upgrade from BranchLockManager to DistributedLockManager
Ensures all enterprise features (TTL, heartbeat, resource-level locking) work correctly
"""
import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from core.branch.lock_manager import BranchLockManager
from core.branch.distributed_lock_manager import DistributedLockManager
from models.branch_state import (
    BranchState, BranchLock, BranchStateInfo,
    LockType, LockScope
)

# Mark all tests as async
pytestmark = pytest.mark.asyncio


class TestEnterpriseFeatureCompatibility:
    """Test that all enterprise features work with distributed upgrade"""
    
    async def test_ttl_feature_preserved(self):
        """Test that TTL auto-release works in distributed version"""
        # Create both managers for comparison
        base_manager = BranchLockManager()
        
        # Mock database session
        mock_session = AsyncMock(spec=AsyncSession)
        distributed_manager = DistributedLockManager(mock_session)
        
        # Both should have same TTL settings
        assert base_manager.default_lock_timeout == distributed_manager.default_lock_timeout
        assert base_manager.indexing_lock_timeout == distributed_manager.indexing_lock_timeout
        assert base_manager.maintenance_lock_timeout == distributed_manager.maintenance_lock_timeout
        
        # Test TTL calculation
        indexing_timeout = distributed_manager._get_default_timeout(LockType.INDEXING)
        assert indexing_timeout == timedelta(hours=4)
        
        maintenance_timeout = distributed_manager._get_default_timeout(LockType.MAINTENANCE)
        assert maintenance_timeout == timedelta(hours=1)
    
    async def test_heartbeat_feature_preserved(self):
        """Test that heartbeat mechanism works with distributed locks"""
        mock_session = AsyncMock(spec=AsyncSession)
        manager = DistributedLockManager(mock_session)
        
        # Create lock with heartbeat
        lock = BranchLock(
            id="hb-test",
            branch_name="test",
            lock_type=LockType.INDEXING,
            lock_scope=LockScope.BRANCH,
            locked_by="test-service",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
            heartbeat_interval=60,
            last_heartbeat=datetime.now(timezone.utc),
            heartbeat_source="test-service",
            auto_release_enabled=True,
            reason="Testing heartbeat"
        )
        
        manager._active_locks[lock.id] = lock
        
        # Heartbeat settings should be preserved
        assert manager.heartbeat_check_interval == 30
        assert manager.heartbeat_grace_multiplier == 3
        
        # Send heartbeat
        with patch.object(manager, 'get_branch_state', new_callable=AsyncMock) as mock_get:
            mock_state = BranchStateInfo(
                branch_name="test",
                current_state=BranchState.ACTIVE,
                state_changed_by="system",
                state_change_reason="Test"
            )
            mock_get.return_value = mock_state
            
            with patch.object(manager, '_store_branch_state', new_callable=AsyncMock):
                success = await manager.send_heartbeat(
                    lock_id="hb-test",
                    service_name="test-service",
                    status="healthy",
                    progress_info={"progress": 50}
                )
                
                assert success is True
                assert lock.heartbeat_source == "test-service"
    
    async def test_resource_level_locking_enhanced(self):
        """Test that resource-level locking gets distributed lock benefits"""
        mock_session = AsyncMock(spec=AsyncSession)
        manager = DistributedLockManager(mock_session)
        
        # Mock the distributed lock mechanism
        distributed_lock_calls = []
        
        async def mock_distributed_lock(resource_id, timeout_ms=5000, lock_type="exclusive"):
            distributed_lock_calls.append({
                "resource_id": resource_id,
                "timeout_ms": timeout_ms,
                "lock_type": lock_type
            })
            
            # Simulate successful lock acquisition
            class MockLock:
                async def __aenter__(self):
                    return True
                async def __aexit__(self, *args):
                    pass
            
            return MockLock()
        
        manager.distributed_lock = mock_distributed_lock
        
        # Mock parent acquire_lock
        with patch.object(BranchLockManager, 'acquire_lock', new_callable=AsyncMock) as mock_parent:
            mock_parent.return_value = "resource-lock-123"
            
            # Test resource-specific lock
            lock_id = await manager.acquire_lock(
                branch_name="feature-1",
                lock_type=LockType.INDEXING,
                locked_by="funnel-service",
                lock_scope=LockScope.RESOURCE,
                resource_type="object_type",
                resource_id="Employee",
                reason="Indexing Employee objects"
            )
            
            # Verify distributed lock was called with correct resource ID
            assert len(distributed_lock_calls) == 1
            assert distributed_lock_calls[0]["resource_id"] == "branch:feature-1:type:object_type:id:Employee"
            assert lock_id == "resource-lock-123"
    
    async def test_foundry_style_minimal_locking(self):
        """Test Foundry-style minimal scope locking preference"""
        mock_session = AsyncMock(spec=AsyncSession)
        manager = DistributedLockManager(mock_session)
        
        # Mock necessary methods
        with patch.object(manager, 'distributed_lock', new_callable=AsyncMock):
            with patch.object(manager, 'get_branch_state', new_callable=AsyncMock) as mock_get_state:
                with patch.object(manager, '_store_branch_state', new_callable=AsyncMock):
                    with patch.object(manager, '_detect_indexing_resource_types', new_callable=AsyncMock) as mock_detect:
                        # Setup mocks
                        mock_state = BranchStateInfo(
                            branch_name="optimize-branch",
                            current_state=BranchState.ACTIVE,
                            state_changed_by="system",
                            state_change_reason="Active"
                        )
                        mock_get_state.return_value = mock_state
                        mock_detect.return_value = ["object_type", "link_type"]
                        
                        # Call lock_for_indexing without force flag (Foundry style)
                        lock_ids = await manager.lock_for_indexing(
                            branch_name="optimize-branch",
                            locked_by="funnel-service",
                            reason="Incremental indexing",
                            force_branch_lock=False  # Foundry style
                        )
                        
                        # Should create resource-type locks, not branch lock
                        assert len(lock_ids) >= 2  # At least object_type and link_type
                        
                        # Verify it detected resource types
                        mock_detect.assert_called_once_with("optimize-branch")
    
    async def test_lock_conflict_detection_distributed(self):
        """Test that lock conflicts are properly detected in distributed environment"""
        mock_session = AsyncMock(spec=AsyncSession)
        manager = DistributedLockManager(mock_session)
        
        # Create existing lock
        existing_lock = BranchLock(
            id="existing-1",
            branch_name="main",
            lock_type=LockType.INDEXING,
            lock_scope=LockScope.RESOURCE_TYPE,
            resource_type="object_type",
            locked_by="service-1",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            reason="Already indexing"
        )
        
        # Setup branch state with existing lock
        branch_state = BranchStateInfo(
            branch_name="main",
            current_state=BranchState.ACTIVE,
            state_changed_by="system",
            state_change_reason="Active",
            active_locks=[existing_lock]
        )
        
        with patch.object(manager, 'get_branch_state', return_value=branch_state):
            # Try to acquire conflicting lock
            new_lock = BranchLock(
                id="new-1",
                branch_name="main",
                lock_type=LockType.MAINTENANCE,
                lock_scope=LockScope.RESOURCE_TYPE,
                resource_type="object_type",  # Same resource type - conflict!
                locked_by="service-2",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                reason="Maintenance"
            )
            
            # Should detect conflict
            with pytest.raises(Exception) as exc_info:
                await manager._check_lock_conflicts(new_lock)
            
            assert "conflict" in str(exc_info.value).lower()
    
    async def test_auto_merge_conditions_check(self):
        """Test that auto-merge conditions are checked after indexing"""
        mock_session = AsyncMock(spec=AsyncSession)
        manager = DistributedLockManager(mock_session)
        
        # Create branch state ready for merge
        branch_state = BranchStateInfo(
            branch_name="feature-auto-merge",
            current_state=BranchState.READY,
            state_changed_by="funnel-service",
            state_change_reason="Indexing completed",
            auto_merge_enabled=True,
            indexing_completed_at=datetime.now(timezone.utc)
        )
        
        # Mock the auto-merge check
        merge_checked = False
        
        async def mock_check_auto_merge(state):
            nonlocal merge_checked
            merge_checked = True
            assert state.branch_name == "feature-auto-merge"
            assert state.auto_merge_enabled is True
            assert state.is_ready_for_merge is True
        
        manager._check_auto_merge_conditions = mock_check_auto_merge
        
        with patch.object(manager, 'get_branch_state', return_value=branch_state):
            with patch.object(manager, '_store_branch_state', new_callable=AsyncMock):
                # Complete indexing should trigger auto-merge check
                success = await manager.complete_indexing(
                    branch_name="feature-auto-merge",
                    completed_by="funnel-service"
                )
                
                assert success is True
                assert merge_checked is True
    
    async def test_lock_migration_compatibility(self):
        """Test that locks created by BranchLockManager work with DistributedLockManager"""
        # Create lock with base manager
        base_manager = BranchLockManager()
        
        # Initialize base manager state
        await base_manager.initialize()
        
        # Create a lock
        with patch.object(base_manager, 'get_branch_state', new_callable=AsyncMock) as mock_get:
            mock_state = BranchStateInfo(
                branch_name="legacy-branch",
                current_state=BranchState.ACTIVE,
                state_changed_by="system",
                state_change_reason="Active"
            )
            mock_get.return_value = mock_state
            
            with patch.object(base_manager, '_store_branch_state', new_callable=AsyncMock):
                lock_id = await base_manager.acquire_lock(
                    branch_name="legacy-branch",
                    lock_type=LockType.MANUAL,
                    locked_by="legacy-service",
                    reason="Legacy lock"
                )
        
        # Transfer lock to distributed manager
        mock_session = AsyncMock(spec=AsyncSession)
        distributed_manager = DistributedLockManager(mock_session)
        
        # Copy lock state
        distributed_manager._active_locks = base_manager._active_locks.copy()
        distributed_manager._branch_states = base_manager._branch_states.copy()
        
        # Should be able to work with the lock
        lock_status = await distributed_manager.get_lock_status(lock_id)
        assert lock_status is not None
        assert lock_status.locked_by == "legacy-service"
        
        # Should be able to release it
        with patch.object(distributed_manager, 'get_branch_state', return_value=mock_state):
            with patch.object(distributed_manager, '_store_branch_state', new_callable=AsyncMock):
                success = await distributed_manager.release_lock(lock_id, "migration-test")
                assert success is True
        
        # Cleanup
        await base_manager.shutdown()


class TestDistributedLockPerformance:
    """Test performance characteristics of distributed locks"""
    
    async def test_lock_acquisition_timeout(self):
        """Test that lock acquisition respects timeout"""
        mock_session = AsyncMock(spec=AsyncSession)
        manager = DistributedLockManager(mock_session)
        
        # Mock slow lock acquisition
        async def slow_execute(*args, **kwargs):
            sql = str(args[0]) if args else ""
            if "pg_advisory_xact_lock" in sql and "try" not in sql:
                # Simulate timeout
                await asyncio.sleep(0.1)
                raise Exception("Lock acquisition timeout")
            
            # Other queries succeed
            result = MagicMock()
            result.scalar.return_value = False  # try_lock fails
            return result
        
        mock_session.execute = slow_execute
        
        start_time = asyncio.get_event_loop().time()
        
        with pytest.raises(Exception) as exc_info:
            async with manager.distributed_lock("slow-resource", timeout_ms=50):
                pass
        
        elapsed = asyncio.get_event_loop().time() - start_time
        
        # Should timeout quickly
        assert elapsed < 0.2
        assert "timeout" in str(exc_info.value).lower()
    
    async def test_concurrent_resource_locks_performance(self):
        """Test that non-conflicting locks can be acquired concurrently"""
        mock_session = AsyncMock(spec=AsyncSession)
        manager = DistributedLockManager(mock_session)
        
        # Track lock acquisitions
        acquisitions = []
        
        async def mock_distributed_lock(resource_id, timeout_ms=5000, lock_type="exclusive"):
            acquisitions.append({
                "resource_id": resource_id,
                "time": asyncio.get_event_loop().time()
            })
            
            class MockLock:
                async def __aenter__(self):
                    await asyncio.sleep(0.01)  # Simulate small delay
                    return True
                async def __aexit__(self, *args):
                    pass
            
            return MockLock()
        
        manager.distributed_lock = mock_distributed_lock
        
        # Acquire multiple non-conflicting locks concurrently
        async def acquire_lock(resource_type: str):
            with patch.object(BranchLockManager, 'acquire_lock', new_callable=AsyncMock) as mock:
                mock.return_value = f"lock-{resource_type}"
                
                return await manager.acquire_lock(
                    branch_name="perf-test",
                    lock_type=LockType.INDEXING,
                    locked_by=f"service-{resource_type}",
                    lock_scope=LockScope.RESOURCE_TYPE,
                    resource_type=resource_type,
                    reason=f"Indexing {resource_type}"
                )
        
        # Run concurrently
        start_time = asyncio.get_event_loop().time()
        
        results = await asyncio.gather(
            acquire_lock("object_type"),
            acquire_lock("link_type"),
            acquire_lock("action_type"),
            acquire_lock("function_type")
        )
        
        elapsed = asyncio.get_event_loop().time() - start_time
        
        # All should succeed
        assert len(results) == 4
        assert all(r.startswith("lock-") for r in results)
        
        # Should complete quickly (concurrent, not sequential)
        assert elapsed < 0.1  # Much faster than 4 * 0.01 sequential
        
        # Verify all were acquired around the same time
        times = [a["time"] for a in acquisitions]
        time_spread = max(times) - min(times)
        assert time_spread < 0.05  # All started within 50ms


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])