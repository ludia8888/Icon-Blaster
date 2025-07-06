"""
Merge Tasks for Background Processing
Handles branch merge operations asynchronously
"""
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
import structlog

from workers.celery_app import app
from models.job import Job, JobStatus, JobProgress
from core.branch.service import BranchService
from core.branch.models import MergeStrategy
from services.job_service import JobService
from bootstrap.dependencies import get_branch_service, get_redis_client
from common_logging.setup import get_logger

logger = get_logger(__name__)


class MergeTask(Task):
    """Base class for merge tasks with progress tracking"""
    
    def __init__(self):
        self.job_service: Optional[JobService] = None
        self.branch_service: Optional[BranchService] = None
        self.redis_client = None
    
    async def initialize(self):
        """Initialize services"""
        if not self.job_service:
            self.job_service = JobService()
            await self.job_service.initialize()
        
        if not self.branch_service:
            # Get branch service through dependency injection
            from bootstrap.providers import BranchProvider
            provider = BranchProvider()
            self.branch_service = await provider.provide()
        
        if not self.redis_client:
            from bootstrap.providers import RedisProvider
            provider = RedisProvider()
            self.redis_client = await provider.provide()
    
    async def update_progress(self, job_id: str, current_step: str, 
                            completed_steps: int, total_steps: int, 
                            message: str, details: Optional[Dict] = None):
        """Update job progress"""
        progress = JobProgress(
            current_step=current_step,
            completed_steps=completed_steps,
            total_steps=total_steps,
            percentage=(completed_steps / total_steps * 100) if total_steps > 0 else 0,
            message=message,
            details=details or {}
        )
        
        await self.job_service.update_job_progress(job_id, progress)
        
        # Also publish to Redis for real-time updates
        channel = f"job:progress:{job_id}"
        await self.redis_client.publish(channel, progress.json())


@app.task(bind=True, base=MergeTask, name='workers.tasks.merge.branch_merge')
def branch_merge_task(self, job_id: str, proposal_id: str, 
                     strategy: str, user_id: str,
                     conflict_resolutions: Optional[Dict[str, Any]] = None):
    """
    Execute branch merge in background
    
    Args:
        job_id: Job tracking ID
        proposal_id: Merge proposal ID
        strategy: Merge strategy (merge, squash, rebase)
        user_id: User performing the merge
        conflict_resolutions: Optional conflict resolution data
    """
    # Run async code in sync context
    return asyncio.run(
        _async_branch_merge(
            self, job_id, proposal_id, strategy, 
            user_id, conflict_resolutions
        )
    )


