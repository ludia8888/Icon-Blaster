"""
Temporal Query Resolver
Handles time travel queries in GraphQL
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
import strawberry

from core.time_travel import (
    TemporalOperator as CoreTemporalOperator,
    TemporalReference as CoreTemporalReference,
    TemporalQuery as CoreTemporalQuery,
    TemporalResourceQuery as CoreTemporalResourceQuery,
    TemporalComparisonQuery as CoreTemporalComparisonQuery,
    get_time_travel_service
)
from .temporal_schema import (
    TemporalResourceQueryInput,
    TemporalComparisonInput,
    TemporalQueryResult,
    TemporalComparisonResult,
    ResourceTimeline,
    TemporalSnapshot,
    TemporalResourceVersion,
    TimelineEvent
)


class TemporalResolver:
    """Resolver for temporal queries"""
    
    async def query_temporal(
        self,
        info: strawberry.Info,
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
    
    async def compare_temporal_states(
        self,
        info: strawberry.Info,
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
    
    async def get_resource_timeline(
        self,
        info: strawberry.Info,
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
    
    async def create_temporal_snapshot(
        self,
        info: strawberry.Info,
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