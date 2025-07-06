"""
Idempotency Models
Ensures exactly-once processing with Event ID and Commit Hash tracking
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field
import hashlib
import uuid


class IdempotencyKey(BaseModel):
    """Idempotency key for deduplication"""
    
    # Primary key components
    event_id: str = Field(..., description="Unique event identifier")
    consumer_id: str = Field(..., description="Consumer/service identifier")
    
    # Additional context
    event_type: str = Field(..., description="Type of event")
    resource_id: Optional[str] = Field(None, description="Associated resource ID")
    
    def get_key(self) -> str:
        """Generate composite idempotency key"""
        return f"{self.consumer_id}:{self.event_id}"
    
    def get_hash(self) -> str:
        """Generate hash of idempotency key"""
        key_str = f"{self.consumer_id}:{self.event_id}:{self.event_type}"
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]


class EventProcessingRecord(BaseModel):
    """Record of processed event"""
    
    # Event identification
    event_id: str = Field(..., description="Unique event ID")
    event_type: str = Field(..., description="Event type")
    event_version: int = Field(..., description="Event schema version")
    
    # Processing details
    consumer_id: str = Field(..., description="Consumer that processed the event")
    consumer_version: str = Field(..., description="Consumer version")
    
    # Commit tracking
    input_commit_hash: str = Field(..., description="Commit hash of input state")
    output_commit_hash: str = Field(..., description="Commit hash after processing")
    
    # Processing metadata
    processed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processing_duration_ms: int = Field(..., description="Processing time in milliseconds")
    
    # Result tracking
    status: str = Field(..., description="success, failed, skipped")
    error_message: Optional[str] = Field(None, description="Error details if failed")
    retry_count: int = Field(0, description="Number of retry attempts")
    
    # Side effects
    side_effects: List[str] = Field(default_factory=list, description="List of side effects")
    created_resources: List[str] = Field(default_factory=list, description="Resources created")
    updated_resources: List[str] = Field(default_factory=list, description="Resources updated")
    
    # Idempotency
    idempotency_key: str = Field(..., description="Composite idempotency key")
    is_duplicate: bool = Field(False, description="Whether this was a duplicate")


class EventEnvelope(BaseModel):
    """Event envelope with idempotency support"""
    
    # Event metadata
    event_id: str = Field(default_factory=lambda: generate_event_id())
    event_type: str = Field(..., description="Type of event")
    event_version: int = Field(1, description="Event schema version")
    
    # Timing
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = Field(None, description="Event expiration time")
    
    # Source tracking
    source_service: str = Field(..., description="Service that created the event")
    source_version: str = Field(..., description="Version of source service")
    source_commit_hash: str = Field(..., description="Git commit of source service")
    
    # Causality tracking
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    causation_id: Optional[str] = Field(None, description="ID of event that caused this")
    sequence_number: Optional[int] = Field(None, description="Sequence in event stream")
    
    # Payload
    payload: Dict[str, Any] = Field(..., description="Event payload")
    
    # Idempotency
    idempotency_token: Optional[str] = Field(None, description="Client-provided token")
    
    def get_processing_key(self, consumer_id: str) -> str:
        """Get idempotency key for a specific consumer"""
        return f"{consumer_id}:{self.event_id}"
    
    def calculate_payload_hash(self) -> str:
        """Calculate hash of event payload"""
        import json
        payload_str = json.dumps(self.payload, sort_keys=True)
        return hashlib.sha256(payload_str.encode()).hexdigest()


class ConsumerState(BaseModel):
    """State tracking for idempotent consumer"""
    
    consumer_id: str = Field(..., description="Consumer identifier")
    consumer_version: str = Field(..., description="Consumer version")
    
    # Position tracking
    last_processed_event_id: Optional[str] = Field(None, description="Last successfully processed event")
    last_processed_timestamp: Optional[datetime] = Field(None, description="Timestamp of last processing")
    last_sequence_number: Optional[int] = Field(None, description="Last processed sequence number")
    
    # State hash
    state_commit_hash: str = Field(..., description="Current state commit hash")
    state_version: int = Field(0, description="State version number")
    
    # Processing stats
    events_processed: int = Field(0, description="Total events processed")
    events_skipped: int = Field(0, description="Events skipped (duplicates)")
    events_failed: int = Field(0, description="Events that failed processing")
    
    # Health tracking
    last_heartbeat: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_healthy: bool = Field(True, description="Consumer health status")
    error_count: int = Field(0, description="Consecutive error count")
    
    def update_position(self, event_id: str, sequence: Optional[int] = None):
        """Update processing position"""
        self.last_processed_event_id = event_id
        self.last_processed_timestamp = datetime.now(timezone.utc)
        if sequence is not None:
            self.last_sequence_number = sequence
        self.events_processed += 1


class IdempotentResult(BaseModel):
    """Result of idempotent processing"""
    
    # Processing outcome
    processed: bool = Field(..., description="Whether event was processed")
    was_duplicate: bool = Field(..., description="Whether event was already processed")
    
    # State transition
    previous_commit_hash: Optional[str] = Field(None, description="State before processing")
    new_commit_hash: Optional[str] = Field(None, description="State after processing")
    
    # Result data
    result: Optional[Dict[str, Any]] = Field(None, description="Processing result")
    side_effects: List[str] = Field(default_factory=list, description="Side effects executed")
    
    # Error handling
    error: Optional[str] = Field(None, description="Error message if failed")
    should_retry: bool = Field(False, description="Whether to retry processing")
    
    # Metadata
    processing_time_ms: int = Field(..., description="Processing duration")
    processor_version: str = Field(..., description="Version of processor")


class EventReplayRequest(BaseModel):
    """Request to replay events"""
    
    consumer_id: str = Field(..., description="Consumer to replay for")
    
    # Replay range
    from_event_id: Optional[str] = Field(None, description="Start from this event (exclusive)")
    to_event_id: Optional[str] = Field(None, description="End at this event (inclusive)")
    from_timestamp: Optional[datetime] = Field(None, description="Start from this time")
    to_timestamp: Optional[datetime] = Field(None, description="End at this time")
    
    # Replay options
    skip_side_effects: bool = Field(False, description="Skip external side effects")
    force_reprocess: bool = Field(False, description="Reprocess even if already processed")
    dry_run: bool = Field(False, description="Simulate replay without changes")
    
    # Filtering
    event_types: Optional[List[str]] = Field(None, description="Filter by event types")
    resource_ids: Optional[List[str]] = Field(None, description="Filter by resource IDs")


class ConsumerCheckpoint(BaseModel):
    """Checkpoint for consumer state"""
    
    consumer_id: str = Field(..., description="Consumer identifier")
    checkpoint_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Position
    event_id: str = Field(..., description="Event ID at checkpoint")
    sequence_number: Optional[int] = Field(None, description="Sequence number")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # State snapshot
    state_commit_hash: str = Field(..., description="State hash at checkpoint")
    state_data: Optional[Dict[str, Any]] = Field(None, description="Serialized state")
    
    # Metadata
    events_since_last: int = Field(..., description="Events processed since last checkpoint")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = Field(None, description="Checkpoint expiration")


# Helper functions

def generate_event_id() -> str:
    """Generate unique event ID"""
    return f"evt_{uuid.uuid4().hex[:12]}_{int(datetime.now().timestamp() * 1000)}"


def calculate_state_hash(state_data: Dict[str, Any]) -> str:
    """Calculate hash of consumer state"""
    import json
    state_str = json.dumps(state_data, sort_keys=True)
    return hashlib.sha256(state_str.encode()).hexdigest()


def is_event_expired(event: EventEnvelope) -> bool:
    """Check if event has expired"""
    if not event.expires_at:
        return False
    return datetime.now(timezone.utc) > event.expires_at