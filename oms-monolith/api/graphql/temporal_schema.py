"""
GraphQL Schema for Time Travel Queries
Temporal query types and resolvers for point-in-time data access
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
import strawberry
from strawberry.types import Info

from core.time_travel import (
    TemporalOperator as CoreTemporalOperator,
    TemporalReference as CoreTemporalReference,
    TemporalQuery as CoreTemporalQuery,
    TemporalResourceQuery as CoreTemporalResourceQuery,
    TemporalResourceVersion as CoreTemporalResourceVersion,
    TemporalQueryResult as CoreTemporalQueryResult,
    TemporalDiff as CoreTemporalDiff,
    TemporalComparisonQuery as CoreTemporalComparisonQuery,
    TemporalComparisonResult as CoreTemporalComparisonResult,
    ResourceTimeline as CoreResourceTimeline,
    TimelineEvent as CoreTimelineEvent,
    get_time_travel_service
)


@strawberry.enum
class TemporalOperator:
    """Temporal query operators"""
    AS_OF = "AS_OF"
    BETWEEN = "BETWEEN"
    FROM_TO = "FROM_TO"
    ALL_VERSIONS = "ALL_VERSIONS"
    BEFORE = "BEFORE"
    AFTER = "AFTER"


@strawberry.input
class TemporalReferenceInput:
    """Input for temporal reference"""
    timestamp: Optional[datetime] = None
    version: Optional[int] = None
    commit_hash: Optional[str] = None
    relative_time: Optional[str] = None  # e.g., "-1h", "-7d"


@strawberry.input
class TemporalQueryInput:
    """Input for temporal query specification"""
    operator: TemporalOperator
    point_in_time: Optional[TemporalReferenceInput] = None
    start_time: Optional[TemporalReferenceInput] = None
    end_time: Optional[TemporalReferenceInput] = None
    include_deleted: bool = False
    include_metadata: bool = True


@strawberry.input
class TemporalResourceQueryInput:
    """Input for temporal resource query"""
    resource_type: str
    resource_id: Optional[str] = None
    branch: str = "main"
    temporal: TemporalQueryInput
    filters: Optional[strawberry.scalars.JSON] = None
    limit: int = 100
    offset: int = 0


@strawberry.input
class TemporalComparisonInput:
    """Input for temporal comparison"""
    resource_types: List[str]
    branch: str = "main"
    time1: TemporalReferenceInput
    time2: TemporalReferenceInput
    include_unchanged: bool = False
    detailed_diff: bool = True
    filters: Optional[strawberry.scalars.JSON] = None


@strawberry.type
class TemporalResourceVersion:
    """Resource at a specific point in time"""
    resource_type: str
    resource_id: str
    branch: str
    version: int
    commit_hash: str
    valid_time: datetime
    content: strawberry.scalars.JSON
    modified_by: str
    change_type: str
    change_summary: Optional[str] = None
    next_version: Optional[int] = None
    previous_version: Optional[int] = None
    version_duration: Optional[float] = None


@strawberry.type
class TemporalQueryResult:
    """Result of temporal query"""
    resources: List[TemporalResourceVersion]
    total_count: int
    has_more: bool
    execution_time_ms: float
    time_range_covered: Optional[strawberry.scalars.JSON] = None
    versions_scanned: int = 0
    cache_hit: bool = False


@strawberry.type
class TemporalDiff:
    """Difference between two temporal states"""
    resource_type: str
    resource_id: str
    operation: str  # created, updated, deleted, unchanged
    from_version: Optional[int] = None
    to_version: Optional[int] = None
    changes: List[strawberry.scalars.JSON] = strawberry.field(default_factory=list)
    fields_added: int = 0
    fields_removed: int = 0
    fields_modified: int = 0


@strawberry.type
class TemporalComparisonResult:
    """Result of temporal comparison"""
    time1_resolved: datetime
    time2_resolved: datetime
    differences: strawberry.scalars.JSON  # Dict[str, List[TemporalDiff]]
    total_created: int = 0
    total_updated: int = 0
    total_deleted: int = 0
    total_unchanged: int = 0
    execution_time_ms: float
    cache_hit: bool = False


@strawberry.type
class TimelineEvent:
    """Event in resource timeline"""
    timestamp: datetime
    version: int
    commit_hash: str
    event_type: str
    description: str
    modified_by: str
    change_summary: Optional[str] = None
    fields_changed: List[str] = strawberry.field(default_factory=list)
    related_resources: List[strawberry.scalars.JSON] = strawberry.field(default_factory=list)


@strawberry.type
class ResourceTimeline:
    """Complete timeline for a resource"""
    resource_type: str
    resource_id: str
    branch: str
    events: List[TimelineEvent]
    created_at: datetime
    last_modified_at: datetime
    deleted_at: Optional[datetime] = None
    total_versions: int
    total_updates: int
    unique_contributors: List[str]
    average_time_between_changes: Optional[float] = None


@strawberry.type
class TemporalSnapshot:
    """Snapshot of system at point in time"""
    branch: str
    timestamp: datetime
    commit_hash: Optional[str] = None
    resource_counts: strawberry.scalars.JSON
    total_resources: int
    total_versions: int
    resources: Optional[strawberry.scalars.JSON] = None
    created_at: datetime
    created_by: str
    description: Optional[str] = None
    tags: List[str] = strawberry.field(default_factory=list)


# Query extensions
@strawberry.type
class TemporalQueries:
    """Time travel related queries"""
    
    @strawberry.field
    async def temporal_query(
        self,
        info: Info,
        query: TemporalResourceQueryInput
    ) -> TemporalQueryResult:
        """Execute temporal query for resources"""
        service = await get_time_travel_service()
        
        # Convert input to core models
        temporal_ref = None
        if query.temporal.point_in_time:
            temporal_ref = CoreTemporalReference(
                timestamp=query.temporal.point_in_time.timestamp,
                version=query.temporal.point_in_time.version,
                commit_hash=query.temporal.point_in_time.commit_hash,
                relative_time=query.temporal.point_in_time.relative_time
            )
        
        start_ref = None
        if query.temporal.start_time:
            start_ref = CoreTemporalReference(
                timestamp=query.temporal.start_time.timestamp,
                version=query.temporal.start_time.version,
                commit_hash=query.temporal.start_time.commit_hash,
                relative_time=query.temporal.start_time.relative_time
            )
        
        end_ref = None
        if query.temporal.end_time:
            end_ref = CoreTemporalReference(
                timestamp=query.temporal.end_time.timestamp,
                version=query.temporal.end_time.version,
                commit_hash=query.temporal.end_time.commit_hash,
                relative_time=query.temporal.end_time.relative_time
            )
        
        core_temporal = CoreTemporalQuery(
            operator=CoreTemporalOperator(query.temporal.operator.value),
            point_in_time=temporal_ref,
            start_time=start_ref,
            end_time=end_ref,
            include_deleted=query.temporal.include_deleted,
            include_metadata=query.temporal.include_metadata
        )
        
        core_query = CoreTemporalResourceQuery(
            resource_type=query.resource_type,
            resource_id=query.resource_id,
            branch=query.branch,
            temporal=core_temporal,
            filters=query.filters,
            limit=query.limit,
            offset=query.offset
        )
        
        # Execute appropriate query based on operator
        if core_temporal.operator == CoreTemporalOperator.AS_OF:
            result = await service.query_as_of(core_query)
        elif core_temporal.operator in [CoreTemporalOperator.BETWEEN, CoreTemporalOperator.FROM_TO]:
            result = await service.query_between(core_query)
        elif core_temporal.operator == CoreTemporalOperator.ALL_VERSIONS:
            result = await service.query_all_versions(core_query)
        else:
            raise ValueError(f"Unsupported temporal operator: {core_temporal.operator}")
        
        # Convert result to GraphQL types
        return TemporalQueryResult(
            resources=[
                TemporalResourceVersion(
                    resource_type=r.resource_type,
                    resource_id=r.resource_id,
                    branch=r.branch,
                    version=r.version,
                    commit_hash=r.commit_hash,
                    valid_time=r.valid_time,
                    content=r.content,
                    modified_by=r.modified_by,
                    change_type=r.change_type,
                    change_summary=r.change_summary,
                    next_version=r.next_version,
                    previous_version=r.previous_version,
                    version_duration=r.version_duration
                ) for r in result.resources
            ],
            total_count=result.total_count,
            has_more=result.has_more,
            execution_time_ms=result.execution_time_ms,
            time_range_covered=result.time_range_covered,
            versions_scanned=result.versions_scanned,
            cache_hit=result.cache_hit
        )
    
    @strawberry.field
    async def temporal_comparison(
        self,
        info: Info,
        comparison: TemporalComparisonInput
    ) -> TemporalComparisonResult:
        """Compare states at different times"""
        service = await get_time_travel_service()
        
        # Convert input
        time1_ref = CoreTemporalReference(
            timestamp=comparison.time1.timestamp,
            version=comparison.time1.version,
            commit_hash=comparison.time1.commit_hash,
            relative_time=comparison.time1.relative_time
        )
        
        time2_ref = CoreTemporalReference(
            timestamp=comparison.time2.timestamp,
            version=comparison.time2.version,
            commit_hash=comparison.time2.commit_hash,
            relative_time=comparison.time2.relative_time
        )
        
        core_comparison = CoreTemporalComparisonQuery(
            resource_types=comparison.resource_types,
            branch=comparison.branch,
            time1=time1_ref,
            time2=time2_ref,
            include_unchanged=comparison.include_unchanged,
            detailed_diff=comparison.detailed_diff,
            filters=comparison.filters
        )
        
        result = await service.compare_temporal_states(core_comparison)
        
        # Convert differences to GraphQL format
        differences_dict = {}
        for resource_type, diffs in result.differences.items():
            differences_dict[resource_type] = [
                {
                    "resource_type": d.resource_type,
                    "resource_id": d.resource_id,
                    "operation": d.operation,
                    "from_version": d.from_version,
                    "to_version": d.to_version,
                    "changes": d.changes,
                    "fields_added": d.fields_added,
                    "fields_removed": d.fields_removed,
                    "fields_modified": d.fields_modified
                } for d in diffs
            ]
        
        return TemporalComparisonResult(
            time1_resolved=result.time1_resolved,
            time2_resolved=result.time2_resolved,
            differences=differences_dict,
            total_created=result.total_created,
            total_updated=result.total_updated,
            total_deleted=result.total_deleted,
            total_unchanged=result.total_unchanged,
            execution_time_ms=result.execution_time_ms,
            cache_hit=result.cache_hit
        )
    
    @strawberry.field
    async def resource_timeline(
        self,
        info: Info,
        resource_type: str,
        resource_id: str,
        branch: str = "main"
    ) -> ResourceTimeline:
        """Get complete timeline for a resource"""
        service = await get_time_travel_service()
        
        result = await service.get_resource_timeline(
            resource_type, resource_id, branch
        )
        
        return ResourceTimeline(
            resource_type=result.resource_type,
            resource_id=result.resource_id,
            branch=result.branch,
            events=[
                TimelineEvent(
                    timestamp=e.timestamp,
                    version=e.version,
                    commit_hash=e.commit_hash,
                    event_type=e.event_type,
                    description=e.description,
                    modified_by=e.modified_by,
                    change_summary=e.change_summary,
                    fields_changed=e.fields_changed,
                    related_resources=e.related_resources
                ) for e in result.events
            ],
            created_at=result.created_at,
            last_modified_at=result.last_modified_at,
            deleted_at=result.deleted_at,
            total_versions=result.total_versions,
            total_updates=result.total_updates,
            unique_contributors=result.unique_contributors,
            average_time_between_changes=result.average_time_between_changes
        )
    
    @strawberry.field
    async def temporal_snapshot(
        self,
        info: Info,
        branch: str,
        timestamp: datetime,
        include_data: bool = False
    ) -> TemporalSnapshot:
        """Get snapshot of system at specific time"""
        service = await get_time_travel_service()
        
        # Get current user from context
        user = info.context.get("user", {"username": "system"})
        
        result = await service.create_temporal_snapshot(
            branch=branch,
            timestamp=timestamp,
            created_by=user.get("username", "system"),
            include_data=include_data
        )
        
        return TemporalSnapshot(
            branch=result.branch,
            timestamp=result.timestamp,
            commit_hash=result.commit_hash,
            resource_counts=result.resource_counts,
            total_resources=result.total_resources,
            total_versions=result.total_versions,
            resources=result.resources,
            created_at=result.created_at,
            created_by=result.created_by,
            description=result.description,
            tags=result.tags
        )