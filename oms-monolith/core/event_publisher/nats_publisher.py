"""NATS Event Publisher for MSA integration"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any
import uuid
import os

import nats
from nats.js import JetStreamContext
from nats.errors import TimeoutError

from shared.events import EventPublisher, Event

logger = logging.getLogger(__name__)


class NATSEventPublisher(EventPublisher):
    """NATS-based event publisher implementation"""
    
    def __init__(self):
        self.nc: Optional[nats.NATS] = None
        self.js: Optional[JetStreamContext] = None
        self.stream_name = os.getenv("NATS_STREAM_NAME", "audit-events")
        self.nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
        self._connected = False
        
    async def connect(self):
        """Connect to NATS and setup JetStream"""
        try:
            self.nc = await nats.connect(
                servers=[self.nats_url],
                error_cb=self._error_cb,
                disconnected_cb=self._disconnected_cb,
                reconnected_cb=self._reconnected_cb
            )
            
            # Create JetStream context
            self.js = self.nc.jetstream()
            
            # Ensure stream exists
            await self._ensure_stream()
            
            self._connected = True
            logger.info(f"Connected to NATS at {self.nats_url}")
            
        except Exception as e:
            logger.error(f"Failed to connect to NATS: {e}")
            raise
            
    async def _ensure_stream(self):
        """Ensure the JetStream stream exists"""
        try:
            await self.js.stream_info(self.stream_name)
            logger.info(f"Stream {self.stream_name} already exists")
        except:
            # Create stream if it doesn't exist
            await self.js.add_stream(
                name=self.stream_name,
                subjects=[f"{self.stream_name}.>"],
                retention="limits",
                max_msgs=10000,
                max_age=86400  # 1 day
            )
            logger.info(f"Created stream {self.stream_name}")
            
    async def publish(self, event: Event) -> bool:
        """Publish an event to NATS"""
        if not self._connected:
            logger.error("Not connected to NATS")
            return False
            
        try:
            # Convert event to CloudEvents format
            cloud_event = self._to_cloud_event(event)
            
            # Determine subject based on event type
            subject = f"{self.stream_name}.{event.event_type.replace(':', '.')}"
            
            # Publish to NATS
            ack = await self.js.publish(
                subject,
                json.dumps(cloud_event).encode(),
                headers={
                    "Content-Type": "application/cloudevents+json",
                    "CE-Type": event.event_type,
                    "CE-ID": cloud_event["id"]
                }
            )
            
            logger.info(f"Published event {cloud_event['id']} to {subject}, seq: {ack.seq}")
            return True
            
        except TimeoutError:
            logger.error(f"Timeout publishing event {event.event_type}")
            return False
        except Exception as e:
            logger.error(f"Error publishing event: {e}")
            return False
            
    def _to_cloud_event(self, event: Event) -> Dict[str, Any]:
        """Convert internal event to CloudEvents format"""
        return {
            "specversion": "1.0",
            "type": event.event_type,
            "source": f"oms/{event.source}",
            "id": str(uuid.uuid4()),
            "time": datetime.utcnow().isoformat() + "Z",
            "datacontenttype": "application/json",
            "data": event.data,
            "subject": event.data.get("object_id", "unknown"),
            "service": "oms",
            "traceid": event.correlation_id or str(uuid.uuid4())
        }
        
    async def close(self):
        """Close NATS connection"""
        if self.nc and not self.nc.is_closed:
            await self.nc.close()
            self._connected = False
            logger.info("Closed NATS connection")
            
    async def _error_cb(self, e):
        logger.error(f"NATS error: {e}")
        
    async def _disconnected_cb(self):
        logger.warning("NATS disconnected")
        self._connected = False
        
    async def _reconnected_cb(self):
        logger.info("NATS reconnected")
        self._connected = True
        
    async def publish_batch(self, events: list[Event]) -> int:
        """Publish multiple events"""
        success_count = 0
        for event in events:
            if await self.publish(event):
                success_count += 1
        return success_count