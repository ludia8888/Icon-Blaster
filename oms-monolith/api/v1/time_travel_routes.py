"""
Time Travel API Routes
REST endpoints for temporal queries and point-in-time data access
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field

from core.auth import UserContext
from middleware.auth_middleware import get_current_user
from core.time_travel import (
    TemporalOperator, TemporalReference, TemporalQuery,
    TemporalResourceQuery, TemporalComparisonQuery,
    get_time_travel_service
)
from utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/time-travel", tags=["Time Travel"])


# Request/Response Models

class TemporalReferenceRequest(BaseModel):
    """Request model for temporal reference"""
    timestamp: Optional[datetime] = Field(None, description="Specific timestamp")
    version: Optional[int] = Field(None, description="Specific version number")
    commit_hash: Optional[str] = Field(None, description="Specific commit hash")
    relative_time: Optional[str] = Field(None, description="Relative time like '-1h', '-7d'")


class AsOfQueryRequest(BaseModel):
    """Request for AS OF query"""
    resource_type: str = Field(..., description="Type of resource")
    resource_id: Optional[str] = Field(None, description="Specific resource ID")
    branch: str = Field("main", description="Branch to query")
    point_in_time: TemporalReferenceRequest = Field(..., description="Point in time")
    include_deleted: bool = Field(False, description="Include deleted resources")
    limit: int = Field(100, ge=1, le=1000)
    offset: int = Field(0, ge=0)


class BetweenQueryRequest(BaseModel):
    """Request for BETWEEN query"""
    resource_type: str = Field(..., description="Type of resource")
    resource_id: Optional[str] = Field(None, description="Specific resource ID")
    branch: str = Field("main", description="Branch to query")
    start_time: TemporalReferenceRequest = Field(..., description="Start time")
    end_time: Optional[TemporalReferenceRequest] = Field(None, description="End time")
    include_deleted: bool = Field(False, description="Include deleted resources")
    limit: int = Field(100, ge=1, le=1000)
    offset: int = Field(0, ge=0)


class CompareStatesRequest(BaseModel):
    """Request for comparing states"""
    resource_types: List[str] = Field(..., description="Resource types to compare")
    branch: str = Field("main", description="Branch to compare")
    time1: TemporalReferenceRequest = Field(..., description="First time point")
    time2: TemporalReferenceRequest = Field(..., description="Second time point")
    include_unchanged: bool = Field(False, description="Include unchanged resources")
    detailed_diff: bool = Field(True, description="Include field-level differences")


# Endpoints

@router.post("/as-of")
async def query_as_of(
    request: AsOfQueryRequest,
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Query resources as they were at a specific point in time
    
    Examples:
    - Get object_type as of yesterday: {"relative_time": "-1d"}
    - Get object_type at specific time: {"timestamp": "2024-01-01T00:00:00Z"}
    - Get object_type at version 5: {"version": 5}
    """
    service = await get_time_travel_service()
    
    # Build temporal reference
    temporal_ref = TemporalReference(
        timestamp=request.point_in_time.timestamp,
        version=request.point_in_time.version,
        commit_hash=request.point_in_time.commit_hash,
        relative_time=request.point_in_time.relative_time
    )
    
    # Build query
    temporal_query = TemporalQuery(
        operator=TemporalOperator.AS_OF,
        point_in_time=temporal_ref,
        include_deleted=request.include_deleted
    )
    
    resource_query = TemporalResourceQuery(
        resource_type=request.resource_type,
        resource_id=request.resource_id,
        branch=request.branch,
        temporal=temporal_query,
        limit=request.limit,
        offset=request.offset
    )
    
    # Execute query
    result = await service.query_as_of(resource_query)
    
    return {
        "resources": [r.dict() for r in result.resources],
        "total_count": result.total_count,
        "has_more": result.has_more,
        "execution_time_ms": result.execution_time_ms,
        "time_queried": temporal_ref.to_timestamp().isoformat()
    }


