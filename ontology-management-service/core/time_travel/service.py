"""
Time Travel Query Service
Service for executing temporal queries and point-in-time data access
"""
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone, timedelta
import asyncio
from collections import defaultdict
import json

from .models import (
    TemporalQuery, TemporalResourceQuery, TemporalOperator,
    TemporalReference, TemporalResourceVersion, TemporalQueryResult,
    TemporalDiff, TemporalSnapshot, TemporalComparisonQuery,
    TemporalComparisonResult, TimelineEvent, ResourceTimeline
)
from .cache import TemporalQueryCache
from .metrics import (
    track_temporal_query, temporal_query_with_circuit_breaker,
    TemporalQueryMetrics, track_cache_operation
)
from .db_optimizations import TimeTravelDBOptimizer, TemporalCursorPagination
from ..versioning.version_service import VersionTrackingService, get_version_service
from ..branch.foundry_branch_service import FoundryBranchService
from models.etag import ResourceVersion, VersionInfo
from shared.database.sqlite_connector import SQLiteConnector
from shared.cache.smart_cache import SmartCache
from common_logging.setup import get_logger
import redis.asyncio as redis

logger = get_logger(__name__)


class TimeTravelQueryService:
    """
    Service for temporal queries leveraging existing version tracking
    """
    
    def __init__(
        self,
        version_service: Optional[VersionTrackingService] = None,
        redis_client: Optional[redis.Redis] = None,
        smart_cache: Optional[SmartCache] = None
    ):
        self.version_service = version_service
        self._connector: Optional[SQLiteConnector] = None
        self._cache = TemporalQueryCache(
            redis_client=redis_client,
            smart_cache=smart_cache
        )
        self._optimizer: Optional[TimeTravelDBOptimizer] = None
        
    async def initialize(self):
        """Initialize service and ensure version service is ready"""
        if not self.version_service:
            self.version_service = await get_version_service()
        
        # Get direct access to version DB for complex queries
        self._connector = self.version_service._connector
        
        # Initialize optimizer
        self._optimizer = TimeTravelDBOptimizer(self._connector)
        
        # Create optimized indexes on first run
        await self._optimizer.create_optimized_indexes()
        await self._optimizer.analyze_and_optimize()
        
    @temporal_query_with_circuit_breaker("as_of")
    async def query_as_of(
        self,
        query: TemporalResourceQuery
    ) -> TemporalQueryResult:
        """
        Execute AS OF query - get resource state at specific time
        """
        start_time = asyncio.get_event_loop().time()
        
        # Check cache first
        cache_key = self._cache._generate_cache_key(
            "as_of",
            query.resource_type,
            query.resource_id,
            query.branch,
            {
                "time": query.temporal.point_in_time.to_timestamp().isoformat(),
                "include_deleted": query.temporal.include_deleted
            }
        )
        
        cached_result = await self._cache.get_cached_result(cache_key)
        if cached_result:
            return cached_result
        
        # Resolve temporal reference to timestamp
        target_time = query.temporal.point_in_time.to_timestamp()
        
        # Build SQL query for AS OF
        if query.resource_id:
            # Query specific resource
            sql = """
                SELECT * FROM resource_versions
                WHERE resource_type = :resource_type 
                AND resource_id = :resource_id 
                AND branch = :branch
                AND modified_at <= :target_time
                ORDER BY version DESC
                LIMIT 1
            """
            params = {
                "resource_type": query.resource_type,
                "resource_id": query.resource_id,
                "branch": query.branch,
                "target_time": target_time.isoformat()
            }
        else:
            # Query all resources of type
            sql = """
                WITH latest_versions AS (
                    SELECT resource_id, MAX(version) as max_version
                    FROM resource_versions
                    WHERE resource_type = :resource_type 
                    AND branch = :branch
                    AND modified_at <= :target_time
                    GROUP BY resource_id
                )
                SELECT rv.*
                FROM resource_versions rv
                INNER JOIN latest_versions lv 
                    ON rv.resource_id = lv.resource_id 
                    AND rv.version = lv.max_version
                WHERE rv.resource_type = :resource_type 
                AND rv.branch = :branch
                ORDER BY rv.resource_id
                LIMIT :limit OFFSET :offset
            """
            params = {
                "resource_type": query.resource_type,
                "branch": query.branch,
                "target_time": target_time.isoformat(),
                "limit": query.limit,
                "offset": query.offset
            }
        
        rows = await self._connector.fetch_all(sql, params)
        
        # Convert to temporal resource versions
        resources = []
        for row in rows:
            # Skip deleted resources unless requested
            if row['change_type'] == 'delete' and not query.temporal.include_deleted:
                continue
                
            resource = await self._row_to_temporal_resource(row)
            resources.append(resource)
        
        # Get total count
        count_sql = """
            SELECT COUNT(DISTINCT resource_id) as count
            FROM resource_versions
            WHERE resource_type = :resource_type 
            AND branch = :branch
            AND modified_at <= :target_time
        """
        count_result = await self._connector.fetch_one(count_sql, {
            "resource_type": query.resource_type,
            "branch": query.branch,
            "target_time": target_time.isoformat()
        })
        total_count = count_result['count'] if count_result else 0
        
        execution_time = (asyncio.get_event_loop().time() - start_time) * 1000
        
        result = TemporalQueryResult(
            query=query,
            execution_time_ms=execution_time,
            resources=resources,
            total_count=total_count,
            has_more=len(resources) + query.offset < total_count,
            time_range_covered={"as_of": target_time},
            versions_scanned=len(rows),
            cache_hit=False,
            cacheable=True
        )
        
        # Cache the result
        await self._cache.cache_result(cache_key, result)
        
        return result
    
    async def query_between(
        self,
        query: TemporalResourceQuery
    ) -> TemporalQueryResult:
        """
        Execute BETWEEN query - get all versions in time range
        """
        start_time = asyncio.get_event_loop().time()
        
        # Resolve temporal references
        start_timestamp = query.temporal.start_time.to_timestamp()
        end_timestamp = query.temporal.end_time.to_timestamp() if query.temporal.end_time else datetime.utcnow()
        
        # Build SQL query
        if query.resource_id:
            sql = """
                SELECT * FROM resource_versions
                WHERE resource_type = :resource_type 
                AND resource_id = :resource_id 
                AND branch = :branch
                AND modified_at BETWEEN :start_time AND :end_time
                ORDER BY version
                LIMIT :limit OFFSET :offset
            """
            params = {
                "resource_type": query.resource_type,
                "resource_id": query.resource_id,
                "branch": query.branch,
                "start_time": start_timestamp.isoformat(),
                "end_time": end_timestamp.isoformat(),
                "limit": query.limit,
                "offset": query.offset
            }
        else:
            sql = """
                SELECT * FROM resource_versions
                WHERE resource_type = :resource_type 
                AND branch = :branch
                AND modified_at BETWEEN :start_time AND :end_time
                ORDER BY resource_id, version
                LIMIT :limit OFFSET :offset
            """
            params = {
                "resource_type": query.resource_type,
                "branch": query.branch,
                "start_time": start_timestamp.isoformat(),
                "end_time": end_timestamp.isoformat(),
                "limit": query.limit,
                "offset": query.offset
            }
        
        rows = await self._connector.fetch_all(sql, params)
        
        # Convert to temporal resources
        resources = []
        for row in rows:
            if row['change_type'] == 'delete' and not query.temporal.include_deleted:
                continue
                
            resource = await self._row_to_temporal_resource(row)
            resources.append(resource)
        
        # Get total count
        count_sql = """
            SELECT COUNT(*) as count
            FROM resource_versions
            WHERE resource_type = :resource_type 
            AND branch = :branch
            AND modified_at BETWEEN :start_time AND :end_time
        """
        count_params = {
            "resource_type": query.resource_type,
            "branch": query.branch,
            "start_time": start_timestamp.isoformat(),
            "end_time": end_timestamp.isoformat()
        }
        if query.resource_id:
            count_sql += " AND resource_id = :resource_id"
            count_params["resource_id"] = query.resource_id
            
        count_result = await self._connector.fetch_one(count_sql, count_params)
        total_count = count_result['count'] if count_result else 0
        
        execution_time = (asyncio.get_event_loop().time() - start_time) * 1000
        
        return TemporalQueryResult(
            query=query,
            execution_time_ms=execution_time,
            resources=resources,
            total_count=total_count,
            has_more=len(resources) + query.offset < total_count,
            time_range_covered={
                "start": start_timestamp,
                "end": end_timestamp
            },
            versions_scanned=len(rows)
        )
    
    async def query_all_versions(
        self,
        query: TemporalResourceQuery
    ) -> TemporalQueryResult:
        """
        Get all versions of a resource
        """
        if not query.resource_id:
            raise ValueError("resource_id required for ALL_VERSIONS query")
            
        start_time = asyncio.get_event_loop().time()
        
        sql = """
            SELECT * FROM resource_versions
            WHERE resource_type = :resource_type 
            AND resource_id = :resource_id 
            AND branch = :branch
            ORDER BY version
            LIMIT :limit OFFSET :offset
        """
        params = {
            "resource_type": query.resource_type,
            "resource_id": query.resource_id,
            "branch": query.branch,
            "limit": query.limit,
            "offset": query.offset
        }
        
        rows = await self._connector.fetch_all(sql, params)
        
        # Convert and calculate version durations
        resources = []
        prev_time = None
        
        for i, row in enumerate(rows):
            resource = await self._row_to_temporal_resource(row)
            
            # Calculate duration this version was active
            if i < len(rows) - 1:
                next_time = datetime.fromisoformat(rows[i + 1]['modified_at'])
                resource.version_duration = (next_time - resource.valid_time).total_seconds()
                resource.next_version = rows[i + 1]['version']
            
            if i > 0:
                resource.previous_version = rows[i - 1]['version']
                
            resources.append(resource)
        
        # Get total count
        count_sql = """
            SELECT COUNT(*) as count
            FROM resource_versions
            WHERE resource_type = :resource_type 
            AND resource_id = :resource_id 
            AND branch = :branch
        """
        count_result = await self._connector.fetch_one(count_sql, {
            "resource_type": query.resource_type,
            "resource_id": query.resource_id,
            "branch": query.branch
        })
        total_count = count_result['count'] if count_result else 0
        
        execution_time = (asyncio.get_event_loop().time() - start_time) * 1000
        
        return TemporalQueryResult(
            query=query,
            execution_time_ms=execution_time,
            resources=resources,
            total_count=total_count,
            has_more=len(resources) + query.offset < total_count,
            versions_scanned=len(rows)
        )
    
    async def compare_temporal_states(
        self,
        query: TemporalComparisonQuery
    ) -> TemporalComparisonResult:
        """
        Compare system state at two different times
        """
        start_time = asyncio.get_event_loop().time()
        
        # Resolve times
        time1 = query.time1.to_timestamp()
        time2 = query.time2.to_timestamp()
        
        differences = defaultdict(list)
        total_stats = {
            "created": 0,
            "updated": 0,
            "deleted": 0,
            "unchanged": 0
        }
        
        for resource_type in query.resource_types:
            # Get state at time1
            state1 = await self._get_state_at_time(resource_type, query.branch, time1)
            
            # Get state at time2
            state2 = await self._get_state_at_time(resource_type, query.branch, time2)
            
            # Compare states
            type_diffs = await self._compare_states(
                resource_type, state1, state2, 
                query.time1, query.time2,
                query.detailed_diff
            )
            
            # Apply filters
            if query.filters:
                type_diffs = self._apply_filters(type_diffs, query.filters)
            
            # Filter unchanged if not requested
            if not query.include_unchanged:
                type_diffs = [d for d in type_diffs if d.operation != "unchanged"]
            
            differences[resource_type] = type_diffs
            
            # Update statistics
            for diff in type_diffs:
                if diff.operation == "created":
                    total_stats["created"] += 1
                elif diff.operation == "updated":
                    total_stats["updated"] += 1
                elif diff.operation == "deleted":
                    total_stats["deleted"] += 1
                else:
                    total_stats["unchanged"] += 1
        
        execution_time = (asyncio.get_event_loop().time() - start_time) * 1000
        
        return TemporalComparisonResult(
            query=query,
            execution_time_ms=execution_time,
            time1_resolved=time1,
            time2_resolved=time2,
            differences=dict(differences),
            total_created=total_stats["created"],
            total_updated=total_stats["updated"],
            total_deleted=total_stats["deleted"],
            total_unchanged=total_stats["unchanged"]
        )
    
    async def get_resource_timeline(
        self,
        resource_type: str,
        resource_id: str,
        branch: str = "main"
    ) -> ResourceTimeline:
        """
        Get complete timeline for a resource
        """
        # Get all versions
        sql = """
            SELECT * FROM resource_versions
            WHERE resource_type = :resource_type 
            AND resource_id = :resource_id 
            AND branch = :branch
            ORDER BY version
        """
        rows = await self._connector.fetch_all(sql, {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "branch": branch
        })
        
        if not rows:
            raise ValueError(f"Resource {resource_type}/{resource_id} not found")
        
        # Build timeline events
        events = []
        contributors = set()
        
        for row in rows:
            event = TimelineEvent(
                timestamp=datetime.fromisoformat(row['modified_at']),
                version=row['version'],
                commit_hash=row['commit_hash'],
                event_type=row['change_type'],
                description=f"{row['change_type'].title()} {resource_type}",
                modified_by=row['modified_by'],
                change_summary=row['change_summary'],
                fields_changed=json.loads(row['fields_changed']) if row['fields_changed'] else []
            )
            events.append(event)
            contributors.add(row['modified_by'])
        
        # Calculate statistics
        created_at = datetime.fromisoformat(rows[0]['modified_at'])
        last_modified_at = datetime.fromisoformat(rows[-1]['modified_at'])
        deleted_at = None
        
        if rows[-1]['change_type'] == 'delete':
            deleted_at = last_modified_at
        
        # Calculate activity metrics
        if len(events) > 1:
            total_duration = (last_modified_at - created_at).total_seconds()
            avg_time_between = total_duration / (len(events) - 1)
        else:
            avg_time_between = None
        
        return ResourceTimeline(
            resource_type=resource_type,
            resource_id=resource_id,
            branch=branch,
            events=events,
            created_at=created_at,
            last_modified_at=last_modified_at,
            deleted_at=deleted_at,
            total_versions=len(events),
            total_updates=len([e for e in events if e.event_type == 'update']),
            unique_contributors=list(contributors),
            average_time_between_changes=avg_time_between
        )
    
    async def create_temporal_snapshot(
        self,
        branch: str,
        timestamp: datetime,
        created_by: str,
        description: Optional[str] = None,
        include_data: bool = False
    ) -> TemporalSnapshot:
        """
        Create a snapshot of entire system at specific time
        """
        # Get resource counts at timestamp
        sql = """
            WITH latest_versions AS (
                SELECT resource_type, resource_id, MAX(version) as max_version
                FROM resource_versions
                WHERE branch = :branch
                AND modified_at <= :timestamp
                GROUP BY resource_type, resource_id
            )
            SELECT rv.resource_type, COUNT(DISTINCT rv.resource_id) as count
            FROM resource_versions rv
            INNER JOIN latest_versions lv 
                ON rv.resource_type = lv.resource_type 
                AND rv.resource_id = lv.resource_id 
                AND rv.version = lv.max_version
            WHERE rv.branch = :branch
            AND rv.change_type != 'delete'
            GROUP BY rv.resource_type
        """
        
        rows = await self._connector.fetch_all(sql, {
            "branch": branch,
            "timestamp": timestamp.isoformat()
        })
        
        resource_counts = {row['resource_type']: row['count'] for row in rows}
        total_resources = sum(resource_counts.values())
        
        # Get total versions count
        version_sql = """
            SELECT COUNT(*) as count
            FROM resource_versions
            WHERE branch = :branch
            AND modified_at <= :timestamp
        """
        version_result = await self._connector.fetch_one(version_sql, {
            "branch": branch,
            "timestamp": timestamp.isoformat()
        })
        total_versions = version_result['count'] if version_result else 0
        
        # Optionally include actual data
        snapshot_data = None
        if include_data:
            snapshot_data = {}
            for resource_type in resource_counts:
                resources = await self._get_state_at_time(resource_type, branch, timestamp)
                snapshot_data[resource_type] = [
                    json.loads(r['content']) for r in resources.values()
                ]
        
        return TemporalSnapshot(
            branch=branch,
            timestamp=timestamp,
            resource_counts=resource_counts,
            total_resources=total_resources,
            total_versions=total_versions,
            resources=snapshot_data,
            created_at=datetime.utcnow(),
            created_by=created_by,
            description=description
        )
    
    async def _row_to_temporal_resource(self, row: Dict[str, Any]) -> TemporalResourceVersion:
        """Convert database row to temporal resource"""
        content = json.loads(row['content']) if row['content'] else {}
        
        return TemporalResourceVersion(
            resource_type=row['resource_type'],
            resource_id=row['resource_id'],
            branch=row['branch'],
            version=row['version'],
            commit_hash=row['commit_hash'],
            valid_time=datetime.fromisoformat(row['modified_at']),
            content=content,
            modified_by=row['modified_by'],
            change_type=row['change_type'],
            change_summary=row['change_summary']
        )
    
    async def _get_state_at_time(
        self, 
        resource_type: str, 
        branch: str, 
        timestamp: datetime
    ) -> Dict[str, Dict[str, Any]]:
        """Get all resources of type at specific time"""
        sql = """
            WITH latest_versions AS (
                SELECT resource_id, MAX(version) as max_version
                FROM resource_versions
                WHERE resource_type = :resource_type 
                AND branch = :branch
                AND modified_at <= :timestamp
                GROUP BY resource_id
            )
            SELECT rv.*
            FROM resource_versions rv
            INNER JOIN latest_versions lv 
                ON rv.resource_id = lv.resource_id 
                AND rv.version = lv.max_version
            WHERE rv.resource_type = :resource_type 
            AND rv.branch = :branch
        """
        
        rows = await self._connector.fetch_all(sql, {
            "resource_type": resource_type,
            "branch": branch,
            "timestamp": timestamp.isoformat()
        })
        
        # Build state map
        state = {}
        for row in rows:
            if row['change_type'] != 'delete':
                state[row['resource_id']] = row
                
        return state
    
    async def _compare_states(
        self,
        resource_type: str,
        state1: Dict[str, Dict[str, Any]],
        state2: Dict[str, Dict[str, Any]],
        time1_ref: TemporalReference,
        time2_ref: TemporalReference,
        detailed: bool = True
    ) -> List[TemporalDiff]:
        """Compare two states and generate diffs"""
        diffs = []
        
        all_ids = set(state1.keys()) | set(state2.keys())
        
        for resource_id in all_ids:
            if resource_id in state1 and resource_id not in state2:
                # Deleted
                diff = TemporalDiff(
                    resource_type=resource_type,
                    resource_id=resource_id,
                    from_time=time1_ref,
                    to_time=time2_ref,
                    from_version=state1[resource_id]['version'],
                    operation="deleted"
                )
                diffs.append(diff)
                
            elif resource_id not in state1 and resource_id in state2:
                # Created
                diff = TemporalDiff(
                    resource_type=resource_type,
                    resource_id=resource_id,
                    from_time=time1_ref,
                    to_time=time2_ref,
                    to_version=state2[resource_id]['version'],
                    operation="created"
                )
                diffs.append(diff)
                
            else:
                # Possibly updated
                v1 = state1[resource_id]
                v2 = state2[resource_id]
                
                if v1['version'] != v2['version']:
                    diff = TemporalDiff(
                        resource_type=resource_type,
                        resource_id=resource_id,
                        from_time=time1_ref,
                        to_time=time2_ref,
                        from_version=v1['version'],
                        to_version=v2['version'],
                        operation="updated"
                    )
                    
                    if detailed and v1['content'] and v2['content']:
                        # Calculate field-level changes
                        content1 = json.loads(v1['content'])
                        content2 = json.loads(v2['content'])
                        
                        changes = []
                        fields_added = 0
                        fields_removed = 0
                        fields_modified = 0
                        
                        # Check for changes
                        all_fields = set(content1.keys()) | set(content2.keys())
                        for field in all_fields:
                            if field not in content1:
                                changes.append({
                                    "field": field,
                                    "operation": "added",
                                    "new_value": content2[field]
                                })
                                fields_added += 1
                            elif field not in content2:
                                changes.append({
                                    "field": field,
                                    "operation": "removed",
                                    "old_value": content1[field]
                                })
                                fields_removed += 1
                            elif content1[field] != content2[field]:
                                changes.append({
                                    "field": field,
                                    "operation": "modified",
                                    "old_value": content1[field],
                                    "new_value": content2[field]
                                })
                                fields_modified += 1
                        
                        diff.changes = changes
                        diff.fields_added = fields_added
                        diff.fields_removed = fields_removed
                        diff.fields_modified = fields_modified
                    
                    diffs.append(diff)
                else:
                    # Unchanged
                    if resource_id in state1 and resource_id in state2:
                        diff = TemporalDiff(
                            resource_type=resource_type,
                            resource_id=resource_id,
                            from_time=time1_ref,
                            to_time=time2_ref,
                            from_version=v1['version'],
                            to_version=v2['version'],
                            operation="unchanged"
                        )
                        diffs.append(diff)
        
        return diffs
    
    def _apply_filters(
        self, 
        diffs: List[TemporalDiff], 
        filters: Dict[str, Any]
    ) -> List[TemporalDiff]:
        """Apply filters to diff results"""
        # This is a placeholder - implement actual filtering logic
        return diffs


# Global instance
_time_travel_service: Optional[TimeTravelQueryService] = None


async def get_time_travel_service() -> TimeTravelQueryService:
    """Get global time travel service instance"""
    global _time_travel_service
    if _time_travel_service is None:
        _time_travel_service = TimeTravelQueryService()
        await _time_travel_service.initialize()
    return _time_travel_service