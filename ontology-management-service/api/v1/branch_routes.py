"""
Branch Management API
Endpoints for creating, reading, updating, and deleting branches.
"""
from typing import List, Dict, Any, Annotated
from fastapi import APIRouter, Depends, HTTPException, status, Request

from core.auth_utils import UserContext
from core.iam.dependencies import require_scope
from core.iam.iam_integration import IAMScope
from middleware.etag_middleware import enable_etag
from bootstrap.dependencies import get_branch_service, get_job_service
from monitoring.async_merge_metrics import track_api_performance, metrics_collector
from middleware.auth_middleware import get_current_user

# Import models (adjust paths as needed)
try:
    from models.branch import Branch
except ImportError:
    # Fallback for missing models
    Branch = Dict[str, Any]

# Import BranchService
from core.branch.service import BranchService

router = APIRouter(prefix="/branches", tags=["Branch Management"])

@router.get("/", dependencies=[Depends(require_scope([IAMScope.BRANCHES_READ]))])
async def list_branches(
    branch_service: BranchService = Depends(get_branch_service)
):
    """List all branches"""
    return await branch_service.list_branches()

@router.post("/", response_model=Branch, status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_scope([IAMScope.BRANCHES_WRITE]))])
async def create_branch(
    name: str,
    from_branch: str = "main",
    branch_service: BranchService = Depends(get_branch_service)
):
    """Create a new branch"""
    try:
        return await branch_service.create_branch(name=name, from_branch=from_branch)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@router.get("/{branch_name}", response_model=Branch, dependencies=[Depends(require_scope([IAMScope.BRANCHES_READ]))])
async def get_branch(
    branch_name: str,
    branch_service: BranchService = Depends(get_branch_service)
):
    """Get a specific branch by name"""
    branch = await branch_service.get_branch(branch_name)
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
    return branch

@router.get("/{branch_id}", dependencies=[Depends(require_scope([IAMScope.BRANCHES_READ]))])
@enable_etag(
    resource_type_func=lambda params: "branch",
    resource_id_func=lambda params: params["branch_id"],
    branch_func=lambda params: params["branch_id"]
)
async def get_branch_by_id(
    branch_id: str,
    req: Request,
    current_user: Annotated[UserContext, Depends(get_current_user)],
    branch_service: BranchService = Depends(get_branch_service)
) -> Dict[str, Any]:
    """Get details of a specific branch."""
    branch = await branch_service.get_branch(branch_id)
    if not branch:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Branch not found")
    return branch

# --- Proposal Routes ---

@router.get("/{branch_id}/proposals", dependencies=[Depends(require_scope([IAMScope.PROPOSALS_READ]))])
@enable_etag(
    resource_type_func=lambda params: "proposals_collection",
    resource_id_func=lambda params: f"{params['branch_id']}_proposals",
    branch_func=lambda params: params['branch_id']
)
async def list_proposals(
    branch_id: str,
    req: Request,
    current_user: Annotated[UserContext, Depends(get_current_user)],
    branch_service: BranchService = Depends(get_branch_service)
) -> List[Dict[str, Any]]:
    """List all proposals for a specific branch."""
    return await branch_service.list_proposals(branch_name=branch_id)

@router.get("/{branch_id}/proposals/{proposal_id}", dependencies=[Depends(require_scope([IAMScope.PROPOSALS_READ]))])
@enable_etag(
    resource_type_func=lambda params: "proposal",
    resource_id_func=lambda params: params["proposal_id"],
    branch_func=lambda params: params['branch_id']
)
async def get_proposal(
    branch_id: str,
    proposal_id: str,
    req: Request,
    current_user: Annotated[UserContext, Depends(get_current_user)],
    branch_service: BranchService = Depends(get_branch_service)
) -> Dict[str, Any]:
    """Get details of a specific proposal."""
    proposal = await branch_service.get_proposal(proposal_id=proposal_id)
    if not proposal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proposal not found")
    # Ensure the proposal belongs to the correct branch
    if proposal.get("branch") != branch_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Proposal {proposal_id} not found in branch {branch_id}")
    return proposal

# ===================================
# ASYNC MERGE ENDPOINTS
# ===================================

