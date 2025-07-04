#!/usr/bin/env python3
"""
Test script to verify NATS event publishing and subscription flow
"""
import asyncio
import json
from datetime import datetime

from core.event_publisher.nats_publisher import NATSEventPublisher
from core.event_publisher.cloudevents_enhanced import CloudEventBuilder, EventType
from shared.infrastructure.real_nats_client import RealNATSClient
from utils.logger import get_logger

logger = get_logger("test_event_flow")


async def test_subscriber(subject: str, data: Any, **kwargs):
    """Test subscriber callback"""
    logger.info(f"Received event on {subject}: {json.dumps(data, indent=2)}")
    logger.info(f"Additional args: {kwargs}")


async def test_event_flow():
    """Test end-to-end event flow"""
    logger.info("Starting NATS event flow test...")
    
    # Initialize publisher
    publisher = NATSEventPublisher("nats://localhost:4222")
    
    # Initialize subscriber client
    subscriber = RealNATSClient()
    
    try:
        # Connect both
        logger.info("Connecting to NATS...")
        await publisher.connect()
        await subscriber.connect()
        
        # Subscribe to test subjects
        logger.info("Setting up subscriptions...")
        await subscriber.subscribe("oms.>", test_subscriber)
        await subscriber.subscribe("events.>", test_subscriber)
        
        # Give subscriptions time to establish
        await asyncio.sleep(1)
        
        # Test 1: Simple event publish
        logger.info("\n=== Test 1: Simple Event ===")
        success = await publisher.publish("oms.test.simple", {
            "message": "Hello NATS!",
            "timestamp": datetime.utcnow().isoformat()
        })
        logger.info(f"Simple publish success: {success}")
        
        await asyncio.sleep(0.5)
        
        # Test 2: CloudEvent publish
        logger.info("\n=== Test 2: CloudEvent ===")
        cloud_event = CloudEventBuilder(
            EventType.SCHEMA_CREATED,
            "/oms/main"
        ).with_subject("schema/test-schema").with_data({
            "schema_id": "test-123",
            "name": "TestSchema",
            "version": "1.0.0"
        }).with_correlation("corr-123").build()
        
        success = await publisher.publish_event(cloud_event)
        logger.info(f"CloudEvent publish success: {success}")
        
        await asyncio.sleep(0.5)
        
        # Test 3: Batch publish
        logger.info("\n=== Test 3: Batch Events ===")
        batch_events = [
            {
                "type": "com.foundry.oms.test.batch1",
                "data": {"index": 1, "message": "Batch event 1"}
            },
            {
                "type": "com.foundry.oms.test.batch2",
                "data": {"index": 2, "message": "Batch event 2"}
            }
        ]
        
        success = await publisher.publish_batch(batch_events)
        logger.info(f"Batch publish success: {success}")
        
        await asyncio.sleep(0.5)
        
        # Test 4: Branch event simulation
        logger.info("\n=== Test 4: Branch Event ===")
        branch_event = CloudEventBuilder(
            EventType.BRANCH_CREATED,
            "/oms/branches"
        ).with_subject("branch/feature-xyz").with_data({
            "branch_id": "feature-xyz",
            "base_branch": "main",
            "created_by": "test-user"
        }).with_oms_context(
            branch="feature-xyz",
            commit="abc123def",
            author="test-user"
        ).build()
        
        success = await publisher.publish_event(branch_event)
        logger.info(f"Branch event publish success: {success}")
        
        await asyncio.sleep(1)
        
        # Check health
        logger.info("\n=== Health Check ===")
        pub_health = await publisher.publisher.health_check()
        sub_health = await subscriber.health_check()
        
        logger.info(f"Publisher health: {pub_health}")
        logger.info(f"Subscriber health: {json.dumps(sub_health, indent=2)}")
        
        logger.info("\nEvent flow test completed successfully!")
        
    except Exception as e:
        logger.error(f"Test failed: {e}", exc_info=True)
        
    finally:
        # Cleanup
        logger.info("Cleaning up...")
        await publisher.disconnect()
        await subscriber.close()


async def main():
    """Main entry point"""
    try:
        await test_event_flow()
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as e:
        logger.error(f"Test error: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())