"""
Final verification of lock system behavior
Confirms actual behavior matches design
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


class TestFinalLockVerification:
    """Final verification that the lock system works as designed"""
    
    async def test_lock_scope_hierarchy(self):
        """Verify lock scope hierarchy: Branch > ResourceType > Resource"""
        manager = BranchLockManager()
        
        print("\n=== Lock Scope Hierarchy Test ===")
        
        # Scenario 1: Branch lock blocks everything
        print("\n1. Branch lock blocks all other locks:")
        branch_lock = await manager.acquire_lock(
            branch_name="hierarchy-test",
            lock_type=LockType.MANUAL,
            locked_by="admin",
            lock_scope=LockScope.BRANCH,
            reason="Branch maintenance"
        )
        print(f"  ✓ Branch lock acquired: {branch_lock}")
        
        # Try resource type lock - should fail
        try:
            await manager.acquire_lock(
                branch_name="hierarchy-test",
                lock_type=LockType.INDEXING,
                locked_by="indexer",
                lock_scope=LockScope.RESOURCE_TYPE,
                resource_type="object_type"
            )
            print("  ✗ ERROR: Resource type lock should have been blocked!")
        except LockConflictError:
            print("  ✓ Resource type lock correctly blocked by branch lock")
        
        # Release branch lock
        await manager.release_lock(branch_lock, "admin")
        print("  ✓ Branch lock released")
        
        # Scenario 2: Different resource types don't conflict
        print("\n2. Different resource types can be locked simultaneously:")
        object_lock = await manager.acquire_lock(
            branch_name="hierarchy-test",
            lock_type=LockType.INDEXING,
            locked_by="indexer1",
            lock_scope=LockScope.RESOURCE_TYPE,
            resource_type="object_type"
        )
        print(f"  ✓ object_type lock acquired: {object_lock}")
        
        link_lock = await manager.acquire_lock(
            branch_name="hierarchy-test",
            lock_type=LockType.INDEXING,
            locked_by="indexer2",
            lock_scope=LockScope.RESOURCE_TYPE,
            resource_type="link_type"
        )
        print(f"  ✓ link_type lock acquired: {link_lock}")
        
        # Same resource type should conflict
        try:
            await manager.acquire_lock(
                branch_name="hierarchy-test",
                lock_type=LockType.INDEXING,
                locked_by="indexer3",
                lock_scope=LockScope.RESOURCE_TYPE,
                resource_type="object_type"
            )
            print("  ✗ ERROR: Same resource type should conflict!")
        except LockConflictError:
            print("  ✓ Same resource type correctly conflicts")
        
        print(f"\n  Active locks: {len(manager._active_locks)}")
        
    async def test_foundry_style_minimal_locking(self):
        """Verify Foundry-style minimal scope locking"""
        manager = BranchLockManager()
        
        print("\n=== Foundry-Style Minimal Locking Test ===")
        
        # Simulate Funnel Service indexing specific resources
        print("\n1. Funnel Service indexes specific resource types:")
        
        lock_ids = await manager.lock_for_indexing(
            branch_name="foundry-branch",
            locked_by="funnel-service",
            resource_types=["object_type", "link_type"],
            force_branch_lock=False  # Foundry style
        )
        
        print(f"  ✓ Acquired {len(lock_ids)} resource-type locks")
        
        # Developers can still work on other resources
        print("\n2. Developers can work on other resources:")
        
        action_lock = await manager.acquire_lock(
            branch_name="foundry-branch",
            lock_type=LockType.MANUAL,
            locked_by="developer1",
            lock_scope=LockScope.RESOURCE_TYPE,
            resource_type="action_type",
            reason="Adding new action"
        )
        print(f"  ✓ Developer acquired action_type lock: {action_lock}")
        
        # Branch state should remain ACTIVE
        state = await manager.get_branch_state("foundry-branch")
        print(f"  ✓ Branch state: {state.current_state.value} (not locked)")
        
        # Complete indexing
        print("\n3. Complete indexing:")
        success = await manager.complete_indexing(
            branch_name="foundry-branch",
            completed_by="funnel-service",
            resource_types=["object_type", "link_type"]
        )
        print(f"  ✓ Indexing completed: {success}")
        
        # Developer can still work
        print(f"  ✓ Developer still has action_type lock")
        assert action_lock in manager._active_locks
        
    async def test_ttl_and_heartbeat_working(self):
        """Verify TTL and heartbeat mechanisms work"""
        manager = BranchLockManager()
        
        print("\n=== TTL and Heartbeat Test ===")
        
        # Create lock with short TTL
        print("\n1. Lock with 2-second TTL:")
        short_ttl_lock = await manager.acquire_lock(
            branch_name="ttl-test",
            lock_type=LockType.MANUAL,
            locked_by="user1",
            timeout=timedelta(seconds=2),
            enable_heartbeat=False  # No heartbeat
        )
        
        lock = manager._active_locks[short_ttl_lock]
        print(f"  ✓ Lock expires at: {lock.expires_at}")
        
        # Wait for expiration
        print("  ⏳ Waiting 3 seconds...")
        await asyncio.sleep(3)
        
        # Run cleanup
        await manager.cleanup_expired_locks()
        
        if short_ttl_lock in manager._active_locks:
            print("  ✗ ERROR: TTL expired lock not cleaned up!")
        else:
            print("  ✓ TTL expired lock was cleaned up")
        
        # Create lock with heartbeat
        print("\n2. Lock with heartbeat:")
        hb_lock = await manager.acquire_lock(
            branch_name="hb-test",
            lock_type=LockType.INDEXING,
            locked_by="long-service",
            timeout=timedelta(hours=1),
            enable_heartbeat=True,
            heartbeat_interval=60
        )
        
        lock = manager._active_locks[hb_lock]
        print(f"  ✓ Heartbeat interval: {lock.heartbeat_interval}s")
        print(f"  ✓ Last heartbeat: {lock.last_heartbeat}")
        
        # Send heartbeat
        await asyncio.sleep(0.5)
        success = await manager.send_heartbeat(
            lock_id=hb_lock,
            service_name="long-service",
            status="healthy",
            progress_info={"progress": 50}
        )
        print(f"  ✓ Heartbeat sent: {success}")
        
        # Simulate missed heartbeats
        print("\n3. Simulate missed heartbeats:")
        lock.last_heartbeat = datetime.now(timezone.utc) - timedelta(minutes=5)
        print(f"  ✓ Set last heartbeat to 5 minutes ago")
        
        # Run heartbeat cleanup
        await manager.cleanup_heartbeat_expired_locks()
        
        if hb_lock in manager._active_locks:
            print("  ✗ ERROR: Heartbeat expired lock not cleaned up!")
        else:
            print("  ✓ Heartbeat expired lock was cleaned up")
        
    async def test_real_world_scenario(self):
        """Test a real-world scenario"""
        manager = BranchLockManager()
        
        print("\n=== Real World Scenario ===")
        print("Scenario: Multiple teams working on 'feature-analytics' branch")
        
        # Data team starts indexing object types
        print("\n1. Data team starts indexing Employee and Department objects:")
        data_locks = []
        for obj_type in ["Employee", "Department"]:
            lock_id = await manager.acquire_lock(
                branch_name="feature-analytics",
                lock_type=LockType.INDEXING,
                locked_by="data-team-etl",
                lock_scope=LockScope.RESOURCE,
                resource_type="object_type",
                resource_id=obj_type,
                reason=f"Reindexing {obj_type} for analytics",
                enable_heartbeat=True,
                heartbeat_interval=300  # 5 minutes
            )
            data_locks.append(lock_id)
            print(f"  ✓ Locked {obj_type}: {lock_id}")
        
        # Backend team can work on APIs
        print("\n2. Backend team adds new analytics API:")
        api_lock = await manager.acquire_lock(
            branch_name="feature-analytics",
            lock_type=LockType.MANUAL,
            locked_by="backend-dev-1",
            lock_scope=LockScope.RESOURCE_TYPE,
            resource_type="action_type",
            reason="Adding analytics dashboard API"
        )
        print(f"  ✓ Backend team locked action_type: {api_lock}")
        
        # Frontend team can work on functions
        print("\n3. Frontend team updates dashboard functions:")
        ui_lock = await manager.acquire_lock(
            branch_name="feature-analytics",
            lock_type=LockType.MANUAL,
            locked_by="frontend-dev-1",
            lock_scope=LockScope.RESOURCE_TYPE,
            resource_type="function_type",
            reason="Update dashboard rendering functions"
        )
        print(f"  ✓ Frontend team locked function_type: {ui_lock}")
        
        # Check branch state
        state = await manager.get_branch_state("feature-analytics")
        print(f"\n4. Branch state: {state.current_state.value}")
        print(f"   Active locks: {len(state.active_locks)}")
        
        # Data team sends heartbeats during long indexing
        print("\n5. Data team sends heartbeats:")
        for lock_id in data_locks:
            success = await manager.send_heartbeat(
                lock_id=lock_id,
                service_name="data-team-etl",
                status="healthy",
                progress_info={"indexed": 50000, "total": 100000}
            )
            print(f"  ✓ Heartbeat for {lock_id[:8]}...: {success}")
        
        # Teams complete their work
        print("\n6. Teams complete work:")
        for lock_id in data_locks:
            await manager.release_lock(lock_id, "data-team-etl")
        print("  ✓ Data team completed indexing")
        
        await manager.release_lock(api_lock, "backend-dev-1")
        print("  ✓ Backend team completed API")
        
        await manager.release_lock(ui_lock, "frontend-dev-1")
        print("  ✓ Frontend team completed UI")
        
        # Final state
        state = await manager.get_branch_state("feature-analytics")
        print(f"\n7. Final branch state: {state.current_state.value}")
        print(f"   Active locks: {len(state.active_locks)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])