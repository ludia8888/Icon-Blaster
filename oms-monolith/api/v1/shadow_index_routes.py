"""
Shadow Index API Routes
Near-zero downtime indexing with atomic switch pattern
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel, Field

from core.auth_utils import UserContext
from middleware.auth_middleware import get_current_user
from core.shadow_index.manager import get_shadow_manager, ShadowIndexConflictError, SwitchValidationError
from models.shadow_index import (
    ShadowIndexInfo, ShadowIndexState, IndexType, SwitchRequest, SwitchResult
)
from utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/shadow-index", tags=["Shadow Index Management"])


# Request/Response Models

class StartShadowBuildRequest(BaseModel):
    """Request to start a shadow index build"""
    branch_name: str = Field(..., description="Branch to build index for")
    index_type: IndexType = Field(..., description="Type of index to build")
    resource_types: List[str] = Field(..., description="Resource types to include")
    service_instance_id: Optional[str] = Field(None, description="Service instance ID")
    build_config: Optional[Dict[str, Any]] = Field(None, description="Additional build configuration")


class StartShadowBuildResponse(BaseModel):
    """Response after starting shadow build"""
    shadow_index_id: str
    message: str
    estimated_build_time_minutes: Optional[int] = None


class UpdateProgressRequest(BaseModel):
    """Request to update build progress"""
    progress_percent: int = Field(..., ge=0, le=100, description="Build progress percentage")
    estimated_completion_seconds: Optional[int] = Field(None, description="Estimated time to completion")
    record_count: Optional[int] = Field(None, description="Current record count")


class CompleteBuildRequest(BaseModel):
    """Request to mark build as complete"""
    index_size_bytes: int = Field(..., description="Final index size in bytes")
    record_count: int = Field(..., description="Final record count")
    build_summary: Optional[Dict[str, Any]] = Field(None, description="Build summary information")


class ShadowIndexStatusResponse(BaseModel):
    """Detailed shadow index status"""
    shadow_index_id: str
    branch_name: str
    index_type: IndexType
    state: ShadowIndexState
    build_progress_percent: int
    estimated_completion_seconds: Optional[int]
    
    # Timing information
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    switched_at: Optional[datetime]
    
    # Size information
    index_size_bytes: Optional[int]
    record_count: Optional[int]
    
    # Service information
    service_name: str
    service_instance_id: Optional[str]
    
    # Switch information
    switch_ready: bool
    estimated_switch_duration_seconds: int


class ShadowIndexListResponse(BaseModel):
    """List of shadow indexes"""
    shadows: List[ShadowIndexStatusResponse]
    total_count: int
    active_builds: int
    ready_for_switch: int


# Shadow Index Management Endpoints

@router.post("/start")
async def start_shadow_build(
    request: StartShadowBuildRequest,
    background_tasks: BackgroundTasks,
    user: UserContext = Depends(get_current_user)
) -> StartShadowBuildResponse:
    """Start building a shadow index in the background (no locks required)"""
    # Only service accounts or admins can start shadow builds
    if not (user.is_service_account or user.is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only service accounts or administrators can start shadow builds"
        )
    
    shadow_manager = get_shadow_manager()
    
    try:
        shadow_index_id = await shadow_manager.start_shadow_build(
            branch_name=request.branch_name,
            index_type=request.index_type,
            resource_types=request.resource_types,
            service_name=user.username,
            service_instance_id=request.service_instance_id,
            build_config=request.build_config
        )
        
        # Estimate build time based on resource types and configuration
        estimated_minutes = len(request.resource_types) * 5  # 5 minutes per resource type
        if request.build_config and request.build_config.get("full_rebuild"):
            estimated_minutes *= 2
        
        logger.info(
            f"Started shadow index build: {shadow_index_id} for {request.branch_name}:{request.index_type.value}"
        )
        
        return StartShadowBuildResponse(
            shadow_index_id=shadow_index_id,
            message=f"Shadow index build started for {request.branch_name}",
            estimated_build_time_minutes=estimated_minutes
        )
        
    except ShadowIndexConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error starting shadow build: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start shadow build: {str(e)}"
        )


@router.post("/{shadow_index_id}/progress")
async def update_build_progress(
    shadow_index_id: str,
    request: UpdateProgressRequest,
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Update build progress for a shadow index"""
    # Only service accounts can update progress
    if not user.is_service_account:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only service accounts can update build progress"
        )
    
    shadow_manager = get_shadow_manager()
    
    success = await shadow_manager.update_build_progress(
        shadow_index_id=shadow_index_id,
        progress_percent=request.progress_percent,
        estimated_completion_seconds=request.estimated_completion_seconds,
        record_count=request.record_count,
        service_name=user.username
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shadow index not found or not in building state: {shadow_index_id}"
        )
    
    return {
        "success": True,
        "message": f"Progress updated to {request.progress_percent}%",
        "shadow_index_id": shadow_index_id
    }