@router.post("/{branch_id}/proposals/{proposal_id}/merge", status_code=status.HTTP_202_ACCEPTED, dependencies=[Depends(require_scope([IAMScope.PROPOSALS_WRITE]))])
@track_api_performance("merge_proposal_async", "POST")
async def merge_proposal_async(
    branch_id: str,
    proposal_id: str,
    merge_request: Dict[str, Any],
    req: Request,
    current_user: Annotated[UserContext, Depends(get_current_user)],
    job_service: Annotated[Any, Depends(get_job_service)]
) -> Dict[str, Any]:
    """
    Queue branch merge operation for background processing
    Returns immediately with job ID for tracking
    """
    from models.job import JobType, JobPriority
    from workers.tasks.merge import branch_merge_task
    
    # Validate merge request
    strategy = merge_request.get("strategy", "merge")
    if strategy not in ["merge", "squash", "rebase"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid merge strategy: {strategy}"
        )
    
    conflict_resolutions = merge_request.get("conflict_resolutions")
    idempotency_key = merge_request.get("idempotency_key")
    
    # Create job (service already initialized via DI)
    
    job = await job_service.create_job(
        job_type=JobType.BRANCH_MERGE,
        created_by=current_user.user_id,
        metadata={
            "proposal_id": proposal_id,
            "source_branch": branch_id,
            "merge_strategy": strategy,
            "conflict_resolutions": conflict_resolutions
        },
        priority=JobPriority.HIGH,
        idempotency_key=idempotency_key,
        tenant_id=current_user.tenant_id
    )
    
    # Queue the task
    task = branch_merge_task.delay(
        job_id=job.id,
        proposal_id=proposal_id,
        strategy=strategy,
        user_id=current_user.user_id,
        conflict_resolutions=conflict_resolutions
    )
    
    # Update job with Celery task ID
    job.celery_task_id = task.id
    await job_service._save_job(job)
    
    # Record metrics
    metrics_collector.record_job_request("BRANCH_MERGE", strategy)
    
    return {
        "job_id": job.id,
        "celery_task_id": task.id,
        "status": "queued",
        "message": f"Merge operation queued for proposal {proposal_id}",
        "tracking_url": f"/api/v1/jobs/{job.id}",
        "estimated_duration_minutes": 5  # Rough estimate
    }

@router.get("/jobs/{job_id}", dependencies=[Depends(require_scope([IAMScope.PROPOSALS_READ]))])
async def get_job_status(
    job_id: str,
    req: Request,
    current_user: Annotated[UserContext, Depends(get_current_user)],
    job_service: Annotated[Any, Depends(get_job_service)]
) -> Dict[str, Any]:
    """Get job status and progress"""
    
    job = await job_service.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
    
    # Check permissions
    if job.created_by != current_user.user_id and not current_user.roles.get("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    response = {
        "job_id": job.id,
        "type": job.type,
        "status": job.status,
        "progress": {
            "current_step": job.progress.current_step,
            "completed_steps": job.progress.completed_steps,
            "total_steps": job.progress.total_steps,
            "percentage": job.progress.percentage,
            "message": job.progress.message
        },
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "result": job.result
    }
    
    # Add error details if failed
    if job.status == "failed":
        response["error"] = {
            "message": job.metadata.error_message,
            "retry_count": job.metadata.retry_count,
            "can_retry": job.can_retry()
        }
    
    return response

@router.post("/jobs/{job_id}/cancel", dependencies=[Depends(require_scope([IAMScope.PROPOSALS_WRITE]))])
async def cancel_job(
    job_id: str,
    req: Request,
    current_user: Annotated[UserContext, Depends(get_current_user)],
    job_service: Annotated[Any, Depends(get_job_service)]
) -> Dict[str, Any]:
    """Cancel a running job"""
    from workers.celery_app import app as celery_app
    
    job = await job_service.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job {job_id} not found"
        )
    
    # Check permissions
    if job.created_by != current_user.user_id and not current_user.roles.get("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # Check if job can be cancelled
    if job.is_terminal():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Job is already {job.status} and cannot be cancelled"
        )
    
    # Cancel Celery task if exists
    if job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=True)
    
    # Update job status
    await job_service.update_job_status(job_id, "cancelled", "Cancelled by user")
    
    return {
        "job_id": job_id,
        "status": "cancelled",
        "message": "Job cancelled successfully"
    }

# Legacy merge endpoint (deprecated but kept for backward compatibility)
@router.post("/{branch_id}/proposals/{proposal_id}/merge-sync", deprecated=True, dependencies=[Depends(require_scope([IAMScope.PROPOSALS_WRITE]))])
async def merge_proposal_sync(
    branch_id: str,
    proposal_id: str,
    merge_request: Dict[str, Any],
    req: Request,
    current_user: Annotated[UserContext, Depends(get_current_user)],
    branch_service: BranchService = Depends(get_branch_service)
) -> Dict[str, Any]:
    """
    (DEPRECATED) Synchronously merge a proposal.
    This is kept for backward compatibility and simple test cases.
    """
    import warnings
    warnings.warn(
        "Synchronous merge is deprecated. Use POST /merge for async processing.",
        DeprecationWarning,
        stacklevel=2
    )
    
    # This is the old synchronous implementation
    # We keep it but add warnings and recommend the async version
    strategy = merge_request.get("strategy", "merge")
    conflict_resolutions = merge_request.get("conflict_resolutions")
    
    try:
        result = await branch_service.merge_branch(
            proposal_id=proposal_id,
            strategy=strategy,
            user_id=current_user.user_id,
            conflict_resolutions=conflict_resolutions
        )
        
        return {
            "success": result.success,
            "merged_commit": result.merged_commit_hash,
            "conflicts": result.conflicts,
            "deprecation_warning": "This endpoint is deprecated. Use POST /merge for async processing."
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Merge failed: {str(e)}"
        )
    return proposal 