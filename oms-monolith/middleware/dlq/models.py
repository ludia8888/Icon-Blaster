"""
Dead Letter Queue data models
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List


class MessageStatus(Enum):
    """DLQ message status"""
    PENDING = "pending"
    PROCESSING = "processing"
    RETRYING = "retrying"
    FAILED = "failed"
    POISON = "poison"
    EXPIRED = "expired"
    COMPLETED = "completed"


class RetryStrategy(Enum):
    """Retry strategies for failed messages"""
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    FIXED_DELAY = "fixed_delay"
    IMMEDIATE = "immediate"
    CUSTOM = "custom"


@dataclass
class RetryConfig:
    """Retry configuration for DLQ messages"""
    max_retries: int = 3
    initial_delay_seconds: int = 60
    max_delay_seconds: int = 3600
    backoff_multiplier: float = 2.0
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF
    
    # Poison message detection
    poison_threshold: int = 5  # Mark as poison after this many failures
    
    # Message expiration
    ttl_seconds: int = 86400  # 24 hours
    
    # Batch processing
    batch_size: int = 10
    batch_timeout_seconds: int = 30


@dataclass
class DLQMessage:
    """Dead letter queue message"""
    id: str
    queue_name: str
    original_queue: str
    content: Dict[str, Any]
    error_message: str
    status: MessageStatus = MessageStatus.PENDING
    retry_count: int = 0
    
    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    next_retry_at: Optional[datetime] = None
    expired_at: Optional[datetime] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    error_history: List[Dict[str, Any]] = field(default_factory=list)
    
    # Deduplication
    content_hash: Optional[str] = None
    
    def add_error(self, error: str, details: Optional[Dict[str, Any]] = None):
        """Add error to history"""
        self.error_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "error": error,
            "details": details or {},
            "retry_count": self.retry_count
        })
        self.error_message = error
        self.updated_at = datetime.utcnow()
    
    def increment_retry(self):
        """Increment retry count"""
        self.retry_count += 1
        self.updated_at = datetime.utcnow()
    
    def mark_as_poison(self):
        """Mark message as poison"""
        self.status = MessageStatus.POISON
        self.updated_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "queue_name": self.queue_name,
            "original_queue": self.original_queue,
            "content": self.content,
            "error_message": self.error_message,
            "status": self.status.value,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
            "expired_at": self.expired_at.isoformat() if self.expired_at else None,
            "metadata": self.metadata,
            "error_history": self.error_history,
            "content_hash": self.content_hash
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DLQMessage":
        """Create from dictionary"""
        message = cls(
            id=data["id"],
            queue_name=data["queue_name"],
            original_queue=data["original_queue"],
            content=data["content"],
            error_message=data["error_message"],
            status=MessageStatus(data["status"]),
            retry_count=data["retry_count"]
        )
        
        # Parse timestamps
        message.created_at = datetime.fromisoformat(data["created_at"])
        message.updated_at = datetime.fromisoformat(data["updated_at"])
        
        if data.get("next_retry_at"):
            message.next_retry_at = datetime.fromisoformat(data["next_retry_at"])
        
        if data.get("expired_at"):
            message.expired_at = datetime.fromisoformat(data["expired_at"])
        
        # Set optional fields
        message.metadata = data.get("metadata", {})
        message.error_history = data.get("error_history", [])
        message.content_hash = data.get("content_hash")
        
        return message


@dataclass
class DLQMetrics:
    """Metrics for DLQ operations"""
    total_messages: int = 0
    pending_messages: int = 0
    processing_messages: int = 0
    failed_messages: int = 0
    poison_messages: int = 0
    expired_messages: int = 0
    completed_messages: int = 0
    
    # Retry metrics
    total_retries: int = 0
    successful_retries: int = 0
    failed_retries: int = 0
    
    # Performance metrics
    average_retry_time_ms: float = 0.0
    average_processing_time_ms: float = 0.0
    
    # Time window
    metrics_window_start: datetime = field(default_factory=datetime.utcnow)
    last_update: datetime = field(default_factory=datetime.utcnow)
    
    def update_status_count(self, status_counts: Dict[MessageStatus, int]):
        """Update status counts from dictionary"""
        self.pending_messages = status_counts.get(MessageStatus.PENDING, 0)
        self.processing_messages = status_counts.get(MessageStatus.PROCESSING, 0)
        self.failed_messages = status_counts.get(MessageStatus.FAILED, 0)
        self.poison_messages = status_counts.get(MessageStatus.POISON, 0)
        self.expired_messages = status_counts.get(MessageStatus.EXPIRED, 0)
        self.completed_messages = status_counts.get(MessageStatus.COMPLETED, 0)
        
        self.total_messages = sum(status_counts.values())
        self.last_update = datetime.utcnow()
    
    @property
    def success_rate(self) -> float:
        """Calculate retry success rate"""
        if self.total_retries == 0:
            return 0.0
        return (self.successful_retries / self.total_retries) * 100
    
    @property
    def poison_rate(self) -> float:
        """Calculate poison message rate"""
        if self.total_messages == 0:
            return 0.0
        return (self.poison_messages / self.total_messages) * 100