"""
NATS Event Backend for Unified Event Publisher
Implements high-throughput event streaming using NATS JetStream
"""
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from shared.infrastructure.real_nats_client import RealNATSClient
from core.event_publisher.cloudevents_enhanced import EnhancedCloudEvent
from ..unified_publisher import EventPublisherBackend, PublisherConfig

logger = logging.getLogger(__name__)


class NATSEventBackend(EventPublisherBackend):
    """
    NATS JetStream backend for event publishing
    Provides guaranteed delivery and event streaming capabilities
    """
    
    def __init__(self, config: PublisherConfig):
        self.config = config
        self.client: Optional[RealNATSClient] = None
        self._connected = False
        
    async def connect(self) -> None:
        """Connect to NATS server"""
        try:
            self.client = RealNATSClient(
                servers=[self.config.endpoint] if self.config.endpoint else None
            )
            await self.client.connect()
            
            # Ensure event streams exist
            await self._ensure_event_streams()
            
            self._connected = True
            logger.info(f"Connected to NATS at {self.config.endpoint}")
            
        except Exception as e:
            logger.error(f"Failed to connect to NATS: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Disconnect from NATS server"""
        if self.client:
            await self.client.close()
            self._connected = False
            logger.info("Disconnected from NATS")
    
    async def publish(self, event: Dict[str, Any]) -> bool:
        """Publish single event to NATS"""
        if not self._connected or not self.client:
            logger.error("NATS client not connected")
            return False
        
        try:
            # Convert to CloudEvent if needed
            cloud_event = self._to_cloud_event(event)
            
            # Get NATS subject based on event type
            subject = self._get_subject(cloud_event)
            
            # Prepare message with CloudEvents headers
            headers = cloud_event.to_binary_headers()
            
            # Publish to NATS with JetStream
            if self.config.enable_batching:
                # Use JetStream for guaranteed delivery
                result = await self.client.jetstream_publish(
                    subject=subject,
                    data=cloud_event.data or {},
                    msg_id=cloud_event.id,
                    expected_stream=self.config.nats_stream
                )
                logger.debug(f"Published to JetStream: {subject}, seq={result['seq']}")
            else:
                # Regular NATS publish for fire-and-forget
                await self.client.publish(
                    subject=subject,
                    data=cloud_event.data or {},
                    headers=headers
                )
                logger.debug(f"Published to NATS: {subject}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to publish event to NATS: {e}")
            return False
    
    async def publish_batch(self, events: List[Dict[str, Any]]) -> bool:
        """Publish multiple events to NATS"""
        if not self._connected or not self.client:
            logger.error("NATS client not connected")
            return False
        
        success_count = 0
        
        for event in events:
            try:
                cloud_event = self._to_cloud_event(event)
                subject = self._get_subject(cloud_event)
                
                # Use JetStream for batch with deduplication
                result = await self.client.jetstream_publish(
                    subject=subject,
                    data=cloud_event.data or {},
                    msg_id=cloud_event.id,
                    expected_stream=self.config.nats_stream
                )
                
                if not result.get('duplicate', False):
                    success_count += 1
                    
            except Exception as e:
                logger.error(f"Failed to publish batch event: {e}")
                continue
        
        logger.info(f"Published {success_count}/{len(events)} events to NATS")
        return success_count == len(events)
    
    async def health_check(self) -> bool:
        """Check NATS connection health"""
        if not self.client:
            return False
        
        health = await self.client.health_check()
        return health.get("connected", False)
    
    async def _ensure_event_streams(self) -> None:
        """Ensure required JetStream streams exist"""
        try:
            # Main event stream
            await self._create_stream(
                name=self.config.nats_stream.upper(),
                subjects=[
                    f"{self.config.nats_subject_prefix}.>",
                    "events.>",
                    "oms.>"
                ],
                description="OMS event stream for all application events"
            )
            
            # Schema events stream
            await self._create_stream(
                name="SCHEMA_EVENTS",
                subjects=["oms.schema.>", "schema.>"],
                description="Schema change events"
            )
            
            # Branch events stream
            await self._create_stream(
                name="BRANCH_EVENTS",
                subjects=["oms.branch.>", "branch.>"],
                description="Branch and proposal events"
            )
            
            # Action events stream
            await self._create_stream(
                name="ACTION_EVENTS",
                subjects=["oms.action.>", "action.>"],
                description="Action execution events"
            )
            
        except Exception as e:
            logger.error(f"Failed to create event streams: {e}")
            # Continue anyway - streams might already exist
    
    async def _create_stream(self, name: str, subjects: List[str], description: str) -> None:
        """Create or update a JetStream stream"""
        try:
            # Check if stream exists
            await self.client.js.stream_info(name)
            logger.debug(f"Stream {name} already exists")
        except:
            # Create new stream
            await self.client.js.add_stream(
                name=name,
                subjects=subjects,
                retention="limits",
                max_msgs=10000000,  # 10M messages
                max_bytes=10*1024*1024*1024,  # 10GB
                max_age=86400*30,  # 30 days
                storage="file",
                num_replicas=1,
                duplicate_window=300,  # 5 minute deduplication
                description=description
            )
            logger.info(f"Created JetStream stream: {name}")
    
    def _to_cloud_event(self, event: Dict[str, Any]) -> EnhancedCloudEvent:
        """Convert event dict to CloudEvent"""
        if "specversion" in event:
            # Already a CloudEvent
            return EnhancedCloudEvent(**event)
        
        # Convert from custom format
        return EnhancedCloudEvent(
            type=event.get("type", "com.foundry.oms.unknown"),
            source=event.get("source", "/oms"),
            data=event.get("data", {}),
            subject=event.get("subject"),
            ce_correlationid=event.get("correlation_id"),
            ce_branch=event.get("metadata", {}).get("branch"),
            ce_commit=event.get("metadata", {}).get("commit"),
            ce_author=event.get("metadata", {}).get("author")
        )
    
    def _get_subject(self, event: EnhancedCloudEvent) -> str:
        """Generate NATS subject from event"""
        # Use the CloudEvent's built-in method
        base_subject = event.get_nats_subject()
        
        # Add prefix if configured
        if self.config.nats_subject_prefix and not base_subject.startswith(self.config.nats_subject_prefix):
            return f"{self.config.nats_subject_prefix}.{base_subject}"
        
        return base_subject