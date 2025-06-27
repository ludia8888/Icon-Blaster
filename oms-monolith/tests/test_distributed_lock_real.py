"""
REAL integration tests for DistributedLockManager
No mocks - tests actual behavior with real database operations
"""
import pytest
import asyncio
import os
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, pool
import hashlib

from core.branch.distributed_lock_manager import DistributedLockManager
from core.branch.lock_manager import LockConflictError
from models.branch_state import (
    BranchState, BranchLock, BranchStateInfo,
    LockType, LockScope
)

# Use real PostgreSQL for testing
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/test_oms"
)

pytestmark = pytest.mark.asyncio


class TestRealDistributedLocks:
    """Real integration tests with actual PostgreSQL"""
    
    @pytest.fixture
    async def real_db_engine(self):
        """Create real database engine"""
        # Use NullPool to avoid connection issues in tests
        engine = create_async_engine(
            TEST_DATABASE_URL,
            poolclass=pool.NullPool,
            echo=True  # Log all SQL
        )
        
        # Create schema
        async with engine.begin() as conn:
            # Drop existing tables for clean test
            await conn.execute(text("DROP TABLE IF EXISTS branch_states CASCADE"))
            await conn.execute(text("DROP TABLE IF EXISTS lock_audit CASCADE"))
            
            # Create tables
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS branch_states (
                    branch_name VARCHAR(255) PRIMARY KEY,
                    state_data JSONB NOT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    updated_by VARCHAR(255) NOT NULL,
                    version INTEGER DEFAULT 1
                )
            """))
            
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS lock_audit (
                    id SERIAL PRIMARY KEY,
                    lock_id VARCHAR(255) NOT NULL,
                    branch_name VARCHAR(255) NOT NULL,
                    lock_type VARCHAR(50) NOT NULL,
                    lock_scope VARCHAR(50) NOT NULL,
                    resource_type VARCHAR(100),
                    resource_id VARCHAR(255),
                    locked_by VARCHAR(255) NOT NULL,
                    action VARCHAR(50) NOT NULL,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    metadata JSONB
                )
            """))
        
        yield engine
        
        # Cleanup
        await engine.dispose()
    
    @pytest.fixture
    async def db_session(self, real_db_engine):
        """Create real database session"""
        async_session = sessionmaker(
            real_db_engine, class_=AsyncSession, expire_on_commit=False
        )
        
        async with async_session() as session:
            yield session
            await session.rollback()
    
    async def test_real_advisory_lock_conflict(self, real_db_engine):
        """Test that PostgreSQL advisory locks actually prevent conflicts"""
        results = {"session1": None, "session2": None, "error": None}
        
        async def try_lock_session1():
            async_session = sessionmaker(
                real_db_engine, class_=AsyncSession, expire_on_commit=False
            )
            async with async_session() as session:
                manager = DistributedLockManager(session)
                
                try:
                    async with manager.distributed_lock("test-resource-1", timeout_ms=10000):
                        results["session1"] = "acquired"
                        await asyncio.sleep(2)  # Hold lock for 2 seconds
                        results["session1"] = "released"
                except Exception as e:
                    results["error"] = f"Session1: {str(e)}"
        
        async def try_lock_session2():
            await asyncio.sleep(0.5)  # Start after session1
            
            async_session = sessionmaker(
                real_db_engine, class_=AsyncSession, expire_on_commit=False
            )
            async with async_session() as session:
                manager = DistributedLockManager(session)
                
                try:
                    # This should fail or wait
                    async with manager.distributed_lock("test-resource-1", timeout_ms=1000):
                        results["session2"] = "acquired"
                except LockConflictError:
                    results["session2"] = "blocked"
                except Exception as e:
                    results["session2"] = "timeout"
        
        # Run both sessions concurrently
        await asyncio.gather(
            try_lock_session1(),
            try_lock_session2(),
            return_exceptions=True
        )
        
        # Verify real conflict occurred
        assert results["session1"] == "released"
        assert results["session2"] in ["blocked", "timeout"]
        assert results["error"] is None
    
    async def test_real_lock_persistence(self, db_session):
        """Test that lock state is actually persisted in PostgreSQL"""
        manager = DistributedLockManager(db_session)
        
        # Create branch state
        state_info = BranchStateInfo(
            branch_name="test-persistence",
            current_state=BranchState.ACTIVE,
            state_changed_by="test-user",
            state_change_reason="Testing persistence"
        )
        
        # Store it
        await manager._store_branch_state(state_info)
        await db_session.commit()
        
        # Query database directly
        result = await db_session.execute(
            text("SELECT state_data FROM branch_states WHERE branch_name = :name"),
            {"name": "test-persistence"}
        )
        row = result.fetchone()
        
        assert row is not None
        state_data = row[0]
        assert state_data["branch_name"] == "test-persistence"
        assert state_data["current_state"] == "ACTIVE"
    
    async def test_real_lock_cleanup(self, db_session):
        """Test that expired locks are actually cleaned up"""
        manager = DistributedLockManager(db_session)
        
        # Create expired lock
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        expired_lock = BranchLock(
            id="expired-lock-1",
            branch_name="cleanup-test",
            lock_type=LockType.MANUAL,
            lock_scope=LockScope.BRANCH,
            locked_by="test-service",
            expires_at=past_time,
            reason="Test expiration"
        )
        
        # Create active lock
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        active_lock = BranchLock(
            id="active-lock-1",
            branch_name="cleanup-test",
            lock_type=LockType.MANUAL,
            lock_scope=LockScope.BRANCH,
            locked_by="test-service",
            expires_at=future_time,
            reason="Test active"
        )
        
        # Store branch with both locks
        state_info = BranchStateInfo(
            branch_name="cleanup-test",
            current_state=BranchState.ACTIVE,
            state_changed_by="test-user",
            state_change_reason="Testing cleanup",
            active_locks=[expired_lock, active_lock]
        )
        
        await manager._store_branch_state(state_info)
        await db_session.commit()
        
        # Run cleanup
        await manager.cleanup_expired_locks_distributed()
        await db_session.commit()
        
        # Verify expired lock was removed
        result = await db_session.execute(
            text("SELECT state_data FROM branch_states WHERE branch_name = :name"),
            {"name": "cleanup-test"}
        )
        row = result.fetchone()
        
        state_data = row[0]
        active_locks = state_data["active_locks"]
        
        assert len(active_locks) == 1
        assert active_locks[0]["id"] == "active-lock-1"
    
    async def test_real_concurrent_indexing(self, real_db_engine):
        """Test Foundry-style concurrent indexing of different resource types"""
        results = []
        errors = []
        
        async def index_resource_type(service_id: int, resource_type: str):
            async_session = sessionmaker(
                real_db_engine, class_=AsyncSession, expire_on_commit=False
            )
            
            async with async_session() as session:
                manager = DistributedLockManager(session)
                
                try:
                    # Initialize branch state if needed
                    try:
                        state_info = await manager.get_branch_state("concurrent-test")
                    except:
                        state_info = BranchStateInfo(
                            branch_name="concurrent-test",
                            current_state=BranchState.ACTIVE,
                            state_changed_by="system",
                            state_change_reason="Initial"
                        )
                        await manager._store_branch_state(state_info)
                        await session.commit()
                    
                    # Try to acquire resource-type lock
                    lock_id = await manager.acquire_lock(
                        branch_name="concurrent-test",
                        lock_type=LockType.INDEXING,
                        locked_by=f"indexer-{service_id}",
                        lock_scope=LockScope.RESOURCE_TYPE,
                        resource_type=resource_type,
                        reason=f"Indexing {resource_type}"
                    )
                    
                    results.append({
                        "service": service_id,
                        "resource_type": resource_type,
                        "lock_id": lock_id,
                        "status": "acquired"
                    })
                    
                    # Simulate indexing work
                    await asyncio.sleep(1)
                    
                    # Release lock
                    await manager.release_lock(lock_id, f"indexer-{service_id}")
                    
                    results[-1]["status"] = "completed"
                    
                except Exception as e:
                    errors.append({
                        "service": service_id,
                        "resource_type": resource_type,
                        "error": str(e)
                    })
        
        # Run 4 indexers concurrently on different resource types
        await asyncio.gather(
            index_resource_type(1, "object_type"),
            index_resource_type(2, "link_type"),
            index_resource_type(3, "action_type"),
            index_resource_type(4, "function_type"),
            return_exceptions=True
        )
        
        # All should succeed (different resource types)
        assert len(results) == 4
        assert all(r["status"] == "completed" for r in results)
        assert len(errors) == 0
    
    async def test_real_heartbeat_expiration(self, db_session):
        """Test that locks with missed heartbeats are actually expired"""
        manager = DistributedLockManager(db_session)
        
        # Create lock with missed heartbeat
        past_heartbeat = datetime.now(timezone.utc) - timedelta(minutes=10)
        heartbeat_lock = BranchLock(
            id="heartbeat-test-1",
            branch_name="heartbeat-branch",
            lock_type=LockType.INDEXING,
            lock_scope=LockScope.BRANCH,
            locked_by="dead-service",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),  # TTL still valid
            heartbeat_interval=60,  # Expects heartbeat every minute
            last_heartbeat=past_heartbeat,  # But hasn't sent one for 10 minutes
            heartbeat_source="dead-service",
            auto_release_enabled=True,
            reason="Testing heartbeat expiration"
        )
        
        # Store it
        state_info = BranchStateInfo(
            branch_name="heartbeat-branch",
            current_state=BranchState.LOCKED_FOR_WRITE,
            state_changed_by="dead-service",
            state_change_reason="Testing",
            active_locks=[heartbeat_lock]
        )
        
        manager._branch_states["heartbeat-branch"] = state_info
        manager._active_locks[heartbeat_lock.id] = heartbeat_lock
        
        await manager._store_branch_state(state_info)
        await db_session.commit()
        
        # Run heartbeat cleanup
        await manager.cleanup_heartbeat_expired_locks()
        
        # Lock should be gone
        assert heartbeat_lock.id not in manager._active_locks
        
        # Verify in database too
        result = await db_session.execute(
            text("SELECT state_data FROM branch_states WHERE branch_name = :name"),
            {"name": "heartbeat-branch"}
        )
        row = result.fetchone()
        
        if row:
            state_data = row[0]
            active_locks = state_data.get("active_locks", [])
            assert len(active_locks) == 0
    
    async def test_real_transaction_rollback(self, real_db_engine):
        """Test that locks are released on transaction rollback"""
        results = {"lock_held_during_transaction": False, "lock_available_after_rollback": False}
        
        async def transaction_with_rollback():
            async_session = sessionmaker(
                real_db_engine, class_=AsyncSession, expire_on_commit=False
            )
            
            async with async_session() as session:
                manager = DistributedLockManager(session)
                
                try:
                    async with manager.distributed_lock("rollback-test"):
                        results["lock_held_during_transaction"] = True
                        # Simulate error that causes rollback
                        raise Exception("Simulated error")
                except Exception:
                    # Transaction will rollback
                    pass
        
        async def try_lock_after_rollback():
            await asyncio.sleep(0.5)  # Wait for first transaction to fail
            
            async_session = sessionmaker(
                real_db_engine, class_=AsyncSession, expire_on_commit=False
            )
            
            async with async_session() as session:
                manager = DistributedLockManager(session)
                
                try:
                    # This should succeed if rollback released the lock
                    async with manager.distributed_lock("rollback-test", timeout_ms=1000):
                        results["lock_available_after_rollback"] = True
                except:
                    results["lock_available_after_rollback"] = False
        
        # Run both
        await asyncio.gather(
            transaction_with_rollback(),
            try_lock_after_rollback(),
            return_exceptions=True
        )
        
        # Verify rollback released the lock
        assert results["lock_held_during_transaction"] is True
        assert results["lock_available_after_rollback"] is True


