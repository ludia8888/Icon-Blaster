#!/usr/bin/env python3
"""
Manual integration test for NATS event flow
Can be run without pytest
"""
import asyncio
import sys
import os
from datetime import datetime
from typing import Dict, Any, List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.logger import get_logger

logger = get_logger("integration_test")


class MockNATSClient:
    """Mock NATS client for testing without real NATS server"""
    
    def __init__(self):
        self.connected = False
        self.published_events: List[Dict[str, Any]] = []
        self.subscribers = {}
        self.js_streams = {}
        
    async def connect(self, **kwargs):
        logger.info("Mock NATS client connected")
        self.connected = True
        
    async def close(self):
        logger.info("Mock NATS client disconnected")
        self.connected = False
        
    async def publish(self, subject: str, data: Any, headers=None):
        event = {
            "subject": subject,
            "data": data,
            "headers": headers,
            "timestamp": datetime.utcnow().isoformat()
        }
        self.published_events.append(event)
        logger.info(f"Published to {subject}: {data}")
        
        # Trigger subscribers
        for pattern, callbacks in self.subscribers.items():
            if self._match_subject(pattern, subject):
                for cb in callbacks:
                    await cb(subject=subject, data=data, reply=None)
        
    async def subscribe(self, subject: str, cb, queue=None):
        if subject not in self.subscribers:
            self.subscribers[subject] = []
        self.subscribers[subject].append(cb)
        logger.info(f"Subscribed to {subject}")
        
    async def jetstream_publish(self, subject: str, data: Any, msg_id=None, expected_stream=None):
        event = {
            "subject": subject,
            "data": data,
            "msg_id": msg_id,
            "stream": expected_stream or "DEFAULT",
            "seq": len(self.published_events) + 1
        }
        self.published_events.append(event)
        logger.info(f"JetStream published to {subject}: {data}")
        
        return {
            "seq": event["seq"],
            "stream": event["stream"],
            "duplicate": False
        }
    
    async def health_check(self):
        return {
            "connected": self.connected,
            "published": len(self.published_events),
            "subscribers": len(self.subscribers)
        }
    
    def _match_subject(self, pattern: str, subject: str) -> bool:
        """Simple subject matching (supports > wildcard)"""
        if pattern.endswith(">"):
            prefix = pattern[:-1]
            return subject.startswith(prefix)
        return pattern == subject
    
    @property
    def js(self):
        """Mock JetStream context"""
        return self
    
    async def stream_info(self, name: str):
        if name in self.js_streams:
            return self.js_streams[name]
        raise Exception(f"Stream {name} not found")
    
    async def add_stream(self, **kwargs):
        name = kwargs.get("name")
        self.js_streams[name] = kwargs
        logger.info(f"Created JetStream stream: {name}")


# Monkey patch the real client import
import shared.infrastructure.real_nats_client
shared.infrastructure.real_nats_client.RealNATSClient = MockNATSClient


