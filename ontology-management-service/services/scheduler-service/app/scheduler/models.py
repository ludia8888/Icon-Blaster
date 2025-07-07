"""Data models for scheduler service."""

from datetime import datetime
from typing import Dict, List, Optional, Any, Union
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict


class JobStatus(str, Enum):
    """Job status enum."""
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"
    ERROR = "error"


class ExecutionStatus(str, Enum):
    """Execution status enum."""
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    MISSED = "missed"


class CronSchedule(BaseModel):
    """Cron-based schedule."""
    cron_expression: str = Field(..., description="Cron expression (e.g., '0 0 * * *')")
    timezone: str = Field(default="UTC", description="Timezone for cron execution")


class IntervalSchedule(BaseModel):
    """Interval-based schedule."""
    interval_seconds: int = Field(..., gt=0, description="Interval in seconds")
    start_time: Optional[datetime] = Field(default=None, description="Start time for interval")


class OneTimeSchedule(BaseModel):
    """One-time schedule."""
    run_at: datetime = Field(..., description="Exact time to run the job")


class JobConfig(BaseModel):
    """Job configuration."""
    job_type: str = Field(..., description="Type of job to execute")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Job parameters")
    max_retries: int = Field(default=3, ge=0, description="Maximum retry attempts")
    retry_delay_seconds: int = Field(default=60, gt=0, description="Delay between retries")
    timeout_seconds: int = Field(default=300, gt=0, description="Job execution timeout")
    tags: List[str] = Field(default_factory=list, description="Job tags for filtering")


class Job(BaseModel):
    """Scheduled job model."""
    id: Optional[str] = Field(default=None, description="Job ID")
    name: str = Field(..., description="Job name")
    description: Optional[str] = Field(default=None, description="Job description")
    
    # Schedule can be one of three types
    schedule: Union[CronSchedule, IntervalSchedule, OneTimeSchedule] = Field(
        ..., description="Job schedule configuration"
    )
    
    config: JobConfig = Field(..., description="Job execution configuration")
    
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    updated_at: datetime = Field(default_factory=lambda: datetime.utcnow())
    enabled: bool = Field(default=True, description="Whether job is enabled")
    status: JobStatus = Field(default=JobStatus.ACTIVE, description="Job status")
    
    next_run_time: Optional[datetime] = Field(default=None, description="Next scheduled run")
    last_run_time: Optional[datetime] = Field(default=None, description="Last execution time")
    
    class Config:
        use_enum_values = True


class JobExecution(BaseModel):
    """Job execution record."""
    id: str = Field(..., description="Execution ID")
    job_id: str = Field(..., description="Parent job ID")
    started_at: datetime = Field(..., description="Execution start time")
    finished_at: Optional[datetime] = Field(default=None, description="Execution end time")
    status: ExecutionStatus = Field(..., description="Execution status")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
    result: Optional[Dict[str, Any]] = Field(default=None, description="Execution result")
    retry_count: int = Field(default=0, description="Number of retry attempts")
    
    class Config:
        use_enum_values = True


# Request/Response models for API
class CreateJobRequest(BaseModel):
    """Create job request."""
    job: Job


class UpdateJobRequest(BaseModel):
    """Update job request."""
    job: Job


class ListJobsRequest(BaseModel):
    """List jobs request."""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)
    tags: Optional[List[str]] = None
    status: Optional[JobStatus] = None
    enabled_only: bool = False


class RunJobRequest(BaseModel):
    """Run job request."""
    override_parameters: Optional[Dict[str, Any]] = None


class JobHistoryRequest(BaseModel):
    """Job history request."""
    limit: int = Field(default=50, ge=1, le=100)
    status_filter: Optional[ExecutionStatus] = None