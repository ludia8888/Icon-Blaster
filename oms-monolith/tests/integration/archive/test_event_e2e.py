#!/usr/bin/env python3
"""
End-to-End Event Flow Test
Simulates complete event publishing and subscription
"""
import asyncio
import json
from datetime import datetime
from typing import Dict, Any, List

# Simple logger
class Logger:
    def info(self, msg): print(f"[INFO] {msg}")
    def error(self, msg): print(f"[ERROR] {msg}")
    def warning(self, msg): print(f"[WARNING] {msg}")

logger = Logger()


class EventStore:
    """Stores all events for verification"""
    def __init__(self):
        self.published_events: List[Dict] = []
        self.received_events: List[Dict] = []
        self.audit_logs: List[Dict] = []


# Global event store
event_store = EventStore()


class MockBranchService:
    """Simulates branch service with event publishing"""
    
    def __init__(self, event_publisher):
        self.event_publisher = event_publisher
        self.branches = {}
    
    async def create_branch(self, name: str, from_branch: str, user_id: str, description: str = None):
        """Create a branch and publish event"""
        logger.info(f"Creating branch: {name} from {from_branch}")
        
        # Simulate branch creation
        branch = {
            "id": name,
            "name": name,
            "parent_branch": from_branch,
            "author": user_id,
            "description": description,
            "created_at": datetime.utcnow().isoformat()
        }
        self.branches[name] = branch
        
        # Publish event (like in real service)
        if self.event_publisher:
            try:
                await self.event_publisher.publish_branch_created(
                    branch_name=name,
                    parent_branch=from_branch,
                    author=user_id,
                    description=description
                )
                logger.info(f"✓ Branch created event published for: {name}")
            except Exception as e:
                logger.warning(f"Failed to publish branch created event: {e}")
        
        return branch


class MockEventSubscriber:
    """Simulates event subscriber service"""
    
    def __init__(self):
        self.handlers = {}
        self.running = False
    
    async def start(self):
        """Start subscriber"""
        logger.info("Event Subscriber starting...")
        self.running = True
        await self._setup_subscriptions()
        logger.info("Event Subscriber started")
    
    async def _setup_subscriptions(self):
        """Setup event handlers"""
        self.handlers = {
            "oms.branch.created": self._handle_branch_created,
            "oms.schema.changed": self._handle_schema_changed,
            "oms.proposal.created": self._handle_proposal_created,
        }
        logger.info(f"Configured {len(self.handlers)} event handlers")
    
    async def process_event(self, subject: str, data: Any):
        """Process incoming event"""
        logger.info(f"Subscriber received event on {subject}")
        
        # Store received event
        event_store.received_events.append({
            "subject": subject,
            "data": data,
            "received_at": datetime.utcnow().isoformat()
        })
        
        # Find matching handler
        for pattern, handler in self.handlers.items():
            if self._matches_pattern(pattern, subject):
                await handler(data)
                break
    
    def _matches_pattern(self, pattern: str, subject: str) -> bool:
        """Simple pattern matching"""
        return subject.startswith(pattern.replace(".>", ""))
    
    async def _handle_branch_created(self, event_data: Dict):
        """Handle branch created event"""
        logger.info(f"Processing branch created event: {event_data.get('branch_name')}")
        
        # Simulate audit log
        audit = {
            "event_type": "branch_created",
            "data": event_data,
            "processed_at": datetime.utcnow().isoformat()
        }
        event_store.audit_logs.append(audit)
        
        logger.info("✓ Branch created event processed and audit logged")
    
    async def _handle_schema_changed(self, event_data: Dict):
        logger.info(f"Processing schema changed event")
    
    async def _handle_proposal_created(self, event_data: Dict):
        logger.info(f"Processing proposal created event")


class MockNATSInfrastructure:
    """Simulates NATS message routing"""
    
    def __init__(self):
        self.subscribers = {}
    
    def subscribe(self, pattern: str, handler):
        """Register a subscriber"""
        if pattern not in self.subscribers:
            self.subscribers[pattern] = []
        self.subscribers[pattern].append(handler)
        logger.info(f"Subscribed to pattern: {pattern}")
    
    async def publish(self, subject: str, data: Any):
        """Route published message to subscribers"""
        logger.info(f"NATS routing message on subject: {subject}")
        
        # Find matching subscribers
        delivered = 0
        for pattern, handlers in self.subscribers.items():
            if self._matches(pattern, subject):
                for handler in handlers:
                    await handler(subject, data)
                    delivered += 1
        
        logger.info(f"Message delivered to {delivered} subscribers")
        return delivered > 0
    
    def _matches(self, pattern: str, subject: str) -> bool:
        """Pattern matching with wildcards"""
        if pattern.endswith(".>"):
            prefix = pattern[:-2]
            return subject.startswith(prefix)
        return pattern == subject


# Global NATS mock
nats_mock = MockNATSInfrastructure()


