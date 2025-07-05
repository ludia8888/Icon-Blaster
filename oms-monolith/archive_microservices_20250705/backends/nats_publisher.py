"""
NATS Event Publisher
Wraps the unified publisher with NATS backend for backward compatibility
"""
from typing import Dict, Any, Optional
from core.events.unified_publisher import UnifiedEventPublisher, PublisherConfig, PublisherBackend
from core.event_publisher.cloudevents_enhanced import EnhancedCloudEvent, CloudEventBuilder, EventType
from utils.logger import get_logger

logger = get_logger(__name__)


class NATSEventPublisher:
    """
    NATS Event Publisher with CloudEvents support
    This is a compatibility wrapper around the UnifiedEventPublisher
    """
    
    def __init__(self, nats_url: Optional[str] = None):
        self.nats_url = nats_url or "nats://localhost:4222"
        self.config = PublisherConfig.nats_streaming(self.nats_url)
        self.publisher = UnifiedEventPublisher(self.config)
        self._connected = False
    
    async def connect(self):
        """Connect to NATS server"""
        if not self._connected:
            await self.publisher.connect()
            self._connected = True
            logger.info(f"NATS publisher connected to {self.nats_url}")
    
    async def disconnect(self):
        """Disconnect from NATS server"""
        if self._connected:
            await self.publisher.disconnect()
            self._connected = False
            logger.info("NATS publisher disconnected")
    
    async def publish(self, subject: str, data: Any) -> bool:
        """
        Publish event to NATS
        
        Args:
            subject: NATS subject (e.g., "oms.schema.created")
            data: Event data (dict or CloudEvent)
            
        Returns:
            bool: Success status
        """
        if not self._connected:
            await self.connect()
        
        try:
            # Handle CloudEvent objects
            if isinstance(data, EnhancedCloudEvent):
                return await self.publisher.publish(
                    event_type=str(data.type),
                    data=data.data or {},
                    subject=subject or data.subject,
                    source=data.source,
                    correlation_id=data.ce_correlationid,
                    metadata={
                        "branch": data.ce_branch,
                        "commit": data.ce_commit,
                        "author": data.ce_author
                    }
                )
            
            # Handle dict events
            elif isinstance(data, dict):
                # Extract event type from subject if not in data
                event_type = data.get("type", self._subject_to_event_type(subject))
                
                return await self.publisher.publish(
                    event_type=event_type,
                    data=data.get("data", data),
                    subject=subject,
                    source=data.get("source", "/oms"),
                    correlation_id=data.get("correlation_id"),
                    metadata=data.get("metadata")
                )
            
            # Handle raw data
            else:
                return await self.publisher.publish(
                    event_type=self._subject_to_event_type(subject),
                    data={"value": data},
                    subject=subject,
                    source="/oms"
                )
                
        except Exception as e:
            logger.error(f"Failed to publish to NATS subject {subject}: {e}")
            return False
    
    async def publish_event(self, event: EnhancedCloudEvent) -> bool:
        """
        Publish a CloudEvent to NATS
        
        Args:
            event: CloudEvent to publish
            
        Returns:
            bool: Success status
        """
        subject = event.get_nats_subject()
        return await self.publish(subject, event)
    
    async def publish_batch(self, events: list) -> bool:
        """
        Publish multiple events
        
        Args:
            events: List of events to publish
            
        Returns:
            bool: Success status
        """
        if not self._connected:
            await self.connect()
        
        formatted_events = []
        for event in events:
            if isinstance(event, EnhancedCloudEvent):
                formatted_events.append(event.to_structured_format())
            elif isinstance(event, dict):
                formatted_events.append(event)
            else:
                logger.warning(f"Skipping invalid event type: {type(event)}")
        
        return await self.publisher.publish_batch(formatted_events)
    
    def _subject_to_event_type(self, subject: str) -> str:
        """Convert NATS subject to event type"""
        # oms.schema.created -> com.foundry.oms.schema.created
        if subject.startswith("oms."):
            return f"com.foundry.{subject}"
        elif subject.startswith("events."):
            return f"com.foundry.oms.{subject[7:]}"
        else:
            return f"com.foundry.oms.{subject}"
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()