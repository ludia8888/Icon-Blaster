"""
Branch Lock Management API
Administrative endpoints for managing branch locks and schema freeze
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from pydantic import BaseModel, Field

from core.auth_utils import UserContext
from middleware.auth_middleware import get_current_user
from core.branch.lock_manager import get_lock_manager, LockConflictError, InvalidStateTransitionError
from models.branch_state import (
    BranchState, BranchLock, BranchStateInfo, 
    LockType, LockScope
)
from core.iam.dependencies import require_scope
from core.iam.iam_integration import IAMScope
from common_logging.setup import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/branch-locks", tags=["Branch Lock Management"])


# Request/Response Models

class LockRequest(BaseModel):
    """Request to acquire a lock"""
    branch_name: str = Field(..., description="Branch to lock")
    lock_type: LockType = Field(..., description="Type of lock")
    lock_scope: LockScope = Field(LockScope.BRANCH, description="Scope of lock")
    resource_type: Optional[str] = Field(None, description="Resource type if scoped")
    resource_id: Optional[str] = Field(None, description="Resource ID if scoped")
    reason: str = Field(..., description="Reason for lock")
    timeout_hours: Optional[int] = Field(None, description="Lock timeout in hours")


class LockResponse(BaseModel):
    """Response after acquiring a lock"""
    lock_id: str
    message: str
    expires_at: Optional[datetime]


class BranchStatusResponse(BaseModel):
    """Branch status response"""
    branch_name: str
    current_state: BranchState
    is_write_locked: bool
    is_ready_for_merge: bool
    active_locks: List[BranchLock]
    indexing_info: Optional[Dict[str, Any]] = None


class ForceUnlockRequest(BaseModel):
    """Request to force unlock a branch"""
    reason: str = Field(..., description="Reason for force unlock")


class StartIndexingRequest(BaseModel):
    """Request to start indexing (Foundry-style)"""
    resource_types: Optional[List[str]] = Field(None, description="Specific resource types to index")
    force_branch_lock: bool = Field(False, description="Force full branch lock (legacy mode)")
    reason: str = Field("Data indexing in progress", description="Reason for indexing")


class IndexingResponse(BaseModel):
    """Response after starting indexing (Foundry-style)"""
    lock_ids: List[str] = Field(..., description="List of acquired lock IDs")
    locked_resource_types: List[str] = Field(..., description="Resource types that were locked")
    lock_scope: str = Field(..., description="Scope of locking (branch or resource_type)")
    message: str = Field(..., description="Success message")
    branch_state: str = Field(..., description="Current branch state")
    other_resources_available: bool = Field(..., description="Whether other resources can still be edited")


class CompleteIndexingRequest(BaseModel):
    """Request to complete indexing (Foundry-style)"""
    resource_types: Optional[List[str]] = Field(None, description="Specific resource types that completed indexing")
    reason: str = Field("Indexing completed", description="Reason for completion")


class HeartbeatRequest(BaseModel):
    """Request to send a heartbeat for a lock"""
    service_name: str = Field(..., description="Name of the service sending the heartbeat")
    status: str = Field("healthy", description="Status of the service (healthy, warning, error)")
    progress_info: Optional[Dict[str, Any]] = Field(None, description="Optional progress information")


class HeartbeatResponse(BaseModel):
    """Response after sending heartbeat"""
    success: bool
    message: str
    last_heartbeat: Optional[datetime]


class LockHealthResponse(BaseModel):
    """Response with lock health status"""
    lock_id: str
    is_active: bool
    heartbeat_enabled: bool
    last_heartbeat: Optional[datetime]
    heartbeat_source: Optional[str]
    ttl_expired: bool
    heartbeat_expired: bool
    auto_release_enabled: bool
    seconds_since_last_heartbeat: Optional[int] = None
    heartbeat_health: Optional[str] = None
    seconds_until_ttl_expiry: Optional[int] = None


class ExtendTTLRequest(BaseModel):
    """Request to extend lock TTL"""
    extension_hours: float = Field(..., description="Hours to extend the TTL by")
    reason: str = Field("TTL extension", description="Reason for extension")


# Administrative Endpoints

@router.get("/status/{branch_name}", dependencies=[Depends(require_scope([IAMScope.BRANCHES_READ]))])
async def get_branch_status(
    branch_name: str,
    req: Request,
    user: UserContext = Depends(get_current_user),
) -> BranchStatusResponse:
    """Get current status of a branch"""
    lock_manager = get_lock_manager()
    branch_state = await lock_manager.get_branch_state(branch_name)
    
    indexing_info = None
    if branch_state.indexing_started_at or branch_state.indexing_completed_at:
        indexing_info = {
            "started_at": branch_state.indexing_started_at,
            "completed_at": branch_state.indexing_completed_at,
            "service": branch_state.indexing_service,
            "duration_seconds": None
        }
        
        if (branch_state.indexing_started_at and 
            branch_state.indexing_completed_at):
            duration = branch_state.indexing_completed_at - branch_state.indexing_started_at
            indexing_info["duration_seconds"] = int(duration.total_seconds())
    
    return BranchStatusResponse(
        branch_name=branch_name,
        current_state=branch_state.current_state,
        is_write_locked=branch_state.is_write_locked,
        is_ready_for_merge=branch_state.is_ready_for_merge,
        active_locks=branch_state.active_locks,
        indexing_info=indexing_info
    )


@router.get("/locks", dependencies=[Depends(require_scope([IAMScope.BRANCHES_READ]))])
async def list_active_locks(
    req: Request,
    branch_name: Optional[str] = Query(None, description="Filter by branch"),
    user: UserContext = Depends(get_current_user),
) -> List[BranchLock]:
    """List all active locks"""
    lock_manager = get_lock_manager()
    return await lock_manager.list_active_locks(branch_name)


@router.get("/locks/{lock_id}", dependencies=[Depends(require_scope([IAMScope.BRANCHES_READ]))])
async def get_lock_status(
    lock_id: str,
    req: Request,
    user: UserContext = Depends(get_current_user),
) -> BranchLock:
    """Get status of a specific lock"""
    lock_manager = get_lock_manager()
    lock = await lock_manager.get_lock_status(lock_id)
    
    if not lock:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lock {lock_id} not found"
        )
    
    return lock


@router.post("/acquire", dependencies=[Depends(require_scope([IAMScope.BRANCHES_WRITE, IAMScope.SYSTEM_ADMIN]))])
async def acquire_lock(
    request: LockRequest,
    req: Request,
    user: UserContext = Depends(get_current_user),
) -> LockResponse:
    """Acquire a lock on a branch or resource"""
    # Check if user has admin permissions for manual locks
    if request.lock_type == LockType.MANUAL:
        # For manual locks, require system admin scope explicitly
        if IAMScope.SYSTEM_ADMIN not in req.state.permissions:
             raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only administrators can acquire manual locks"
            )

    lock_manager = get_lock_manager()

    try:
        timeout = None
        if request.timeout_hours:
            timeout = timedelta(hours=request.timeout_hours)

        lock_id = await lock_manager.acquire_lock(
            branch_name=request.branch_name,
            lock_type=request.lock_type,
            locked_by=user.username,
            lock_scope=request.lock_scope,
            resource_type=request.resource_type,
            resource_id=request.resource_id,
            reason=request.reason,
            timeout=timeout
        )

        # Get lock details for response
        lock = await lock_manager.get_lock_status(lock_id)

        return LockResponse(
            lock_id=lock_id,
            message=f"Lock acquired successfully on {request.branch_name}",
            expires_at=lock.expires_at if lock else None
        )

    except LockConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )


@router.delete("/locks/{lock_id}", dependencies=[Depends(require_scope([IAMScope.BRANCHES_WRITE]))])
async def release_lock(
    lock_id: str,
    req: Request,
    user: UserContext = Depends(get_current_user),
) -> Dict[str, str]:
    """Release a specific lock"""
    lock_manager = get_lock_manager()
    
    # Get lock to check ownership
    lock = await lock_manager.get_lock_status(lock_id)
    if not lock:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lock {lock_id} not found"
        )
    
    # Check if user can release this lock
    if lock.locked_by != user.username and not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only release locks you created, or be an administrator"
        )
    
    success = await lock_manager.release_lock(lock_id, user.username)
    
    if success:
        return {"message": f"Lock {lock_id} released successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lock {lock_id} not found or already released"
        )


@router.post("/force-unlock/{branch_name}", dependencies=[Depends(require_scope([IAMScope.SYSTEM_ADMIN]))])  # Only admins can force unlock
async def force_unlock_branch(
    branch_name: str,
    request: ForceUnlockRequest,
    req: Request,
    user: UserContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """Force unlock all locks on a branch (admin only)"""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can force unlock branches"
        )
    
    lock_manager = get_lock_manager()
    
    try:
        count = await lock_manager.force_unlock(
            branch_name=branch_name,
            admin_user=user.username,
            reason=request.reason
        )
        
        return {
            "message": f"Force unlock completed for branch {branch_name}",
            "locks_released": count,
            "reason": request.reason
        }
        
    except Exception as e:
        logger.error(f"Force unlock failed for {branch_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Force unlock failed: {str(e)}"
        )


# Service Integration Endpoints (for Funnel Service, etc.)

@router.post("/indexing/{branch_name}/start", dependencies=[Depends(require_scope([IAMScope.BRANCHES_WRITE, IAMScope.SERVICE_ACCOUNT]))])
async def start_indexing(
    branch_name: str,
    request: StartIndexingRequest,
    req: Request,
    service_name: str = "funnel-service",
    user: UserContext = Depends(get_current_user),
) -> IndexingResponse:
    """Start indexing for a branch (Foundry-style: minimal scope)"""
    # This endpoint would typically be called by Funnel Service
    # Check if user is a service account or admin
    if not (user.is_service_account or user.is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only service accounts or administrators can start indexing"
        )
    
    lock_manager = get_lock_manager()
    
    try:
        # Start indexing with Foundry-style granular locking
        lock_ids = await lock_manager.lock_for_indexing(
            branch_name=branch_name,
            locked_by=service_name,
            reason=request.reason,
            resource_types=request.resource_types,
            force_branch_lock=request.force_branch_lock
        )
        
        # Get updated branch state
        branch_state = await lock_manager.get_branch_state(branch_name)
        
        # Determine which resource types were actually locked
        locked_resource_types = []
        lock_scope = "resource_type"  # Default to granular
        
        if request.force_branch_lock:
            lock_scope = "branch"
            locked_resource_types = ["all"]
        else:
            # Extract locked resource types from active locks
            for lock in branch_state.active_locks:
                if (lock.is_active and 
                    lock.lock_type.value == "indexing" and 
                    lock.resource_type and
                    lock.resource_type not in locked_resource_types):
                    locked_resource_types.append(lock.resource_type)
        
        # Determine if other resources are available
        all_resource_types = {"object_type", "link_type", "action_type", "function_type"}
        locked_types_set = set(locked_resource_types) if locked_resource_types != ["all"] else all_resource_types
        other_resources_available = len(all_resource_types - locked_types_set) > 0 and not request.force_branch_lock
        
        logger.info(
            f"Indexing started for branch {branch_name} by {service_name}. "
            f"Lock scope: {lock_scope}, Resource types: {locked_resource_types}, "
            f"Other resources available: {other_resources_available}"
        )
        
        return IndexingResponse(
            lock_ids=lock_ids,
            locked_resource_types=locked_resource_types,
            lock_scope=lock_scope,
            message=f"Indexing started for branch {branch_name}" + 
                   (f" (resource types: {', '.join(locked_resource_types)})" if lock_scope == "resource_type" else " (full branch)"),
            branch_state=branch_state.current_state.value,
            other_resources_available=other_resources_available
        )
        
    except LockConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot start indexing: {str(e)}"
        )


@router.post("/indexing/{branch_name}/complete", dependencies=[Depends(require_scope([IAMScope.BRANCHES_WRITE, IAMScope.SERVICE_ACCOUNT]))])
async def complete_indexing(
    branch_name: str,
    request: CompleteIndexingRequest,
    req: Request,
    service_name: str = "funnel-service",
    user: UserContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """Complete indexing for a branch (Foundry-style: granular)"""
    # Check if user is a service account or admin
    if not (user.is_service_account or user.is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only service accounts or administrators can complete indexing"
        )
    
    lock_manager = get_lock_manager()
    
    # Get branch state before completion
    branch_state_before = await lock_manager.get_branch_state(branch_name)
    
    success = await lock_manager.complete_indexing(
        branch_name=branch_name,
        completed_by=service_name,
        resource_types=request.resource_types
    )
    
    if success:
        # Get updated branch state
        branch_state_after = await lock_manager.get_branch_state(branch_name)
        
        # Check what remains locked
        remaining_indexing_locks = [
            lock for lock in branch_state_after.active_locks
            if lock.lock_type.value == "indexing" and lock.is_active
        ]
        
        completion_type = "partial" if remaining_indexing_locks else "complete"
        
        response_data = {
            "message": f"Indexing {completion_type}ly completed for branch {branch_name}",
            "completed_resource_types": request.resource_types or ["all"],
            "completion_type": completion_type,
            "branch_state": branch_state_after.current_state.value,
            "remaining_locks": len(remaining_indexing_locks)
        }
        
        if remaining_indexing_locks:
            remaining_types = [lock.resource_type for lock in remaining_indexing_locks if lock.resource_type]
            response_data["remaining_resource_types"] = remaining_types
            response_data["message"] += f". Still indexing: {', '.join(remaining_types)}"
        else:
            response_data["message"] += ". All indexing complete - branch ready for merge"
        
        logger.info(
            f"Indexing {completion_type}ly completed for branch {branch_name} by {service_name}. "
            f"Resource types: {request.resource_types or ['all']}, "
            f"Remaining locks: {len(remaining_indexing_locks)}"
        )
        
        return response_data
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No active indexing found for branch {branch_name}" +
                   (f" with resource types {request.resource_types}" if request.resource_types else "")
        )


# Utility Endpoints

@router.post("/cleanup-expired", dependencies=[Depends(require_scope([IAMScope.SYSTEM_ADMIN]))])
async def cleanup_expired_locks(
    req: Request,
    user: UserContext = Depends(get_current_user),
) -> Dict[str, str]:
    """Manually trigger cleanup of expired locks (admin only)"""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can trigger lock cleanup"
        )
    
    lock_manager = get_lock_manager()
    await lock_manager.cleanup_expired_locks()
    
    return {"message": "Expired locks cleanup completed"}


# Dashboard/Monitoring Endpoints

@router.get("/dashboard", dependencies=[Depends(require_scope([IAMScope.BRANCHES_READ]))])
async def get_dashboard_data(
    req: Request,
    user: UserContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get dashboard data for monitoring branch locks"""
    lock_manager = get_lock_manager()
    
    all_locks = await lock_manager.list_active_locks()
    
    # Group by lock type
    locks_by_type = {}
    for lock in all_locks:
        lock_type = lock.lock_type.value
        if lock_type not in locks_by_type:
            locks_by_type[lock_type] = []
        locks_by_type[lock_type].append(lock)
    
    # Find branches that are locked
    locked_branches = list(set(lock.branch_name for lock in all_locks))
    
    return {
        "total_active_locks": len(all_locks),
        "locked_branches": locked_branches,
        "locks_by_type": {k: len(v) for k, v in locks_by_type.items()},
        "recent_locks": all_locks[:10],  # Most recent 10 locks
    }


