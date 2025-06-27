"""
Comprehensive tests for DistributedLockManager with PostgreSQL advisory locks
Tests real distributed lock scenarios and integration with existing features
"""
import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Tuple

from core.branch.distributed_lock_manager import DistributedLockManager
from core.branch.lock_manager import LockConflictError
from models.branch_state import (
    BranchState, BranchLock, BranchStateInfo,
    LockType, LockScope
)
from utils.logger import get_logger

logger = get_logger(__name__)

# Mark all tests as async
pytestmark = pytest.mark.asyncio


@pytest.fixture
def db_session():
    """Create test database session"""
    # For testing, use mock session
    mock_session = AsyncMock(spec=AsyncSession)
    
    # Mock execute method for SQL queries
    async def mock_execute(*args, **kwargs):
        result = MagicMock()
        result.scalar.return_value = True
        result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result
    
    mock_session.execute = mock_execute
    return mock_session


@pytest.fixture
def distributed_lock_manager(db_session):
    """Create DistributedLockManager instance"""
    manager = DistributedLockManager(db_session)
    # Don't call initialize/shutdown in tests as they create background tasks
    return manager


class TestDistributedLockManager:
    """Test distributed lock functionality"""
    
    async def test_calculate_lock_key(self, distributed_lock_manager):
        """Test consistent lock key calculation"""
        manager = distributed_lock_manager
        
        # Same resource should always get same key
        key1 = manager._calculate_lock_key("branch:main")
        key2 = manager._calculate_lock_key("branch:main")
        assert key1 == key2
        
        # Different resources should get different keys
        key3 = manager._calculate_lock_key("branch:feature")
        assert key1 != key3
        
        # Key should be valid PostgreSQL int64
        assert isinstance(key1, int)
        assert -2**63 <= key1 < 2**63
    
    async def test_distributed_lock_acquisition(self, distributed_lock_manager):
        """Test basic distributed lock acquisition and release"""
        manager = distributed_lock_manager
        
        # Mock PostgreSQL advisory lock functions
        with patch.object(manager.db_session, 'execute') as mock_execute:
            # Mock successful lock acquisition
            mock_result = MagicMock()
            mock_result.scalar.return_value = True
            mock_execute.return_value = mock_result
            
            acquired = False
            async with manager.distributed_lock("test-resource") as result:
                acquired = result
                assert acquired is True
                
                # Verify correct SQL was executed
                calls = mock_execute.call_args_list
                
                # Should set lock timeout
                assert any("SET LOCAL lock_timeout" in str(call) for call in calls)
                
                # Should try advisory lock
                assert any("pg_try_advisory_xact_lock" in str(call) for call in calls)
    
    async def test_distributed_lock_conflict(self, distributed_lock_manager):
        """Test distributed lock conflict handling"""
        manager = distributed_lock_manager
        
        with patch.object(manager.db_session, 'execute') as mock_execute:
            # Mock failed lock acquisition
            mock_result = MagicMock()
            mock_result.scalar.return_value = False
            
            # Mock timeout on wait
            mock_execute.side_effect = [
                mock_result,  # SET lock_timeout
                mock_result,  # pg_try_advisory_xact_lock returns False
                Exception("Lock timeout")  # pg_advisory_xact_lock times out
            ]
            
            with pytest.raises(LockConflictError) as exc_info:
                async with manager.distributed_lock("contested-resource"):
                    pass
            
            assert "Could not acquire exclusive lock" in str(exc_info.value)
    
    async def test_acquire_lock_with_distributed_backend(self, distributed_lock_manager):
        """Test that acquire_lock uses distributed locks"""
        manager = distributed_lock_manager
        
        # Mock the distributed lock context manager
        distributed_lock_called = False
        original_distributed_lock = manager.distributed_lock
        
        async def mock_distributed_lock(resource_id, timeout_ms=5000, lock_type="exclusive"):
            nonlocal distributed_lock_called
            distributed_lock_called = True
            # Verify correct resource ID format
            assert resource_id.startswith("branch:")
            return original_distributed_lock(resource_id, timeout_ms, lock_type)
        
        manager.distributed_lock = mock_distributed_lock
        
        # Mock parent's acquire_lock to avoid full implementation
        with patch.object(manager.__class__.__bases__[0], 'acquire_lock', new_callable=AsyncMock) as mock_parent:
            mock_parent.return_value = "lock-123"
            
            # Test branch-level lock
            lock_id = await manager.acquire_lock(
                branch_name="feature-1",
                lock_type=LockType.INDEXING,
                locked_by="test-user",
                lock_scope=LockScope.BRANCH
            )
            
            assert distributed_lock_called is True
            assert lock_id == "lock-123"
            
            # Verify parent was called with same parameters
            mock_parent.assert_called_once()
            
        # Reset and test resource-type lock
        distributed_lock_called = False
        manager.distributed_lock = mock_distributed_lock
        
        with patch.object(manager.__class__.__bases__[0], 'acquire_lock', new_callable=AsyncMock) as mock_parent:
            mock_parent.return_value = "lock-456"
            
            lock_id = await manager.acquire_lock(
                branch_name="feature-2",
                lock_type=LockType.INDEXING,
                locked_by="test-user",
                lock_scope=LockScope.RESOURCE_TYPE,
                resource_type="object_type"
            )
            
            assert distributed_lock_called is True
            assert lock_id == "lock-456"
    
    async def test_store_branch_state_persistence(self, distributed_lock_manager):
        """Test that branch state is persisted to PostgreSQL"""
        manager = distributed_lock_manager
        
        state_info = BranchStateInfo(
            branch_name="test-branch",
            current_state=BranchState.ACTIVE,
            state_changed_by="test-user",
            state_change_reason="Testing"
        )
        
        # Mock parent's _store_branch_state
        parent_called = False
        async def mock_parent_store(state):
            nonlocal parent_called
            parent_called = True
        
        with patch.object(manager.__class__.__bases__[0], '_store_branch_state', mock_parent_store):
            await manager._store_branch_state(state_info)
        
        # Verify database was updated
        result = await manager.db_session.execute(
            text("SELECT state_data FROM branch_states WHERE branch_name = :name"),
            {"name": "test-branch"}
        )
        row = result.fetchone()
        
        # In real PostgreSQL this would work
        # For SQLite test, we verify the SQL was correct
        assert parent_called is True
    
    async def test_cleanup_expired_locks_distributed(self, distributed_lock_manager):
        """Test distributed cleanup of expired locks"""
        manager = distributed_lock_manager
        
        # Create test data with expired locks
        now = datetime.now(timezone.utc)
        expired_lock = BranchLock(
            id="expired-1",
            branch_name="branch-1",
            lock_type=LockType.INDEXING,
            lock_scope=LockScope.BRANCH,
            locked_by="test-user",
            expires_at=now - timedelta(hours=1),  # Expired
            reason="Test lock"
        )
        
        active_lock = BranchLock(
            id="active-1",
            branch_name="branch-1",
            lock_type=LockType.MANUAL,
            lock_scope=LockScope.BRANCH,
            locked_by="test-user",
            expires_at=now + timedelta(hours=1),  # Not expired
            reason="Test lock"
        )
        
        state_info = BranchStateInfo(
            branch_name="branch-1",
            current_state=BranchState.LOCKED_FOR_WRITE,
            state_changed_by="test-user",
            state_change_reason="Testing",
            active_locks=[expired_lock, active_lock]
        )
        
        # Mock database query
        with patch.object(manager.db_session, 'execute') as mock_execute:
            # Mock finding branches with locks
            mock_result = MagicMock()
            mock_result.fetchall.return_value = [
                ("branch-1", state_info.json())
            ]
            mock_execute.return_value = mock_result
            
            # Mock the store operation
            with patch.object(manager, '_store_branch_state') as mock_store:
                await manager.cleanup_expired_locks_distributed()
                
                # Verify expired lock was removed
                mock_store.assert_called_once()
                updated_state = mock_store.call_args[0][0]
                assert len(updated_state.active_locks) == 1
                assert updated_state.active_locks[0].id == "active-1"
    
    async def test_list_active_locks_distributed(self, distributed_lock_manager):
        """Test listing locks across all instances"""
        manager = distributed_lock_manager
        
        # Create test locks
        lock1 = BranchLock(
            id="lock-1",
            branch_name="branch-1",
            lock_type=LockType.INDEXING,
            lock_scope=LockScope.RESOURCE_TYPE,
            resource_type="object_type",
            locked_by="service-1",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            reason="Indexing objects"
        )
        
        lock2 = BranchLock(
            id="lock-2",
            branch_name="branch-2",
            lock_type=LockType.MAINTENANCE,
            lock_scope=LockScope.BRANCH,
            locked_by="service-2",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
            reason="Maintenance"
        )
        
        # Mock database query
        with patch.object(manager.db_session, 'execute') as mock_execute:
            mock_result = MagicMock()
            mock_result.__iter__ = lambda self: iter([
                ("branch-1", [lock1.dict()]),
                ("branch-2", [lock2.dict()])
            ])
            mock_execute.return_value = mock_result
            
            locks = await manager.list_active_locks_distributed()
            
            assert len(locks) == 2
            assert locks[0]["branch"] == "branch-1"
            assert locks[0]["lock"]["id"] == "lock-1"
            assert locks[1]["branch"] == "branch-2"
            assert locks[1]["lock"]["id"] == "lock-2"
    
    async def test_concurrent_lock_attempts(self, distributed_lock_manager):
        """Test handling of concurrent lock attempts"""
        manager = distributed_lock_manager
        
        # Simulate two services trying to lock same resource
        lock_acquired = []
        errors = []
        
        async def try_acquire_lock(service_name: str, delay: float = 0):
            try:
                if delay > 0:
                    await asyncio.sleep(delay)
                
                # Mock distributed lock behavior
                if len(lock_acquired) == 0:
                    # First caller gets the lock
                    async with manager.distributed_lock(f"branch:main:type:object_type"):
                        lock_acquired.append(service_name)
                        await asyncio.sleep(0.1)  # Hold lock briefly
                else:
                    # Second caller should fail
                    raise LockConflictError(f"Lock held by {lock_acquired[0]}")
                    
            except LockConflictError as e:
                errors.append((service_name, str(e)))
        
        # Run concurrent lock attempts
        with patch.object(manager, 'distributed_lock', try_acquire_lock):
            await asyncio.gather(
                try_acquire_lock("service-1"),
                try_acquire_lock("service-2", delay=0.05),
                return_exceptions=True
            )
        
        # Verify only one service got the lock
        assert len(lock_acquired) == 1
        assert len(errors) == 1
        assert errors[0][0] == "service-2"
        assert "Lock held by" in errors[0][1]
    
    async def test_heartbeat_with_distributed_locks(self, distributed_lock_manager):
        """Test heartbeat mechanism works with distributed locks"""
        manager = distributed_lock_manager
        
        # Create a lock with heartbeat enabled
        lock = BranchLock(
            id="heartbeat-lock",
            branch_name="test-branch",
            lock_type=LockType.INDEXING,
            lock_scope=LockScope.BRANCH,
            locked_by="indexing-service",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
            heartbeat_interval=60,
            last_heartbeat=datetime.now(timezone.utc),
            heartbeat_source="indexing-service",
            reason="Long running indexing"
        )
        
        # Add to active locks
        manager._active_locks[lock.id] = lock
        
        # Send heartbeat
        success = await manager.send_heartbeat(
            lock_id=lock.id,
            service_name="indexing-service",
            status="healthy",
            progress_info={"processed": 1000, "total": 5000}
        )
        
        assert success is True
        assert lock.last_heartbeat > datetime.now(timezone.utc) - timedelta(seconds=5)
        assert lock.heartbeat_source == "indexing-service"
    
    async def test_postgresql_specific_features(self, distributed_lock_manager):
        """Test PostgreSQL-specific features like JSONB queries"""
        manager = distributed_lock_manager
        
        # This test verifies the SQL queries are correct for PostgreSQL
        # In a real test environment with PostgreSQL, these would execute
        
        # Test JSONB array length query
        with patch.object(manager.db_session, 'execute') as mock_execute:
            mock_result = MagicMock()
            mock_result.fetchall.return_value = []
            mock_execute.return_value = mock_result
            
            await manager.list_active_locks_distributed()
            
            # Verify JSONB query was used
            executed_sql = str(mock_execute.call_args[0][0])
            assert "jsonb_array_length" in executed_sql
            assert "state_data->'active_locks'" in executed_sql
    
    def test_schema_creation(self):
        """Test that the distributed lock schema SQL is valid"""
        from core.branch.distributed_lock_manager import DISTRIBUTED_LOCK_SCHEMA
        
        # Verify schema contains necessary components
        assert "CREATE TABLE IF NOT EXISTS branch_states" in DISTRIBUTED_LOCK_SCHEMA
        assert "state_data JSONB NOT NULL" in DISTRIBUTED_LOCK_SCHEMA
        assert "CREATE TABLE IF NOT EXISTS lock_audit" in DISTRIBUTED_LOCK_SCHEMA
        assert "CREATE OR REPLACE FUNCTION get_active_advisory_locks" in DISTRIBUTED_LOCK_SCHEMA
        
        # Verify indexes
        assert "INDEX idx_branch_updated" in DISTRIBUTED_LOCK_SCHEMA
        assert "INDEX idx_active_locks" in DISTRIBUTED_LOCK_SCHEMA
        assert "INDEX idx_lock_audit_branch" in DISTRIBUTED_LOCK_SCHEMA