class TestRealPerformance:
    """Real performance tests with actual database"""
    
    async def test_lock_acquisition_performance(self, real_db_engine):
        """Measure actual lock acquisition time"""
        async_session = sessionmaker(
            real_db_engine, class_=AsyncSession, expire_on_commit=False
        )
        
        async with async_session() as session:
            manager = DistributedLockManager(session)
            
            times = []
            
            for i in range(10):
                start = asyncio.get_event_loop().time()
                
                async with manager.distributed_lock(f"perf-test-{i}"):
                    elapsed = asyncio.get_event_loop().time() - start
                    times.append(elapsed)
            
            avg_time = sum(times) / len(times)
            max_time = max(times)
            
            print(f"\nLock acquisition times:")
            print(f"Average: {avg_time*1000:.2f}ms")
            print(f"Max: {max_time*1000:.2f}ms")
            
            # Should be fast
            assert avg_time < 0.05  # 50ms average
            assert max_time < 0.1   # 100ms max


if __name__ == "__main__":
    import sys
    
    if "--real" in sys.argv:
        # Run only if explicitly requested
        pytest.main([__file__, "-v", "-s", "--tb=short"])
    else:
        print("Run with --real flag to execute real database tests")
        print("Requires PostgreSQL running at localhost:5432 with database 'test_oms'")
        print("Example: python test_distributed_lock_real.py --real")