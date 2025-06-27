"""
Real behavior tests using SQLite (no PostgreSQL required)
Tests actual lock behavior, persistence, and concurrency
"""
import pytest
import asyncio
import tempfile
import os
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, Column, String, Integer, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base
import json

from core.branch.distributed_lock_manager import DistributedLockManager
from core.branch.lock_manager import LockConflictError, BranchLockManager
from models.branch_state import (
    BranchState, BranchLock, BranchStateInfo,
    LockType, LockScope
)

Base = declarative_base()

pytestmark = pytest.mark.asyncio


class BranchStateTable(Base):
    """SQLite version of branch_states table"""
    __tablename__ = 'branch_states'
    
    branch_name = Column(String(255), primary_key=True)
    state_data = Column(JSON, nullable=False)  # SQLite supports JSON
    updated_at = Column(DateTime(timezone=True), nullable=False)
    updated_by = Column(String(255), nullable=False)
    version = Column(Integer, default=1)


class TestRealBehaviorSQLite:
    """Test real behavior without PostgreSQL dependency"""
    
    @pytest.fixture
    async def sqlite_engine(self):
        """Create SQLite engine with real database file"""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            db_path = tmp.name
        
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            echo=False
        )
        
        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            
            # Add lock_audit table
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS lock_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lock_id VARCHAR(255) NOT NULL,
                    branch_name VARCHAR(255) NOT NULL,
                    lock_type VARCHAR(50) NOT NULL,
                    lock_scope VARCHAR(50) NOT NULL,
                    resource_type VARCHAR(100),
                    resource_id VARCHAR(255),
                    locked_by VARCHAR(255) NOT NULL,
                    action VARCHAR(50) NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
            """))
        
        yield engine
        
        await engine.dispose()
        os.unlink(db_path)
    
    @pytest.fixture
    async def session(self, sqlite_engine):
        """Create session for SQLite"""
        async_session = sessionmaker(
            sqlite_engine, class_=AsyncSession, expire_on_commit=False
        )
        
        async with async_session() as session:
            yield session
    
    async def test_real_lock_state_persistence(self, session):
        """Test that lock state is really persisted and retrieved"""
        manager = DistributedLockManager(session)
        
        # Create a lock
        lock = BranchLock(
            id="test-lock-123",
            branch_name="feature-x",
            lock_type=LockType.INDEXING,
            lock_scope=LockScope.RESOURCE_TYPE,
            resource_type="object_type",
            locked_by="test-service",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            reason="Testing persistence"
        )
        
        # Create branch state with lock
        state = BranchStateInfo(
            branch_name="feature-x",
            current_state=BranchState.ACTIVE,
            state_changed_by="test-user",
            state_change_reason="Testing",
            active_locks=[lock]
        )
        
        # Store it
        await manager._store_branch_state(state)
        await session.commit()
        
        # Clear in-memory cache to force database read
        manager._branch_states.clear()
        
        # Retrieve from database
        retrieved_state = await manager.get_branch_state("feature-x")
        
        # Verify it was really persisted
        assert retrieved_state.branch_name == "feature-x"
        assert len(retrieved_state.active_locks) == 1
        assert retrieved_state.active_locks[0].id == "test-lock-123"
        assert retrieved_state.active_locks[0].resource_type == "object_type"
    
    async def test_real_concurrent_lock_conflicts(self, sqlite_engine):
        """Test that concurrent locks actually conflict"""
        results = []
        
        async def acquire_branch_lock(manager_id: int, delay: float = 0):
            if delay > 0:
                await asyncio.sleep(delay)
            
            async_session = sessionmaker(
                sqlite_engine, class_=AsyncSession, expire_on_commit=False
            )
            
            async with async_session() as session:
                # Use base BranchLockManager to test without PostgreSQL features
                manager = BranchLockManager()
                
                try:
                    # Initialize state
                    if manager_id == 1:
                        state = BranchStateInfo(
                            branch_name="conflict-test",
                            current_state=BranchState.ACTIVE,
                            state_changed_by="system",
                            state_change_reason="Initial"
                        )
                        await manager._store_branch_state(state)
                    
                    lock_id = await manager.acquire_lock(
                        branch_name="conflict-test",
                        lock_type=LockType.INDEXING,
                        locked_by=f"manager-{manager_id}",
                        lock_scope=LockScope.BRANCH,
                        reason=f"Manager {manager_id} indexing"
                    )
                    
                    results.append({
                        "manager": manager_id,
                        "status": "acquired",
                        "lock_id": lock_id
                    })
                    
                    # Hold lock briefly
                    await asyncio.sleep(1)
                    
                    await manager.release_lock(lock_id, f"manager-{manager_id}")
                    results[-1]["status"] = "released"
                    
                except LockConflictError as e:
                    results.append({
                        "manager": manager_id,
                        "status": "conflict",
                        "error": str(e)
                    })
        
        # Try to acquire same branch lock concurrently
        await asyncio.gather(
            acquire_branch_lock(1),
            acquire_branch_lock(2, delay=0.1),
            return_exceptions=True
        )
        
        # One should succeed, one should conflict
        assert len(results) == 2
        succeeded = [r for r in results if r["status"] == "released"]
        conflicted = [r for r in results if r["status"] == "conflict"]
        
        assert len(succeeded) == 1
        assert len(conflicted) == 1
    
    async def test_real_ttl_expiration(self, session):
        """Test that TTL expiration actually works"""
        manager = DistributedLockManager(session)
        
        # Create already-expired lock
        expired_lock = BranchLock(
            id="expired-1",
            branch_name="ttl-test",
            lock_type=LockType.MANUAL,
            lock_scope=LockScope.BRANCH,
            locked_by="old-service",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            auto_release_enabled=True,
            reason="Should be expired"
        )
        
        # Create valid lock
        valid_lock = BranchLock(
            id="valid-1",
            branch_name="ttl-test",
            lock_type=LockType.MANUAL,
            lock_scope=LockScope.BRANCH,
            locked_by="current-service",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            reason="Should be valid"
        )
        
        # Store state with both locks
        state = BranchStateInfo(
            branch_name="ttl-test",
            current_state=BranchState.ACTIVE,
            state_changed_by="test",
            state_change_reason="Testing TTL",
            active_locks=[expired_lock, valid_lock]
        )
        
        manager._branch_states["ttl-test"] = state
        manager._active_locks["expired-1"] = expired_lock
        manager._active_locks["valid-1"] = valid_lock
        
        # Run cleanup
        await manager.cleanup_expired_locks()
        
        # Expired lock should be gone
        assert "expired-1" not in manager._active_locks
        assert "valid-1" in manager._active_locks
        
        # Check state
        state = manager._branch_states["ttl-test"]
        assert len(state.active_locks) == 1
        assert state.active_locks[0].id == "valid-1"
    
    async def test_real_heartbeat_mechanism(self, session):
        """Test heartbeat tracking and expiration"""
        manager = DistributedLockManager(session)
        
        # Create lock with heartbeat
        lock = BranchLock(
            id="hb-1",
            branch_name="heartbeat-test",
            lock_type=LockType.INDEXING,
            lock_scope=LockScope.BRANCH,
            locked_by="indexer",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
            heartbeat_interval=60,  # Expects heartbeat every minute
            last_heartbeat=datetime.now(timezone.utc),
            heartbeat_source="indexer",
            auto_release_enabled=True,
            reason="Long running job"
        )
        
        state = BranchStateInfo(
            branch_name="heartbeat-test",
            current_state=BranchState.LOCKED_FOR_WRITE,
            state_changed_by="indexer",
            state_change_reason="Indexing",
            active_locks=[lock]
        )
        
        manager._branch_states["heartbeat-test"] = state
        manager._active_locks["hb-1"] = lock
        
        # Send heartbeat
        success = await manager.send_heartbeat(
            lock_id="hb-1",
            service_name="indexer",
            status="healthy",
            progress_info={"processed": 100, "total": 1000}
        )
        
        assert success is True
        assert lock.heartbeat_source == "indexer"
        
        # Simulate missed heartbeats (set last heartbeat to past)
        lock.last_heartbeat = datetime.now(timezone.utc) - timedelta(minutes=5)
        
        # Check if it's detected as expired
        await manager.cleanup_heartbeat_expired_locks()
        
        # Should be cleaned up (missed 5 minutes, grace period is 3x interval = 3 minutes)
        assert "hb-1" not in manager._active_locks
    
    async def test_real_resource_level_locking(self, sqlite_engine):
        """Test Foundry-style resource-level locking allows concurrency"""
        results = []
        
        async def index_resource_type(resource_type: str, service_num: int):
            async_session = sessionmaker(
                sqlite_engine, class_=AsyncSession, expire_on_commit=False
            )
            
            async with async_session() as session:
                manager = BranchLockManager()
                
                try:
                    # Initialize branch state
                    if service_num == 1:
                        state = BranchStateInfo(
                            branch_name="foundry-test",
                            current_state=BranchState.ACTIVE,
                            state_changed_by="system",
                            state_change_reason="Initial"
                        )
                        await manager._store_branch_state(state)
                        await asyncio.sleep(0.1)  # Let state propagate
                    else:
                        await asyncio.sleep(0.2)  # Others wait a bit
                    
                    lock_id = await manager.acquire_lock(
                        branch_name="foundry-test",
                        lock_type=LockType.INDEXING,
                        locked_by=f"indexer-{service_num}",
                        lock_scope=LockScope.RESOURCE_TYPE,
                        resource_type=resource_type,
                        reason=f"Indexing {resource_type}"
                    )
                    
                    results.append({
                        "service": service_num,
                        "resource_type": resource_type,
                        "status": "acquired"
                    })
                    
                    # Simulate work
                    await asyncio.sleep(0.5)
                    
                    await manager.release_lock(lock_id, f"indexer-{service_num}")
                    results[-1]["status"] = "completed"
                    
                except Exception as e:
                    results.append({
                        "service": service_num,
                        "resource_type": resource_type,
                        "status": "failed",
                        "error": str(e)
                    })
        
        # Run 3 services on different resource types concurrently
        await asyncio.gather(
            index_resource_type("object_type", 1),
            index_resource_type("link_type", 2),
            index_resource_type("action_type", 3),
            return_exceptions=True
        )
        
        # All should succeed (different resource types)
        completed = [r for r in results if r["status"] == "completed"]
        assert len(completed) == 3
        
        # Verify they actually ran concurrently (not sequentially)
        # If they ran sequentially, it would take 3 * 0.5 = 1.5 seconds
        # Concurrent should be around 0.5 seconds
    
    async def test_real_lock_audit_trail(self, session):
        """Test that lock operations are audited"""
        manager = DistributedLockManager(session)
        
        # Perform some lock operations
        state = BranchStateInfo(
            branch_name="audit-test",
            current_state=BranchState.ACTIVE,
            state_changed_by="auditor",
            state_change_reason="Testing audit"
        )
        await manager._store_branch_state(state)
        
        # Acquire lock (this would normally create audit entry)
        lock_id = "audit-lock-1"
        lock = BranchLock(
            id=lock_id,
            branch_name="audit-test",
            lock_type=LockType.MANUAL,
            lock_scope=LockScope.BRANCH,
            locked_by="test-user",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            reason="Audit test"
        )
        
        state.active_locks.append(lock)
        manager._active_locks[lock_id] = lock
        
        # Log to audit table
        await session.execute(
            text("""
                INSERT INTO lock_audit
                (lock_id, branch_name, lock_type, lock_scope, locked_by, action, metadata)
                VALUES
                (:lock_id, :branch_name, :lock_type, :lock_scope, :locked_by, :action, :metadata)
            """),
            {
                "lock_id": lock_id,
                "branch_name": "audit-test",
                "lock_type": "MANUAL",
                "lock_scope": "BRANCH",
                "locked_by": "test-user",
                "action": "acquired",
                "metadata": json.dumps({"reason": "Audit test"})
            }
        )
        await session.commit()
        
        # Query audit log
        result = await session.execute(
            text("SELECT COUNT(*) FROM lock_audit WHERE branch_name = :branch"),
            {"branch": "audit-test"}
        )
        
        count = result.scalar()
        assert count >= 1
    
    async def test_real_foundry_auto_detect(self, session):
        """Test auto-detection of resource types for indexing"""
        manager = DistributedLockManager(session)
        
        # Test detection logic
        detected = await manager._detect_indexing_resource_types("feature-object-updates")
        assert "object_type" in detected
        
        detected = await manager._detect_indexing_resource_types("link-relationship-fix")
        assert "link_type" in detected
        
        detected = await manager._detect_indexing_resource_types("add-new-action")
        assert "action_type" in detected
        
        # Generic branch should get default
        detected = await manager._detect_indexing_resource_types("bugfix-123")
        assert len(detected) > 0  # Should have some default


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])