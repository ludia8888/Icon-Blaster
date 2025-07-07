"""
Branch State Management
Defines branch states and lock mechanisms for data integrity
"""
from enum import Enum
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from uuid import UUID, uuid4


class BranchState(str, Enum):
    """
    Branch state for managing schema freeze and data integrity
    
    State Transitions:
    ACTIVE -> LOCKED_FOR_WRITE (when indexing starts)
    LOCKED_FOR_WRITE -> READY (when indexing completes)
    READY -> ACTIVE (after merge or timeout)
    ACTIVE -> ARCHIVED (when branch is deleted)
    """
    ACTIVE = "ACTIVE"                    # Normal operation, read/write allowed
    LOCKED_FOR_WRITE = "LOCKED_FOR_WRITE"  # Indexing in progress, read-only
    READY = "READY"                      # Indexing complete, ready for merge
    MERGED = "MERGED"                    # Branch has been successfully merged
    FAILED = "FAILED"                    # An operation on the branch failed
    ARCHIVED = "ARCHIVED"                # Branch deleted, historical record
    ERROR = "ERROR"                      # Error state, requires manual intervention


class LockType(str, Enum):
    """Types of locks that can be applied"""
    INDEXING = "INDEXING"               # Lock during Funnel Service indexing
    MIGRATION = "MIGRATION"             # Lock during schema migration
    BACKUP = "BACKUP"                   # Lock during backup operations
    MAINTENANCE = "MAINTENANCE"         # Lock during maintenance
    MANUAL = "MANUAL"                   # Manual lock by administrator


class LockScope(str, Enum):
    """Scope of the lock"""
    BRANCH = "BRANCH"                   # Entire branch locked
    RESOURCE_TYPE = "RESOURCE_TYPE"     # Specific resource type locked
    RESOURCE = "RESOURCE"               # Individual resource locked


class BranchLock(BaseModel):
    """
    Represents a lock on a branch or resource
    """
    id: str = Field(..., description="Unique lock ID")
    branch_name: str = Field(..., description="Branch being locked")
    lock_type: LockType = Field(..., description="Type of lock")
    lock_scope: LockScope = Field(..., description="Scope of the lock")
    
    # Optional resource targeting
    resource_type: Optional[str] = Field(None, description="Specific resource type if scoped")
    resource_id: Optional[str] = Field(None, description="Specific resource ID if scoped")
    
    # Lock metadata
    locked_by: str = Field(..., description="User or service that created the lock")
    locked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = Field(None, description="When lock expires")
    reason: str = Field(..., description="Reason for the lock")
    
    # State tracking
    is_active: bool = Field(True, description="Whether lock is currently active")
    released_at: Optional[datetime] = Field(None, description="When lock was released")
    released_by: Optional[str] = Field(None, description="Who released the lock")
    
    # TTL & Heartbeat support
    heartbeat_interval: int = Field(60, description="Heartbeat interval in seconds")
    last_heartbeat: Optional[datetime] = Field(None, description="Last heartbeat timestamp")
    heartbeat_source: Optional[str] = Field(None, description="Service/process sending heartbeats")
    auto_release_enabled: bool = Field(True, description="Whether lock can be auto-released on expiry")
    
    # Additional context
    metadata: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)