# TTL & Heartbeat Endpoints (Priority 4 Feature)

@router.post("/locks/{lock_id}/heartbeat", dependencies=[Depends(require_scope([IAMScope.BRANCHES_WRITE]))])
async def send_lock_heartbeat(
    lock_id: str,
    request: HeartbeatRequest,
    req: Request,
    user: UserContext = Depends(get_current_user),
) -> HeartbeatResponse:
    """Send a heartbeat for a lock to indicate the service is still active"""
    # Service accounts can send heartbeats for their own locks
    # Admins can send heartbeats for any lock
    if not (user.is_service_account or user.is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only service accounts or administrators can send heartbeats"
        )
    
    lock_manager = get_lock_manager()
    
    try:
        success = await lock_manager.send_heartbeat(
            lock_id=lock_id,
            service_name=request.service_name,
            status=request.status,
            progress_info=request.progress_info
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lock {lock_id} not found or inactive"
            )
        
        # Get updated lock info
        lock = await lock_manager.get_lock_status(lock_id)
        
        return HeartbeatResponse(
            success=True,
            message=f"Heartbeat recorded for lock {lock_id}",
            last_heartbeat=lock.last_heartbeat if lock else None
        )
        
    except Exception as e:
        logger.error(f"Error sending heartbeat for lock {lock_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to send heartbeat: {str(e)}"
        )


