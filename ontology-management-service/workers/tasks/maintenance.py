"""
Maintenance Tasks
Background jobs for system cleanup and monitoring
"""
import asyncio
from datetime import datetime, timedelta
from typing import List
from celery import Task

from workers.celery_app import app
from services.job_service import JobService
from common_logging.setup import get_logger

logger = get_logger(__name__)


class MaintenanceTask(Task):
    """Base class for maintenance tasks"""
    
    def __init__(self):
        self.job_service: JobService = None
    
    async def initialize(self):
        """Initialize services"""
        if not self.job_service:
            self.job_service = JobService()
            await self.job_service.initialize()


@app.task(bind=True, base=MaintenanceTask, name='workers.tasks.maintenance.cleanup_expired_jobs')
def cleanup_expired_jobs_task(self, batch_size: int = 100):
    """Clean up expired jobs"""
    return asyncio.run(_async_cleanup_expired_jobs(self, batch_size))


async def _async_cleanup_expired_jobs(task: MaintenanceTask, batch_size: int):
    """Async implementation of cleanup"""
    await task.initialize()
    
    cleaned_count = await task.job_service.cleanup_expired_jobs(batch_size)
    
    logger.info(f"Cleaned up {cleaned_count} expired jobs")
    
    return {
        "cleaned_count": cleaned_count,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.task(bind=True, base=MaintenanceTask, name='workers.tasks.maintenance.check_stuck_jobs')
def check_stuck_jobs_task(self, timeout_minutes: int = 60):
    """Check for stuck jobs and alert"""
    return asyncio.run(_async_check_stuck_jobs(self, timeout_minutes))


async def _async_check_stuck_jobs(task: MaintenanceTask, timeout_minutes: int):
    """Async implementation of stuck job checking"""
    await task.initialize()
    
    stuck_jobs = await task.job_service.check_stuck_jobs(timeout_minutes)
    
    if stuck_jobs:
        logger.warning(f"Found {len(stuck_jobs)} stuck jobs", stuck_jobs=stuck_jobs)
        
        # TODO: Send alerts to monitoring system
        # await send_alert("Stuck jobs detected", {"job_ids": stuck_jobs})
    
    return {
        "stuck_job_count": len(stuck_jobs),
        "stuck_job_ids": stuck_jobs,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.task(bind=True, base=MaintenanceTask, name='workers.tasks.maintenance.generate_job_stats')
def generate_job_stats_task(self):
    """Generate job statistics for monitoring"""
    return asyncio.run(_async_generate_job_stats(self))


async def _async_generate_job_stats(task: MaintenanceTask):
    """Generate comprehensive job statistics"""
    await task.initialize()
    
    # Get overall stats
    stats = await task.job_service.get_job_stats()
    
    # Get recent activity (last 24 hours)
    from models.job import JobFilter
    recent_filter = JobFilter(
        created_after=datetime.utcnow() - timedelta(hours=24)
    )
    recent_stats = await task.job_service.get_job_stats(recent_filter)
    
    result = {
        "overall": stats.dict(),
        "last_24h": recent_stats.dict(),
        "timestamp": datetime.utcnow().isoformat()
    }
    
    logger.info("Generated job statistics", stats=result)
    
    # TODO: Send to monitoring system
    # await send_metrics("job_stats", result)
    
    return result


@app.task(bind=True, name='workers.tasks.maintenance.cleanup_redis_data')
def cleanup_redis_data_task(self, max_age_hours: int = 24):
    """Clean up old Redis data"""
    return asyncio.run(_async_cleanup_redis_data(self, max_age_hours))


async def _async_cleanup_redis_data(task, max_age_hours: int):
    """Clean up old Redis progress and event data"""
    from bootstrap.providers import RedisProvider
    provider = RedisProvider()
    redis_client = await provider.provide()
    
    import time
    cutoff_time = time.time() - (max_age_hours * 60 * 60)
    cleaned_keys = 0
    
    # Clean up job progress data
    progress_keys = await redis_client.keys("job:progress:*")
    for key in progress_keys:
        key_age = await redis_client.object("idletime", key)
        if key_age and key_age > cutoff_time:
            await redis_client.delete(key)
            cleaned_keys += 1
    
    # Clean up job event data
    event_keys = await redis_client.keys("job:events:*")
    for key in event_keys:
        key_age = await redis_client.object("idletime", key)
        if key_age and key_age > cutoff_time:
            await redis_client.delete(key)
            cleaned_keys += 1
    
    # Clean up job logs older than 7 days
    log_cutoff = time.time() - (7 * 24 * 60 * 60)  # 7 days
    log_keys = await redis_client.keys("job:logs:*")
    for key in log_keys:
        key_age = await redis_client.object("idletime", key)
        if key_age and key_age > log_cutoff:
            await redis_client.delete(key)
            cleaned_keys += 1
    
    logger.info(f"Cleaned up {cleaned_keys} Redis keys")
    
    return {
        "cleaned_keys": cleaned_keys,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.task(bind=True, name='workers.tasks.maintenance.health_check')
def health_check_task(self):
    """Worker health check task"""
    return asyncio.run(_async_health_check(self))


async def _async_health_check(task):
    """Perform worker health check"""
    try:
        # Check database connectivity
        job_service = JobService()
        await job_service.initialize()
        
        # Test Redis connectivity
        from bootstrap.providers import RedisProvider
        provider = RedisProvider()
        redis_client = await provider.provide()
        await redis_client.ping()
        
        # Test basic job operations
        from models.job import JobType
        test_job = await job_service.create_job(
            job_type=JobType.SCHEMA_VALIDATION,
            created_by="health_check",
            metadata={"test": True}
        )
        
        # Clean up test job
        await job_service._delete_job(test_job.id)
        
        result = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {
                "database": "ok",
                "redis": "ok",
                "job_service": "ok"
            }
        }
        
        logger.info("Worker health check passed")
        return result
        
    except Exception as e:
        result = {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }
        
        logger.error("Worker health check failed", error=str(e), exc_info=True)
        return result