async def _async_branch_merge(task: MergeTask, job_id: str, proposal_id: str,
                             strategy_str: str, user_id: str,
                             conflict_resolutions: Optional[Dict[str, Any]] = None):
    """Async implementation of branch merge"""
    
    await task.initialize()
    
    try:
        # Update job status to in_progress
        await task.job_service.update_job_status(job_id, JobStatus.IN_PROGRESS)
        
        # Step 1: Validate proposal
        await task.update_progress(
            job_id, "validating_proposal", 1, 6,
            "Validating merge proposal"
        )
        
        proposal = await task.branch_service.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        
        # Step 2: Check branch status
        await task.update_progress(
            job_id, "checking_branches", 2, 6,
            "Checking branch status"
        )
        
        source_info = await task.branch_service._get_branch_info(proposal.source_branch)
        target_info = await task.branch_service._get_branch_info(proposal.target_branch)
        
        if not source_info or not target_info:
            raise ValueError("Source or target branch not found")
        
        # Step 3: Acquire distributed lock
        await task.update_progress(
            job_id, "acquiring_lock", 3, 6,
            "Acquiring merge lock"
        )
        
        lock_key = f"merge:lock:{proposal.target_branch}"
        lock_acquired = await acquire_distributed_lock(
            task.redis_client, lock_key, timeout=300  # 5 minutes
        )
        
        if not lock_acquired:
            raise RuntimeError(
                f"Could not acquire lock for branch {proposal.target_branch}. "
                "Another merge may be in progress."
            )
        
        try:
            # Step 4: Perform merge
            await task.update_progress(
                job_id, "merging", 4, 6,
                f"Performing {strategy_str} merge",
                {"source": proposal.source_branch, "target": proposal.target_branch}
            )
            
            strategy = MergeStrategy(strategy_str)
            merge_result = await task.branch_service.merge_branch(
                proposal_id=proposal_id,
                strategy=strategy,
                user_id=user_id,
                conflict_resolutions=conflict_resolutions
            )
            
            # Step 5: Verify merge
            await task.update_progress(
                job_id, "verifying", 5, 6,
                "Verifying merge result"
            )
            
            if not merge_result.success:
                raise RuntimeError(
                    f"Merge failed: {merge_result.conflicts}"
                )
            
            # Step 6: Complete
            await task.update_progress(
                job_id, "completed", 6, 6,
                "Merge completed successfully"
            )
            
            # Update job with result
            result = {
                "success": True,
                "merged_commit": merge_result.merged_commit_hash,
                "proposal_id": proposal_id,
                "strategy": strategy_str,
                "merged_at": datetime.utcnow().isoformat()
            }
            
            await task.job_service.complete_job(job_id, result)
            
            logger.info(
                "Merge completed successfully",
                job_id=job_id,
                proposal_id=proposal_id,
                result=result
            )
            
            return result
            
        finally:
            # Always release lock
            await release_distributed_lock(task.redis_client, lock_key)
    
    except SoftTimeLimitExceeded:
        # Handle timeout gracefully
        error_msg = "Merge operation timed out"
        logger.error(error_msg, job_id=job_id, proposal_id=proposal_id)
        
        await task.job_service.fail_job(
            job_id, 
            error_message=error_msg,
            error_stack="Task exceeded time limit"
        )
        
        raise
    
    except Exception as e:
        # Handle failure
        logger.error(
            "Merge failed",
            job_id=job_id,
            proposal_id=proposal_id,
            error=str(e),
            exc_info=True
        )
        
        await task.job_service.fail_job(
            job_id,
            error_message=str(e),
            error_stack=traceback.format_exc()
        )
        
        # Check if we should retry
        job = await task.job_service.get_job(job_id)
        if job and job.can_retry():
            # Schedule retry
            raise branch_merge_task.retry(
                countdown=60 * (job.metadata.retry_count + 1),  # Exponential backoff
                max_retries=job.metadata.max_retries
            )
        
        raise


async def acquire_distributed_lock(redis_client, key: str, timeout: int = 60) -> bool:
    """
    Acquire distributed lock using Redis
    
    Args:
        redis_client: Redis client
        key: Lock key
        timeout: Lock timeout in seconds
    
    Returns:
        True if lock acquired, False otherwise
    """
    import uuid
    
    lock_id = str(uuid.uuid4())
    lock_key = f"lock:{key}"
    
    # Try to acquire lock with NX (only if not exists) and EX (expire time)
    acquired = await redis_client.set(
        lock_key, lock_id, 
        nx=True,  # Only set if not exists
        ex=timeout  # Expire after timeout
    )
    
    if acquired:
        # Store lock ID for this task
        await redis_client.set(f"{lock_key}:owner", lock_id, ex=timeout)
    
    return bool(acquired)


async def release_distributed_lock(redis_client, key: str):
    """Release distributed lock"""
    lock_key = f"lock:{key}"
    owner_key = f"{lock_key}:owner"
    
    # Get lock owner
    owner_id = await redis_client.get(owner_key)
    
    if owner_id:
        # Only delete if we own the lock
        current_owner = await redis_client.get(lock_key)
        if current_owner and current_owner.decode() == owner_id.decode():
            await redis_client.delete(lock_key)
            await redis_client.delete(owner_key)


# Import required for traceback
import traceback