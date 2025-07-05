"""
Integration test for NATS event publishing and subscription
Tests the complete event flow from publisher to subscriber
"""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from core.event_publisher.nats_publisher import NATSEventPublisher
from core.event_publisher.cloudevents_enhanced import CloudEventBuilder, EventType
from core.events.branch_event_publisher import BranchEventPublisher
from shared.infrastructure.real_nats_client import RealNATSClient


class TestNATSEventFlow:
    """Test NATS event publishing and subscription flow"""
    
    @pytest.fixture
    def mock_nats_client(self):
        """Create a mock NATS client"""
        client = AsyncMock(spec=RealNATSClient)
        client.connect = AsyncMock()
        client.close = AsyncMock()
        client.publish = AsyncMock(return_value=True)
        client.jetstream_publish = AsyncMock(return_value={
            "seq": 1,
            "stream": "TEST_STREAM",
            "duplicate": False
        })
        client.subscribe = AsyncMock()
        client.health_check = AsyncMock(return_value={"connected": True})
        
        # Mock the js attribute for JetStream
        client.js = AsyncMock()
        client.js.stream_info = AsyncMock(side_effect=Exception("Stream not found"))
        client.js.add_stream = AsyncMock()
        
        return client
    
    @pytest.fixture
    def captured_events(self):
        """List to capture published events"""
        return []
    
    @pytest.mark.asyncio
    async def test_simple_event_publish(self, mock_nats_client, captured_events):
        """Test simple event publishing"""
        # Capture published events
        async def capture_publish(subject, data, headers=None):
            captured_events.append({
                "subject": subject,
                "data": data,
                "headers": headers
            })
            return True
        
        mock_nats_client.publish = AsyncMock(side_effect=capture_publish)
        
        with patch('shared.infrastructure.real_nats_client.RealNATSClient', return_value=mock_nats_client):
            publisher = NATSEventPublisher()
            await publisher.connect()
            
            # Publish a simple event
            success = await publisher.publish("oms.test.event", {
                "message": "Hello NATS!",
                "timestamp": datetime.utcnow().isoformat()
            })
            
            assert success is True
            assert len(captured_events) == 1
            assert captured_events[0]["subject"] == "oms.test.event"
            assert captured_events[0]["data"]["message"] == "Hello NATS!"
    
    @pytest.mark.asyncio
    async def test_cloudevent_publish(self, mock_nats_client, captured_events):
        """Test CloudEvent publishing"""
        # Capture JetStream publishes
        async def capture_js_publish(subject, data, headers=None):
            captured_events.append({
                "subject": subject,
                "data": json.loads(data) if isinstance(data, bytes) else data,
                "headers": headers
            })
            return {
                "seq": len(captured_events),
                "stream": "OMS-EVENTS",
                "duplicate": False
            }
        
        mock_nats_client.jetstream_publish = AsyncMock(side_effect=capture_js_publish)
        
        with patch('shared.infrastructure.real_nats_client.RealNATSClient', return_value=mock_nats_client):
            publisher = NATSEventPublisher()
            await publisher.connect()
            
            # Create and publish a CloudEvent
            event = CloudEventBuilder(
                EventType.SCHEMA_CREATED,
                "/oms/main"
            ).with_subject("schema/test-schema").with_data({
                "schema_id": "test-123",
                "name": "TestSchema",
                "version": "1.0.0"
            }).with_correlation("corr-123").build()
            
            success = await publisher.publish_event(event)
            
            assert success is True
            assert len(captured_events) == 1
            assert captured_events[0]["subject"] == "oms.schema.created"
            assert captured_events[0]["data"]["schema_id"] == "test-123"
    
    @pytest.mark.asyncio
    async def test_branch_event_publisher(self, mock_nats_client, captured_events):
        """Test branch-specific event publisher"""
        # Capture JetStream publishes
        async def capture_js_publish(subject, data, headers=None):
            captured_events.append({
                "subject": subject,
                "data": json.loads(data) if isinstance(data, bytes) else data,
                "headers": headers
            })
            return {
                "seq": len(captured_events),
                "stream": "OMS-EVENTS",
                "duplicate": False
            }
        
        mock_nats_client.jetstream_publish = AsyncMock(side_effect=capture_js_publish)
        
        with patch('shared.infrastructure.real_nats_client.RealNATSClient', return_value=mock_nats_client):
            publisher = BranchEventPublisher()
            
            # Test branch created event
            await publisher.publish_branch_created(
                branch_name="feature-xyz",
                parent_branch="main",
                author="test@example.com",
                description="New feature branch"
            )
            
            assert len(captured_events) == 1
            assert captured_events[0]["subject"] == "oms.branch.created"
            assert captured_events[0]["data"]["branch_name"] == "feature-xyz"
            assert captured_events[0]["data"]["parent_branch"] == "main"
            
            # Test proposal created event
            await publisher.publish_proposal_created(
                proposal_id="prop-123",
                source_branch="feature-xyz",
                target_branch="main",
                title="Add new feature",
                author="test@example.com"
            )
            
            assert len(captured_events) == 2
            assert captured_events[1]["subject"] == "oms.proposal.created"
            assert captured_events[1]["data"]["proposal_id"] == "prop-123"
    
    @pytest.mark.asyncio
    async def test_batch_event_publish(self, mock_nats_client, captured_events):
        """Test batch event publishing"""
        # Track all JetStream calls
        js_calls = []
        
        async def capture_js_publish(subject, data, **kwargs):
            js_calls.append({
                "subject": subject,
                "data": json.loads(data) if isinstance(data, bytes) else data
            })
            return {
                "seq": len(js_calls),
                "stream": "OMS-EVENTS",
                "duplicate": False
            }
        
        mock_nats_client.jetstream_publish = AsyncMock(side_effect=capture_js_publish)
        
        with patch('shared.infrastructure.real_nats_client.RealNATSClient', return_value=mock_nats_client):
            publisher = NATSEventPublisher()
            await publisher.connect()
            
            # Create batch of events
            events = [
                {
                    "type": "com.foundry.oms.test.batch1",
                    "data": {"index": 1, "message": "Event 1"}
                },
                {
                    "type": "com.foundry.oms.test.batch2",
                    "data": {"index": 2, "message": "Event 2"}
                },
                {
                    "type": "com.foundry.oms.test.batch3",
                    "data": {"index": 3, "message": "Event 3"}
                }
            ]
            
            success = await publisher.publish_batch(events)
            
            assert success is True
            assert len(js_calls) == 3
            
            # Verify each event was published
            for i, call in enumerate(js_calls):
                assert call["data"]["index"] == i + 1
                assert f"Event {i + 1}" in call["data"]["message"]
    
    @pytest.mark.asyncio
    async def test_event_subscription(self, mock_nats_client):
        """Test event subscription handling"""
        received_events = []
        
        async def test_handler(subject, data, **kwargs):
            received_events.append({
                "subject": subject,
                "data": data,
                "kwargs": kwargs
            })
        
        # Simulate subscription and message delivery
        async def simulate_subscribe(subject, cb, queue=None):
            # Simulate receiving a message
            await cb(MagicMock(
                subject="oms.test.received",
                data=json.dumps({"test": "data"}).encode(),
                reply=None
            ))
            return MagicMock()
        
        mock_nats_client.subscribe = AsyncMock(side_effect=simulate_subscribe)
        
        with patch('shared.infrastructure.real_nats_client.RealNATSClient', return_value=mock_nats_client):
            client = RealNATSClient()
            await client.connect()
            
            # Subscribe to events
            await client.subscribe("oms.>", test_handler)
            
            # Verify handler was called
            assert len(received_events) == 1
            assert received_events[0]["subject"] == "oms.test.received"
            assert received_events[0]["data"]["test"] == "data"
    
    @pytest.mark.asyncio
    async def test_error_handling(self, mock_nats_client):
        """Test error handling in event publishing"""
        # Make publish fail
        mock_nats_client.jetstream_publish = AsyncMock(side_effect=Exception("Connection failed"))
        
        with patch('shared.infrastructure.real_nats_client.RealNATSClient', return_value=mock_nats_client):
            publisher = NATSEventPublisher()
            await publisher.connect()
            
            # Should return False on error
            success = await publisher.publish("oms.test.error", {"data": "test"})
            assert success is False
    
    @pytest.mark.asyncio
    async def test_connection_lifecycle(self, mock_nats_client):
        """Test connection lifecycle management"""
        with patch('shared.infrastructure.real_nats_client.RealNATSClient', return_value=mock_nats_client):
            publisher = NATSEventPublisher()
            
            # Test connect
            await publisher.connect()
            mock_nats_client.connect.assert_called_once()
            
            # Test disconnect
            await publisher.disconnect()
            mock_nats_client.close.assert_called_once()
            
            # Test context manager
            async with NATSEventPublisher() as pub:
                mock_nats_client.connect.call_count == 2
            
            mock_nats_client.close.call_count == 2


