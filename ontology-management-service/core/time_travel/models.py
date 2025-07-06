"""
Time Travel Query Models
Models for temporal queries and point-in-time data access
"""
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from pydantic import BaseModel, Field, validator
from enum import Enum


class TemporalOperator(str, Enum):
    """Temporal query operators"""
    AS_OF = "AS_OF"
    BETWEEN = "BETWEEN"
    FROM_TO = "FROM_TO"
    ALL_VERSIONS = "ALL_VERSIONS"
    BEFORE = "BEFORE"
    AFTER = "AFTER"


class TemporalReference(BaseModel):
    """Reference to a point in time"""
    
    # Different ways to specify time
    timestamp: Optional[datetime] = Field(None, description="Specific timestamp")
    version: Optional[int] = Field(None, description="Specific version number")
    commit_hash: Optional[str] = Field(None, description="Specific commit hash")
    relative_time: Optional[str] = Field(None, description="Relative time like '-1h', '-7d'")
    
    @validator('relative_time')
    def validate_relative_time(cls, v):
        if v:
            # Validate format like -1h, -7d, -30m
            import re
            if not re.match(r'^-\d+[hdmw]$', v):
                raise ValueError("Relative time must be in format like '-1h', '-7d', '-30m', '-1w'")
        return v
    
    def to_timestamp(self, base_time: Optional[datetime] = None) -> datetime:
        """Convert temporal reference to timestamp"""
        if self.timestamp:
            return self.timestamp
        
        if self.relative_time:
            from datetime import timedelta
            base = base_time or datetime.utcnow()
            
            # Parse relative time
            import re
            match = re.match(r'^-(\d+)([hdmw])$', self.relative_time)
            if match:
                amount = int(match.group(1))
                unit = match.group(2)
                
                if unit == 'h':
                    delta = timedelta(hours=amount)
                elif unit == 'd':
                    delta = timedelta(days=amount)
                elif unit == 'm':
                    delta = timedelta(minutes=amount)
                elif unit == 'w':
                    delta = timedelta(weeks=amount)
                
                return base - delta
        
        raise ValueError("No valid temporal reference provided")


class TemporalQuery(BaseModel):
    """Temporal query specification"""
    
    operator: TemporalOperator = Field(..., description="Temporal operator")
    
    # Time references
    point_in_time: Optional[TemporalReference] = Field(None, description="Single point in time")
    start_time: Optional[TemporalReference] = Field(None, description="Start of time range")
    end_time: Optional[TemporalReference] = Field(None, description="End of time range")
    
    # Query options
    include_deleted: bool = Field(False, description="Include deleted resources")
    include_metadata: bool = Field(True, description="Include version metadata")
    
    @validator('point_in_time')
    def validate_point_in_time(cls, v, values):
        operator = values.get('operator')
        if operator in [TemporalOperator.AS_OF, TemporalOperator.BEFORE, TemporalOperator.AFTER]:
            if not v:
                raise ValueError(f"point_in_time required for {operator} operator")
        return v
    
    @validator('start_time')
    def validate_start_time(cls, v, values):
        operator = values.get('operator')
        if operator in [TemporalOperator.BETWEEN, TemporalOperator.FROM_TO]:
            if not v:
                raise ValueError(f"start_time required for {operator} operator")
        return v


class TemporalResourceQuery(BaseModel):
    """Query for temporal resource data"""
    
    resource_type: str = Field(..., description="Type of resource")
    resource_id: Optional[str] = Field(None, description="Specific resource ID")
    branch: str = Field("main", description="Branch to query")
    
    temporal: TemporalQuery = Field(..., description="Temporal query specification")
    
    # Filters
    filters: Optional[Dict[str, Any]] = Field(None, description="Additional filters")
    
    # Pagination
    limit: int = Field(100, ge=1, le=1000, description="Maximum results")
    offset: int = Field(0, ge=0, description="Offset for pagination")


class TemporalJoinQuery(BaseModel):
    """Temporal join between resources"""
    
    left_resource: TemporalResourceQuery = Field(..., description="Left side of join")
    right_resource: TemporalResourceQuery = Field(..., description="Right side of join")
    
    join_condition: Dict[str, str] = Field(..., description="Join fields mapping")
    join_type: str = Field("inner", description="Join type: inner, left, right, full")
    
    # Temporal alignment
    temporal_alignment: str = Field("same_time", description="How to align time: same_time, latest, earliest")


