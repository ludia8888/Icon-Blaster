"""
Tests for TTL & Heartbeat automatic lock release functionality
Validates Priority 4 Foundry-style improvement
"""
import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from core.branch.lock_manager import BranchLockManager, LockConflictError
from models.branch_state import (
    BranchState, BranchLock, BranchStateInfo, HeartbeatRecord,
    LockType, LockScope, is_lock_expired_by_ttl, is_lock_expired_by_heartbeat
)


class TestTTLHeartbeatFunctionality:
    """Test TTL & Heartbeat automatic lock release mechanisms"""
    
    @pytest.fixture
    def lock_manager(self):
        """Create a lock manager for testing"""
        return BranchLockManager()
    
    @pytest.mark.asyncio
    async def test_heartbeat_enabled_lock_creation(self, lock_manager):
        """Test that locks are created with heartbeat support by default"""
        lock_id = await lock_manager.acquire_lock(
            branch_name="test-heartbeat",
            lock_type=LockType.INDEXING,
            locked_by="test-service",
            enable_heartbeat=True,
            heartbeat_interval=60
        )
        
        lock = await lock_manager.get_lock_status(lock_id)
        
        # Verify heartbeat properties
        assert lock.heartbeat_interval == 60
        assert lock.last_heartbeat is not None
        assert lock.heartbeat_source == "test-service"
        assert lock.auto_release_enabled == True
        
        # Heartbeat should be recent (within last few seconds)
        now = datetime.now(timezone.utc)
        time_since_heartbeat = (now - lock.last_heartbeat).total_seconds()
        assert time_since_heartbeat < 5  # Less than 5 seconds ago
    
    @pytest.mark.asyncio
    async def test_send_heartbeat(self, lock_manager):
        """Test sending heartbeats for active locks"""
        # Create lock with heartbeat
        lock_id = await lock_manager.acquire_lock(
            branch_name="heartbeat-test",
            lock_type=LockType.INDEXING,
            locked_by="funnel-service",
            enable_heartbeat=True,
            heartbeat_interval=120
        )
        
        # Wait a moment
        await asyncio.sleep(0.1)
        
        # Send heartbeat
        success = await lock_manager.send_heartbeat(
            lock_id=lock_id,
            service_name="funnel-service",
            status="healthy",
            progress_info={"indexing_progress": 75}
        )
        
        assert success == True
        
        # Verify heartbeat was recorded
        lock = await lock_manager.get_lock_status(lock_id)
        assert lock.heartbeat_source == "funnel-service"
        
        # Last heartbeat should be very recent
        now = datetime.now(timezone.utc)
        time_since_heartbeat = (now - lock.last_heartbeat).total_seconds()
        assert time_since_heartbeat < 2  # Less than 2 seconds ago
    
    @pytest.mark.asyncio
    async def test_heartbeat_for_nonexistent_lock(self, lock_manager):
        """Test sending heartbeat for non-existent lock fails gracefully"""
        success = await lock_manager.send_heartbeat(
            lock_id="non-existent-lock",
            service_name="test-service",
            status="healthy"
        )
        
        assert success == False
    
    @pytest.mark.asyncio
    async def test_lock_health_status(self, lock_manager):
        """Test getting health status of locks"""
        # Create lock with heartbeat
        lock_id = await lock_manager.acquire_lock(
            branch_name="health-test",
            lock_type=LockType.INDEXING,
            locked_by="test-service",
            enable_heartbeat=True,
            heartbeat_interval=60
        )
        
        # Get health status
        health = await lock_manager.get_lock_health_status(lock_id)
        
        assert health["lock_id"] == lock_id
        assert health["is_active"] == True
        assert health["heartbeat_enabled"] == True
        assert health["heartbeat_source"] == "test-service"
        assert health["ttl_expired"] == False
        assert health["heartbeat_expired"] == False
        assert health["auto_release_enabled"] == True
        assert "seconds_since_last_heartbeat" in health
        assert health["heartbeat_health"] == "healthy"
    
    @pytest.mark.asyncio
    async def test_ttl_expiry_detection(self, lock_manager):
        """Test TTL expiry detection"""
        # Create lock with very short TTL
        lock_id = await lock_manager.acquire_lock(
            branch_name="ttl-test",
            lock_type=LockType.MANUAL,
            locked_by="test-user",
            timeout=timedelta(milliseconds=100)  # Very short TTL
        )
        
        # Wait for TTL to expire
        await asyncio.sleep(0.2)
        
        # Check expiry
        lock = await lock_manager.get_lock_status(lock_id)
        assert is_lock_expired_by_ttl(lock) == True
        
        # Health status should reflect expiry
        health = await lock_manager.get_lock_health_status(lock_id)
        assert health["ttl_expired"] == True
    
    @pytest.mark.asyncio
    async def test_heartbeat_expiry_detection(self, lock_manager):
        """Test heartbeat expiry detection"""
        # Create lock with heartbeat
        lock_id = await lock_manager.acquire_lock(
            branch_name="heartbeat-expiry-test",
            lock_type=LockType.INDEXING,
            locked_by="test-service",
            enable_heartbeat=True,
            heartbeat_interval=1  # 1 second interval
        )
        
        # Manually set old heartbeat (simulate missed heartbeats)
        lock = await lock_manager.get_lock_status(lock_id)
        old_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=10)  # 10 seconds ago
        lock.last_heartbeat = old_heartbeat
        
        # Check expiry (should be expired after 3x heartbeat interval = 3 seconds)
        assert is_lock_expired_by_heartbeat(lock) == True
        
        # Health status should reflect heartbeat expiry
        health = await lock_manager.get_lock_health_status(lock_id)
        assert health["heartbeat_expired"] == True
        assert health["heartbeat_health"] == "critical"
    
    @pytest.mark.asyncio
    async def test_ttl_cleanup(self, lock_manager):
        """Test automatic cleanup of TTL expired locks"""
        # Create lock with very short TTL
        lock_id = await lock_manager.acquire_lock(
            branch_name="ttl-cleanup-test",
            lock_type=LockType.MANUAL,
            locked_by="test-user",
            timeout=timedelta(milliseconds=50)  # Very short TTL
        )
        
        # Verify lock exists
        assert await lock_manager.get_lock_status(lock_id) is not None
        
        # Wait for TTL to expire
        await asyncio.sleep(0.1)
        
        # Run cleanup
        await lock_manager.cleanup_expired_locks()
        
        # Lock should be cleaned up
        assert await lock_manager.get_lock_status(lock_id) is None
    
    @pytest.mark.asyncio
    async def test_heartbeat_cleanup(self, lock_manager):
        """Test automatic cleanup of heartbeat expired locks"""
        # Create lock with heartbeat
        lock_id = await lock_manager.acquire_lock(
            branch_name="heartbeat-cleanup-test",
            lock_type=LockType.INDEXING,
            locked_by="test-service",
            enable_heartbeat=True,
            heartbeat_interval=1  # 1 second interval
        )
        
        # Verify lock exists
        assert await lock_manager.get_lock_status(lock_id) is not None
        
        # Manually set old heartbeat
        lock = await lock_manager.get_lock_status(lock_id)
        lock.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=10)
        
        # Run heartbeat cleanup
        await lock_manager.cleanup_heartbeat_expired_locks()
        
        # Lock should be cleaned up
        assert await lock_manager.get_lock_status(lock_id) is None
    
    @pytest.mark.asyncio
    async def test_extend_lock_ttl(self, lock_manager):
        """Test extending lock TTL"""
        # Create lock with short TTL
        lock_id = await lock_manager.acquire_lock(
            branch_name="extend-ttl-test",
            lock_type=LockType.MANUAL,
            locked_by="test-user",
            timeout=timedelta(hours=1)
        )
        
        lock = await lock_manager.get_lock_status(lock_id)
        original_expiry = lock.expires_at
        
        # Extend TTL by 2 hours
        success = await lock_manager.extend_lock_ttl(
            lock_id=lock_id,
            extension_duration=timedelta(hours=2),
            extended_by="admin",
            reason="Need more time for testing"
        )
        
        assert success == True
        
        # Verify TTL was extended
        updated_lock = await lock_manager.get_lock_status(lock_id)
        assert updated_lock.expires_at > original_expiry
        
        # Should be extended by approximately 2 hours
        extension = updated_lock.expires_at - original_expiry
        assert abs(extension.total_seconds() - 7200) < 60  # Within 1 minute of 2 hours
    
    @pytest.mark.asyncio
    async def test_auto_release_disabled_locks_not_cleaned(self, lock_manager):
        """Test that locks with auto_release_enabled=False are not automatically cleaned"""
        # Create lock with auto_release disabled
        lock_id = await lock_manager.acquire_lock(
            branch_name="no-auto-release-test",
            lock_type=LockType.MANUAL,
            locked_by="test-user",
            timeout=timedelta(milliseconds=50)
        )
        
        # Disable auto release
        lock = await lock_manager.get_lock_status(lock_id)
        lock.auto_release_enabled = False
        
        # Wait for TTL to expire
        await asyncio.sleep(0.1)
        
        # Run cleanup
        await lock_manager.cleanup_expired_locks()
        
        # Lock should still exist (not auto-released)
        assert await lock_manager.get_lock_status(lock_id) is not None
    
    @pytest.mark.asyncio
    async def test_write_permission_respects_expired_locks(self, lock_manager):
        """Test that write permission checks ignore expired locks"""
        # Create lock with very short TTL
        lock_id = await lock_manager.acquire_lock(
            branch_name="expired-permission-test",
            lock_type=LockType.INDEXING,
            locked_by="test-service",
            lock_scope=LockScope.RESOURCE_TYPE,
            resource_type="object_type",
            timeout=timedelta(milliseconds=50)
        )
        
        # Initially should block write
        can_write, reason = await lock_manager.check_write_permission(
            branch_name="expired-permission-test",
            action="write",
            resource_type="object_type"
        )
        assert can_write == False
        assert "locked" in reason.lower()
        
        # Wait for TTL to expire
        await asyncio.sleep(0.1)
        
        # Now should allow write (expired lock is ignored)
        can_write, reason = await lock_manager.check_write_permission(
            branch_name="expired-permission-test",
            action="write",
            resource_type="object_type"
        )
        assert can_write == True
    
    @pytest.mark.asyncio
    async def test_heartbeat_grace_period(self, lock_manager):
        """Test heartbeat grace period (3x heartbeat_interval)"""
        # Create lock with 2-second heartbeat interval
        lock_id = await lock_manager.acquire_lock(
            branch_name="grace-period-test",
            lock_type=LockType.INDEXING,
            locked_by="test-service",
            enable_heartbeat=True,
            heartbeat_interval=2
        )
        
        # Simulate missed heartbeat within grace period (5 seconds old, less than 3x2=6)
        lock = await lock_manager.get_lock_status(lock_id)
        lock.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=5)
        
        # Should not be considered expired yet
        assert is_lock_expired_by_heartbeat(lock) == False
        
        # Health should be warning, not critical
        health = await lock_manager.get_lock_health_status(lock_id)
        assert health["heartbeat_health"] == "warning"
        
        # Now simulate heartbeat beyond grace period (7 seconds old, more than 3x2=6)
        lock.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=7)
        
        # Should be considered expired
        assert is_lock_expired_by_heartbeat(lock) == True
        
        # Health should be critical
        health = await lock_manager.get_lock_health_status(lock_id)
        assert health["heartbeat_health"] == "critical"