@router.post("/{shadow_index_id}/complete")
async def complete_shadow_build(
    shadow_index_id: str,
    request: CompleteBuildRequest,
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Mark shadow index build as complete"""
    # Only service accounts can complete builds
    if not user.is_service_account:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only service accounts can complete builds"
        )
    
    shadow_manager = get_shadow_manager()
    
    success = await shadow_manager.complete_shadow_build(
        shadow_index_id=shadow_index_id,
        index_size_bytes=request.index_size_bytes,
        record_count=request.record_count,
        service_name=user.username
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shadow index not found or not in building state: {shadow_index_id}"
        )
    
    logger.info(f"Shadow index build completed: {shadow_index_id}")
    
    return {
        "success": True,
        "message": "Shadow index build completed successfully",
        "shadow_index_id": shadow_index_id,
        "ready_for_switch": True,
        "index_size_bytes": request.index_size_bytes,
        "record_count": request.record_count
    }


@router.post("/{shadow_index_id}/switch")
async def request_atomic_switch(
    shadow_index_id: str,
    request: SwitchRequest,
    user: UserContext = Depends(get_current_user)
) -> SwitchResult:
    """Perform atomic switch from shadow to primary index (requires short lock < 10s)"""
    # Only service accounts or admins can request switches
    if not (user.is_service_account or user.is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only service accounts or administrators can request index switches"
        )
    
    shadow_manager = get_shadow_manager()
    
    try:
        switch_result = await shadow_manager.request_atomic_switch(
            shadow_index_id=shadow_index_id,
            request=request,
            service_name=user.username
        )
        
        if switch_result.success:
            logger.info(
                f"Atomic switch completed successfully: {shadow_index_id} "
                f"in {switch_result.switch_duration_ms}ms"
            )
        else:
            logger.warning(
                f"Atomic switch failed: {shadow_index_id} - {switch_result.message}"
            )
        
        return switch_result
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except SwitchValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error during atomic switch: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Atomic switch failed: {str(e)}"
        )


@router.get("/{shadow_index_id}/status")
async def get_shadow_status(
    shadow_index_id: str,
    user: UserContext = Depends(get_current_user)
) -> ShadowIndexStatusResponse:
    """Get detailed status of a shadow index"""
    shadow_manager = get_shadow_manager()
    
    shadow_info = await shadow_manager.get_shadow_status(shadow_index_id)
    if not shadow_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shadow index not found: {shadow_index_id}"
        )
    
    # Calculate switch readiness and duration
    switch_ready = shadow_info.state == ShadowIndexState.BUILT
    estimated_switch_duration = 5  # Default 5 seconds
    
    if shadow_info.index_size_bytes:
        from models.shadow_index import estimate_switch_duration
        estimated_switch_duration = estimate_switch_duration(
            shadow_info.index_size_bytes,
            shadow_info.switch_strategy
        )
    
    return ShadowIndexStatusResponse(
        shadow_index_id=shadow_info.id,
        branch_name=shadow_info.branch_name,
        index_type=shadow_info.index_type,
        state=shadow_info.state,
        build_progress_percent=shadow_info.build_progress_percent,
        estimated_completion_seconds=shadow_info.estimated_completion_seconds,
        created_at=shadow_info.created_at,
        started_at=shadow_info.started_at,
        completed_at=shadow_info.completed_at,
        switched_at=shadow_info.switched_at,
        index_size_bytes=shadow_info.index_size_bytes,
        record_count=shadow_info.record_count,
        service_name=shadow_info.service_name,
        service_instance_id=shadow_info.service_instance_id,
        switch_ready=switch_ready,
        estimated_switch_duration_seconds=estimated_switch_duration
    )


@router.get("/list")
async def list_shadow_indexes(
    branch_name: Optional[str] = None,
    state: Optional[ShadowIndexState] = None,
    user: UserContext = Depends(get_current_user)
) -> ShadowIndexListResponse:
    """List shadow indexes with optional filtering"""
    shadow_manager = get_shadow_manager()
    
    shadows = await shadow_manager.list_active_shadows(branch_name)
    
    # Filter by state if specified
    if state:
        shadows = [s for s in shadows if s.state == state]
    
    # Convert to response format
    shadow_responses = []
    active_builds = 0
    ready_for_switch = 0
    
    for shadow_info in shadows:
        if shadow_info.state == ShadowIndexState.BUILDING:
            active_builds += 1
        elif shadow_info.state == ShadowIndexState.BUILT:
            ready_for_switch += 1
        
        estimated_switch_duration = 5
        if shadow_info.index_size_bytes:
            from models.shadow_index import estimate_switch_duration
            estimated_switch_duration = estimate_switch_duration(
                shadow_info.index_size_bytes,
                shadow_info.switch_strategy
            )
        
        shadow_responses.append(ShadowIndexStatusResponse(
            shadow_index_id=shadow_info.id,
            branch_name=shadow_info.branch_name,
            index_type=shadow_info.index_type,
            state=shadow_info.state,
            build_progress_percent=shadow_info.build_progress_percent,
            estimated_completion_seconds=shadow_info.estimated_completion_seconds,
            created_at=shadow_info.created_at,
            started_at=shadow_info.started_at,
            completed_at=shadow_info.completed_at,
            switched_at=shadow_info.switched_at,
            index_size_bytes=shadow_info.index_size_bytes,
            record_count=shadow_info.record_count,
            service_name=shadow_info.service_name,
            service_instance_id=shadow_info.service_instance_id,
            switch_ready=shadow_info.state == ShadowIndexState.BUILT,
            estimated_switch_duration_seconds=estimated_switch_duration
        ))
    
    return ShadowIndexListResponse(
        shadows=shadow_responses,
        total_count=len(shadow_responses),
        active_builds=active_builds,
        ready_for_switch=ready_for_switch
    )


@router.delete("/{shadow_index_id}")
async def cancel_shadow_build(
    shadow_index_id: str,
    reason: str = "Manual cancellation",
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Cancel an active shadow build"""
    # Only service accounts or admins can cancel builds
    if not (user.is_service_account or user.is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only service accounts or administrators can cancel builds"
        )
    
    shadow_manager = get_shadow_manager()
    
    success = await shadow_manager.cancel_shadow_build(
        shadow_index_id=shadow_index_id,
        service_name=user.username,
        reason=reason
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shadow index not found or cannot be cancelled: {shadow_index_id}"
        )
    
    logger.info(f"Shadow index build cancelled: {shadow_index_id} by {user.username}")
    
    return {
        "success": True,
        "message": f"Shadow index build cancelled: {reason}",
        "shadow_index_id": shadow_index_id
    }


# Monitoring and Dashboard Endpoints

@router.get("/dashboard")
async def get_shadow_dashboard(
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get dashboard data for shadow index monitoring"""
    shadow_manager = get_shadow_manager()
    
    all_shadows = await shadow_manager.list_active_shadows()
    
    # Categorize by state
    state_counts = {}
    for state in ShadowIndexState:
        state_counts[state.value] = len([s for s in all_shadows if s.state == state])
    
    # Recent activity
    recent_shadows = sorted(all_shadows, key=lambda s: s.created_at, reverse=True)[:10]
    
    # Performance metrics
    completed_switches = [s for s in all_shadows if s.state == ShadowIndexState.ACTIVE and s.switched_at]
    avg_switch_time = 0
    if completed_switches:
        switch_times = []
        for shadow in completed_switches:
            if shadow.completed_at and shadow.switched_at:
                switch_duration = (shadow.switched_at - shadow.completed_at).total_seconds()
                switch_times.append(switch_duration)
        
        if switch_times:
            avg_switch_time = sum(switch_times) / len(switch_times)
    
    return {
        "total_shadows": len(all_shadows),
        "state_distribution": state_counts,
        "recent_activity": [
            {
                "id": s.id,
                "branch_name": s.branch_name,
                "index_type": s.index_type.value,
                "state": s.state.value,
                "created_at": s.created_at,
                "progress": s.build_progress_percent
            }
            for s in recent_shadows
        ],
        "performance_metrics": {
            "average_switch_time_seconds": round(avg_switch_time, 2),
            "completed_switches_count": len(completed_switches),
            "active_builds": state_counts.get("BUILDING", 0),
            "ready_for_switch": state_counts.get("BUILT", 0)
        }
    }