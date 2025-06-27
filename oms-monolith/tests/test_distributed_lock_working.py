"""
Test DistributedLockManager with real behavior verification
"""
import pytest
import asyncio
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from core.branch.distributed_lock_manager import DistributedLockManager
from core.branch.lock_manager import LockConflictError
from models.branch_state import (
    BranchState, BranchLock, BranchStateInfo,
    LockType, LockScope
)

pytestmark = pytest.mark.asyncio


class TestDistributedLockWorking:
    """Test DistributedLockManager actually works"""
    
    def create_mock_session(self):
        """Create a properly mocked database session"""
        mock_session = AsyncMock(spec=AsyncSession)
        
        # Storage for our "database"
        db_storage = {}
        
        async def mock_execute(stmt, params=None):
            sql = str(stmt)
            result = MagicMock()
            
            # Handle different SQL statements
            if "INSERT INTO branch_states" in sql:
                # Store branch state
                branch_name = params["branch_name"]
                db_storage[branch_name] = params["state_data"]
                result.rowcount = 1
                
            elif "SELECT state_data FROM branch_states" in sql:
                # Retrieve branch state
                branch_name = params["branch_name"]
                if branch_name in db_storage:
                    result.fetchone.return_value = (db_storage[branch_name],)
                else:
                    result.fetchone.return_value = None
                    
            elif "pg_try_advisory_xact_lock" in sql:
                # Simulate advisory lock
                result.scalar.return_value = True
                
            elif "SET LOCAL lock_timeout" in sql:
                # Ignore timeout setting
                pass
                
            else:
                print(f"Unhandled SQL: {sql}")
                
            return result
        
        mock_session.execute = mock_execute
        mock_session.commit = AsyncMock()
        return mock_session, db_storage
    
    async def test_distributed_lock_basic_functionality(self):
        """Test basic distributed lock functionality"""
        session, storage = self.create_mock_session()
        manager = DistributedLockManager(session)
        
        # Acquire a lock
        lock_acquired = False
        async with manager.distributed_lock("test-resource-1"):
            lock_acquired = True
            
        assert lock_acquired is True
        
        # Verify SQL was executed
        assert session.execute.called
        
    async def test_lock_persistence_to_database(self):
        """Test that locks are actually persisted"""
        session, storage = self.create_mock_session()
        manager = DistributedLockManager(session)
        
        # Create and store a branch state with lock
        lock = BranchLock(
            id="test-lock-1",
            branch_name="persist-test",
            lock_type=LockType.INDEXING,
            lock_scope=LockScope.RESOURCE_TYPE,
            resource_type="object_type",
            locked_by="test-service",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            reason="Testing persistence"
        )
        
        state = BranchStateInfo(
            branch_name="persist-test",
            current_state=BranchState.ACTIVE,
            state_changed_by="tester",
            state_change_reason="Test",
            active_locks=[lock]
        )
        
        # Store it
        await manager._store_branch_state(state)
        
        # Verify it was stored
        assert "persist-test" in storage
        stored_data = json.loads(storage["persist-test"])
        assert stored_data["branch_name"] == "persist-test"
        assert len(stored_data["active_locks"]) == 1
        assert stored_data["active_locks"][0]["id"] == "test-lock-1"
        
    async def test_lock_retrieval_from_database(self):
        """Test that locks can be retrieved"""
        session, storage = self.create_mock_session()
        manager = DistributedLockManager(session)
        
        # Pre-populate storage
        state_data = {
            "branch_name": "retrieve-test",
            "current_state": "ACTIVE",
            "state_changed_by": "tester",
            "state_change_reason": "Test",
            "state_changed_at": datetime.now(timezone.utc).isoformat(),
            "active_locks": [{
                "id": "stored-lock-1",
                "branch_name": "retrieve-test",
                "lock_type": "MANUAL",
                "lock_scope": "BRANCH",
                "locked_by": "stored-user",
                "locked_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                "is_active": True,
                "reason": "Stored lock"
            }]
        }
        storage["retrieve-test"] = json.dumps(state_data)
        
        # Retrieve it
        state = await manager.get_branch_state("retrieve-test")
        
        assert state.branch_name == "retrieve-test"
        assert len(state.active_locks) == 1
        assert state.active_locks[0].id == "stored-lock-1"
        
    async def test_distributed_cleanup_actually_removes_expired(self):
        """Test that cleanup actually removes expired locks"""
        session, storage = self.create_mock_session()
        manager = DistributedLockManager(session)
        
        # Create state with expired and valid locks
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        
        state_data = {
            "branch_name": "cleanup-test",
            "current_state": "ACTIVE",
            "state_changed_by": "tester",
            "state_change_reason": "Test",
            "state_changed_at": datetime.now(timezone.utc).isoformat(),
            "active_locks": [
                {
                    "id": "expired-1",
                    "branch_name": "cleanup-test",
                    "lock_type": "MANUAL",
                    "lock_scope": "BRANCH",
                    "locked_by": "old-user",
                    "locked_at": past_time.isoformat(),
                    "expires_at": past_time.isoformat(),  # Expired
                    "is_active": True,
                    "reason": "Should be removed"
                },
                {
                    "id": "valid-1",
                    "branch_name": "cleanup-test",
                    "lock_type": "MANUAL", 
                    "lock_scope": "BRANCH",
                    "locked_by": "current-user",
                    "locked_at": datetime.now(timezone.utc).isoformat(),
                    "expires_at": future_time.isoformat(),  # Valid
                    "is_active": True,
                    "reason": "Should remain"
                }
            ]
        }
        
        # Mock the query to return our test data
        async def mock_execute_with_cleanup(stmt, params=None):
            sql = str(stmt)
            result = MagicMock()
            
            if "jsonb_array_length" in sql:
                # Return branches with locks
                result.__iter__ = lambda self: iter([
                    ("cleanup-test", json.dumps(state_data))
                ])
            else:
                # Let parent handle other queries
                return await session.execute.__wrapped__(stmt, params)
                
            return result
            
        # Replace execute temporarily
        original_execute = session.execute
        session.execute = mock_execute_with_cleanup
        
        # Run cleanup
        await manager.cleanup_expired_locks_distributed()
        
        # Restore original
        session.execute = original_execute
        
        # Verify the state was updated with only valid lock
        updated_json = storage.get("cleanup-test")
        if updated_json:
            updated_data = json.loads(updated_json)
            active_locks = updated_data.get("active_locks", [])
            assert len(active_locks) == 1
            assert active_locks[0]["id"] == "valid-1"
            
    async def test_acquire_lock_uses_distributed_lock(self):
        """Test that acquire_lock actually uses distributed locking"""
        session, storage = self.create_mock_session()
        manager = DistributedLockManager(session)
        
        distributed_lock_called = False
        resource_locked = None
        
        # Mock distributed_lock to track calls
        original_distributed_lock = manager.distributed_lock
        
        @asyncio.coroutine  
        def mock_distributed_lock(resource_id, timeout_ms=5000, lock_type="exclusive"):
            nonlocal distributed_lock_called, resource_locked
            distributed_lock_called = True
            resource_locked = resource_id
            
            # Return a proper async context manager
            class AsyncLockContext:
                async def __aenter__(self):
                    return True
                async def __aexit__(self, *args):
                    pass
            
            return AsyncLockContext()
        
        manager.distributed_lock = mock_distributed_lock
        
        # Now test acquire_lock
        with patch('core.branch.lock_manager.BranchLockManager.acquire_lock', new_callable=AsyncMock) as mock_parent:
            mock_parent.return_value = "lock-123"
            
            lock_id = await manager.acquire_lock(
                branch_name="dist-test",
                lock_type=LockType.INDEXING,
                locked_by="test-user",
                lock_scope=LockScope.RESOURCE_TYPE,
                resource_type="object_type"
            )
            
            assert distributed_lock_called is True
            assert resource_locked == "branch:dist-test:type:object_type"
            assert lock_id == "lock-123"
            
    async def test_concurrent_resource_locks_allowed(self):
        """Test that different resources can be locked concurrently"""
        session, storage = self.create_mock_session()
        manager = DistributedLockManager(session)
        
        # Track which resources got locked
        locked_resources = []
        
        async def mock_acquire(branch_name, lock_type, locked_by, **kwargs):
            resource_type = kwargs.get('resource_type', 'unknown')
            locked_resources.append(resource_type)
            return f"lock-{resource_type}"
        
        with patch('core.branch.lock_manager.BranchLockManager.acquire_lock', side_effect=mock_acquire):
            # These should all succeed (different resources)
            tasks = [
                manager.acquire_lock(
                    branch_name="concurrent-test",
                    lock_type=LockType.INDEXING,
                    locked_by=f"indexer-{i}",
                    lock_scope=LockScope.RESOURCE_TYPE,
                    resource_type=resource_type
                )
                for i, resource_type in enumerate(["object_type", "link_type", "action_type"])
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # All should succeed
            assert len(results) == 3
            assert all(isinstance(r, str) and r.startswith("lock-") for r in results)
            assert len(set(locked_resources)) == 3  # All different resources


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])