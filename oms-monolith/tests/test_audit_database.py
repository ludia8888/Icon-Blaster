"""
Tests for Audit Database Service
Validates audit log storage, querying, and compliance features
"""
import pytest
import pytest_asyncio
import asyncio
import tempfile
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

from core.audit.audit_database import AuditDatabase, AuditRetentionPolicy
from models.audit_events import (
    AuditEventV1, AuditEventFilter, AuditAction, ResourceType,
    ActorInfo, TargetInfo, ChangeDetails, create_audit_event
)


class TestAuditRetentionPolicy:
    """Test audit retention policy functionality"""
    
    def test_default_retention_periods(self):
        """Test default retention periods for different actions"""
        policy = AuditRetentionPolicy()
        
        # Security events - extended retention
        assert policy.get_retention_days(AuditAction.AUTH_LOGIN) == 2555  # 7 years
        assert policy.get_retention_days(AuditAction.AUTH_FAILED) == 2555
        assert policy.get_retention_days(AuditAction.ACL_CREATE) == 2555
        
        # Schema changes - long retention
        assert policy.get_retention_days(AuditAction.SCHEMA_CREATE) == 1825  # 5 years
        assert policy.get_retention_days(AuditAction.OBJECT_TYPE_UPDATE) == 1825
        
        # Regular operations - standard retention
        assert policy.get_retention_days(AuditAction.BRANCH_CREATE) == 365  # 1 year
        assert policy.get_retention_days(AuditAction.BRANCH_MERGE) == 730  # 2 years
        
        # System operations - shorter retention
        assert policy.get_retention_days(AuditAction.INDEXING_STARTED) == 90  # 3 months
        assert policy.get_retention_days(AuditAction.INDEXING_FAILED) == 180  # 6 months
    
    def test_expiry_date_calculation(self):
        """Test expiry date calculation"""
        policy = AuditRetentionPolicy()
        
        base_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        
        # Security event - 7 years
        expiry = policy.calculate_expiry_date(AuditAction.AUTH_LOGIN, base_time)
        expected = base_time + timedelta(days=2555)
        assert expiry == expected
        
        # Schema event - 5 years
        expiry = policy.calculate_expiry_date(AuditAction.SCHEMA_CREATE, base_time)
        expected = base_time + timedelta(days=1825)
        assert expiry == expected
        
        # Unknown action - default retention
        expiry = policy.calculate_expiry_date(AuditAction.SYSTEM_EXPORT, base_time)
        expected = base_time + timedelta(days=2555)  # Default
        assert expiry == expected


