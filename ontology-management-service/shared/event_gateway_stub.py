"""Event Gateway service stub for gradual migration."""

import os
import logging
from typing import Dict, List, Optional, Any, AsyncIterator
from datetime import datetime
import json
import asyncio

from cloudevents.http import CloudEvent, from_dict, to_json

logger = logging.getLogger(__name__)

# Feature flag for using microservice
USE_EVENT_GATEWAY = os.getenv("USE_EVENT_GATEWAY", "false").lower() == "true"
EVENT_GATEWAY_ENDPOINT = os.getenv("EVENT_GATEWAY_ENDPOINT", "event-gateway:50057")


class EventGatewayStub:
    """Stub that routes to either local NATS or microservice."""
    
    def __init__(self):
        self._local_nats = None
        self._grpc_client = None
        self._local_events = asyncio.Queue()  # Simple local queue for testing
        
        if USE_EVENT_GATEWAY:
            try:
                from shared.event_gateway_client import EventGatewayClient
                self._grpc_client = EventGatewayClient(EVENT_GATEWAY_ENDPOINT)
                logger.info("Using event gateway microservice")
            except Exception as e:
                logger.warning(f"Failed to initialize event gateway client: {e}")
                logger.info("Falling back to local event handling")
                self._init_local_handler()
        else:
            self._init_local_handler()
    
    def _init_local_handler(self):
        """Initialize local event handler."""
        logger.info("Using local event handling")
    
    async def initialize(self) -> None:
        """Initialize event publisher connections."""
        # The __init__ method handles initialization logic including connection.
        logger.info("EventGatewayStub initialized.")

    async def close(self) -> None:
        """Close event publisher connections."""
        if self._grpc_client and hasattr(self._grpc_client, 'close'):
            await self._grpc_client.close()
        logger.info("EventGatewayStub closed.")

    async def publish(
        self,
        event_type: str,
        data: Dict[str, Any],
        correlation_id: Optional[str] = None
    ) -> None:
        """Publish an event, compatible with the protocol."""
        # Create a CloudEvent object from the provided data.
        attributes = {
            "type": event_type,
            "source": "ontology-management-service",
        }
        if correlation_id:
            attributes["subject"] = correlation_id

        event = CloudEvent(attributes, data)
        await self.publish_event(event)

    async def publish_batch(self, events: List[Dict[str, Any]]) -> None:
        """Publish multiple events in batch (Not implemented)."""
        logger.warning("publish_batch is not implemented in EventGatewayStub.")
        # In a real scenario, you might loop and call self.publish,
        # or use a batch endpoint if the gRPC service supports it.
        for event_data in events:
            # Assuming each dict has 'event_type' and 'data' keys
            await self.publish(
                event_type=event_data.get("event_type", "default.event"),
                data=event_data.get("data", {})
            )

    async def publish_event(
        self,
        event: CloudEvent,
        stream: str = "events",
        headers: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Publish a CloudEvent."""
        if self._grpc_client:
            return await self._grpc_client.publish_event(event, stream, headers)
        else:
            # Local implementation
            return await self._publish_event_local(event, stream, headers)
    
    async def subscribe(
        self,
        consumer_id: str,
        event_types: List[str],
        stream: str = "events",
        callback = None
    ) -> str:
        """Subscribe to events."""
        if self._grpc_client:
            return await self._grpc_client.subscribe(
                consumer_id=consumer_id,
                event_types=event_types,
                stream=stream
            )
        else:
            # Local implementation
            return await self._subscribe_local(consumer_id, event_types, stream, callback)
    
    async def stream_events(
        self,
        subscription_id: str,
        batch_size: int = 10
    ) -> AsyncIterator[Dict[str, Any]]:
        """Stream events for a subscription."""
        if self._grpc_client:
            async for event in self._grpc_client.stream_events(subscription_id):
                yield event
        else:
            # Local implementation
            async for event in self._stream_events_local(subscription_id):
                yield event
    
    async def _publish_event_local(
        self,
        event: CloudEvent,
        stream: str,
        headers: Optional[Dict[str, str]]
    ) -> Dict[str, Any]:
        """Publish event locally."""
        from uuid import uuid4
        
        # Ensure event has required fields
        if not event.get("id"):
            event["id"] = str(uuid4())
        if not event.get("time"):
            event["time"] = datetime.utcnow().isoformat()
        
        # Put in local queue
        await self._local_events.put({
            "cloud_event": json.loads(to_json(event)),
            "stream": stream,
            "headers": headers or {},
            "sequence": self._local_events.qsize() + 1
        })
        
        logger.info(f"Published local event: {event['id']}")
        
        return {
            "event_id": event["id"],
            "sequence": self._local_events.qsize(),
            "published_at": datetime.utcnow()
        }
    
    async def _subscribe_local(
        self,
        consumer_id: str,
        event_types: List[str],
        stream: str,
        callback = None
    ) -> str:
        """Subscribe to events locally."""
        from uuid import uuid4
        
        subscription_id = f"{consumer_id}_{stream}_{uuid4().hex[:8]}"
        
        # Store subscription info
        if not hasattr(self, "_subscriptions"):
            self._subscriptions = {}
        
        self._subscriptions[subscription_id] = {
            "consumer_id": consumer_id,
            "event_types": event_types,
            "stream": stream,
            "callback": callback
        }
        
        # Start processing if callback provided
        if callback:
            asyncio.create_task(self._process_local_subscription(subscription_id))
        
        logger.info(f"Created local subscription: {subscription_id}")
        return subscription_id
    
    async def _stream_events_local(self, subscription_id: str) -> AsyncIterator[Dict[str, Any]]:
        """Stream events locally."""
        if not hasattr(self, "_subscriptions"):
            return
        
        sub = self._subscriptions.get(subscription_id)
        if not sub:
            return
        
        while True:
            try:
                # Get event from queue
                event_data = await asyncio.wait_for(
                    self._local_events.get(),
                    timeout=1.0
                )
                
                # Check if event matches subscription
                event_type = event_data["cloud_event"].get("type")
                if sub["event_types"] and event_type not in sub["event_types"]:
                    continue
                
                if event_data["stream"] != sub["stream"]:
                    continue
                
                # Yield event
                yield {
                    "cloud_event": event_data["cloud_event"],
                    "metadata": {
                        "stream_name": event_data["stream"],
                        "sequence": event_data["sequence"],
                        "received_at": datetime.utcnow(),
                        "delivery_count": 1,
                        "headers": event_data["headers"]
                    }
                }
                
            except asyncio.TimeoutError:
                # No events available
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Error streaming local events: {e}")
                await asyncio.sleep(1)
    
    async def _process_local_subscription(self, subscription_id: str):
        """Process local subscription with callback."""
        sub = self._subscriptions.get(subscription_id)
        if not sub or not sub["callback"]:
            return
        
        async for event in self._stream_events_local(subscription_id):
            try:
                await sub["callback"](event)
            except Exception as e:
                logger.error(f"Error in local subscription callback: {e}")

    def unsubscribe(self, event_type: str, handler: Any) -> None:
        """Unsubscribe from an event type (Not implemented)."""
        # This would require more sophisticated subscription management.
        logger.warning(f"Unsubscribe for event type '{event_type}' is not implemented.")
        pass


# Global instance
_event_gateway_stub = None


def get_event_gateway_stub() -> EventGatewayStub:
    """Get or create event gateway service stub."""
    global _event_gateway_stub
    if _event_gateway_stub is None:
        _event_gateway_stub = EventGatewayStub()
    return _event_gateway_stub