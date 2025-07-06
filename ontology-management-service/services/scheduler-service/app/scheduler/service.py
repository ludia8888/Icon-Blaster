"""Scheduler service implementation using APScheduler."""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Callable
from uuid import uuid4

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.events import (
    EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED,
    JobExecutionEvent
)
from apscheduler.job import Job as APJob
import aioredis
import pytz

from .models import (
    Job, JobExecution, JobStatus, ExecutionStatus,
    CronSchedule, IntervalSchedule, OneTimeSchedule
)
from .executors import JobExecutor

logger = logging.getLogger(__name__)


class SchedulerService:
    """APScheduler-based job scheduling service."""
    
    def __init__(self, redis_url: str = "redis://localhost:6379/6"):
        self.redis_url = redis_url
        self.redis: Optional[aioredis.Redis] = None
        self.scheduler = AsyncIOScheduler(
            job_defaults={
                'coalesce': True,
                'max_instances': 1,
                'misfire_grace_time': 30
            }
        )
        self.executor = JobExecutor()
        self._is_initialized = False
        
        # Register event listeners
        self.scheduler.add_listener(
            self._on_job_executed,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED
        )
    
    async def initialize(self):
        """Initialize the scheduler service."""
        if self._is_initialized:
            return
        
        # Connect to Redis
        self.redis = await aioredis.from_url(self.redis_url, decode_responses=True)
        
        # Start scheduler
        self.scheduler.start()
        
        # Restore jobs from Redis
        await self._restore_jobs()
        
        self._is_initialized = True
        logger.info("Scheduler service initialized")
    
    async def shutdown(self):
        """Shutdown the scheduler service."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        
        if self.redis:
            await self.redis.close()
        
        self._is_initialized = False
        logger.info("Scheduler service shutdown")
    
    async def create_job(self, job: Job) -> Job:
        """Create a new scheduled job."""
        if not job.id:
            job.id = str(uuid4())
        
        # Save job to Redis
        await self._save_job(job)
        
        # Schedule job if enabled
        if job.enabled:
            self._schedule_job(job)
        
        logger.info(f"Created job: {job.id}")
        return job
    
    async def get_job(self, job_id: str) -> Optional[Job]:
        """Get a job by ID."""
        job_data = await self.redis.hget("scheduler:jobs", job_id)
        if not job_data:
            return None
        
        return Job.parse_raw(job_data)
    
    async def update_job(self, job_id: str, job: Job) -> Optional[Job]:
        """Update an existing job."""
        existing_job = await self.get_job(job_id)
        if not existing_job:
            return None
        
        job.id = job_id
        job.created_at = existing_job.created_at
        job.updated_at = datetime.now(timezone.utc)
        
        # Save updated job
        await self._save_job(job)
        
        # Reschedule job
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
        
        if job.enabled:
            self._schedule_job(job)
        
        logger.info(f"Updated job: {job_id}")
        return job
    
    async def delete_job(self, job_id: str) -> bool:
        """Delete a job."""
        # Remove from scheduler
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
        
        # Remove from Redis
        await self.redis.hdel("scheduler:jobs", job_id)
        await self.redis.delete(f"scheduler:history:{job_id}")
        
        logger.info(f"Deleted job: {job_id}")
        return True
    
    async def list_jobs(
        self,
        page: int = 1,
        page_size: int = 50,
        tags: Optional[List[str]] = None,
        status: Optional[str] = None,
        enabled_only: bool = False
    ) -> tuple[List[Job], int]:
        """List jobs with filtering and pagination."""
        # Get all jobs from Redis
        all_jobs_data = await self.redis.hgetall("scheduler:jobs")
        all_jobs = [Job.parse_raw(data) for data in all_jobs_data.values()]
        
        # Filter jobs
        filtered_jobs = []
        for job in all_jobs:
            if enabled_only and not job.enabled:
                continue
            
            if tags and not any(tag in job.config.tags for tag in tags):
                continue
            
            if status and job.status != status:
                continue
            
            filtered_jobs.append(job)
        
        # Sort by created_at descending
        filtered_jobs.sort(key=lambda x: x.created_at, reverse=True)
        
        # Paginate
        total = len(filtered_jobs)
        start = (page - 1) * page_size
        end = start + page_size
        
        return filtered_jobs[start:end], total
    
    async def run_job(self, job_id: str, override_parameters: Optional[Dict] = None) -> str:
        """Manually trigger a job execution."""
        job = await self.get_job(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        
        # Create execution record
        execution = JobExecution(
            id=str(uuid4()),
            job_id=job_id,
            started_at=datetime.now(timezone.utc),
            status=ExecutionStatus.RUNNING
        )
        
        # Save execution
        await self._save_execution(execution)
        
        # Run job asynchronously
        asyncio.create_task(self._execute_job(job, execution, override_parameters))
        
        return execution.id
    
    async def get_job_status(self, job_id: str) -> Optional[Dict]:
        """Get current status of a job."""
        job = await self.get_job(job_id)
        if not job:
            return None
        
        # Get APScheduler job
        ap_job = self.scheduler.get_job(job_id)
        
        # Get current execution if any
        current_execution = None
        executions = await self._get_job_executions(job_id, limit=1)
        if executions and executions[0].status == ExecutionStatus.RUNNING:
            current_execution = executions[0]
        
        return {
            "job_id": job_id,
            "status": job.status,
            "current_execution": current_execution,
            "next_run_time": ap_job.next_run_time if ap_job else None
        }
    
    async def get_job_history(
        self,
        job_id: str,
        limit: int = 50,
        status_filter: Optional[str] = None
    ) -> List[JobExecution]:
        """Get execution history for a job."""
        executions = await self._get_job_executions(job_id, limit=limit * 2)
        
        # Filter by status if specified
        if status_filter:
            executions = [e for e in executions if e.status == status_filter]
        
        return executions[:limit]
    
    async def pause_jobs(self, job_ids: Optional[List[str]] = None) -> int:
        """Pause specified jobs or all jobs."""
        count = 0
        
        if job_ids:
            for job_id in job_ids:
                if self.scheduler.get_job(job_id):
                    self.scheduler.pause_job(job_id)
                    job = await self.get_job(job_id)
                    if job:
                        job.status = JobStatus.PAUSED
                        await self._save_job(job)
                        count += 1
        else:
            # Pause all jobs
            self.scheduler.pause()
            all_jobs_data = await self.redis.hgetall("scheduler:jobs")
            for job_data in all_jobs_data.values():
                job = Job.parse_raw(job_data)
                job.status = JobStatus.PAUSED
                await self._save_job(job)
                count += 1
        
        return count
    
    async def resume_jobs(self, job_ids: Optional[List[str]] = None) -> int:
        """Resume specified jobs or all jobs."""
        count = 0
        
        if job_ids:
            for job_id in job_ids:
                if self.scheduler.get_job(job_id):
                    self.scheduler.resume_job(job_id)
                    job = await self.get_job(job_id)
                    if job:
                        job.status = JobStatus.ACTIVE
                        await self._save_job(job)
                        count += 1
        else:
            # Resume all jobs
            self.scheduler.resume()
            all_jobs_data = await self.redis.hgetall("scheduler:jobs")
            for job_data in all_jobs_data.values():
                job = Job.parse_raw(job_data)
                if job.enabled:
                    job.status = JobStatus.ACTIVE
                    await self._save_job(job)
                    count += 1
        
        return count
    
    async def get_scheduler_status(self) -> Dict:
        """Get overall scheduler status."""
        all_jobs_data = await self.redis.hgetall("scheduler:jobs")
        all_jobs = [Job.parse_raw(data) for data in all_jobs_data.values()]
        
        active_jobs = sum(1 for j in all_jobs if j.status == JobStatus.ACTIVE)
        paused_jobs = sum(1 for j in all_jobs if j.status == JobStatus.PAUSED)
        
        # Count running executions
        running_executions = 0
        for job in all_jobs:
            executions = await self._get_job_executions(job.id, limit=1)
            if executions and executions[0].status == ExecutionStatus.RUNNING:
                running_executions += 1
        
        return {
            "is_running": self.scheduler.running,
            "total_jobs": len(all_jobs),
            "active_jobs": active_jobs,
            "paused_jobs": paused_jobs,
            "running_executions": running_executions,
            "server_time": datetime.now(timezone.utc)
        }
    
    def _schedule_job(self, job: Job):
        """Schedule a job with APScheduler."""
        # Create trigger based on schedule type
        if isinstance(job.schedule, CronSchedule):
            trigger = CronTrigger.from_crontab(
                job.schedule.cron_expression,
                timezone=pytz.timezone(job.schedule.timezone or "UTC")
            )
        elif isinstance(job.schedule, IntervalSchedule):
            trigger = IntervalTrigger(
                seconds=job.schedule.interval_seconds,
                start_date=job.schedule.start_time
            )
        elif isinstance(job.schedule, OneTimeSchedule):
            trigger = DateTrigger(run_date=job.schedule.run_at)
        else:
            raise ValueError(f"Unknown schedule type: {type(job.schedule)}")
        
        # Add job to scheduler
        self.scheduler.add_job(
            self._job_wrapper,
            trigger,
            id=job.id,
            name=job.name,
            kwargs={"job_id": job.id},
            replace_existing=True,
            misfire_grace_time=30
        )
        
        # Update job status
        job.status = JobStatus.ACTIVE
        job.next_run_time = self.scheduler.get_job(job.id).next_run_time
    
    async def _job_wrapper(self, job_id: str):
        """Wrapper function executed by APScheduler."""
        job = await self.get_job(job_id)
        if not job:
            logger.error(f"Job not found: {job_id}")
            return
        
        # Create execution record
        execution = JobExecution(
            id=str(uuid4()),
            job_id=job_id,
            started_at=datetime.now(timezone.utc),
            status=ExecutionStatus.RUNNING
        )
        
        # Save execution
        await self._save_execution(execution)
        
        # Execute job
        await self._execute_job(job, execution)
    
    async def _execute_job(
        self,
        job: Job,
        execution: JobExecution,
        override_parameters: Optional[Dict] = None
    ):
        """Execute a job and update execution record."""
        try:
            # Merge parameters
            parameters = job.config.parameters.copy()
            if override_parameters:
                parameters.update(override_parameters)
            
            # Execute job
            result = await self.executor.execute(
                job_type=job.config.job_type,
                parameters=parameters,
                timeout=job.config.timeout_seconds
            )
            
            # Update execution record
            execution.finished_at = datetime.now(timezone.utc)
            execution.status = ExecutionStatus.SUCCESS
            execution.result = result
            
            # Update job
            job.last_run_time = execution.started_at
            await self._save_job(job)
            
        except Exception as e:
            logger.error(f"Job execution failed: {job_id}", exc_info=True)
            
            # Update execution record
            execution.finished_at = datetime.now(timezone.utc)
            execution.status = ExecutionStatus.FAILED
            execution.error_message = str(e)
            
            # Retry if configured
            if execution.retry_count < job.config.max_retries:
                execution.retry_count += 1
                await asyncio.sleep(job.config.retry_delay_seconds)
                await self._execute_job(job, execution, override_parameters)
                return
        
        finally:
            # Save execution
            await self._save_execution(execution)
    
    async def _save_job(self, job: Job):
        """Save job to Redis."""
        await self.redis.hset(
            "scheduler:jobs",
            job.id,
            job.json()
        )
    
    async def _save_execution(self, execution: JobExecution):
        """Save execution to Redis."""
        key = f"scheduler:history:{execution.job_id}"
        
        # Add to sorted set (score is timestamp)
        await self.redis.zadd(
            key,
            {execution.json(): execution.started_at.timestamp()}
        )
        
        # Trim to keep only recent history
        await self.redis.zremrangebyrank(key, 0, -1001)  # Keep last 1000
    
    async def _get_job_executions(
        self,
        job_id: str,
        limit: int = 50
    ) -> List[JobExecution]:
        """Get job executions from Redis."""
        key = f"scheduler:history:{job_id}"
        
        # Get recent executions
        executions_data = await self.redis.zrevrange(key, 0, limit - 1)
        
        executions = []
        for data in executions_data:
            try:
                executions.append(JobExecution.parse_raw(data))
            except Exception as e:
                logger.error(f"Failed to parse execution: {e}")
        
        return executions
    
    async def _restore_jobs(self):
        """Restore jobs from Redis on startup."""
        all_jobs_data = await self.redis.hgetall("scheduler:jobs")
        
        for job_data in all_jobs_data.values():
            try:
                job = Job.parse_raw(job_data)
                if job.enabled and job.status == JobStatus.ACTIVE:
                    self._schedule_job(job)
                    logger.info(f"Restored job: {job.id}")
            except Exception as e:
                logger.error(f"Failed to restore job: {e}")
    
    def _on_job_executed(self, event: JobExecutionEvent):
        """Handle job execution events from APScheduler."""
        if event.exception:
            logger.error(
                f"Job {event.job_id} crashed: {event.exception}",
                exc_info=(type(event.exception), event.exception, event.exception.__traceback__)
            )
        else:
            logger.info(f"Job {event.job_id} executed successfully")