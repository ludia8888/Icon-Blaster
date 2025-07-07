import asyncio
import traceback
from typing import Dict, Any, Optional
from datetime import datetime

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
import structlog
from redis.asyncio import Redis

from workers.celery_app import app
from models.job import Job, JobStatus, JobProgress
from core.branch.foundry_branch_service import FoundryBranchService
from core.validation.service import ValidationService
from core.validation.models import ValidationRequest
from core.validation.dependencies import get_validation_service_from_container
from services.job_service import JobService
from bootstrap.providers.redis_provider import RedisProvider
from core.time_travel.service import get_time_travel_service
from core.versioning.version_service import get_version_service
from database.clients.unified_database_client import get_unified_database_client
from common_logging.setup import get_logger

logger = get_logger(__name__)


class MergeTask(Task):
    """Base class for merge tasks with progress tracking"""
    
    def __init__(self):
        self.job_service: Optional[JobService] = None
        self.branch_service: Optional[FoundryBranchService] = None
        self.validation_service: Optional[ValidationService] = None
        self.redis_client: Optional[Redis] = None
    
    async def initialize(self):
        """Initialize all required services by creating them directly."""
        if all([self.job_service, self.branch_service, self.validation_service, self.redis_client]):
            return

        logger.debug("Initializing services for MergeTask directly...")

        self.job_service = JobService()
        await self.job_service.initialize()
        
        redis_provider = RedisProvider()
        self.redis_client = await redis_provider.provide()
        
        self.validation_service = await get_validation_service_from_container()
        time_travel_service = await get_time_travel_service()
        version_service = await get_version_service()
        
        db_client = await get_unified_database_client()
        
        if not db_client.postgres_client:
            raise RuntimeError("Postgres client not available in UnifiedDatabaseClient for FoundryBranchService")
        
        # FoundryBranchService expects a session-like object, which is the Postgres client itself.
        self.branch_service = FoundryBranchService(
            db_session=db_client.postgres_client,
            time_travel_service=time_travel_service,
            version_service=version_service
        )
        
        logger.debug("All services for MergeTask initialized.")

    async def update_progress(self, job_id: str, current_step: str,
                             completed_steps: int, total_steps: int, 
                             message: str, details: Optional[Dict] = None):
        assert self.job_service and self.redis_client
        progress = JobProgress(
            current_step=current_step,
            completed_steps=completed_steps,
            total_steps=total_steps,
            percentage=(completed_steps / total_steps * 100) if total_steps > 0 else 0,
            message=message,
            details=details or {}
        )
        await self.job_service.update_job_progress(job_id, progress)
        channel = f"job:progress:{job_id}"
        await self.redis_client.publish(channel, progress.model_dump_json())


@app.task(bind=True, base=MergeTask, name='workers.tasks.merge.branch_merge')
def branch_merge_task(self, job_id: str, proposal_id: str, 
                     strategy: str, user_id: str,
                     conflict_resolutions: Optional[Dict[str, Any]] = None):
    return asyncio.run(
        _async_branch_merge(
            self, job_id, proposal_id, strategy, 
            user_id, conflict_resolutions
        )
    )


async def _async_branch_merge(task: MergeTask, job_id: str, proposal_id: str,
                             strategy_str: str, user_id: str,
                             conflict_resolutions: Optional[Dict[str, Any]] = None):
    """Async implementation of branch merge with validation."""
    await task.initialize()
    
    assert task.job_service and task.branch_service and task.validation_service and task.redis_client

    job = None
    try:
        job = await task.job_service.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found, aborting task.")
            return

        await task.job_service.update_job_status(job_id=job_id, status=JobStatus.IN_PROGRESS)
        
        source_branch = job.metadata.source_branch
        target_branch = job.metadata.target_branch
        parent_commit = job.metadata.model_extra.get('parent_commit_hash') if job.metadata.model_extra else None

        if not source_branch or not target_branch:
            raise ValueError(f"Job {job_id} metadata is missing source or target branch")

        await task.update_progress(job_id, "checking_branches", 1, 6, "Checking branch status")
        
        source_info = await task.branch_service._get_branch_info(source_branch)
        target_info = await task.branch_service._get_branch_info(target_branch)
        
        if not source_info or not target_info:
            raise ValueError("Source or target branch not found")

        await task.update_progress(job_id, "acquiring_lock", 2, 6, f"Acquiring merge lock for '{target_branch}'")
        
        lock_key = f"merge:lock:{target_branch}"
        async with task.redis_client.lock(lock_key, timeout=300, blocking=False) as lock:
            if not await lock.acquire():
                raise RuntimeError(f"Could not acquire lock for branch {target_branch}.")

            await task.update_progress(job_id, "validating_changes", 3, 6, "Scanning for breaking changes")
            validation_request = ValidationRequest(
                source_branch=source_branch,
                target_branch=target_branch,
                include_impact_analysis=True
            )
            validation_result = await task.validation_service.validate_breaking_changes(validation_request)
            
            if not validation_result.is_valid:
                await task.job_service.fail_job(
                    job_id=job_id,
                    error_message="Merge blocked by breaking changes.",
                    error_stack=validation_result.model_dump_json(indent=2)
                )
                return

            await task.update_progress(job_id, "merging", 4, 6, f"Performing '{strategy_str}' merge")
            
            if not parent_commit:
                raise ValueError("parent_commit_hash is required for a three-way merge")
            
            merge_result = await task.branch_service.merge_branch(
                source_branch=source_branch,
                target_branch=target_branch,
                parent_commit=parent_commit,
                user_id=user_id,
                merge_strategy=strategy_str
            )
            
            await task.update_progress(job_id, "verifying", 5, 6, "Verifying merge result")
            
            if "error" in merge_result:
                raise RuntimeError(f"Merge failed: {merge_result['error']}")
            
            await task.update_progress(job_id, "completed", 6, 6, "Merge completed successfully")
            
            final_result = {"success": True, **merge_result}
            await task.job_service.complete_job(job_id=job_id, result=final_result)
            return final_result

    except Exception as e:
        logger.error("Merge task failed", job_id=job_id, error=str(e), exc_info=True)
        if job and task.job_service:
            await task.job_service.fail_job(job_id=job_id, error_message=str(e), error_stack=traceback.format_exc())
        raise 