class TestAuditDatabase:
    """Test audit database functionality"""
    
    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database file"""
        fd, path = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        yield path
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
    
    @pytest_asyncio.fixture
    async def audit_db(self, temp_db_path):
        """Create audit database instance"""
        db = AuditDatabase(temp_db_path)
        await db.initialize()
        return db
    
    @pytest.fixture
    def sample_audit_event(self):
        """Create sample audit event for testing"""
        actor = ActorInfo(
            id="user123",
            username="testuser",
            email="test@example.com",
            roles=["developer"],
            service_account=False,
            auth_method="jwt",
            ip_address="192.168.1.100",
            user_agent="pytest/1.0"
        )
        
        target = TargetInfo(
            resource_type=ResourceType.OBJECT_TYPE,
            resource_id="object123",
            resource_name="TestObject",
            branch="feature/test"
        )
        
        changes = ChangeDetails(
            commit_hash="abc123",
            version_before="v1.0",
            version_after="v1.1",
            fields_changed=["name", "description"],
            old_values={"name": "Old Name", "description": "Old Desc"},
            new_values={"name": "New Name", "description": "New Desc"}
        )
        
        return create_audit_event(
            action=AuditAction.OBJECT_TYPE_UPDATE,
            actor=actor,
            target=target,
            changes=changes,
            success=True,
            request_id="req-123",
            metadata={"test": True}
        )
    
    @pytest.mark.asyncio
    async def test_database_initialization(self, temp_db_path):
        """Test database schema creation"""
        db = AuditDatabase(temp_db_path)
        assert not db._initialized
        
        await db.initialize()
        assert db._initialized
        assert Path(temp_db_path).exists()
        
        # Test idempotent initialization
        await db.initialize()
        assert db._initialized
    
    @pytest.mark.asyncio
    async def test_store_audit_event(self, audit_db, sample_audit_event):
        """Test storing a single audit event"""
        # Set event ID and time
        sample_audit_event.id = "test-event-123"
        sample_audit_event.time = datetime.now(timezone.utc)
        
        success = await audit_db.store_audit_event(sample_audit_event)
        assert success
        
        # Verify event was stored
        stored_event = await audit_db.get_audit_event_by_id("test-event-123")
        assert stored_event is not None
        assert stored_event['id'] == "test-event-123"
        assert stored_event['action'] == AuditAction.OBJECT_TYPE_UPDATE.value
        assert stored_event['actor_id'] == "user123"
        assert stored_event['actor_username'] == "testuser"
        assert stored_event['target_resource_type'] == ResourceType.OBJECT_TYPE.value
        assert stored_event['target_resource_id'] == "object123"
        assert stored_event['success'] == True
        assert stored_event['changes'] is not None
        assert stored_event['metadata'] is not None
    
    @pytest.mark.asyncio
    async def test_store_audit_events_batch(self, audit_db):
        """Test storing multiple audit events in batch"""
        events = []
        
        for i in range(5):
            actor = ActorInfo(
                id=f"user{i}",
                username=f"testuser{i}",
                service_account=False
            )
            
            target = TargetInfo(
                resource_type=ResourceType.BRANCH,
                resource_id=f"branch{i}",
                resource_name=f"TestBranch{i}"
            )
            
            event = create_audit_event(
                action=AuditAction.BRANCH_CREATE,
                actor=actor,
                target=target,
                success=True
            )
            event.id = f"batch-event-{i}"
            event.time = datetime.now(timezone.utc) - timedelta(minutes=i)
            events.append(event)
        
        stored_count = await audit_db.store_audit_events_batch(events)
        assert stored_count == 5
        
        # Verify all events were stored
        for i in range(5):
            stored_event = await audit_db.get_audit_event_by_id(f"batch-event-{i}")
            assert stored_event is not None
            assert stored_event['actor_id'] == f"user{i}"
    
    @pytest.mark.asyncio
    async def test_query_audit_events_basic(self, audit_db):
        """Test basic audit event querying"""
        # Store some test events
        events = []
        base_time = datetime.now(timezone.utc)
        
        for i in range(10):
            actor = ActorInfo(
                id=f"user{i % 3}",  # 3 different users
                username=f"testuser{i % 3}",
                service_account=False
            )
            
            target = TargetInfo(
                resource_type=ResourceType.OBJECT_TYPE if i % 2 == 0 else ResourceType.LINK_TYPE,
                resource_id=f"resource{i}",
                branch="main" if i < 5 else "feature/test"
            )
            
            event = create_audit_event(
                action=AuditAction.OBJECT_TYPE_CREATE if i % 2 == 0 else AuditAction.LINK_TYPE_CREATE,
                actor=actor,
                target=target,
                success=i % 4 != 3  # Every 4th event fails
            )
            event.id = f"query-test-{i}"
            event.time = base_time - timedelta(minutes=i)
            events.append(event)
        
        await audit_db.store_audit_events_batch(events)
        
        # Test basic query - all events
        filter_criteria = AuditEventFilter(limit=20)
        results, total_count = await audit_db.query_audit_events(filter_criteria)
        
        assert total_count == 10
        assert len(results) == 10
        
        # Events should be ordered by created_at DESC (newest first)
        assert results[0]['id'] == "query-test-0"  # Most recent
        assert results[-1]['id'] == "query-test-9"  # Oldest
    
    @pytest.mark.asyncio
    async def test_query_audit_events_filtering(self, audit_db):
        """Test audit event querying with filters"""
        # Store test events (from previous test)
        events = []
        base_time = datetime.now(timezone.utc)
        
        for i in range(10):
            actor = ActorInfo(
                id=f"user{i % 3}",
                username=f"testuser{i % 3}",
                service_account=False
            )
            
            target = TargetInfo(
                resource_type=ResourceType.OBJECT_TYPE if i % 2 == 0 else ResourceType.LINK_TYPE,
                resource_id=f"resource{i}",
                branch="main" if i < 5 else "feature/test"
            )
            
            event = create_audit_event(
                action=AuditAction.OBJECT_TYPE_CREATE if i % 2 == 0 else AuditAction.LINK_TYPE_CREATE,
                actor=actor,
                target=target,
                success=i % 4 != 3
            )
            event.id = f"filter-test-{i}"
            event.time = base_time - timedelta(minutes=i)
            events.append(event)
        
        await audit_db.store_audit_events_batch(events)
        
        # Test filtering by actor
        filter_criteria = AuditEventFilter(
            actor_ids=["user0"],
            limit=20
        )
        results, total_count = await audit_db.query_audit_events(filter_criteria)
        
        # Should get events 0, 3, 6, 9 (user0)
        assert total_count == 4
        assert all(r['actor_id'] == "user0" for r in results)
        
        # Test filtering by action
        filter_criteria = AuditEventFilter(
            actions=[AuditAction.OBJECT_TYPE_CREATE],
            limit=20
        )
        results, total_count = await audit_db.query_audit_events(filter_criteria)
        
        # Should get events 0, 2, 4, 6, 8 (even numbers)
        assert total_count == 5
        assert all(r['action'] == AuditAction.OBJECT_TYPE_CREATE.value for r in results)
        
        # Test filtering by success status
        filter_criteria = AuditEventFilter(
            success=False,
            limit=20
        )
        results, total_count = await audit_db.query_audit_events(filter_criteria)
        
        # Should get events 3, 7 (every 4th event fails)
        assert total_count == 2
        assert all(r['success'] == False for r in results)
        
        # Test filtering by branch
        filter_criteria = AuditEventFilter(
            branches=["main"],
            limit=20
        )
        results, total_count = await audit_db.query_audit_events(filter_criteria)
        
        # Should get events 0, 1, 2, 3, 4 (main branch)
        assert total_count == 5
        assert all(r['target_branch'] == "main" for r in results)
    
    @pytest.mark.asyncio
    async def test_query_audit_events_pagination(self, audit_db):
        """Test audit event querying with pagination"""
        # Store 25 test events
        events = []
        base_time = datetime.now(timezone.utc)
        
        for i in range(25):
            actor = ActorInfo(
                id="pagtest_user",
                username="pagtest_user",
                service_account=False
            )
            
            target = TargetInfo(
                resource_type=ResourceType.BRANCH,
                resource_id=f"branch{i}"
            )
            
            event = create_audit_event(
                action=AuditAction.BRANCH_CREATE,
                actor=actor,
                target=target,
                success=True
            )
            event.id = f"pag-test-{i:02d}"
            event.time = base_time - timedelta(minutes=i)
            events.append(event)
        
        await audit_db.store_audit_events_batch(events)
        
        # Test first page
        filter_criteria = AuditEventFilter(limit=10, offset=0)
        results, total_count = await audit_db.query_audit_events(filter_criteria)
        
        assert total_count == 25
        assert len(results) == 10
        assert results[0]['id'] == "pag-test-00"  # Most recent
        assert results[9]['id'] == "pag-test-09"
        
        # Test second page
        filter_criteria = AuditEventFilter(limit=10, offset=10)
        results, total_count = await audit_db.query_audit_events(filter_criteria)
        
        assert total_count == 25
        assert len(results) == 10
        assert results[0]['id'] == "pag-test-10"
        assert results[9]['id'] == "pag-test-19"
        
        # Test last page (partial)
        filter_criteria = AuditEventFilter(limit=10, offset=20)
        results, total_count = await audit_db.query_audit_events(filter_criteria)
        
        assert total_count == 25
        assert len(results) == 5
        assert results[0]['id'] == "pag-test-20"
        assert results[4]['id'] == "pag-test-24"
    
    @pytest.mark.asyncio
    async def test_get_audit_statistics(self, audit_db):
        """Test audit statistics generation"""
        # Store test events with different patterns
        events = []
        base_time = datetime.now(timezone.utc)
        
        # Different actors and actions
        test_data = [
            ("user1", AuditAction.OBJECT_TYPE_CREATE, True),
            ("user1", AuditAction.OBJECT_TYPE_UPDATE, True),
            ("user1", AuditAction.OBJECT_TYPE_DELETE, False),  # Failed
            ("user2", AuditAction.LINK_TYPE_CREATE, True),
            ("user2", AuditAction.LINK_TYPE_UPDATE, True),
            ("user3", AuditAction.BRANCH_CREATE, True),
            ("user3", AuditAction.BRANCH_MERGE, False),  # Failed
        ]
        
        for i, (user_id, action, success) in enumerate(test_data):
            actor = ActorInfo(
                id=user_id,
                username=user_id,
                service_account=False
            )
            
            target = TargetInfo(
                resource_type=ResourceType.OBJECT_TYPE,
                resource_id=f"resource{i}"
            )
            
            event = create_audit_event(
                action=action,
                actor=actor,
                target=target,
                success=success
            )
            event.id = f"stats-test-{i}"
            event.time = base_time - timedelta(minutes=i)
            events.append(event)
        
        await audit_db.store_audit_events_batch(events)
        
        # Get statistics
        stats = await audit_db.get_audit_statistics()
        
        assert stats['total_events'] == 7
        
        # Check events by action
        assert stats['events_by_action'][AuditAction.OBJECT_TYPE_CREATE.value] == 1
        assert stats['events_by_action'][AuditAction.OBJECT_TYPE_UPDATE.value] == 1
        assert stats['events_by_action'][AuditAction.OBJECT_TYPE_DELETE.value] == 1
        assert stats['events_by_action'][AuditAction.LINK_TYPE_CREATE.value] == 1
        assert stats['events_by_action'][AuditAction.LINK_TYPE_UPDATE.value] == 1
        assert stats['events_by_action'][AuditAction.BRANCH_CREATE.value] == 1
        assert stats['events_by_action'][AuditAction.BRANCH_MERGE.value] == 1
        
        # Check top actors
        assert stats['top_actors']['user1'] == 3
        assert stats['top_actors']['user2'] == 2
        assert stats['top_actors']['user3'] == 2
        
        # Check success/failure rates
        assert stats['success_rate'] == 5/7  # 5 successful out of 7
        assert stats['failure_rate'] == 2/7  # 2 failed out of 7
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_events(self, audit_db):
        """Test cleanup of expired audit events"""
        # Store events with different creation times
        events = []
        base_time = datetime.now(timezone.utc)
        
        # Create events that should expire (old) and ones that shouldn't (recent)
        old_time = base_time - timedelta(days=100)  # 100 days ago
        recent_time = base_time - timedelta(days=1)  # 1 day ago
        
        for i in range(3):
            # Old events (should expire for INDEXING_STARTED - 90 day retention)
            actor = ActorInfo(id=f"user{i}", username=f"user{i}", service_account=False)
            target = TargetInfo(resource_type=ResourceType.SYSTEM, resource_id=f"old{i}")
            
            event = create_audit_event(
                action=AuditAction.INDEXING_STARTED,  # 90 day retention
                actor=actor,
                target=target,
                success=True
            )
            event.id = f"old-event-{i}"
            event.time = old_time
            events.append(event)
            
            # Recent events (should not expire)
            event = create_audit_event(
                action=AuditAction.INDEXING_STARTED,
                actor=actor,
                target=TargetInfo(resource_type=ResourceType.SYSTEM, resource_id=f"recent{i}"),
                success=True
            )
            event.id = f"recent-event-{i}"
            event.time = recent_time
            events.append(event)
        
        await audit_db.store_audit_events_batch(events)
        
        # Verify all events are stored
        filter_criteria = AuditEventFilter(limit=10)
        results, total_count = await audit_db.query_audit_events(filter_criteria)
        assert total_count == 6
        
        # Run cleanup
        cleaned_count = await audit_db.cleanup_expired_events()
        
        # Should have archived the 3 old events
        assert cleaned_count == 3
        
        # Verify recent events are still accessible (not archived)
        results, total_count = await audit_db.query_audit_events(filter_criteria)
        assert total_count == 3  # Only recent events should be accessible
        
        # All remaining events should be recent ones
        for result in results:
            assert result['id'].startswith('recent-event-')
    
    @pytest.mark.asyncio
    async def test_integrity_verification(self, audit_db, sample_audit_event):
        """Test audit log integrity verification"""
        # Store a sample event
        sample_audit_event.id = "integrity-test"
        sample_audit_event.time = datetime.now(timezone.utc)
        
        success = await audit_db.store_audit_event(sample_audit_event)
        assert success
        
        # Verify integrity
        integrity_report = await audit_db.verify_integrity()
        
        # Should pass since we haven't tampered with anything
        assert integrity_report['integrity_verified'] == True
        assert len(integrity_report['corrupted_events']) == 0
    
    @pytest.mark.asyncio
    async def test_event_hash_calculation(self, audit_db, sample_audit_event):
        """Test event hash calculation for integrity"""
        # Calculate hash for the same event twice
        hash1 = audit_db._calculate_event_hash(sample_audit_event)
        hash2 = audit_db._calculate_event_hash(sample_audit_event)
        
        # Should be identical
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex string
        
        # Modify event and check hash changes
        sample_audit_event.success = False
        hash3 = audit_db._calculate_event_hash(sample_audit_event)
        
        assert hash3 != hash1
    
    @pytest.mark.asyncio
    async def test_batch_hash_calculation(self, audit_db):
        """Test batch hash calculation"""
        events = []
        for i in range(3):
            actor = ActorInfo(id=f"user{i}", username=f"user{i}", service_account=False)
            target = TargetInfo(resource_type=ResourceType.BRANCH, resource_id=f"branch{i}")
            
            event = create_audit_event(
                action=AuditAction.BRANCH_CREATE,
                actor=actor,
                target=target,
                success=True
            )
            event.id = f"batch-hash-{i}"
            events.append(event)
        
        # Calculate hash for the same batch twice
        hash1 = audit_db._calculate_batch_hash(events)
        hash2 = audit_db._calculate_batch_hash(events)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex string
        
        # Reorder events - hash should be same (order independent)
        events_reordered = events[::-1]
        hash3 = audit_db._calculate_batch_hash(events_reordered)
        assert hash3 == hash1
        
        # Modify an event - hash should change
        events[0].success = False
        hash4 = audit_db._calculate_batch_hash(events)
        assert hash4 != hash1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])