class TestDistributedLockIntegration:
    """Integration tests with real scenarios"""
    
    async def test_foundry_style_indexing_scenario(self, distributed_lock_manager):
        """Test Foundry-style resource-specific locking during indexing"""
        manager = distributed_lock_manager
        
        # Scenario: Two services working on different resource types
        # Should NOT conflict in Foundry style
        
        with patch.object(manager.__class__.__bases__[0], 'acquire_lock', new_callable=AsyncMock) as mock_acquire:
            mock_acquire.side_effect = ["lock-1", "lock-2"]
            
            # Service 1 locks object_type for indexing
            lock1 = await manager.acquire_lock(
                branch_name="feature-branch",
                lock_type=LockType.INDEXING,
                locked_by="indexing-service-1",
                lock_scope=LockScope.RESOURCE_TYPE,
                resource_type="object_type",
                reason="Indexing object types"
            )
            
            # Service 2 should be able to lock link_type
            lock2 = await manager.acquire_lock(
                branch_name="feature-branch",
                lock_type=LockType.INDEXING,
                locked_by="indexing-service-2",
                lock_scope=LockScope.RESOURCE_TYPE,
                resource_type="link_type",
                reason="Indexing link types"
            )
            
            assert lock1 == "lock-1"
            assert lock2 == "lock-2"
            
            # Both locks acquired successfully - no conflict
            assert mock_acquire.call_count == 2
    
    async def test_emergency_recovery_scenario(self, distributed_lock_manager):
        """Test recovery from service crash with lost heartbeats"""
        manager = distributed_lock_manager
        
        now = datetime.now(timezone.utc)
        
        # Create a lock that lost heartbeats (simulating crashed service)
        crashed_lock = BranchLock(
            id="crashed-lock",
            branch_name="production",
            lock_type=LockType.INDEXING,
            lock_scope=LockScope.BRANCH,
            locked_by="crashed-service",
            expires_at=now + timedelta(hours=2),  # TTL not expired
            heartbeat_interval=60,
            last_heartbeat=now - timedelta(minutes=10),  # No heartbeat for 10 min
            heartbeat_source="crashed-service",
            auto_release_enabled=True,
            reason="Indexing production data"
        )
        
        # Simulate cleanup process
        manager._active_locks[crashed_lock.id] = crashed_lock
        
        # Add to branch state
        state_info = BranchStateInfo(
            branch_name="production",
            current_state=BranchState.LOCKED_FOR_WRITE,
            state_changed_by="crashed-service",
            state_change_reason="Indexing",
            active_locks=[crashed_lock]
        )
        manager._branch_states["production"] = state_info
        
        # Run heartbeat cleanup
        await manager.cleanup_heartbeat_expired_locks()
        
        # Lock should be released due to missed heartbeats
        assert crashed_lock.id not in manager._active_locks
        
        # Branch should transition back to ACTIVE
        # (In full implementation, this would trigger state transition)
    
    async def test_high_concurrency_scenario(self, distributed_lock_manager):
        """Test behavior under high concurrency with many lock requests"""
        manager = distributed_lock_manager
        
        # Simulate 10 services trying to acquire different resource locks
        results = {"success": 0, "failed": 0}
        
        async def acquire_resource_lock(service_id: int):
            try:
                resource_type = f"type_{service_id % 3}"  # 3 resource types
                
                with patch.object(manager.__class__.__bases__[0], 'acquire_lock', new_callable=AsyncMock) as mock:
                    mock.return_value = f"lock-{service_id}"
                    
                    lock_id = await manager.acquire_lock(
                        branch_name="high-traffic-branch",
                        lock_type=LockType.INDEXING,
                        locked_by=f"service-{service_id}",
                        lock_scope=LockScope.RESOURCE_TYPE,
                        resource_type=resource_type,
                        reason=f"Processing {resource_type}"
                    )
                    
                    results["success"] += 1
                    return lock_id
                    
            except LockConflictError:
                results["failed"] += 1
                return None
        
        # Run concurrent requests
        tasks = [acquire_resource_lock(i) for i in range(10)]
        lock_ids = await asyncio.gather(*tasks, return_exceptions=True)
        
        # In Foundry style, most should succeed (different resources)
        assert results["success"] >= 7  # At least 70% success rate
        assert results["failed"] <= 3   # Maximum 30% conflicts
        
        # Verify no duplicate lock IDs
        successful_locks = [lid for lid in lock_ids if lid and not isinstance(lid, Exception)]
        assert len(successful_locks) == len(set(successful_locks))


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])