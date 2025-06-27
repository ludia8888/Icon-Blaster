"""
Shadow Index Models
Supports near-zero downtime indexing with atomic switch pattern
"""
from enum import Enum
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from uuid import uuid4


class ShadowIndexState(str, Enum):
    """Shadow index lifecycle states"""
    PREPARING = "PREPARING"           # Setting up shadow index
    BUILDING = "BUILDING"             # Building index in background
    BUILT = "BUILT"                   # Index build completed
    SWITCHING = "SWITCHING"           # Atomic switch in progress (< 10s)
    ACTIVE = "ACTIVE"                 # Switch completed, now primary
    FAILED = "FAILED"                 # Build or switch failed
    CANCELLED = "CANCELLED"           # Build cancelled
    CLEANUP = "CLEANUP"               # Cleaning up old index


class IndexType(str, Enum):
    """Types of indexes supported"""
    SEARCH_INDEX = "SEARCH_INDEX"           # Full-text search index
    GRAPH_INDEX = "GRAPH_INDEX"             # Graph relationship index
    SCHEMA_INDEX = "SCHEMA_INDEX"           # Schema metadata index
    VALIDATION_INDEX = "VALIDATION_INDEX"   # Data validation index


class ShadowIndexInfo(BaseModel):
    """Complete shadow index information"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    branch_name: str = Field(..., description="Branch being indexed")
    index_type: IndexType = Field(..., description="Type of index")
    resource_types: List[str] = Field(..., description="Resource types included")
    
    # State tracking
    state: ShadowIndexState = Field(ShadowIndexState.PREPARING)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    switched_at: Optional[datetime] = None
    
    # Service information
    service_name: str = Field(..., description="Service managing the index")
    service_instance_id: Optional[str] = None
    
    # Index metadata
    shadow_index_path: Optional[str] = None      # Path to shadow index
    current_index_path: Optional[str] = None     # Path to current index
    index_size_bytes: Optional[int] = None
    record_count: Optional[int] = None
    
    # Progress tracking
    build_progress_percent: int = Field(0, ge=0, le=100)
    estimated_completion_seconds: Optional[int] = None
    
    # Switch configuration
    max_switch_duration_seconds: int = Field(10, description="Maximum switch time allowed")
    switch_strategy: str = Field("ATOMIC_RENAME", description="Strategy for index switch")
    
    # Error handling
    error_message: Optional[str] = None
    retry_count: int = Field(0, description="Number of retries attempted")
    max_retries: int = Field(3, description="Maximum retries allowed")
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)


class ShadowIndexOperation(BaseModel):
    """Record of a shadow index operation"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    shadow_index_id: str
    operation_type: str  # BUILD_START, BUILD_PROGRESS, BUILD_COMPLETE, SWITCH_START, etc.
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    performed_by: str
    
    # Operation data
    from_state: Optional[ShadowIndexState] = None
    to_state: Optional[ShadowIndexState] = None
    progress_data: Optional[Dict[str, Any]] = None
    
    # Duration tracking
    duration_ms: Optional[int] = None
    
    # Result
    success: bool = True
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SwitchRequest(BaseModel):
    """Request to switch from shadow to primary index"""
    shadow_index_id: str
    force_switch: bool = Field(False, description="Force switch even if validation fails")
    validation_checks: List[str] = Field(default_factory=list)
    backup_current: bool = Field(True, description="Backup current index before switch")
    switch_timeout_seconds: int = Field(10, description="Maximum time allowed for switch")


class SwitchResult(BaseModel):
    """Result of index switch operation"""
    shadow_index_id: str
    success: bool
    switch_duration_ms: int
    
    # Pre-switch validation
    validation_passed: bool = True
    validation_errors: List[str] = Field(default_factory=list)
    
    # Switch details
    old_index_path: Optional[str] = None
    new_index_path: Optional[str] = None
    backup_path: Optional[str] = None
    
    # Post-switch verification
    verification_passed: bool = True
    verification_errors: List[str] = Field(default_factory=list)
    
    # Performance metrics
    index_size_change_bytes: Optional[int] = None
    query_performance_improvement: Optional[float] = None
    
    message: str = Field(..., description="Human-readable result message")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# State transition rules for shadow indexes
SHADOW_INDEX_TRANSITIONS = {
    ShadowIndexState.PREPARING: [
        ShadowIndexState.BUILDING, 
        ShadowIndexState.FAILED, 
        ShadowIndexState.CANCELLED
    ],
    ShadowIndexState.BUILDING: [
        ShadowIndexState.BUILT, 
        ShadowIndexState.FAILED, 
        ShadowIndexState.CANCELLED
    ],
    ShadowIndexState.BUILT: [
        ShadowIndexState.SWITCHING, 
        ShadowIndexState.FAILED, 
        ShadowIndexState.CANCELLED
    ],
    ShadowIndexState.SWITCHING: [
        ShadowIndexState.ACTIVE, 
        ShadowIndexState.FAILED
    ],
    ShadowIndexState.ACTIVE: [
        ShadowIndexState.CLEANUP
    ],
    ShadowIndexState.FAILED: [
        ShadowIndexState.PREPARING,  # Retry
        ShadowIndexState.CANCELLED
    ],
    ShadowIndexState.CANCELLED: [],  # Terminal state
    ShadowIndexState.CLEANUP: []     # Terminal state
}


def is_valid_shadow_transition(from_state: ShadowIndexState, to_state: ShadowIndexState) -> bool:
    """Check if a shadow index state transition is valid"""
    return to_state in SHADOW_INDEX_TRANSITIONS.get(from_state, [])


def get_switch_critical_states() -> List[ShadowIndexState]:
    """Get states where index switching requires lock"""
    return [ShadowIndexState.SWITCHING]


def estimate_switch_duration(index_size_bytes: Optional[int], strategy: str = "ATOMIC_RENAME") -> int:
    """Estimate switch duration in seconds based on index size and strategy"""
    if not index_size_bytes:
        return 5  # Default 5 seconds
    
    if strategy == "ATOMIC_RENAME":
        # Atomic rename is very fast regardless of size
        return min(3, max(1, index_size_bytes // (100 * 1024 * 1024)))  # 1-3 seconds
    elif strategy == "COPY_AND_REPLACE":
        # Copy strategy takes longer
        return min(30, max(5, index_size_bytes // (50 * 1024 * 1024)))  # 5-30 seconds
    else:
        return 10  # Default 10 seconds