@router.get("/locks/{lock_id}/health", dependencies=[Depends(require_scope([IAMScope.BRANCHES_READ]))])
async def get_lock_health(
    lock_id: str,
    req: Request,
    user: UserContext = Depends(get_current_user),
) -> LockHealthResponse:
    """Get health status and heartbeat information for a lock"""
    lock_manager = get_lock_manager()
    
    health_info = await lock_manager.get_lock_health_status(lock_id)
    if not health_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lock {lock_id} not found"
        )
    
    return LockHealthResponse(**health_info)


@router.post("/locks/{lock_id}/extend-ttl", dependencies=[Depends(require_scope([IAMScope.BRANCHES_WRITE]))])
async def extend_lock_ttl(
    lock_id: str,
    request: ExtendTTLRequest,
    req: Request,
    user: UserContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """Extend the TTL of an existing lock"""
    # Only admins can extend TTL
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can extend lock TTL"
        )
    
    lock_manager = get_lock_manager()
    
    try:
        extension_duration = timedelta(hours=request.extension_hours)
        success = await lock_manager.extend_lock_ttl(
            lock_id=lock_id,
            extension_duration=extension_duration,
            extended_by=user.username,
            reason=request.reason
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Lock {lock_id} not found or inactive"
            )
        
        # Get updated lock info
        lock = await lock_manager.get_lock_status(lock_id)
        
        return {
            "success": True,
            "message": f"Lock TTL extended by {request.extension_hours} hours",
            "lock_id": lock_id,
            "new_expires_at": lock.expires_at if lock else None,
            "extended_by": user.username,
            "reason": request.reason
        }
        
    except Exception as e:
        logger.error(f"Error extending TTL for lock {lock_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extend TTL: {str(e)}"
        )


