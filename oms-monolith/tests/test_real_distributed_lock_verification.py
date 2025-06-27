"""
REAL verification of distributed lock behavior
Tests actual functionality without complex mocking
"""
import pytest
import asyncio
import json
import tempfile
import os
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, Column, String, Integer, DateTime
from sqlalchemy.ext.declarative import declarative_base

from core.branch.distributed_lock_manager import DistributedLockManager
from core.branch.lock_manager import BranchLockManager, LockConflictError
from models.branch_state import (
    BranchState, BranchLock, BranchStateInfo,
    LockType, LockScope, is_lock_expired_by_ttl
)

Base = declarative_base()
pytestmark = pytest.mark.asyncio


class TestRealDistributedBehavior:
    """Test REAL behavior of distributed locks"""
    
    async def test_parent_lock_manager_works(self):
        """First verify the parent BranchLockManager works"""
        manager = BranchLockManager()
        
        # Basic lock acquisition
        lock_id = await manager.acquire_lock(
            branch_name="test",
            lock_type=LockType.MANUAL,
            locked_by="user1"
        )
        
        assert lock_id is not None
        assert lock_id in manager._active_locks
        
        # Conflict detection
        with pytest.raises(LockConflictError):
            await manager.acquire_lock(
                branch_name="test",
                lock_type=LockType.MANUAL,
                locked_by="user2"
            )
        
        # Release works
        success = await manager.release_lock(lock_id, "user1")
        assert success is True
        assert lock_id not in manager._active_locks
    
    async def test_distributed_lock_inheritance(self):
        """Test that DistributedLockManager inherits base functionality"""
        # Create a minimal mock session
        class MockSession:
            async def execute(self, stmt, params=None):
                # Minimal implementation
                class Result:
                    def fetchone(self):
                        return None
                    def scalar(self):
                        return True
                return Result()
            
            async def commit(self):
                pass
        
        session = MockSession()
        manager = DistributedLockManager(session)
        
        # Should have base attributes
        assert hasattr(manager, '_branch_states')
        assert hasattr(manager, '_active_locks')
        assert hasattr(manager, 'acquire_lock')
        assert hasattr(manager, 'release_lock')
    
    async def test_ttl_expiration_real_behavior(self):
        """Test TTL expiration actually works"""
        manager = BranchLockManager()
        
        # Create lock with custom timeout
        lock_id = await manager.acquire_lock(
            branch_name="ttl-test",
            lock_type=LockType.MANUAL,
            locked_by="user1",
            timeout=timedelta(seconds=1)  # Very short timeout
        )
        
        lock = manager._active_locks[lock_id]
        assert lock.expires_at is not None
        
        # Wait for expiration
        await asyncio.sleep(2)
        
        # Check if expired
        assert is_lock_expired_by_ttl(lock) is True
        
        # Cleanup should remove it
        await manager.cleanup_expired_locks()
        assert lock_id not in manager._active_locks
    
    async def test_concurrent_resource_locks_real(self):
        """Test concurrent resource-level locks actually work"""
        manager = BranchLockManager()
        results = []
        
        async def acquire_resource_lock(resource_type: str, delay: float = 0):
            if delay > 0:
                await asyncio.sleep(delay)
            
            try:
                lock_id = await manager.acquire_lock(
                    branch_name="foundry-branch",
                    lock_type=LockType.INDEXING,
                    locked_by=f"indexer-{resource_type}",
                    lock_scope=LockScope.RESOURCE_TYPE,
                    resource_type=resource_type
                )
                results.append({"resource": resource_type, "status": "success", "lock_id": lock_id})
            except LockConflictError:
                results.append({"resource": resource_type, "status": "conflict"})
        
        # These should ALL succeed (different resources)
        await asyncio.gather(
            acquire_resource_lock("object_type"),
            acquire_resource_lock("link_type", 0.01),
            acquire_resource_lock("action_type", 0.02),
            return_exceptions=True
        )
        
        # All should succeed
        successes = [r for r in results if r["status"] == "success"]
        assert len(successes) == 3
        
        # Verify they're all active
        assert len(manager._active_locks) == 3
    
    async def test_heartbeat_mechanism_real(self):
        """Test heartbeat mechanism actually works"""
        manager = BranchLockManager()
        
        # Create lock with heartbeat
        lock_id = await manager.acquire_lock(
            branch_name="heartbeat-test",
            lock_type=LockType.INDEXING,
            locked_by="service1",
            enable_heartbeat=True,
            heartbeat_interval=60
        )
        
        lock = manager._active_locks[lock_id]
        original_heartbeat = lock.last_heartbeat
        
        # Send heartbeat
        await asyncio.sleep(0.1)
        success = await manager.send_heartbeat(
            lock_id=lock_id,
            service_name="service1",
            status="healthy"
        )
        
        assert success is True
        assert lock.last_heartbeat > original_heartbeat
    
    async def test_state_transitions_real(self):
        """Test branch state transitions actually work"""
        manager = BranchLockManager()
        
        # Initial state
        state = await manager.get_branch_state("transition-branch")
        assert state.current_state == BranchState.ACTIVE
        
        # Acquire branch-level indexing lock
        lock_id = await manager.acquire_lock(
            branch_name="transition-branch",
            lock_type=LockType.INDEXING,
            locked_by="indexer",
            lock_scope=LockScope.BRANCH
        )
        
        # Should transition to LOCKED_FOR_WRITE
        state = await manager.get_branch_state("transition-branch")
        assert state.current_state == BranchState.LOCKED_FOR_WRITE
        
        # Complete indexing
        await manager.complete_indexing("transition-branch", "indexer")
        
        # Should be READY
        state = await manager.get_branch_state("transition-branch")
        assert state.current_state == BranchState.READY
    
    async def test_distributed_lock_real_sqlite(self):
        """Test distributed lock with real SQLite database"""
        # Create temporary SQLite database
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        try:
            # Create engine
            engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
            
            # Create tables
            async with engine.begin() as conn:
                await conn.execute(text("""
                    CREATE TABLE branch_states (
                        branch_name VARCHAR(255) PRIMARY KEY,
                        state_data TEXT NOT NULL,
                        updated_at TIMESTAMP NOT NULL,
                        updated_by VARCHAR(255) NOT NULL,
                        version INTEGER DEFAULT 1
                    )
                """))
            
            # Create session
            async_session = sessionmaker(
                engine, class_=AsyncSession, expire_on_commit=False
            )
            
            async with async_session() as session:
                manager = DistributedLockManager(session)
                
                # Store a state
                state = BranchStateInfo(
                    branch_name="sqlite-test",
                    current_state=BranchState.ACTIVE,
                    state_changed_by="tester",
                    state_change_reason="Testing SQLite"
                )
                
                await manager._store_branch_state(state)
                await session.commit()
                
                # Clear cache to force DB read
                manager._branch_states.clear()
                
                # Retrieve it
                retrieved = await manager.get_branch_state("sqlite-test")
                assert retrieved.branch_name == "sqlite-test"
                assert retrieved.current_state == BranchState.ACTIVE
                
        finally:
            await engine.dispose()
            os.unlink(db_path)
    
    async def test_real_conflict_scenario(self):
        """Test a real conflict scenario"""
        manager = BranchLockManager()
        
        # User 1 acquires branch lock
        lock1 = await manager.acquire_lock(
            branch_name="conflict-branch",
            lock_type=LockType.MANUAL,
            locked_by="user1",
            lock_scope=LockScope.BRANCH,
            reason="User 1 working"
        )
        
        # User 2 tries to acquire conflicting lock
        conflict_caught = False
        try:
            await manager.acquire_lock(
                branch_name="conflict-branch",
                lock_type=LockType.MANUAL,
                locked_by="user2",
                lock_scope=LockScope.BRANCH,
                reason="User 2 wants to work"
            )
        except LockConflictError as e:
            conflict_caught = True
            assert "conflict" in str(e).lower()
            assert "conflict-branch" in str(e)
        
        assert conflict_caught is True
        
        # But User 2 CAN lock a different resource type
        lock2 = await manager.acquire_lock(
            branch_name="conflict-branch",
            lock_type=LockType.INDEXING,
            locked_by="user2",
            lock_scope=LockScope.RESOURCE_TYPE,
            resource_type="object_type",
            reason="User 2 indexing objects only"
        )
        
        assert lock2 is not None
        assert len(manager._active_locks) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])