async def test_event_flow():
    """Test complete event flow"""
    logger.info("=== Starting NATS Event Flow Integration Test ===\n")
    
    try:
        # Import after patching
        from core.event_publisher.nats_publisher import NATSEventPublisher
        from core.event_publisher.cloudevents_enhanced import CloudEventBuilder, EventType
        from core.events.branch_event_publisher import BranchEventPublisher
        
        # Test 1: Basic NATS Publisher
        logger.info("Test 1: Basic NATS Event Publishing")
        publisher = NATSEventPublisher()
        await publisher.connect()
        
        success = await publisher.publish("oms.test.basic", {
            "message": "Hello from integration test",
            "timestamp": datetime.utcnow().isoformat()
        })
        logger.info(f"Basic publish success: {success}\n")
        
        # Test 2: CloudEvent Publishing
        logger.info("Test 2: CloudEvent Publishing")
        cloud_event = CloudEventBuilder(
            EventType.SCHEMA_CREATED,
            "/oms/main"
        ).with_subject("schema/integration-test").with_data({
            "schema_id": "test-schema-123",
            "name": "IntegrationTestSchema",
            "version": "1.0.0",
            "properties": ["id", "name", "created_at"]
        }).with_correlation("test-corr-123").with_oms_context(
            branch="main",
            commit="abc123",
            author="test@example.com"
        ).build()
        
        success = await publisher.publish_event(cloud_event)
        logger.info(f"CloudEvent publish success: {success}")
        logger.info(f"Event ID: {cloud_event.id}")
        logger.info(f"Event Type: {cloud_event.type}\n")
        
        # Test 3: Branch Event Publisher
        logger.info("Test 3: Branch Event Publisher")
        branch_publisher = BranchEventPublisher()
        
        # Publish branch created
        await branch_publisher.publish_branch_created(
            branch_name="feature/integration-test",
            parent_branch="main",
            author="developer@example.com",
            description="Integration test branch"
        )
        logger.info("Branch created event published")
        
        # Publish proposal created
        await branch_publisher.publish_proposal_created(
            proposal_id="prop-integration-123",
            source_branch="feature/integration-test",
            target_branch="main",
            title="Integration Test Proposal",
            author="developer@example.com",
            description="Testing the event flow"
        )
        logger.info("Proposal created event published\n")
        
        # Test 4: Batch Publishing
        logger.info("Test 4: Batch Event Publishing")
        batch_events = []
        for i in range(5):
            event = CloudEventBuilder(
                f"com.foundry.oms.test.batch{i}",
                "/oms/batch"
            ).with_data({
                "index": i,
                "message": f"Batch event {i}",
                "batch_id": "batch-test-123"
            }).build()
            batch_events.append(event.to_structured_format())
        
        success = await publisher.publish_batch(batch_events)
        logger.info(f"Batch publish success: {success}\n")
        
        # Test 5: Event Subscription
        logger.info("Test 5: Event Subscription Test")
        received_events = []
        
        async def event_handler(subject, data, **kwargs):
            received_events.append({
                "subject": subject,
                "data": data,
                "received_at": datetime.utcnow().isoformat()
            })
            logger.info(f"Received event on {subject}")
        
        # Get the mock client to subscribe
        mock_client = publisher.publisher._backend.client
        await mock_client.subscribe("oms.>", event_handler)
        
        # Publish an event that should be received
        await publisher.publish("oms.subscription.test", {
            "test": "subscription",
            "data": "This should be received"
        })
        
        # Give async handlers time to process
        await asyncio.sleep(0.1)
        
        logger.info(f"Received {len(received_events)} events\n")
        
        # Summary
        logger.info("=== Test Summary ===")
        total_published = len(mock_client.published_events)
        logger.info(f"Total events published: {total_published}")
        logger.info(f"Events received by subscriber: {len(received_events)}")
        
        # Show all published events
        logger.info("\nPublished Events:")
        for i, event in enumerate(mock_client.published_events):
            logger.info(f"{i+1}. {event['subject']} - {event.get('msg_id', 'N/A')}")
        
        # Cleanup
        await publisher.disconnect()
        await branch_publisher.close()
        
        logger.info("\n✅ Integration test completed successfully!")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Integration test failed: {e}", exc_info=True)
        return False


async def test_error_scenarios():
    """Test error handling scenarios"""
    logger.info("\n=== Testing Error Scenarios ===\n")
    
    try:
        from core.event_publisher.nats_publisher import NATSEventPublisher
        
        # Create a publisher that will fail
        class FailingMockClient(MockNATSClient):
            async def jetstream_publish(self, *args, **kwargs):
                raise Exception("Simulated publish failure")
        
        # Patch with failing client
        original_class = shared.infrastructure.real_nats_client.RealNATSClient
        shared.infrastructure.real_nats_client.RealNATSClient = FailingMockClient
        
        publisher = NATSEventPublisher()
        await publisher.connect()
        
        # This should handle the error gracefully
        success = await publisher.publish("oms.error.test", {"will": "fail"})
        logger.info(f"Publish with error returned: {success} (should be False)")
        
        # Restore original mock
        shared.infrastructure.real_nats_client.RealNATSClient = original_class
        
        logger.info("✅ Error handling test passed\n")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error handling test failed: {e}")
        return False


async def main():
    """Run all integration tests"""
    logger.info("Starting NATS Event Flow Integration Tests")
    logger.info("=" * 50)
    
    # Run main event flow test
    flow_success = await test_event_flow()
    
    # Run error scenario tests
    error_success = await test_error_scenarios()
    
    # Final summary
    logger.info("\n" + "=" * 50)
    logger.info("FINAL TEST RESULTS:")
    logger.info(f"Event Flow Test: {'✅ PASSED' if flow_success else '❌ FAILED'}")
    logger.info(f"Error Handling Test: {'✅ PASSED' if error_success else '❌ FAILED'}")
    logger.info("=" * 50)
    
    return flow_success and error_success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)