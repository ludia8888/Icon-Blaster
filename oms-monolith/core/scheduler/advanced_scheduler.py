"""
Enterprise-grade Advanced Scheduler
Distributed task scheduling with persistence, monitoring, and fault tolerance
"""

import asyncio
import json
import pickle
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, List, Optional, Union, Coroutine
from enum import Enum
from dataclasses import dataclass, field
import croniter
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.events import (
    EVENT_JOB_EXECUTED, EVENT_JOB_ERROR, EVENT_JOB_MISSED,
    EVENT_JOB_SUBMITTED, EVENT_JOB_REMOVED, EVENT_JOB_MODIFIED
)

from database.clients import RedisHAClient
from utils import logging
from shared.observability import metrics, tracing
from shared.audit.audit_logger import AuditLogger

logger = logging.get_logger(__name__)
tracer = tracing.get_tracer(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    MISSED = "missed"
    PAUSED = "paused"


class JobPriority(int, Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class JobMetadata:
    """Extended job metadata"""
    job_id: str
    name: str
    description: Optional[str] = None
    category: str = "general"
    owner: str = "system"
    priority: JobPriority = JobPriority.NORMAL
    max_retries: int = 3
    retry_delay: int = 60  # seconds
    timeout: int = 300  # seconds
    tags: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)  # Job IDs
    notify_on_failure: List[str] = field(default_factory=list)  # Email addresses
    notify_on_success: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None


@dataclass
class JobExecution:
    """Job execution record"""
    execution_id: str
    job_id: str
    status: JobStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result: Optional[Any] = None
    duration: Optional[float] = None
    retry_count: int = 0
    worker_id: Optional[str] = None


class JobExecutionContext:
    """Context passed to job functions"""
    def __init__(
        self,
        job_id: str,
        execution_id: str,
        metadata: JobMetadata,
        scheduler: 'EnterpriseScheduler'
    ):
        self.job_id = job_id
        self.execution_id = execution_id
        self.metadata = metadata
        self.scheduler = scheduler
        self.logger = logging.get_logger(f"job.{job_id}")
        self._cancelled = False
        
    async def checkpoint(self, state: Dict[str, Any]):
        """Save job checkpoint for resumption"""
        await self.scheduler.save_checkpoint(self.job_id, self.execution_id, state)
    
    async def update_progress(self, progress: int, message: Optional[str] = None):
        """Update job progress (0-100)"""
        await self.scheduler.update_job_progress(
            self.job_id, self.execution_id, progress, message
        )
    
    def is_cancelled(self) -> bool:
        """Check if job is cancelled"""
        return self._cancelled
    
    async def emit_event(self, event_type: str, data: Dict[str, Any]):
        """Emit custom job event"""
        await self.scheduler.emit_job_event(self.job_id, event_type, data)


class EnterpriseScheduler:
    """
    Enterprise-grade job scheduler with:
    - Distributed execution
    - Job persistence
    - Dependency management
    - Monitoring and alerting
    - Fault tolerance
    - Job prioritization
    - Resource limits
    """
    
    def __init__(
        self,
        redis_client: RedisHAClient,
        worker_id: Optional[str] = None,
        max_workers: int = 10,
        job_defaults: Optional[Dict] = None,
        timezone: str = "UTC"
    ):
        self.redis_client = redis_client
        self.worker_id = worker_id or str(uuid.uuid4())
        self.max_workers = max_workers
        self.timezone = timezone
        
        # Job registry
        self._job_functions: Dict[str, Callable] = {}
        self._job_metadata: Dict[str, JobMetadata] = {}
        
        # Execution tracking
        self._running_jobs: Dict[str, asyncio.Task] = {}
        self._execution_semaphore = asyncio.Semaphore(max_workers)
        
        # APScheduler setup
        jobstores = {
            'default': RedisJobStore(
                db=0,
                jobs_key='apscheduler.jobs',
                run_times_key='apscheduler.run_times',
                redis=redis_client._get_connection()
            )
        }
        
        executors = {
            'default': AsyncIOExecutor()
        }
        
        job_defaults = job_defaults or {
            'coalesce': True,
            'max_instances': 3,
            'misfire_grace_time': 30
        }
        
        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=timezone
        )
        
        # Event listeners
        self.scheduler.add_listener(
            self._on_job_event,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED |
            EVENT_JOB_SUBMITTED | EVENT_JOB_REMOVED | EVENT_JOB_MODIFIED
        )
        
        # Metrics
        self.job_counter = metrics.Counter(
            'scheduler_jobs_total',
            'Total scheduled jobs',
            ['status', 'category']
        )
        self.job_duration = metrics.Histogram(
            'scheduler_job_duration_seconds',
            'Job execution duration',
            ['job_name', 'status']
        )
        self.active_jobs = metrics.Gauge(
            'scheduler_active_jobs',
            'Currently running jobs'
        )
        self.job_queue_size = metrics.Gauge(
            'scheduler_queue_size',
            'Number of pending jobs',
            ['priority']
        )
        
        # Audit logger
        self.audit_logger = AuditLogger()
    
    async def start(self):
        """Start the scheduler"""
        logger.info(f"Starting scheduler with worker_id: {self.worker_id}")
        
        # Register worker
        await self._register_worker()
        
        # Start APScheduler
        self.scheduler.start()
        
        # Start background tasks
        asyncio.create_task(self._monitor_jobs())
        asyncio.create_task(self._cleanup_old_executions())
        asyncio.create_task(self._process_dependencies())
        
        logger.info("Scheduler started successfully")
    
    async def shutdown(self, wait: bool = True):
        """Shutdown the scheduler"""
        logger.info("Shutting down scheduler...")
        
        # Cancel running jobs
        for job_id, task in self._running_jobs.items():
            task.cancel()
        
        # Wait for jobs to complete
        if wait and self._running_jobs:
            await asyncio.gather(
                *self._running_jobs.values(),
                return_exceptions=True
            )
        
        # Shutdown APScheduler
        self.scheduler.shutdown(wait=wait)
        
        # Unregister worker
        await self._unregister_worker()
        
        logger.info("Scheduler shutdown complete")
    
    def register_job(
        self,
        func: Callable,
        job_id: Optional[str] = None,
        name: Optional[str] = None,
        **metadata_kwargs
    ):
        """Register a job function"""
        job_id = job_id or func.__name__
        name = name or func.__name__
        
        # Store function
        self._job_functions[job_id] = func
        
        # Create metadata
        metadata = JobMetadata(
            job_id=job_id,
            name=name,
            **metadata_kwargs
        )
        self._job_metadata[job_id] = metadata
        
        logger.info(f"Registered job: {job_id}")
        
        return job_id
    
    async def schedule_job(
        self,
        job_id: str,
        trigger: Union[str, CronTrigger, IntervalTrigger, DateTrigger],
        args: Optional[List] = None,
        kwargs: Optional[Dict] = None,
        **scheduler_kwargs
    ) -> str:
        """Schedule a job"""
        with tracer.start_as_current_span("schedule_job") as span:
            span.set_attribute("job.id", job_id)
            span.set_attribute("trigger", str(trigger))
            
            if job_id not in self._job_functions:
                raise ValueError(f"Job {job_id} not registered")
            
            # Parse trigger
            if isinstance(trigger, str):
                if trigger.startswith("cron:"):
                    trigger = CronTrigger.from_crontab(trigger[5:])
                elif trigger.startswith("interval:"):
                    parts = trigger[9:].split(":")
                    trigger = IntervalTrigger(**{parts[0]: int(parts[1])})
                elif trigger.startswith("date:"):
                    trigger = DateTrigger(run_date=trigger[5:])
            
            # Add job to scheduler
            job = self.scheduler.add_job(
                self._execute_job,
                trigger=trigger,
                args=[job_id, args or [], kwargs or {}],
                id=f"{job_id}_{uuid.uuid4().hex[:8]}",
                name=self._job_metadata[job_id].name,
                **scheduler_kwargs
            )
            
            # Store job metadata
            await self._save_job_metadata(job.id, self._job_metadata[job_id])
            
            # Audit log
            await self.audit_logger.log_event(
                user_id=self._job_metadata[job_id].owner,
                action="job.scheduled",
                resource=f"job:{job.id}",
                details={
                    "job_id": job_id,
                    "trigger": str(trigger),
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None
                }
            )
            
            self.job_counter.labels(
                status="scheduled",
                category=self._job_metadata[job_id].category
            ).inc()
            
            return job.id
    
    async def schedule_one_time_job(
        self,
        job_id: str,
        run_date: Union[str, datetime],
        args: Optional[List] = None,
        kwargs: Optional[Dict] = None,
        **scheduler_kwargs
    ) -> str:
        """Schedule a one-time job"""
        if isinstance(run_date, str):
            run_date = datetime.fromisoformat(run_date)
        
        return await self.schedule_job(
            job_id,
            DateTrigger(run_date=run_date),
            args,
            kwargs,
            **scheduler_kwargs
        )
    
    async def schedule_recurring_job(
        self,
        job_id: str,
        cron_expression: str,
        args: Optional[List] = None,
        kwargs: Optional[Dict] = None,
        **scheduler_kwargs
    ) -> str:
        """Schedule a recurring job with cron expression"""
        return await self.schedule_job(
            job_id,
            CronTrigger.from_crontab(cron_expression),
            args,
            kwargs,
            **scheduler_kwargs
        )
    
    async def pause_job(self, scheduled_job_id: str):
        """Pause a scheduled job"""
        self.scheduler.pause_job(scheduled_job_id)
        await self._update_job_status(scheduled_job_id, JobStatus.PAUSED)
    
    async def resume_job(self, scheduled_job_id: str):
        """Resume a paused job"""
        self.scheduler.resume_job(scheduled_job_id)
        await self._update_job_status(scheduled_job_id, JobStatus.PENDING)
    
    async def cancel_job(self, scheduled_job_id: str):
        """Cancel a scheduled job"""
        self.scheduler.remove_job(scheduled_job_id)
        await self._update_job_status(scheduled_job_id, JobStatus.CANCELLED)
    
    async def get_job_status(self, scheduled_job_id: str) -> Dict[str, Any]:
        """Get job status and details"""
        job = self.scheduler.get_job(scheduled_job_id)
        if not job:
            return {"status": "not_found"}
        
        # Get execution history
        executions = await self._get_job_executions(scheduled_job_id)
        
        return {
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "trigger": str(job.trigger),
            "pending": job.pending,
            "executions": executions,
            "metadata": await self._get_job_metadata(scheduled_job_id)
        }
    
    async def list_jobs(
        self,
        category: Optional[str] = None,
        status: Optional[JobStatus] = None,
        owner: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List all scheduled jobs with filters"""
        jobs = []
        
        for job in self.scheduler.get_jobs():
            metadata = await self._get_job_metadata(job.id)
            
            # Apply filters
            if category and metadata.get("category") != category:
                continue
            if owner and metadata.get("owner") != owner:
                continue
            
            job_info = {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
                "metadata": metadata
            }
            
            jobs.append(job_info)
        
        return jobs
    
    async def get_execution_history(
        self,
        job_id: Optional[str] = None,
        status: Optional[JobStatus] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100
    ) -> List[JobExecution]:
        """Get job execution history"""
        # Implementation depends on storage backend
        executions = []
        
        # Query from Redis
        pattern = f"execution:*"
        if job_id:
            pattern = f"execution:{job_id}:*"
        
        keys = await self.redis_client.keys(pattern)
        
        for key in keys[-limit:]:
            data = await self.redis_client.get(key)
            if data:
                execution = JobExecution(**data)
                
                # Apply filters
                if status and execution.status != status:
                    continue
                if start_date and execution.started_at < start_date:
                    continue
                if end_date and execution.started_at > end_date:
                    continue
                
                executions.append(execution)
        
        return sorted(executions, key=lambda x: x.started_at, reverse=True)
    
    # Private methods
    async def _execute_job(self, job_id: str, args: List, kwargs: Dict):
        """Execute a job with full lifecycle management"""
        execution_id = str(uuid.uuid4())
        
        with tracer.start_as_current_span("execute_job") as span:
            span.set_attribute("job.id", job_id)
            span.set_attribute("execution.id", execution_id)
            
            # Get metadata
            metadata = self._job_metadata.get(job_id)
            if not metadata:
                logger.error(f"Job metadata not found: {job_id}")
                return
            
            # Create execution record
            execution = JobExecution(
                execution_id=execution_id,
                job_id=job_id,
                status=JobStatus.RUNNING,
                started_at=datetime.now(timezone.utc),
                worker_id=self.worker_id
            )
            
            # Check dependencies
            if metadata.dependencies:
                if not await self._check_dependencies(metadata.dependencies):
                    execution.status = JobStatus.FAILED
                    execution.error = "Dependencies not met"
                    await self._save_execution(execution)
                    return
            
            # Acquire semaphore
            async with self._execution_semaphore:
                self.active_jobs.inc()
                
                try:
                    # Get job function
                    func = self._job_functions.get(job_id)
                    if not func:
                        raise ValueError(f"Job function not found: {job_id}")
                    
                    # Create context
                    context = JobExecutionContext(
                        job_id=job_id,
                        execution_id=execution_id,
                        metadata=metadata,
                        scheduler=self
                    )
                    
                    # Execute with timeout
                    task = asyncio.create_task(func(context, *args, **kwargs))
                    self._running_jobs[execution_id] = task
                    
                    result = await asyncio.wait_for(
                        task,
                        timeout=metadata.timeout
                    )
                    
                    # Success
                    execution.status = JobStatus.COMPLETED
                    execution.result = result
                    execution.completed_at = datetime.now(timezone.utc)
                    execution.duration = (
                        execution.completed_at - execution.started_at
                    ).total_seconds()
                    
                    # Metrics
                    self.job_counter.labels(
                        status="completed",
                        category=metadata.category
                    ).inc()
                    self.job_duration.labels(
                        job_name=metadata.name,
                        status="success"
                    ).observe(execution.duration)
                    
                    # Notifications
                    if metadata.notify_on_success:
                        await self._send_notifications(
                            metadata.notify_on_success,
                            f"Job {metadata.name} completed successfully",
                            execution
                        )
                    
                except asyncio.TimeoutError:
                    execution.status = JobStatus.FAILED
                    execution.error = f"Job timed out after {metadata.timeout}s"
                    span.record_exception(Exception(execution.error))
                    
                    # Cancel task
                    task.cancel()
                    
                    # Retry logic
                    if execution.retry_count < metadata.max_retries:
                        await self._schedule_retry(job_id, execution, args, kwargs)
                    
                except Exception as e:
                    execution.status = JobStatus.FAILED
                    execution.error = str(e)
                    span.record_exception(e)
                    logger.error(f"Job {job_id} failed: {e}")
                    
                    # Retry logic
                    if execution.retry_count < metadata.max_retries:
                        await self._schedule_retry(job_id, execution, args, kwargs)
                    
                    # Notifications
                    if metadata.notify_on_failure:
                        await self._send_notifications(
                            metadata.notify_on_failure,
                            f"Job {metadata.name} failed: {e}",
                            execution
                        )
                    
                finally:
                    # Cleanup
                    self._running_jobs.pop(execution_id, None)
                    self.active_jobs.dec()
                    
                    # Save execution
                    await self._save_execution(execution)
    
    async def _check_dependencies(self, dependencies: List[str]) -> bool:
        """Check if job dependencies are satisfied"""
        for dep_job_id in dependencies:
            # Check last execution
            executions = await self._get_job_executions(dep_job_id, limit=1)
            if not executions or executions[0].status != JobStatus.COMPLETED:
                return False
        return True
    
    async def _schedule_retry(
        self,
        job_id: str,
        execution: JobExecution,
        args: List,
        kwargs: Dict
    ):
        """Schedule job retry"""
        metadata = self._job_metadata[job_id]
        retry_delay = metadata.retry_delay * (2 ** execution.retry_count)  # Exponential backoff
        
        run_date = datetime.now(timezone.utc) + timedelta(seconds=retry_delay)
        
        # Update kwargs with retry info
        kwargs["_retry_count"] = execution.retry_count + 1
        kwargs["_original_execution_id"] = execution.execution_id
        
        await self.schedule_one_time_job(
            job_id,
            run_date,
            args,
            kwargs
        )
        
        logger.info(f"Scheduled retry for job {job_id} in {retry_delay}s")
    
    async def _on_job_event(self, event):
        """Handle APScheduler events"""
        if event.exception:
            logger.error(f"Job {event.job_id} crashed: {event.exception}")
    
    async def _monitor_jobs(self):
        """Monitor job health and performance"""
        while True:
            try:
                # Update queue size metrics
                for priority in JobPriority:
                    count = await self._count_pending_jobs(priority)
                    self.job_queue_size.labels(priority=priority.name).set(count)
                
                # Check for stuck jobs
                await self._check_stuck_jobs()
                
                # Update worker heartbeat
                await self._update_worker_heartbeat()
                
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error(f"Job monitoring error: {e}")
                await asyncio.sleep(60)
    
    async def _cleanup_old_executions(self):
        """Clean up old execution records"""
        while True:
            try:
                # Remove executions older than 30 days
                cutoff = datetime.now(timezone.utc) - timedelta(days=30)
                
                pattern = "execution:*"
                keys = await self.redis_client.keys(pattern)
                
                for key in keys:
                    data = await self.redis_client.get(key)
                    if data:
                        execution = JobExecution(**data)
                        if execution.started_at < cutoff:
                            await self.redis_client.delete(key)
                
                await asyncio.sleep(3600)  # Run hourly
                
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
                await asyncio.sleep(3600)
    
    async def _process_dependencies(self):
        """Process job dependency graph"""
        while True:
            try:
                # Check for jobs waiting on dependencies
                pending_jobs = await self._get_pending_dependency_jobs()
                
                for job in pending_jobs:
                    if await self._check_dependencies(job["dependencies"]):
                        # Dependencies satisfied, schedule job
                        await self.schedule_one_time_job(
                            job["job_id"],
                            datetime.now(timezone.utc),
                            job.get("args", []),
                            job.get("kwargs", {})
                        )
                
                await asyncio.sleep(10)
                
            except Exception as e:
                logger.error(f"Dependency processing error: {e}")
                await asyncio.sleep(30)
    
    # Storage methods
    async def _save_job_metadata(self, scheduled_job_id: str, metadata: JobMetadata):
        """Save job metadata to Redis"""
        key = f"job:metadata:{scheduled_job_id}"
        await self.redis_client.setex(
            key,
            86400 * 30,  # 30 days
            metadata.__dict__
        )
    
    async def _get_job_metadata(self, scheduled_job_id: str) -> Dict[str, Any]:
        """Get job metadata from Redis"""
        key = f"job:metadata:{scheduled_job_id}"
        data = await self.redis_client.get(key)
        return data or {}
    
    async def _save_execution(self, execution: JobExecution):
        """Save execution record"""
        key = f"execution:{execution.job_id}:{execution.execution_id}"
        await self.redis_client.setex(
            key,
            86400 * 30,  # 30 days
            execution.__dict__
        )
    
    async def _get_job_executions(
        self,
        job_id: str,
        limit: int = 10
    ) -> List[JobExecution]:
        """Get job execution history"""
        pattern = f"execution:{job_id}:*"
        keys = await self.redis_client.keys(pattern)
        
        executions = []
        for key in keys[-limit:]:
            data = await self.redis_client.get(key)
            if data:
                executions.append(JobExecution(**data))
        
        return sorted(executions, key=lambda x: x.started_at, reverse=True)
    
    # Worker management
    async def _register_worker(self):
        """Register worker in Redis"""
        key = f"worker:{self.worker_id}"
        await self.redis_client.setex(
            key,
            300,  # 5 minutes
            {
                "worker_id": self.worker_id,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "max_workers": self.max_workers,
                "hostname": os.uname().nodename
            }
        )
    
    async def _unregister_worker(self):
        """Unregister worker"""
        key = f"worker:{self.worker_id}"
        await self.redis_client.delete(key)
    
    async def _update_worker_heartbeat(self):
        """Update worker heartbeat"""
        key = f"worker:{self.worker_id}"
        await self.redis_client.expire(key, 300)
    
    # Helper methods
    async def _count_pending_jobs(self, priority: JobPriority) -> int:
        """Count pending jobs by priority"""
        # Implementation depends on job store
        return 0
    
    async def _check_stuck_jobs(self):
        """Check for stuck/zombie jobs"""
        # Get all running executions
        pattern = "execution:*"
        keys = await self.redis_client.keys(pattern)
        
        for key in keys:
            data = await self.redis_client.get(key)
            if data:
                execution = JobExecution(**data)
                
                if execution.status == JobStatus.RUNNING:
                    # Check if job is actually running
                    if execution.execution_id not in self._running_jobs:
                        # Job is stuck, mark as failed
                        execution.status = JobStatus.FAILED
                        execution.error = "Job stuck/crashed"
                        execution.completed_at = datetime.now(timezone.utc)
                        await self._save_execution(execution)
    
    async def _get_pending_dependency_jobs(self) -> List[Dict]:
        """Get jobs waiting on dependencies"""
        # Implementation depends on storage
        return []
    
    async def _send_notifications(
        self,
        recipients: List[str],
        subject: str,
        execution: JobExecution
    ):
        """Send job notifications"""
        # Implementation depends on notification service
        logger.info(f"Sending notifications to {recipients}: {subject}")
    
    async def _update_job_status(self, scheduled_job_id: str, status: JobStatus):
        """Update job status"""
        key = f"job:status:{scheduled_job_id}"
        await self.redis_client.setex(key, 86400, status.value)
    
    # Public helper methods
    async def save_checkpoint(
        self,
        job_id: str,
        execution_id: str,
        state: Dict[str, Any]
    ):
        """Save job checkpoint"""
        key = f"checkpoint:{job_id}:{execution_id}"
        await self.redis_client.setex(
            key,
            86400,  # 24 hours
            pickle.dumps(state)
        )
    
    async def get_checkpoint(
        self,
        job_id: str,
        execution_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get job checkpoint"""
        key = f"checkpoint:{job_id}:{execution_id}"
        data = await self.redis_client.get(key)
        return pickle.loads(data) if data else None
    
    async def update_job_progress(
        self,
        job_id: str,
        execution_id: str,
        progress: int,
        message: Optional[str] = None
    ):
        """Update job progress"""
        key = f"progress:{job_id}:{execution_id}"
        await self.redis_client.setex(
            key,
            3600,  # 1 hour
            {
                "progress": progress,
                "message": message,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        )
    
    async def emit_job_event(
        self,
        job_id: str,
        event_type: str,
        data: Dict[str, Any]
    ):
        """Emit custom job event"""
        event = {
            "job_id": job_id,
            "event_type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Publish to Redis pub/sub
        await self.redis_client.publish(
            f"job:events:{job_id}",
            json.dumps(event)
        )


# Decorator for easy job registration
def scheduled_job(
    scheduler: EnterpriseScheduler,
    job_id: Optional[str] = None,
    **metadata_kwargs
):
    """Decorator to register a scheduled job"""
    def decorator(func: Callable):
        nonlocal job_id
        job_id = job_id or func.__name__
        
        # Ensure function is async
        if not asyncio.iscoroutinefunction(func):
            raise ValueError(f"Job function {func.__name__} must be async")
        
        # Register job
        scheduler.register_job(func, job_id, **metadata_kwargs)
        
        return func
    
    return decorator