class TemporalResourceVersion(BaseModel):
    """Resource at a specific point in time"""
    
    # Resource identification
    resource_type: str
    resource_id: str
    branch: str
    
    # Version information
    version: int
    commit_hash: str
    valid_time: datetime
    
    # Content
    content: Dict[str, Any]
    
    # Metadata
    modified_by: str
    change_type: str
    change_summary: Optional[str] = None
    
    # Temporal metadata
    next_version: Optional[int] = None
    previous_version: Optional[int] = None
    version_duration: Optional[float] = None  # Seconds this version was active


class TemporalQueryResult(BaseModel):
    """Result of temporal query"""
    
    query: TemporalResourceQuery
    execution_time_ms: float
    
    # Results
    resources: List[TemporalResourceVersion]
    total_count: int
    has_more: bool
    
    # Temporal metadata
    time_range_covered: Optional[Dict[str, datetime]] = None
    versions_scanned: int = 0
    
    # Cache info
    cache_hit: bool = False
    cacheable: bool = True


class TemporalDiff(BaseModel):
    """Difference between two temporal states"""
    
    resource_type: str
    resource_id: str
    
    # Time references
    from_time: TemporalReference
    to_time: TemporalReference
    
    # Version info
    from_version: Optional[int] = None
    to_version: Optional[int] = None
    
    # Changes
    operation: str  # created, updated, deleted, unchanged
    changes: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Statistics
    fields_added: int = 0
    fields_removed: int = 0
    fields_modified: int = 0


class TemporalSnapshot(BaseModel):
    """Snapshot of entire system at a point in time"""
    
    branch: str
    timestamp: datetime
    commit_hash: Optional[str] = None
    
    # Resource counts by type
    resource_counts: Dict[str, int]
    
    # Total statistics
    total_resources: int
    total_versions: int
    
    # Snapshot data
    resources: Optional[Dict[str, List[Dict[str, Any]]]] = None
    
    # Metadata
    created_at: datetime
    created_by: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class TemporalComparisonQuery(BaseModel):
    """Query to compare states at different times"""
    
    resource_types: List[str] = Field(..., description="Resource types to compare")
    branch: str = Field("main", description="Branch to compare")
    
    # Time points to compare
    time1: TemporalReference
    time2: TemporalReference
    
    # Options
    include_unchanged: bool = Field(False, description="Include unchanged resources")
    detailed_diff: bool = Field(True, description="Include field-level differences")
    
    # Filters
    filters: Optional[Dict[str, Any]] = None


class TemporalComparisonResult(BaseModel):
    """Result of temporal comparison"""
    
    query: TemporalComparisonQuery
    execution_time_ms: float
    
    # Time information
    time1_resolved: datetime
    time2_resolved: datetime
    
    # Differences by resource type
    differences: Dict[str, List[TemporalDiff]]
    
    # Summary statistics
    total_created: int = 0
    total_updated: int = 0
    total_deleted: int = 0
    total_unchanged: int = 0
    
    # Cache info
    cache_hit: bool = False


class TimelineEvent(BaseModel):
    """Event in resource timeline"""
    
    timestamp: datetime
    version: int
    commit_hash: str
    
    event_type: str  # created, updated, deleted, renamed
    description: str
    
    modified_by: str
    change_summary: Optional[str] = None
    
    # Changed fields
    fields_changed: List[str] = Field(default_factory=list)
    
    # Related events
    related_resources: List[Dict[str, str]] = Field(default_factory=list)


class ResourceTimeline(BaseModel):
    """Complete timeline for a resource"""
    
    resource_type: str
    resource_id: str
    branch: str
    
    # Timeline
    events: List[TimelineEvent]
    
    # Lifecycle
    created_at: datetime
    last_modified_at: datetime
    deleted_at: Optional[datetime] = None
    
    # Statistics
    total_versions: int
    total_updates: int
    unique_contributors: List[str]
    
    # Activity metrics
    most_active_period: Optional[Dict[str, Any]] = None
    average_time_between_changes: Optional[float] = None