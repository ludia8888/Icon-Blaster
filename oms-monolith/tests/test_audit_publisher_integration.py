"""Integration tests for audit publisher to verify dual-write functionality"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from core.events.unified_publisher import UnifiedEventPublisher, PublisherConfig, PublisherBackend
from core.events.backends.audit_backend import AuditEventBackend
from core.audit.audit_service import AuditService
from core.audit.models import AuditEventV1, EventSeverity, EventCategory


@pytest.fixture
async def mock_db_client():
    """Mock database client for testing"""
    client = Mock()
    client.write_audit_event = AsyncMock(return_value=True)
    client.write_audit_events_batch = AsyncMock(return_value=True)
    client.health_check = AsyncMock(return_value=True)
    return client


@pytest.fixture
async def audit_publisher(mock_db_client):
    """Create audit publisher with mocked database"""
    config = PublisherConfig(
        backend=PublisherBackend.AUDIT,
        endpoint="http://test-events.local",
        enable_dual_write=True,
        audit_db_client=mock_db_client,
        enable_pii_protection=True
    )
    
    publisher = UnifiedEventPublisher(config)
    await publisher.connect()
    
    yield publisher
    
    await publisher.disconnect()


@pytest.mark.asyncio
async def test_audit_backend_dual_write_success(audit_publisher, mock_db_client):
    """Test successful dual-write to database and event stream"""
    # Mock HTTP backend success
    with patch.object(audit_publisher._backend.stream_backend, 'publish', AsyncMock(return_value=True)):
        # Publish an audit event
        result = await audit_publisher.publish(
            event_type="user.login",
            data={
                "user_id": "user123",
                "email": "test@example.com",
                "ip_address": "192.168.1.1",
                "timestamp": datetime.utcnow().isoformat()
            },
            metadata={"source": "test"}
        )
        
        # Verify success
        assert result is True
        
        # Verify database write was called
        mock_db_client.write_audit_event.assert_called_once()
        
        # Verify the event was enriched with audit metadata
        db_call_args = mock_db_client.write_audit_event.call_args[0][0]
        assert 'audit_metadata' in db_call_args
        assert 'event_id' in db_call_args['audit_metadata']
        assert 'hash' in db_call_args['audit_metadata']
        
        # Verify PII was masked
        assert db_call_args['data']['email'] != "test@example.com"
        assert '*' in db_call_args['data']['email']


@pytest.mark.asyncio
async def test_audit_backend_database_only_fallback(audit_publisher, mock_db_client):
    """Test that audit succeeds even if event stream fails (database write is primary)"""
    # Mock HTTP backend failure
    with patch.object(audit_publisher._backend.stream_backend, 'publish', AsyncMock(return_value=False)):
        # Publish an audit event
        result = await audit_publisher.publish(
            event_type="security.alert",
            data={
                "alert_type": "unauthorized_access",
                "resource": "/admin/users"
            },
            metadata={"severity": "high"}
        )
        
        # Should still succeed because database write is primary
        assert result is True
        
        # Verify database write was called
        mock_db_client.write_audit_event.assert_called_once()


@pytest.mark.asyncio
async def test_audit_backend_database_failure(audit_publisher, mock_db_client):
    """Test that audit fails if database write fails"""
    # Mock database failure
    mock_db_client.write_audit_event = AsyncMock(side_effect=Exception("Database error"))
    
    # Publish an audit event
    result = await audit_publisher.publish(
        event_type="test.event",
        data={"test": "data"}
    )
    
    # Should fail because database write is critical
    assert result is False


@pytest.mark.asyncio
async def test_audit_backend_batch_publish(audit_publisher, mock_db_client):
    """Test batch publishing of audit events"""
    # Mock HTTP backend success
    with patch.object(audit_publisher._backend.stream_backend, 'publish_batch', AsyncMock(return_value=True)):
        # Create test events
        events = [
            {
                "type": "user.action",
                "data": {"action": f"action_{i}", "user_id": f"user_{i}"},
                "timestamp": datetime.utcnow().isoformat()
            }
            for i in range(5)
        ]
        
        # Publish batch
        result = await audit_publisher.publish_batch(events)
        
        # Verify success
        assert result is True
        
        # Verify database batch write was called
        mock_db_client.write_audit_events_batch.assert_called_once()
        
        # Verify all events were enriched
        db_call_args = mock_db_client.write_audit_events_batch.call_args[0][0]
        assert len(db_call_args) == 5
        for event in db_call_args:
            assert 'audit_metadata' in event


@pytest.mark.asyncio
async def test_audit_service_integration():
    """Test AuditService integration with new publisher API"""
    # Create mock components
    mock_database = Mock()
    mock_database.initialize = AsyncMock()
    mock_database.store_audit_event = AsyncMock(return_value=True)
    mock_database.store_audit_events_batch = AsyncMock(return_value=5)
    
    mock_publisher = Mock()
    mock_publisher.publish = AsyncMock(return_value=True)
    mock_publisher.publish_batch = AsyncMock(return_value=True)
    
    # Create audit service
    service = AuditService()
    service.database = mock_database
    service.publisher = mock_publisher
    service._initialized = True
    
    # Test immediate audit event
    event = AuditEventV1(
        id="test-event-1",
        timestamp=datetime.utcnow(),
        actor_id="user123",
        action="test.action",
        resource_type="test_resource",
        resource_id="resource123",
        severity=EventSeverity.INFO,
        category=EventCategory.ACCESS,
        metadata={"test": "data"}
    )
    
    result = await service.log_audit_event(event, immediate=True)
    assert result is True
    
    # Verify publisher was called with correct format
    mock_publisher.publish.assert_called_once()
    call_args = mock_publisher.publish.call_args
    assert call_args[1]['event_type'] == "audit.event"
    assert call_args[1]['metadata']['immediate'] is True
    
    # Test batch processing
    mock_publisher.reset_mock()
    
    # Queue multiple events
    for i in range(3):
        event = AuditEventV1(
            id=f"test-event-{i}",
            timestamp=datetime.utcnow(),
            actor_id=f"user{i}",
            action="test.batch",
            resource_type="test_resource",
            resource_id=f"resource{i}",
            severity=EventSeverity.INFO,
            category=EventCategory.ACCESS
        )
        await service.log_audit_event(event, immediate=False)
    
    # Process batch
    await service._trigger_batch_processing()
    
    # Verify batch publisher was called
    mock_publisher.publish_batch.assert_called_once()
    batch_call = mock_publisher.publish_batch.call_args[0][0]
    assert len(batch_call) == 3
    assert all(event['type'] == 'audit.event' for event in batch_call)


@pytest.mark.asyncio
async def test_audit_backend_health_check(audit_publisher, mock_db_client):
    """Test health check for audit backend"""
    # Mock HTTP backend health
    with patch.object(audit_publisher._backend.stream_backend, 'health_check', AsyncMock(return_value=True)):
        # Check health
        health = await audit_publisher._backend.health_check()
        
        assert health is True
        
        # Verify both backends were checked
        mock_db_client.health_check.assert_called_once()


@pytest.mark.asyncio
async def test_backward_compatibility():
    """Test that the deprecated publish_audit_event_direct method still works"""
    mock_db_client = Mock()
    mock_db_client.write_audit_event = AsyncMock(return_value=True)
    
    config = PublisherConfig(
        backend=PublisherBackend.AUDIT,
        audit_db_client=mock_db_client
    )
    
    backend = AuditEventBackend(config)
    await backend.connect()
    
    # Mock stream backend
    with patch.object(backend.stream_backend, 'publish', AsyncMock(return_value=True)):
        # Call deprecated method
        result = await backend.publish_audit_event_direct({"test": "event"})
        
        assert result is True
        mock_db_client.write_audit_event.assert_called_once()
    
    await backend.disconnect()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])