class IntegrationEventPublisher:
    """Event publisher that integrates with mock NATS"""
    
    async def publish_branch_created(self, **kwargs):
        """Publish branch created event"""
        event = {
            "type": "branch_created",
            "data": kwargs,
            "timestamp": datetime.utcnow().isoformat()
        }
        event_store.published_events.append(event)
        
        # Route through NATS
        subject = "oms.branch.created"
        await nats_mock.publish(subject, kwargs)


async def run_integration_test():
    """Run complete integration test"""
    logger.info("=== Starting E2E Event Flow Test ===\n")
    
    # 1. Setup infrastructure
    logger.info("Step 1: Setting up infrastructure")
    
    # Create event publisher
    event_publisher = IntegrationEventPublisher()
    
    # Create services
    branch_service = MockBranchService(event_publisher)
    event_subscriber = MockEventSubscriber()
    
    # 2. Start subscriber
    logger.info("\nStep 2: Starting event subscriber")
    await event_subscriber.start()
    
    # Connect subscriber to NATS
    async def subscriber_handler(subject, data):
        await event_subscriber.process_event(subject, data)
    
    nats_mock.subscribe("oms.>", subscriber_handler)
    
    # 3. Perform operations that generate events
    logger.info("\nStep 3: Performing operations")
    
    # Create a branch (should trigger event)
    branch = await branch_service.create_branch(
        name="feature/test-integration",
        from_branch="main",
        user_id="test@example.com",
        description="Integration test branch"
    )
    
    # Give async operations time to complete
    await asyncio.sleep(0.1)
    
    # 4. Verify results
    logger.info("\n=== Test Results ===")
    
    logger.info(f"\nPublished Events: {len(event_store.published_events)}")
    for event in event_store.published_events:
        logger.info(f"  - {event['type']} at {event['timestamp']}")
    
    logger.info(f"\nReceived Events: {len(event_store.received_events)}")
    for event in event_store.received_events:
        logger.info(f"  - {event['subject']} at {event['received_at']}")
    
    logger.info(f"\nAudit Logs: {len(event_store.audit_logs)}")
    for audit in event_store.audit_logs:
        logger.info(f"  - {audit['event_type']} processed at {audit['processed_at']}")
    
    # 5. Validate flow
    logger.info("\n=== Validation ===")
    
    # Check that event was published
    assert len(event_store.published_events) == 1, "Should have 1 published event"
    published = event_store.published_events[0]
    assert published['type'] == 'branch_created'
    assert published['data']['branch_name'] == 'feature/test-integration'
    logger.info("✓ Event was published correctly")
    
    # Check that event was received
    assert len(event_store.received_events) == 1, "Should have 1 received event"
    received = event_store.received_events[0]
    assert received['subject'] == 'oms.branch.created'
    assert received['data']['branch_name'] == 'feature/test-integration'
    logger.info("✓ Event was received by subscriber")
    
    # Check that event was processed
    assert len(event_store.audit_logs) == 1, "Should have 1 audit log"
    audit = event_store.audit_logs[0]
    assert audit['event_type'] == 'branch_created'
    logger.info("✓ Event was processed and audit logged")
    
    # Verify data consistency
    assert published['data']['branch_name'] == received['data']['branch_name']
    assert published['data']['author'] == received['data']['author']
    logger.info("✓ Event data is consistent across publish/subscribe")
    
    logger.info("\n✅ E2E Event Flow Test PASSED!")
    logger.info("Event successfully flowed from publisher → NATS → subscriber → processor")
    
    return True


async def test_multiple_events():
    """Test multiple events and subscribers"""
    logger.info("\n=== Testing Multiple Events ===")
    
    # Reset event store
    event_store.published_events.clear()
    event_store.received_events.clear()
    
    # Create multiple subscribers
    received_by_sub1 = []
    received_by_sub2 = []
    
    async def sub1_handler(subject, data):
        received_by_sub1.append(subject)
    
    async def sub2_handler(subject, data):
        received_by_sub2.append(subject)
    
    # Subscribe to different patterns
    nats_mock.subscribe("oms.branch.>", sub1_handler)
    nats_mock.subscribe("oms.>", sub2_handler)
    
    # Publish multiple events
    subjects = [
        "oms.branch.created",
        "oms.branch.updated",
        "oms.schema.changed",
        "oms.proposal.created"
    ]
    
    for subject in subjects:
        await nats_mock.publish(subject, {"test": True})
    
    await asyncio.sleep(0.1)
    
    logger.info(f"Subscriber 1 (oms.branch.>) received: {len(received_by_sub1)} events")
    logger.info(f"Subscriber 2 (oms.>) received: {len(received_by_sub2)} events")
    
    assert len(received_by_sub1) == 2, "Sub1 should receive 2 branch events"
    assert len(received_by_sub2) == 4, "Sub2 should receive all 4 events"
    
    logger.info("✓ Multiple subscriber pattern matching works correctly")
    
    return True


async def main():
    """Run all tests"""
    try:
        # Run main integration test
        success1 = await run_integration_test()
        
        # Run multiple events test
        success2 = await test_multiple_events()
        
        if success1 and success2:
            logger.info("\n" + "="*50)
            logger.info("ALL TESTS PASSED! 🎉")
            logger.info("="*50)
            return 0
        else:
            return 1
            
    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)