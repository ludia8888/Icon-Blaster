"""
Real NATS Integration Test
Tests actual NATS connectivity and event flow
"""
import asyncio
import json
import pytest
import pytest_asyncio
from datetime import datetime
import os

from core.event_publisher.nats_publisher import NATSEventPublisher
from core.event_publisher.cloudevents_enhanced import CloudEventBuilder, EventType
from shared.infrastructure.real_nats_client import RealNATSClient


class TestRealNATSIntegration:
    """Test real NATS integration without mocks"""
    
    @pytest.fixture
    def nats_url(self):
        """Get NATS URL from environment or use default"""
        return os.getenv("NATS_URL", "nats://oms-nats:4222")
    
    @pytest_asyncio.fixture
    async def nats_client(self, nats_url):
        """Create real NATS client"""
        client = RealNATSClient(servers=[nats_url])
        await client.connect()
        yield client
        await client.close()
    
    @pytest_asyncio.fixture
    async def nats_publisher(self, nats_url):
        """Create real NATS publisher"""
        publisher = NATSEventPublisher(nats_url)
        await publisher.connect()
        yield publisher
        await publisher.disconnect()
    
    @pytest.mark.asyncio
    async def test_nats_connectivity(self, nats_client):
        """Test basic NATS connectivity"""
        # Check if connected
        assert nats_client.nc is not None
        assert nats_client.nc.is_connected
        
        # Get stats
        stats = nats_client.nc.stats
        assert stats is not None
        assert "in_msgs" in stats
        assert "out_msgs" in stats
    
    @pytest.mark.asyncio
    async def test_publish_and_subscribe(self, nats_client):
        """Test publish and subscribe functionality"""
        received_messages = []
        test_subject = "test.integration.subject"
        
        # Subscribe to subject
        async def message_handler(msg):
            data = json.loads(msg.data.decode())
            received_messages.append(data)
        
        sub = await nats_client.nc.subscribe(test_subject, cb=message_handler)
        
        # Publish test message
        test_data = {
            "message": "Integration test",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await nats_client.publish(test_subject, test_data)
        
        # Wait for message to be received
        await asyncio.sleep(0.1)
        
        # Verify message was received
        assert len(received_messages) == 1
        assert received_messages[0]["message"] == test_data["message"]
        
        # Unsubscribe
        await sub.unsubscribe()
    
    @pytest.mark.asyncio
    async def test_jetstream_publish(self, nats_client):
        """Test JetStream publishing"""
        # Create test stream
        stream_name = "TEST_INTEGRATION_STREAM"
        subject = f"{stream_name.lower()}.test"
        
        try:
            # Try to create stream (may already exist)
            await nats_client.create_stream(
                stream_name,
                subjects=[f"{stream_name.lower()}.>"]
            )
        except Exception:
            pass  # Stream might already exist
        
        # Publish to JetStream
        test_data = {
            "test": "jetstream integration",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        result = await nats_client.jetstream_publish(subject, test_data)
        
        # Verify publish was successful
        assert result is not None
        assert result.seq > 0
        assert result.stream == stream_name
    
    @pytest.mark.asyncio
    async def test_event_publisher_integration(self, nats_publisher):
        """Test NATSEventPublisher integration"""
        # Test simple event publish
        success = await nats_publisher.publish(
            "oms.test.event",
            {
                "action": "test",
                "data": {"key": "value"},
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
        assert success is True
    
    @pytest.mark.asyncio
    async def test_cloudevent_publish(self, nats_publisher):
        """Test CloudEvent publishing"""
        # Create CloudEvent
        event = CloudEventBuilder.create_event(
            event_type=EventType.SCHEMA_OBJECT_TYPE_CREATED,
            source="/test/integration",
            data={
                "object_type": "TestType",
                "properties": ["prop1", "prop2"]
            },
            branch="test-branch",
            commit="test-commit",
            author="test-author"
        )
        
        # Publish CloudEvent
        success = await nats_publisher.publish_cloudevent(event)
        
        assert success is True
    
    @pytest.mark.asyncio
    async def test_concurrent_publishing(self, nats_publisher):
        """Test concurrent event publishing"""
        tasks = []
        num_events = 10
        
        # Create multiple publish tasks
        for i in range(num_events):
            task = nats_publisher.publish(
                f"oms.test.concurrent.{i}",
                {
                    "index": i,
                    "timestamp": datetime.utcnow().isoformat()
                }
            )
            tasks.append(task)
        
        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks)
        
        # Verify all publishes succeeded
        assert all(results)
        assert len(results) == num_events
    
    @pytest.mark.asyncio
    async def test_error_handling(self, nats_url):
        """Test error handling for invalid connection"""
        # Try to connect to invalid server
        invalid_publisher = NATSEventPublisher("nats://invalid-server:4222")
        
        # Should handle connection error gracefully
        try:
            await invalid_publisher.connect()
            # If connection succeeds (e.g., in Docker network), test publish
            success = await invalid_publisher.publish("test.subject", {"test": "data"})
            assert isinstance(success, bool)
        except Exception as e:
            # Connection should fail for invalid server
            assert "invalid-server" in str(e) or "Connection" in str(e)
        finally:
            await invalid_publisher.disconnect()
    
    @pytest.mark.asyncio
    async def test_health_check(self, nats_client):
        """Test NATS health check"""
        health = await nats_client.health_check()
        
        assert health is not None
        assert "connected" in health
        assert health["connected"] is True
        
        if "server_info" in health:
            assert "version" in health["server_info"]
        
        if "stats" in health:
            assert "in_msgs" in health["stats"]
            assert "out_msgs" in health["stats"]


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v", "-s"])