@pytest.mark.asyncio
async def test_real_nats_client_mock():
    """Test RealNATSClient with full mocking"""
    with patch('nats.NATS') as mock_nats_class:
        mock_nc = AsyncMock()
        mock_nc.is_connected = True
        mock_nc.connect = AsyncMock()
        mock_nc.close = AsyncMock()
        mock_nc.publish = AsyncMock()
        mock_nc.subscribe = AsyncMock()
        mock_nc.jetstream = MagicMock()
        mock_nc.stats = {
            "in_msgs": 100,
            "out_msgs": 50,
            "in_bytes": 1000,
            "out_bytes": 500,
            "reconnects": 0
        }
        
        mock_js = AsyncMock()
        mock_js.stream_info = AsyncMock()
        mock_js.add_stream = AsyncMock()
        mock_js.publish = AsyncMock(return_value=MagicMock(seq=1, stream="TEST", duplicate=False))
        mock_nc.jetstream.return_value = mock_js
        
        mock_nats_class.return_value = mock_nc
        
        # Test client operations
        from shared.infrastructure.real_nats_client import RealNATSClient
        client = RealNATSClient()
        await client.connect()
        
        # Test publish
        await client.publish("test.subject", {"data": "test"})
        mock_nc.publish.assert_called_once()
        
        # Test JetStream publish
        result = await client.jetstream_publish("test.js", {"data": "jetstream"})
        assert result["seq"] == 1
        
        # Test health check
        health = await client.health_check()
        assert health["connected"] is True
        assert health["stats"]["in_msgs"] == 100