@router.post("/cleanup-heartbeat-expired", dependencies=[Depends(require_scope([IAMScope.SYSTEM_ADMIN]))])
async def cleanup_heartbeat_expired_locks(
    req: Request,
    user: UserContext = Depends(get_current_user),
) -> Dict[str, str]:
    """Manually trigger cleanup of heartbeat-expired locks (admin only)"""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can trigger heartbeat cleanup"
        )
    
    lock_manager = get_lock_manager()
    await lock_manager.cleanup_heartbeat_expired_locks()
    
    return {"message": "Heartbeat expired locks cleanup completed"}


@router.get("/locks/health-summary", dependencies=[Depends(require_scope([IAMScope.BRANCHES_READ]))])
async def get_locks_health_summary(
    req: Request,
    user: UserContext = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get overall health summary of all locks"""
    lock_manager = get_lock_manager()
    
    all_locks = await lock_manager.list_active_locks()
    
    # Analyze health status
    healthy_locks = 0
    warning_locks = 0
    critical_locks = 0
    heartbeat_enabled_count = 0
    
    lock_details = []
    
    for lock in all_locks:
        health_info = await lock_manager.get_lock_health_status(lock.id)
        if health_info:
            lock_details.append(health_info)
            
            if health_info.get("heartbeat_enabled"):
                heartbeat_enabled_count += 1
                
                health_status = health_info.get("heartbeat_health", "unknown")
                if health_status == "healthy":
                    healthy_locks += 1
                elif health_status == "warning":
                    warning_locks += 1
                elif health_status == "critical":
                    critical_locks += 1
    
    return {
        "total_locks": len(all_locks),
        "heartbeat_enabled_locks": heartbeat_enabled_count,
        "health_summary": {
            "healthy": healthy_locks,
            "warning": warning_locks,
            "critical": critical_locks
        },
        "lock_details": lock_details
    }