class BranchStateInfo(BaseModel):
    """
    Complete branch state information including locks
    """
    branch_name: str
    current_state: BranchState
    previous_state: Optional[BranchState] = None
    
    # State change tracking
    state_changed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    state_changed_by: str = Field(..., description="User or service that changed state")
    state_change_reason: str = Field(..., description="Reason for state change")
    
    # Active locks
    active_locks: List[BranchLock] = Field(default_factory=list)
    
    # Indexing metadata
    indexing_started_at: Optional[datetime] = None
    indexing_completed_at: Optional[datetime] = None
    indexing_service: Optional[str] = None  # e.g., "funnel-service"
    
    # Auto-merge configuration
    auto_merge_enabled: bool = Field(False, description="Whether auto-merge is enabled")
    auto_merge_conditions: List[str] = Field(default_factory=list)
    
    # Additional metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @property
    def is_write_locked(self) -> bool:
        """Check if branch is locked for write operations"""
        return (
            self.current_state == BranchState.LOCKED_FOR_WRITE or
            any(lock.is_active and lock.lock_scope in [LockScope.BRANCH] for lock in self.active_locks)
        )
    
    @property
    def is_ready_for_merge(self) -> bool:
        """Check if branch is ready for merge"""
        return (
            self.current_state == BranchState.READY and
            not self.is_write_locked and
            self.indexing_completed_at is not None
        )
    
    def can_perform_action(self, action: str, resource_type: Optional[str] = None) -> tuple[bool, str]:
        """
        Check if a specific action can be performed on the branch
        
        Args:
            action: Action to perform (read, write, delete, etc.)
            resource_type: Optional resource type for scoped checks
            
        Returns:
            Tuple of (can_perform, reason_if_not)
        """
        if action == "read":
            # Read operations are always allowed
            return True, "Read operations always allowed"
        
        if self.current_state == BranchState.ARCHIVED:
            return False, "Branch is archived"
        
        if self.current_state == BranchState.ERROR:
            return False, "Branch is in error state"
        
        if action in ["write", "update", "delete", "create"]:
            if self.current_state == BranchState.LOCKED_FOR_WRITE:
                return False, f"Branch is locked for write operations: {self.state_change_reason}"
            
            # Check for specific resource locks (filter out expired locks)
            now = datetime.now(timezone.utc)
            for lock in self.active_locks:
                if not lock.is_active:
                    continue
                
                # Skip expired locks (they should be cleaned up automatically)
                if lock.expires_at and now > lock.expires_at:
                    continue
                
                # Skip locks that missed too many heartbeats (if heartbeat is enabled)
                if (lock.last_heartbeat and lock.heartbeat_interval and
                    (now - lock.last_heartbeat).total_seconds() > lock.heartbeat_interval * 3):
                    continue
                
                if lock.lock_scope == LockScope.BRANCH:
                    return False, f"Branch is locked: {lock.reason}"
                
                if (lock.lock_scope == LockScope.RESOURCE_TYPE and 
                    lock.resource_type == resource_type):
                    return False, f"Resource type {resource_type} is locked: {lock.reason}"
        
        return True, "Action allowed"


class BranchStateTransition(BaseModel):
    """Record of a branch state transition"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    branch_name: str
    from_state: BranchState
    to_state: BranchState
    transitioned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    transitioned_by: str
    reason: str
    trigger: str  # What triggered the transition (indexing_start, indexing_complete, manual, etc.)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class HeartbeatRecord(BaseModel):
    """Record of a lock heartbeat"""
    lock_id: str
    branch_name: str
    service_name: str
    heartbeat_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = Field(default="healthy", description="Status of the service (healthy, warning, error)")
    progress_info: Optional[Dict[str, Any]] = Field(None, description="Progress information if available")
    metadata: Dict[str, Any] = Field(default_factory=dict)


# State transition rules
VALID_STATE_TRANSITIONS = {
    BranchState.ACTIVE: [BranchState.LOCKED_FOR_WRITE, BranchState.ARCHIVED, BranchState.ERROR],
    BranchState.LOCKED_FOR_WRITE: [BranchState.READY, BranchState.ACTIVE, BranchState.ERROR],
    BranchState.READY: [BranchState.ACTIVE, BranchState.ARCHIVED],
    BranchState.ARCHIVED: [],  # Terminal state
    BranchState.ERROR: [BranchState.ACTIVE, BranchState.LOCKED_FOR_WRITE]  # Manual recovery
}


def is_valid_transition(from_state: BranchState, to_state: BranchState) -> bool:
    """Check if a state transition is valid"""
    return to_state in VALID_STATE_TRANSITIONS.get(from_state, [])


def get_auto_merge_conditions() -> List[str]:
    """Get list of conditions that must be met for auto-merge"""
    return [
        "indexing_completed",
        "no_conflicts",
        "all_tests_passed",
        "approval_received"  # If approval workflow is enabled
    ]


def is_lock_expired_by_ttl(lock: "BranchLock") -> bool:
    """Check if a lock is expired based on TTL"""
    if not lock.expires_at:
        return False
    return datetime.now(timezone.utc) > lock.expires_at


def is_lock_expired_by_heartbeat(lock: "BranchLock") -> bool:
    """Check if a lock is expired due to missed heartbeats"""
    if not lock.last_heartbeat or not lock.heartbeat_interval:
        return False
    
    max_missed_heartbeats = 3
    heartbeat_timeout = lock.heartbeat_interval * max_missed_heartbeats
    elapsed = (datetime.now(timezone.utc) - lock.last_heartbeat).total_seconds()
    
    return elapsed > heartbeat_timeout