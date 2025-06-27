"""
Basic tests to find real issues in lock implementation
Start simple, find problems, fix them
"""
import pytest
import asyncio
from datetime import datetime, timezone, timedelta

from core.branch.lock_manager import BranchLockManager, LockConflictError
from models.branch_state import (
    BranchState, BranchLock, BranchStateInfo,
    LockType, LockScope
)

pytestmark = pytest.mark.asyncio


class TestBasicLockBehavior:
    """Test the most basic lock behaviors first"""
    
    async def test_lock_manager_can_initialize(self):
        """Can we even create a lock manager?"""
        manager = BranchLockManager()
        assert manager is not None
        assert manager._branch_states == {}
        assert manager._active_locks == {}
    
    async def test_can_acquire_simple_lock(self):
        """Can we acquire a basic lock?"""
        manager = BranchLockManager()
        
        # Don't initialize background tasks for this test
        # await manager.initialize()
        
        lock_id = await manager.acquire_lock(
            branch_name="test-branch",
            lock_type=LockType.MANUAL,
            locked_by="test-user",
            reason="Basic test"
        )
        
        assert lock_id is not None
        assert lock_id in manager._active_locks
        
        # Check the lock details
        lock = manager._active_locks[lock_id]
        assert lock.branch_name == "test-branch"
        assert lock.locked_by == "test-user"
        assert lock.is_active is True
    
    async def test_cannot_acquire_conflicting_locks(self):
        """Do locks actually conflict?"""
        manager = BranchLockManager()
        
        # First lock should succeed
        lock1 = await manager.acquire_lock(
            branch_name="conflict-test",
            lock_type=LockType.INDEXING,
            locked_by="user1",
            lock_scope=LockScope.BRANCH,
            reason="First lock"
        )
        
        assert lock1 is not None
        
        # Second lock on same branch should fail
        with pytest.raises(LockConflictError) as exc_info:
            await manager.acquire_lock(
                branch_name="conflict-test",
                lock_type=LockType.INDEXING,
                locked_by="user2",
                lock_scope=LockScope.BRANCH,
                reason="Should conflict"
            )
        
        assert "conflict" in str(exc_info.value).lower()
    
    async def test_resource_level_locks_dont_conflict(self):
        """Can different resources be locked simultaneously?"""
        manager = BranchLockManager()
        
        # Lock object_type
        lock1 = await manager.acquire_lock(
            branch_name="foundry-test",
            lock_type=LockType.INDEXING,
            locked_by="indexer1",
            lock_scope=LockScope.RESOURCE_TYPE,
            resource_type="object_type",
            reason="Indexing objects"
        )
        
        # Lock link_type - should NOT conflict
        lock2 = await manager.acquire_lock(
            branch_name="foundry-test",
            lock_type=LockType.INDEXING,
            locked_by="indexer2",
            lock_scope=LockScope.RESOURCE_TYPE,
            resource_type="link_type",
            reason="Indexing links"
        )
        
        assert lock1 != lock2
        assert len(manager._active_locks) == 2
    
    async def test_lock_release_actually_releases(self):
        """Does releasing a lock actually release it?"""
        manager = BranchLockManager()
        
        # Acquire lock
        lock_id = await manager.acquire_lock(
            branch_name="release-test",
            lock_type=LockType.MANUAL,
            locked_by="test-user",
            reason="Will be released"
        )
        
        assert lock_id in manager._active_locks
        
        # Release it
        success = await manager.release_lock(lock_id, "test-user")
        assert success is True
        
        # Should be gone from active locks
        assert lock_id not in manager._active_locks
        
        # Should be able to acquire same lock again
        lock2 = await manager.acquire_lock(
            branch_name="release-test",
            lock_type=LockType.MANUAL,
            locked_by="another-user",
            reason="After release"
        )
        
        assert lock2 is not None
    
    async def test_ttl_expiration_detection(self):
        """Are expired locks detected correctly?"""
        manager = BranchLockManager()
        
        # Create an already-expired lock manually
        expired_lock = BranchLock(
            id="expired-1",
            branch_name="ttl-test",
            lock_type=LockType.MANUAL,
            lock_scope=LockScope.BRANCH,
            locked_by="old-user",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            reason="Should be expired"
        )
        
        # Check if it's detected as expired
        from models.branch_state import is_lock_expired_by_ttl
        assert is_lock_expired_by_ttl(expired_lock) is True
        
        # Create a valid lock
        valid_lock = BranchLock(
            id="valid-1",
            branch_name="ttl-test",
            lock_type=LockType.MANUAL,
            lock_scope=LockScope.BRANCH,
            locked_by="current-user",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            reason="Should be valid"
        )
        
        assert is_lock_expired_by_ttl(valid_lock) is False
    
    async def test_heartbeat_expiration_detection(self):
        """Are missed heartbeats detected?"""
        from models.branch_state import is_lock_expired_by_heartbeat
        
        # Lock with missed heartbeat
        missed_heartbeat_lock = BranchLock(
            id="hb-expired",
            branch_name="hb-test",
            lock_type=LockType.INDEXING,
            lock_scope=LockScope.BRANCH,
            locked_by="dead-service",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            heartbeat_interval=60,  # Expects heartbeat every minute
            last_heartbeat=datetime.now(timezone.utc) - timedelta(minutes=5),  # 5 minutes ago
            heartbeat_source="dead-service",
            reason="Missed heartbeats"
        )
        
        # Default grace period is 3x interval = 180 seconds
        # 5 minutes = 300 seconds > 180 seconds, so expired
        assert is_lock_expired_by_heartbeat(missed_heartbeat_lock) is True
        
        # Lock with recent heartbeat
        healthy_lock = BranchLock(
            id="hb-healthy",
            branch_name="hb-test",
            lock_type=LockType.INDEXING,
            lock_scope=LockScope.BRANCH,
            locked_by="healthy-service",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            heartbeat_interval=60,
            last_heartbeat=datetime.now(timezone.utc) - timedelta(seconds=30),  # 30 seconds ago
            heartbeat_source="healthy-service",
            reason="Recent heartbeat"
        )
        
        assert is_lock_expired_by_heartbeat(healthy_lock) is False
    
    async def test_branch_state_transitions(self):
        """Do branch state transitions work?"""
        manager = BranchLockManager()
        
        # Get initial state
        state = await manager.get_branch_state("transition-test")
        assert state.current_state == BranchState.ACTIVE
        
        # Acquire indexing lock
        lock_id = await manager.acquire_lock(
            branch_name="transition-test",
            lock_type=LockType.INDEXING,
            locked_by="indexer",
            lock_scope=LockScope.BRANCH,
            reason="Full branch indexing"
        )
        
        # State should have changed
        state = await manager.get_branch_state("transition-test")
        assert state.current_state == BranchState.LOCKED_FOR_WRITE
        
        # Release lock
        await manager.release_lock(lock_id, "indexer")
        
        # State should be READY
        state = await manager.get_branch_state("transition-test")
        assert state.current_state == BranchState.READY
    
    async def test_concurrent_lock_attempts(self):
        """What happens with truly concurrent lock attempts?"""
        manager = BranchLockManager()
        results = []
        
        async def try_acquire_lock(user_id: int):
            try:
                lock_id = await manager.acquire_lock(
                    branch_name="concurrent-test",
                    lock_type=LockType.MANUAL,
                    locked_by=f"user-{user_id}",
                    lock_scope=LockScope.BRANCH,
                    reason=f"Concurrent attempt {user_id}"
                )
                results.append({"user": user_id, "status": "success", "lock_id": lock_id})
            except LockConflictError as e:
                results.append({"user": user_id, "status": "conflict", "error": str(e)})
        
        # Try to acquire same lock from 3 users at once
        await asyncio.gather(
            try_acquire_lock(1),
            try_acquire_lock(2),
            try_acquire_lock(3),
            return_exceptions=True
        )
        
        # Only one should succeed
        successes = [r for r in results if r["status"] == "success"]
        conflicts = [r for r in results if r["status"] == "conflict"]
        
        assert len(successes) == 1
        assert len(conflicts) == 2
        
        print(f"Success: User {successes[0]['user']}")
        print(f"Conflicts: {[r['user'] for r in conflicts]}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])