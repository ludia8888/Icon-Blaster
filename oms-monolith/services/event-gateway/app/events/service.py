"""Event Gateway service implementation using NATS JetStream and CloudEvents."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, AsyncIterator
from uuid import uuid4
import hashlib
import hmac

import nats
from nats.js import JetStreamContext
from nats.errors import TimeoutError as NatsTimeoutError
from cloudevents.http import CloudEvent
from cloudevents.conversion import to_dict, from_dict
import aioredis
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .models import (
    Event, EventMetadata, Webhook, WebhookConfig, WebhookStats,
    Stream, StreamConfig, PublishResult, Subscription
)

logger = logging.getLogger(__name__)


class EventGatewayService:
    """NATS-based event gateway with CloudEvents support."""
    
    def __init__(
        self,
        nats_url: str = "nats://localhost:4222",
        redis_url: str = "redis://localhost:6379/7"
    ):
        self.nats_url = nats_url
        self.redis_url = redis_url
        self.nc: Optional[nats.NATS] = None
        self.js: Optional[JetStreamContext] = None
        self.redis: Optional[aioredis.Redis] = None
        self._subscriptions: Dict[str, Subscription] = {}
        self._webhook_executor = WebhookExecutor()
        self._is_initialized = False
    
    async def initialize(self):
        """Initialize the event gateway service."""
        if self._is_initialized:
            return
        
        # Connect to NATS
        self.nc = await nats.connect(self.nats_url)
        self.js = self.nc.jetstream()
        
        # Connect to Redis
        self.redis = await aioredis.from_url(self.redis_url, decode_responses=True)
        
        # Create default streams
        await self._create_default_streams()
        
        # Start webhook processor
        asyncio.create_task(self._webhook_processor())
        
        self._is_initialized = True
        logger.info("Event gateway service initialized")
    
    async def shutdown(self):
        """Shutdown the event gateway service."""
        # Cancel all subscriptions
        for sub in self._subscriptions.values():
            if sub.nats_sub:
                await sub.nats_sub.unsubscribe()
        
        self._subscriptions.clear()
        
        # Close connections
        if self.nc:
            await self.nc.close()
        
        if self.redis:
            await self.redis.close()
        
        self._is_initialized = False
        logger.info("Event gateway service shutdown")
    
    async def publish_event(
        self,
        event: CloudEvent,
        stream: str = "events",
        headers: Optional[Dict[str, str]] = None
    ) -> PublishResult:
        """Publish a CloudEvent to NATS JetStream."""
        if not self.js:
            raise RuntimeError("JetStream not initialized")
        
        # Ensure event has required fields
        if not event.get("id"):
            event["id"] = str(uuid4())
        if not event.get("time"):
            event["time"] = datetime.now(timezone.utc).isoformat()
        if not event.get("specversion"):
            event["specversion"] = "1.0"
        
        # Convert CloudEvent to dict
        event_dict = to_dict(event)
        
        # Prepare NATS message
        subject = f"{stream}.{event['type'].replace(':', '.')}"
        data = json.dumps(event_dict).encode()
        
        # Add headers
        msg_headers = headers or {}
        msg_headers["ce-id"] = event["id"]
        msg_headers["ce-type"] = event["type"]
        msg_headers["ce-source"] = event["source"]
        
        # Publish to JetStream
        ack = await self.js.publish(subject, data, headers=msg_headers)
        
        # Queue for webhook processing
        await self._queue_for_webhooks(event_dict, stream, ack.seq)
        
        logger.info(f"Published event: {event['id']} to {subject}")
        
        return PublishResult(
            event_id=event["id"],
            sequence=ack.seq,
            published_at=datetime.now(timezone.utc)
        )
    
    async def publish_events_batch(
        self,
        events: List[CloudEvent],
        stream: str = "events",
        headers: Optional[Dict[str, str]] = None
    ) -> List[PublishResult]:
        """Publish multiple events as a batch."""
        results = []
        
        for event in events:
            try:
                result = await self.publish_event(event, stream, headers)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to publish event: {e}")
                # Continue with other events
        
        return results
    
    async def subscribe(
        self,
        consumer_id: str,
        event_types: List[str],
        stream: str = "events",
        durable_name: Optional[str] = None,
        start_sequence: Optional[int] = None,
        deliver_new: bool = True,
        max_in_flight: int = 100,
        ack_wait_seconds: int = 30,
        callback = None
    ) -> str:
        """Subscribe to events with filtering."""
        if not self.js:
            raise RuntimeError("JetStream not initialized")
        
        # Generate subscription ID
        subscription_id = f"{consumer_id}_{stream}_{uuid4().hex[:8]}"
        
        # Create subject filter
        if event_types:
            # Subscribe to specific event types
            subjects = [f"{stream}.{et.replace(':', '.')}" for et in event_types]
        else:
            # Subscribe to all events in stream
            subjects = [f"{stream}.>"]
        
        # Configure consumer
        config = {
            "max_ack_pending": max_in_flight,
            "ack_wait": ack_wait_seconds * 1_000_000_000,  # nanoseconds
        }
        
        if durable_name:
            config["durable_name"] = durable_name
        
        if start_sequence:
            config["opt_start_seq"] = start_sequence
        elif deliver_new:
            config["deliver_policy"] = "new"
        else:
            config["deliver_policy"] = "all"
        
        # Create pull subscription for each subject
        subs = []
        for subject in subjects:
            sub = await self.js.pull_subscribe(subject, durable=durable_name, config=config)
            subs.append(sub)
        
        # Store subscription
        subscription = Subscription(
            id=subscription_id,
            consumer_id=consumer_id,
            event_types=event_types,
            stream=stream,
            durable_name=durable_name,
            nats_subs=subs,
            callback=callback
        )
        
        self._subscriptions[subscription_id] = subscription
        
        # Start message processor if callback provided
        if callback:
            asyncio.create_task(self._process_subscription(subscription))
        
        logger.info(f"Created subscription: {subscription_id}")
        return subscription_id
    
    async def unsubscribe(self, consumer_id: str, subscription_id: str) -> bool:
        """Unsubscribe from events."""
        subscription = self._subscriptions.get(subscription_id)
        if not subscription or subscription.consumer_id != consumer_id:
            return False
        
        # Unsubscribe from NATS
        for sub in subscription.nats_subs:
            await sub.unsubscribe()
        
        # Remove subscription
        del self._subscriptions[subscription_id]
        
        logger.info(f"Removed subscription: {subscription_id}")
        return True
    
    async def stream_events(
        self,
        subscription_id: str,
        batch_size: int = 10,
        timeout_seconds: int = 1
    ) -> AsyncIterator[Event]:
        """Stream events for a subscription."""
        subscription = self._subscriptions.get(subscription_id)
        if not subscription:
            raise ValueError(f"Subscription not found: {subscription_id}")
        
        while True:
            try:
                # Fetch messages from all subscriptions
                messages = []
                for sub in subscription.nats_subs:
                    try:
                        batch = await sub.fetch(batch_size, timeout=timeout_seconds)
                        messages.extend(batch)
                    except NatsTimeoutError:
                        # No messages available
                        pass
                
                # Process messages
                for msg in messages:
                    try:
                        # Parse CloudEvent
                        event_dict = json.loads(msg.data.decode())
                        cloud_event = from_dict(event_dict)
                        
                        # Create metadata
                        metadata = EventMetadata(
                            stream_name=subscription.stream,
                            sequence=msg.metadata.sequence.stream,
                            received_at=datetime.now(timezone.utc),
                            delivery_count=msg.metadata.num_delivered,
                            headers=dict(msg.headers) if msg.headers else {}
                        )
                        
                        # Yield event
                        yield Event(cloud_event=cloud_event, metadata=metadata)
                        
                        # Acknowledge message
                        await msg.ack()
                        
                    except Exception as e:
                        logger.error(f"Failed to process message: {e}")
                        # Negative acknowledge to retry
                        await msg.nak()
                
                # If no messages, wait a bit
                if not messages:
                    await asyncio.sleep(0.1)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error streaming events: {e}")
                await asyncio.sleep(1)
    
    async def acknowledge_event(
        self,
        consumer_id: str,
        event_id: str,
        sequence: int
    ) -> bool:
        """Acknowledge event processing."""
        # In pull-based subscriptions, acknowledgment happens during streaming
        # This method is for compatibility with push-based systems
        logger.info(f"Event acknowledged: {event_id} by {consumer_id}")
        return True
    
    async def register_webhook(self, webhook: Webhook) -> Webhook:
        """Register a new webhook."""
        if not webhook.id:
            webhook.id = str(uuid4())
        
        webhook.created_at = datetime.now(timezone.utc)
        webhook.updated_at = webhook.created_at
        webhook.stats = WebhookStats()
        
        # Save to Redis
        await self.redis.hset(
            "webhooks",
            webhook.id,
            webhook.json()
        )
        
        logger.info(f"Registered webhook: {webhook.id}")
        return webhook
    
    async def update_webhook(self, webhook_id: str, webhook: Webhook) -> Optional[Webhook]:
        """Update an existing webhook."""
        existing = await self.get_webhook(webhook_id)
        if not existing:
            return None
        
        webhook.id = webhook_id
        webhook.created_at = existing.created_at
        webhook.updated_at = datetime.now(timezone.utc)
        webhook.stats = existing.stats
        
        # Save to Redis
        await self.redis.hset(
            "webhooks",
            webhook.id,
            webhook.json()
        )
        
        logger.info(f"Updated webhook: {webhook_id}")
        return webhook
    
    async def delete_webhook(self, webhook_id: str) -> bool:
        """Delete a webhook."""
        result = await self.redis.hdel("webhooks", webhook_id)
        logger.info(f"Deleted webhook: {webhook_id}")
        return result > 0
    
    async def get_webhook(self, webhook_id: str) -> Optional[Webhook]:
        """Get a webhook by ID."""
        data = await self.redis.hget("webhooks", webhook_id)
        if not data:
            return None
        return Webhook.parse_raw(data)
    
    async def list_webhooks(
        self,
        event_types: Optional[List[str]] = None,
        enabled_only: bool = False
    ) -> List[Webhook]:
        """List webhooks with filtering."""
        all_data = await self.redis.hgetall("webhooks")
        webhooks = [Webhook.parse_raw(data) for data in all_data.values()]
        
        # Filter webhooks
        filtered = []
        for webhook in webhooks:
            if enabled_only and not webhook.enabled:
                continue
            
            if event_types:
                # Check if webhook listens to any of the requested event types
                if not any(et in webhook.event_types for et in event_types):
                    continue
            
            filtered.append(webhook)
        
        return filtered
    
    async def create_stream(self, stream: Stream) -> Stream:
        """Create a new JetStream stream."""
        if not self.js:
            raise RuntimeError("JetStream not initialized")
        
        config = {
            "name": stream.name,
            "subjects": stream.subjects or [f"{stream.name}.>"],
            "retention": "limits",
            "storage": "file",
            "max_msgs": stream.config.max_msgs or -1,
            "max_bytes": stream.config.max_bytes or -1,
            "max_age": stream.config.max_age_seconds * 1_000_000_000 if stream.config.max_age_seconds else 0,
            "max_msg_size": stream.config.max_msg_size or -1,
            "num_replicas": stream.config.replicas or 1,
            "discard": "new" if stream.config.discard_new_per_subject else "old"
        }
        
        await self.js.add_stream(**config)
        stream.created_at = datetime.now(timezone.utc)
        
        logger.info(f"Created stream: {stream.name}")
        return stream
    
    async def delete_stream(self, stream_name: str) -> bool:
        """Delete a JetStream stream."""
        if not self.js:
            raise RuntimeError("JetStream not initialized")
        
        try:
            await self.js.delete_stream(stream_name)
            logger.info(f"Deleted stream: {stream_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete stream: {e}")
            return False
    
    async def list_streams(self) -> List[Stream]:
        """List all JetStream streams."""
        if not self.js:
            raise RuntimeError("JetStream not initialized")
        
        streams = []
        
        # Get stream info from NATS
        stream_names = await self.js.streams_info()
        
        for info in stream_names:
            stream = Stream(
                name=info.config.name,
                description=info.config.description or "",
                subjects=info.config.subjects,
                config=StreamConfig(
                    max_msgs=info.config.max_msgs,
                    max_bytes=info.config.max_bytes,
                    max_age_seconds=info.config.max_age // 1_000_000_000 if info.config.max_age else 0,
                    max_msg_size=info.config.max_msg_size,
                    replicas=info.config.num_replicas
                ),
                created_at=datetime.now(timezone.utc)  # NATS doesn't track creation time
            )
            streams.append(stream)
        
        return streams
    
    async def _create_default_streams(self):
        """Create default streams if they don't exist."""
        default_streams = [
            Stream(
                name="events",
                description="Default event stream",
                subjects=["events.>"],
                config=StreamConfig(
                    max_age_seconds=86400 * 7,  # 7 days
                    replicas=1
                )
            ),
            Stream(
                name="audit",
                description="Audit event stream",
                subjects=["audit.>"],
                config=StreamConfig(
                    max_age_seconds=86400 * 30,  # 30 days
                    replicas=1
                )
            ),
            Stream(
                name="metrics",
                description="Metrics event stream",
                subjects=["metrics.>"],
                config=StreamConfig(
                    max_age_seconds=86400,  # 1 day
                    replicas=1
                )
            )
        ]
        
        for stream in default_streams:
            try:
                await self.create_stream(stream)
            except Exception as e:
                # Stream might already exist
                logger.debug(f"Stream {stream.name} might already exist: {e}")
    
    async def _queue_for_webhooks(self, event_dict: Dict, stream: str, sequence: int):
        """Queue event for webhook delivery."""
        # Get webhooks that should receive this event
        event_type = event_dict.get("type")
        webhooks = await self.list_webhooks(event_types=[event_type], enabled_only=True)
        
        if not webhooks:
            return
        
        # Queue for each webhook
        for webhook in webhooks:
            await self.redis.lpush(
                "webhook_queue",
                json.dumps({
                    "webhook_id": webhook.id,
                    "event": event_dict,
                    "stream": stream,
                    "sequence": sequence,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            )
    
    async def _webhook_processor(self):
        """Process webhook delivery queue."""
        while True:
            try:
                # Get item from queue
                item = await self.redis.brpop("webhook_queue", timeout=1)
                if not item:
                    continue
                
                # Parse queue item
                data = json.loads(item[1])
                webhook_id = data["webhook_id"]
                event_dict = data["event"]
                
                # Get webhook
                webhook = await self.get_webhook(webhook_id)
                if not webhook or not webhook.enabled:
                    continue
                
                # Deliver webhook
                success = await self._webhook_executor.deliver(webhook, event_dict)
                
                # Update stats
                webhook.stats.total_deliveries += 1
                if success:
                    webhook.stats.successful_deliveries += 1
                else:
                    webhook.stats.failed_deliveries += 1
                webhook.stats.last_delivery_at = datetime.now(timezone.utc)
                
                # Save updated webhook
                await self.redis.hset(
                    "webhooks",
                    webhook.id,
                    webhook.json()
                )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error processing webhook: {e}")
                await asyncio.sleep(1)
    
    async def _process_subscription(self, subscription: Subscription):
        """Process messages for a subscription with callback."""
        async for event in self.stream_events(subscription.id):
            try:
                if subscription.callback:
                    await subscription.callback(event)
            except Exception as e:
                logger.error(f"Error in subscription callback: {e}")


class WebhookExecutor:
    """Webhook delivery executor with retry logic."""
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def deliver(self, webhook: Webhook, event_dict: Dict) -> bool:
        """Deliver event to webhook URL."""
        async with httpx.AsyncClient(
            timeout=webhook.config.timeout_seconds,
            verify=webhook.config.verify_ssl
        ) as client:
            
            # Prepare headers
            headers = webhook.config.headers.copy()
            headers["Content-Type"] = "application/cloudevents+json"
            
            # Add signature if secret configured
            if webhook.config.secret:
                signature = self._calculate_signature(
                    webhook.config.secret,
                    json.dumps(event_dict)
                )
                headers["X-Webhook-Signature"] = signature
            
            # Send request
            response = await client.post(
                webhook.url,
                json=event_dict,
                headers=headers
            )
            
            # Check response
            response.raise_for_status()
            
            logger.info(f"Delivered event to webhook: {webhook.id}")
            return True
    
    def _calculate_signature(self, secret: str, payload: str) -> str:
        """Calculate HMAC signature for webhook payload."""
        return hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()