@router.post("/between")
async def query_between(
    request: BetweenQueryRequest,
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Query all versions of resources between two points in time
    
    Examples:
    - Get changes in last week: {"start_time": {"relative_time": "-7d"}}
    - Get changes between versions: {"start_time": {"version": 5}, "end_time": {"version": 10}}
    """
    service = await get_time_travel_service()
    
    # Build temporal references
    start_ref = TemporalReference(
        timestamp=request.start_time.timestamp,
        version=request.start_time.version,
        commit_hash=request.start_time.commit_hash,
        relative_time=request.start_time.relative_time
    )
    
    end_ref = None
    if request.end_time:
        end_ref = TemporalReference(
            timestamp=request.end_time.timestamp,
            version=request.end_time.version,
            commit_hash=request.end_time.commit_hash,
            relative_time=request.end_time.relative_time
        )
    
    # Build query
    temporal_query = TemporalQuery(
        operator=TemporalOperator.BETWEEN,
        start_time=start_ref,
        end_time=end_ref,
        include_deleted=request.include_deleted
    )
    
    resource_query = TemporalResourceQuery(
        resource_type=request.resource_type,
        resource_id=request.resource_id,
        branch=request.branch,
        temporal=temporal_query,
        limit=request.limit,
        offset=request.offset
    )
    
    # Execute query
    result = await service.query_between(resource_query)
    
    return {
        "resources": [r.dict() for r in result.resources],
        "total_count": result.total_count,
        "has_more": result.has_more,
        "execution_time_ms": result.execution_time_ms,
        "time_range": result.time_range_covered,
        "versions_scanned": result.versions_scanned
    }


@router.get("/versions/{resource_type}/{resource_id}")
async def get_all_versions(
    resource_type: str,
    resource_id: str,
    branch: str = Query("main", description="Branch to query"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get all versions of a specific resource"""
    service = await get_time_travel_service()
    
    # Build query for all versions
    temporal_query = TemporalQuery(
        operator=TemporalOperator.ALL_VERSIONS
    )
    
    resource_query = TemporalResourceQuery(
        resource_type=resource_type,
        resource_id=resource_id,
        branch=branch,
        temporal=temporal_query,
        limit=limit,
        offset=offset
    )
    
    # Execute query
    result = await service.query_all_versions(resource_query)
    
    return {
        "resource_type": resource_type,
        "resource_id": resource_id,
        "branch": branch,
        "versions": [r.dict() for r in result.resources],
        "total_versions": result.total_count,
        "has_more": result.has_more,
        "execution_time_ms": result.execution_time_ms
    }


@router.post("/compare")
async def compare_states(
    request: CompareStatesRequest,
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Compare resource states at two different points in time
    
    Examples:
    - Compare current with yesterday: time1={relative_time: "-1d"}, time2={timestamp: null}
    - Compare two versions: time1={version: 5}, time2={version: 10}
    """
    service = await get_time_travel_service()
    
    # Build temporal references
    time1_ref = TemporalReference(
        timestamp=request.time1.timestamp,
        version=request.time1.version,
        commit_hash=request.time1.commit_hash,
        relative_time=request.time1.relative_time
    )
    
    time2_ref = TemporalReference(
        timestamp=request.time2.timestamp,
        version=request.time2.version,
        commit_hash=request.time2.commit_hash,
        relative_time=request.time2.relative_time
    )
    
    # Build comparison query
    comparison_query = TemporalComparisonQuery(
        resource_types=request.resource_types,
        branch=request.branch,
        time1=time1_ref,
        time2=time2_ref,
        include_unchanged=request.include_unchanged,
        detailed_diff=request.detailed_diff
    )
    
    # Execute comparison
    result = await service.compare_temporal_states(comparison_query)
    
    # Format differences for API response
    differences = {}
    for resource_type, diffs in result.differences.items():
        differences[resource_type] = [d.dict() for d in diffs]
    
    return {
        "time1": result.time1_resolved.isoformat(),
        "time2": result.time2_resolved.isoformat(),
        "differences": differences,
        "summary": {
            "created": result.total_created,
            "updated": result.total_updated,
            "deleted": result.total_deleted,
            "unchanged": result.total_unchanged
        },
        "execution_time_ms": result.execution_time_ms
    }


@router.get("/timeline/{resource_type}/{resource_id}")
async def get_resource_timeline(
    resource_type: str,
    resource_id: str,
    branch: str = Query("main", description="Branch to query"),
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get complete timeline of changes for a resource"""
    service = await get_time_travel_service()
    
    timeline = await service.get_resource_timeline(
        resource_type, resource_id, branch
    )
    
    return timeline.dict()


@router.post("/snapshot")
async def create_snapshot(
    branch: str = Query(..., description="Branch to snapshot"),
    timestamp: datetime = Query(..., description="Point in time to snapshot"),
    description: Optional[str] = Query(None, description="Snapshot description"),
    include_data: bool = Query(False, description="Include actual resource data"),
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Create a snapshot of the system at a specific point in time"""
    service = await get_time_travel_service()
    
    snapshot = await service.create_temporal_snapshot(
        branch=branch,
        timestamp=timestamp,
        created_by=user.username,
        description=description,
        include_data=include_data
    )
    
    return snapshot.dict()


@router.get("/resource-at-time")
async def get_resource_at_time(
    resource_type: str = Query(..., description="Type of resource"),
    resource_id: str = Query(..., description="Resource ID"),
    branch: str = Query("main", description="Branch to query"),
    timestamp: Optional[datetime] = Query(None, description="Specific timestamp"),
    version: Optional[int] = Query(None, description="Specific version"),
    relative_time: Optional[str] = Query(None, description="Relative time like '-1h'"),
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get a single resource at a specific point in time"""
    if not any([timestamp, version, relative_time]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either timestamp, version, or relative_time"
        )
    
    service = await get_time_travel_service()
    
    # Build temporal reference
    temporal_ref = TemporalReference(
        timestamp=timestamp,
        version=version,
        relative_time=relative_time
    )
    
    # Build query
    temporal_query = TemporalQuery(
        operator=TemporalOperator.AS_OF,
        point_in_time=temporal_ref
    )
    
    resource_query = TemporalResourceQuery(
        resource_type=resource_type,
        resource_id=resource_id,
        branch=branch,
        temporal=temporal_query,
        limit=1
    )
    
    # Execute query
    result = await service.query_as_of(resource_query)
    
    if not result.resources:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource {resource_type}/{resource_id} not found at specified time"
        )
    
    return result.resources[0].dict()


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check for time travel service"""
    try:
        service = await get_time_travel_service()
        return {
            "status": "healthy",
            "service": "time-travel",
            "message": "Time travel query service is operational"
        }
    except Exception as e:
        logger.error(f"Time travel service health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Time travel service is not available"
        )