class TestTTLHeartbeatIntegration:
    """Integration tests for TTL & Heartbeat with Foundry-style locking"""
    
    @pytest.mark.asyncio
    async def test_indexing_locks_with_heartbeat(self):
        """Test that indexing locks include heartbeat by default"""
        lock_manager = BranchLockManager()
        
        # Start indexing (should create locks with heartbeat)
        lock_ids = await lock_manager.lock_for_indexing(
            branch_name="integration-test",
            locked_by="funnel-service",
            resource_types=["object_type", "link_type"]
        )
        
        assert len(lock_ids) == 2
        
        # Check that both locks have heartbeat enabled
        for lock_id in lock_ids:
            lock = await lock_manager.get_lock_status(lock_id)
            assert lock.heartbeat_interval == 120  # 2 minutes as configured
            assert lock.last_heartbeat is not None
            assert lock.heartbeat_source == "funnel-service"
            assert lock.auto_release_enabled == True
    
    @pytest.mark.asyncio
    async def test_stuck_lock_prevention_scenario(self):
        """Test complete scenario of preventing stuck locks"""
        lock_manager = BranchLockManager()
        
        # 1. Start indexing
        lock_ids = await lock_manager.lock_for_indexing(
            branch_name="stuck-prevention-test",
            locked_by="funnel-service",
            resource_types=["object_type"]
        )
        
        lock_id = lock_ids[0]
        
        # 2. Send a few heartbeats (simulating healthy service)
        for i in range(3):
            await asyncio.sleep(0.1)
            success = await lock_manager.send_heartbeat(
                lock_id=lock_id,
                service_name="funnel-service",
                status="healthy",
                progress_info={"progress": i * 25}
            )
            assert success == True
        
        # 3. Simulate service crash (no more heartbeats)
        lock = await lock_manager.get_lock_status(lock_id)
        # Set heartbeat to old timestamp (simulate service stopped sending heartbeats)
        lock.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=400)
        
        # 4. Lock should be detected as expired
        assert is_lock_expired_by_heartbeat(lock) == True
        
        # 5. Cleanup should remove the stuck lock
        await lock_manager.cleanup_heartbeat_expired_locks()
        
        # 6. Lock should be gone
        assert await lock_manager.get_lock_status(lock_id) is None
        
        # 7. Branch should be writable again
        can_write, reason = await lock_manager.check_write_permission(
            branch_name="stuck-prevention-test",
            action="write",
            resource_type="object_type"
        )
        assert can_write == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])