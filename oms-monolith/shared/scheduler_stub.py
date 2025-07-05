"""Scheduler service stub for gradual migration."""

import os
import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

# Note: Removed dependency on core.embeddings since it's now a microservice

logger = logging.getLogger(__name__)

# Feature flag for using microservice
USE_SCHEDULER_MS = os.getenv("USE_SCHEDULER_MS", "false").lower() == "true"
SCHEDULER_SERVICE_ENDPOINT = os.getenv("SCHEDULER_SERVICE_ENDPOINT", "scheduler-service:50056")


class SchedulerServiceStub:
    """Stub that routes to either local APScheduler or microservice."""
    
    def __init__(self):
        self._local_scheduler = None
        self._grpc_client = None
        
        if USE_SCHEDULER_MS:
            try:
                from shared.scheduler_client import SchedulerClient
                self._grpc_client = SchedulerClient(SCHEDULER_SERVICE_ENDPOINT)
                logger.info("Using scheduler microservice")
            except Exception as e:
                logger.warning(f"Failed to initialize scheduler client: {e}")
                logger.info("Falling back to local scheduler")
                self._init_local_scheduler()
        else:
            self._init_local_scheduler()
    
    def _init_local_scheduler(self):
        """Initialize local APScheduler."""
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            self._local_scheduler = AsyncIOScheduler()
            self._local_scheduler.start()
            logger.info("Using local APScheduler")
        except ImportError:
            logger.error("APScheduler not installed")
    
    async def create_job(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new scheduled job."""
        if self._grpc_client:
            return await self._grpc_client.create_job(job)
        else:
            # Local implementation
            return await self._create_job_local(job)
    
    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a job by ID."""
        if self._grpc_client:
            return await self._grpc_client.get_job(job_id)
        else:
            # Local implementation
            return await self._get_job_local(job_id)
    
    async def run_job(self, job_id: str, override_parameters: Optional[Dict] = None) -> str:
        """Manually trigger a job execution."""
        if self._grpc_client:
            return await self._grpc_client.run_job(job_id, override_parameters)
        else:
            # Local implementation
            return await self._run_job_local(job_id, override_parameters)
    
    async def _create_job_local(self, job: Dict[str, Any]) -> Dict[str, Any]:
        """Create job using local scheduler."""
        if not self._local_scheduler:
            raise RuntimeError("Local scheduler not initialized")
        
        # Simple local implementation
        from uuid import uuid4
        job_id = str(uuid4())
        
        # Add job based on schedule type
        schedule = job.get("schedule", {})
        if "cron_expression" in schedule:
            self._local_scheduler.add_job(
                self._execute_job_local,
                'cron',
                id=job_id,
                args=[job],
                **self._parse_cron_schedule(schedule)
            )
        elif "interval_seconds" in schedule:
            self._local_scheduler.add_job(
                self._execute_job_local,
                'interval',
                id=job_id,
                args=[job],
                seconds=schedule["interval_seconds"]
            )
        
        job["id"] = job_id
        job["status"] = "active"
        return job
    
    async def _get_job_local(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job from local scheduler."""
        if not self._local_scheduler:
            return None
        
        job = self._local_scheduler.get_job(job_id)
        if not job:
            return None
        
        return {
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time,
            "status": "active" if job.next_run_time else "paused"
        }
    
    async def _run_job_local(self, job_id: str, override_parameters: Optional[Dict] = None) -> str:
        """Run job using local scheduler."""
        if not self._local_scheduler:
            raise RuntimeError("Local scheduler not initialized")
        
        job = self._local_scheduler.get_job(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        
        # Execute job
        from uuid import uuid4
        execution_id = str(uuid4())
        
        # Run job function with parameters
        await self._execute_job_local(job.args[0], override_parameters)
        
        return execution_id
    
    async def _execute_job_local(self, job: Dict[str, Any], override_parameters: Optional[Dict] = None):
        """Execute a job locally."""
        job_type = job.get("config", {}).get("job_type")
        parameters = job.get("config", {}).get("parameters", {})
        
        if override_parameters:
            parameters.update(override_parameters)
        
        logger.info(f"Executing local job: {job_type}")
        
        # Simple job type handlers
        if job_type == "embedding_refresh":
            # Refresh embeddings for a collection
            collection = parameters.get("collection", "documents")
            logger.info(f"Refreshing embeddings for collection: {collection}")
            # TODO: Implement actual logic
        
        elif job_type == "cleanup":
            # Clean up old data
            retention_days = parameters.get("retention_days", 30)
            logger.info(f"Cleaning up data older than {retention_days} days")
            # TODO: Implement actual logic
        
        else:
            logger.warning(f"Unknown job type: {job_type}")
    
    def _parse_cron_schedule(self, schedule: Dict[str, Any]) -> Dict[str, Any]:
        """Parse cron schedule for APScheduler."""
        cron_parts = schedule["cron_expression"].split()
        return {
            "minute": cron_parts[0],
            "hour": cron_parts[1],
            "day": cron_parts[2],
            "month": cron_parts[3],
            "day_of_week": cron_parts[4],
            "timezone": schedule.get("timezone", "UTC")
        }


# Global instance
_scheduler_stub = None


def get_scheduler_stub() -> SchedulerServiceStub:
    """Get or create scheduler service stub."""
    global _scheduler_stub
    if _scheduler_stub is None:
        _scheduler_stub = SchedulerServiceStub()
    return _scheduler_stub