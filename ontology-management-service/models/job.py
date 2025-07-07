"""
Job Model for Asynchronous Task Processing
Handles background job tracking for merge operations and other long-running tasks
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict
import uuid


class JobStatus(str, Enum):
    """Job execution status"""
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"


class JobType(str, Enum):
    """Supported job types"""
    BRANCH_MERGE = "branch_merge"
    SCHEMA_VALIDATION = "schema_validation"
    BULK_IMPORT = "bulk_import"
    BRANCH_REBASE = "branch_rebase"
    BRANCH_SQUASH = "branch_squash"


class JobPriority(int, Enum):
    """Job priority levels"""
    LOW = 0
    NORMAL = 5
    HIGH = 10
    CRITICAL = 15


class JobMetadata(BaseModel):
    """Job-specific metadata"""
    proposal_id: Optional[str] = None
    source_branch: Optional[str] = None
    target_branch: Optional[str] = None
    merge_strategy: Optional[str] = None
    conflict_resolutions: Optional[Dict[str, Any]] = None
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    error_stack: Optional[str] = None


class JobProgress(BaseModel):
    """Progress tracking for long-running jobs"""
    current_step: str = ""
    total_steps: int = 0
    completed_steps: int = 0
    percentage: float = 0.0
    message: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)


class Job(BaseModel):
    """Job model for tracking asynchronous operations"""
    model_config = ConfigDict(
        use_enum_values=True,
        json_encoders={
            datetime: lambda v: v.isoformat() if v else None
        }
    )
    
    id: str = Field(default_factory=lambda: f"job_{uuid.uuid4()}")
    type: JobType
    status: JobStatus = JobStatus.QUEUED
    priority: JobPriority = JobPriority.NORMAL
    
    # Tracking
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    # User context
    created_by: str
    tenant_id: Optional[str] = None
    
    # Job data
    metadata: JobMetadata = Field(default_factory=JobMetadata)
    progress: JobProgress = Field(default_factory=JobProgress)
    result: Optional[Dict[str, Any]] = None
    
    # Queue management
    queue_name: str = "default"
    celery_task_id: Optional[str] = None
    scheduled_for: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    
    # Idempotency
    idempotency_key: Optional[str] = None
    
    def is_terminal(self) -> bool:
        """Check if job is in terminal state"""
        return self.status in [
            JobStatus.COMPLETED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.DEAD_LETTER
        ]
    
    def can_retry(self) -> bool:
        """Check if job can be retried"""
        return (
            self.status == JobStatus.FAILED and
            self.metadata.retry_count < self.metadata.max_retries
        )
    
    def duration_seconds(self) -> Optional[float]:
        """Calculate job duration in seconds"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


class JobUpdate(BaseModel):
    """Model for job updates"""
    status: Optional[JobStatus] = None
    progress: Optional[JobProgress] = None
    metadata: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    error_stack: Optional[str] = None


class JobFilter(BaseModel):
    """Filters for job queries"""
    status: Optional[List[JobStatus]] = None
    type: Optional[List[JobType]] = None
    created_by: Optional[str] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    tenant_id: Optional[str] = None
    include_expired: bool = False


class JobStats(BaseModel):
    """Job statistics"""
    total: int = 0
    queued: int = 0
    in_progress: int = 0
    completed: int = 0
    failed: int = 0
    retry_rate: float = 0.0
    avg_duration_seconds: float = 0.0
    by_type: Dict[str, int] = Field(default_factory=dict)