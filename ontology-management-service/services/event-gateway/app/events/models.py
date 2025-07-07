"""Data models for event gateway service."""

from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict
from cloudevents.http import CloudEvent


class EventMetadata(BaseModel):
    """Metadata for an event."""
    stream_name: str
    sequence: int
    received_at: datetime
    delivery_count: int = 0
    headers: Dict[str, str] = Field(default_factory=dict)


class Event(BaseModel):
    """Event with CloudEvent and metadata."""
    cloud_event: Dict[str, Any]  # CloudEvent as dict
    metadata: EventMetadata
    
    class Config:
        arbitrary_types_allowed = True


class WebhookConfig(BaseModel):
    """Webhook configuration."""
    headers: Dict[str, str] = Field(default_factory=dict)
    secret: Optional[str] = Field(default=None, description="Secret for HMAC signature")
    timeout_seconds: int = Field(default=30)
    max_retries: int = Field(default=3)
    retry_delay_seconds: int = Field(default=60)
    verify_ssl: bool = Field(default=True)


class WebhookStats(BaseModel):
    """Webhook delivery statistics."""
    total_deliveries: int = 0
    successful_deliveries: int = 0
    failed_deliveries: int = 0
    last_delivery_at: Optional[datetime] = None
    last_delivery_status: Optional[str] = None
    average_response_time_ms: float = 0.0


class Webhook(BaseModel):
    """Webhook configuration."""
    id: Optional[str] = None
    name: str
    url: str
    event_types: List[str] = Field(default_factory=list, description="Event types to deliver")
    config: WebhookConfig = Field(default_factory=WebhookConfig)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    enabled: bool = True
    stats: Optional[WebhookStats] = None


class StreamConfig(BaseModel):
    """Stream configuration."""
    max_msgs: int = Field(default=-1, description="Maximum messages, -1 for unlimited")
    max_bytes: int = Field(default=-1, description="Maximum bytes, -1 for unlimited")
    max_age_seconds: int = Field(default=0, description="Maximum age in seconds, 0 for unlimited")
    max_msg_size: int = Field(default=-1, description="Maximum message size, -1 for unlimited")
    replicas: int = Field(default=1, description="Number of replicas")
    discard_new_per_subject: bool = Field(default=False, description="Discard new messages when limit reached")


class Stream(BaseModel):
    """JetStream stream configuration."""
    name: str
    description: Optional[str] = None
    subjects: List[str] = Field(default_factory=list)
    config: StreamConfig = Field(default_factory=StreamConfig)
    created_at: Optional[datetime] = None


class PublishResult(BaseModel):
    """Result of publishing an event."""
    event_id: str
    sequence: int
    published_at: datetime


class Subscription(BaseModel):
    """Active subscription."""
    id: str
    consumer_id: str
    event_types: List[str]
    stream: str
    durable_name: Optional[str] = None
    nats_subs: Optional[List[Any]] = None  # NATS subscription objects
    callback: Optional[Callable] = None
    
    class Config:
        arbitrary_types_allowed = True


# Request/Response models for API
class PublishEventRequest(BaseModel):
    """Publish event request."""
    event: Dict[str, Any]  # CloudEvent as dict
    stream: str = "events"
    headers: Optional[Dict[str, str]] = None


class PublishEventsBatchRequest(BaseModel):
    """Publish events batch request."""
    events: List[Dict[str, Any]]  # CloudEvents as dicts
    stream: str = "events"
    headers: Optional[Dict[str, str]] = None


class SubscribeRequest(BaseModel):
    """Subscribe request."""
    consumer_id: str
    event_types: List[str] = Field(default_factory=list)
    stream: str = "events"
    durable_name: Optional[str] = None
    start_sequence: Optional[int] = None
    deliver_new: bool = True
    max_in_flight: int = 100
    ack_wait_seconds: int = 30


class ListEventsRequest(BaseModel):
    """List events request."""
    event_types: Optional[List[str]] = None
    stream: str = "events"
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = Field(default=100, ge=1, le=1000)
    start_sequence: Optional[int] = None


class RegisterWebhookRequest(BaseModel):
    """Register webhook request."""
    webhook: Webhook


class UpdateWebhookRequest(BaseModel):
    """Update webhook request."""
    webhook: Webhook


class CreateStreamRequest(BaseModel):
    """Create stream request."""
    stream: Stream