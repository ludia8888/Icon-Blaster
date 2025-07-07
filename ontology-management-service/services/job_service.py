"""
Job Service
Manages background job tracking and state management
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import json
import structlog

from models.job import (
    Job, JobStatus, JobType, JobPriority,
    JobUpdate, JobFilter, JobStats, JobProgress, JobMetadata
)
from database.clients.unified_database_client import UnifiedDatabaseClient, DatabaseBackend
from database.clients.terminus_db import TerminusDBClient
from database.clients.sqlite_client_secure import SQLiteClientSecure
from bootstrap.config import get_config
from common_logging.setup import get_logger
import os

logger = get_logger(__name__)


class JobService:
    """
    Service for managing background jobs
    Stores job state in TerminusDB and publishes updates via Redis
    """
    
    def __init__(self):
        config = get_config()
        
        # Create TerminusDB client
        terminus_endpoint = os.environ.get("TERMINUSDB_ENDPOINT", "http://localhost:6363")
        terminus_client = TerminusDBClient(
            endpoint=terminus_endpoint,
            username=os.environ.get("TERMINUSDB_USER", "admin"),
            password=os.environ.get("TERMINUSDB_PASSWORD", "changeme-admin-pass")
        )
        
        # Create SQLite client as fallback
        sqlite_client = SQLiteClientSecure(config=config.sqlite.model_dump())
        
        # Create unified database client
        self.db_client = UnifiedDatabaseClient(
            terminus_client=terminus_client,
            sqlite_client=sqlite_client,
            default_backend=DatabaseBackend.TERMINUSDB
        )
        
        self.db_name = "oms"
        self.jobs_branch = "_jobs"  # Dedicated branch for job tracking
        self._redis_client = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize job tracking and database connection"""
        try:
            if not self._initialized:
                await self.db_client.connect()
                self._initialized = True
                logger.info("JobService database client initialized")
        except Exception as e:
            logger.warning(f"JobService initialization: {e}")
    
    async def create_job(
        self,
        job_type: JobType,
        created_by: str,
        metadata: Optional[Dict[str, Any]] = None,
        priority: JobPriority = JobPriority.NORMAL,
        idempotency_key: Optional[str] = None,
        scheduled_for: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
        tenant_id: Optional[str] = None
    ) -> Job:
        """
        Create a new job
        
        Args:
            job_type: Type of job to create
            created_by: User creating the job
            metadata: Job-specific metadata
            priority: Job priority
            idempotency_key: Optional key for idempotent job creation
            scheduled_for: Optional scheduled execution time
            expires_at: Optional expiration time
            tenant_id: Optional tenant ID
            
        Returns:
            Created Job instance
        """
        
        # Check for existing job with same idempotency key
        if idempotency_key:
            existing = await self._find_job_by_idempotency_key(idempotency_key)
            if existing:
                logger.info(
                    "Found existing job with idempotency key",
                    idempotency_key=idempotency_key,
                    job_id=existing.id
                )
                return existing
        
        # Create job metadata
        job_metadata = JobMetadata(**(metadata or {}))
        
        # Create job
        job = Job(
            type=job_type,
            status=JobStatus.QUEUED,
            priority=priority,
            created_by=created_by,
            tenant_id=tenant_id,
            metadata=job_metadata,
            idempotency_key=idempotency_key,
            scheduled_for=scheduled_for,
            expires_at=expires_at,
            queue_name=self._get_queue_for_type(job_type)
        )
        
        # Save to database
        await self._save_job(job)
        
        # Publish creation event
        await self._publish_job_event(job, "created")
        
        logger.info(
            "Job created",
            job_id=job.id,
            job_type=job_type,
            created_by=created_by
        )
        
        return job
    
    async def get_job(self, job_id: str) -> Optional[Job]:
        """Get job by ID"""
        await self.initialize()
        
        try:
            docs = await self.db_client.read(
                collection="jobs",
                query={"id": job_id},
                limit=1
            )
            return Job(**docs[0]) if docs else None
        except Exception as e:
            logger.error(f"Error getting job {job_id}: {e}")
            return None
    
    async def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        message: Optional[str] = None
    ):
        """Update job status"""
        job = await self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        job.status = status
        job.updated_at = datetime.utcnow()
        
        if status == JobStatus.IN_PROGRESS:
            job.started_at = datetime.utcnow()
        elif status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            job.completed_at = datetime.utcnow()
        
        if message:
            job.progress.message = message
        
        await self._save_job(job)
        await self._publish_job_event(job, "status_changed")
    
    async def update_job_progress(
        self,
        job_id: str,
        progress: JobProgress
    ):
        """Update job progress"""
        job = await self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        job.progress = progress
        job.updated_at = datetime.utcnow()
        
        await self._save_job(job)
        await self._publish_job_event(job, "progress_updated")
    
    async def complete_job(
        self,
        job_id: str,
        result: Dict[str, Any]
    ):
        """Mark job as completed with result"""
        job = await self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        job.status = JobStatus.COMPLETED
        job.result = result
        job.completed_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        
        await self._save_job(job)
        await self._publish_job_event(job, "completed")
    
    async def fail_job(
        self,
        job_id: str,
        error_message: str,
        error_stack: Optional[str] = None
    ):
        """Mark job as failed"""
        job = await self.get_job(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")
        
        job.status = JobStatus.FAILED
        job.metadata.error_message = error_message
        job.metadata.error_stack = error_stack
        job.completed_at = datetime.utcnow()
        job.updated_at = datetime.utcnow()
        
        # Increment retry count
        job.metadata.retry_count += 1
        
        # Check if should move to DLQ
        if job.metadata.retry_count >= job.metadata.max_retries:
            job.status = JobStatus.DEAD_LETTER
        
        await self._save_job(job)
        await self._publish_job_event(job, "failed")
    
    async def list_jobs(
        self,
        filters: Optional[JobFilter] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Job]:
        """List jobs with optional filters"""
        await self.initialize()
        
        try:
            # Build query
            query = {}
            
            if filters:
                if filters.status:
                    query["status"] = {"$in": [s.value for s in filters.status]}
                if filters.type:
                    query["type"] = {"$in": [t.value for t in filters.type]}
                if filters.created_by:
                    query["created_by"] = filters.created_by
                if filters.tenant_id:
                    query["tenant_id"] = filters.tenant_id
            
            # Get documents
            docs = await self.db_client.read(
                collection="jobs",
                query=query,
                limit=limit,
                offset=offset
            )
            
            return [Job(**doc) for doc in docs]
        except Exception as e:
            logger.error(f"Error listing jobs: {e}")
            return []
    
    async def get_job_stats(
        self,
        filters: Optional[JobFilter] = None
    ) -> JobStats:
        """Get job statistics"""
        jobs = await self.list_jobs(filters, limit=10000)
        
        stats = JobStats()
        stats.total = len(jobs)
        
        total_duration = 0.0
        completed_count = 0
        
        for job in jobs:
            # Status counts
            if job.status == JobStatus.QUEUED:
                stats.queued += 1
            elif job.status == JobStatus.IN_PROGRESS:
                stats.in_progress += 1
            elif job.status == JobStatus.COMPLETED:
                stats.completed += 1
                duration = job.duration_seconds()
                if duration:
                    total_duration += duration
                    completed_count += 1
            elif job.status == JobStatus.FAILED:
                stats.failed += 1
            
            # Type counts
            job_type = job.type.value if hasattr(job.type, 'value') else str(job.type)
            stats.by_type[job_type] = stats.by_type.get(job_type, 0) + 1
        
        # Calculate averages
        if completed_count > 0:
            stats.avg_duration_seconds = total_duration / completed_count
        
        if stats.total > 0:
            stats.retry_rate = sum(
                1 for j in jobs if j.metadata.retry_count > 0
            ) / stats.total
        
        return stats
    
    async def cleanup_expired_jobs(self, batch_size: int = 100) -> int:
        """Clean up expired jobs"""
        now = datetime.utcnow()
        cleaned = 0
        
        # Find expired jobs
        expired_jobs = await self.list_jobs(limit=batch_size)
        
        for job in expired_jobs:
            if job.expires_at and job.expires_at < now:
                await self._delete_job(job.id)
                cleaned += 1
                logger.info(f"Cleaned up expired job: {job.id}")
        
        return cleaned
    
    async def check_stuck_jobs(self, timeout_minutes: int = 60) -> List[str]:
        """Check for stuck in-progress jobs"""
        stuck_threshold = datetime.utcnow() - timedelta(minutes=timeout_minutes)
        stuck_jobs = []
        
        # Find in-progress jobs
        jobs = await self.list_jobs(
            JobFilter(status=[JobStatus.IN_PROGRESS])
        )
        
        for job in jobs:
            if job.started_at and job.started_at < stuck_threshold:
                stuck_jobs.append(job.id)
                logger.warning(
                    "Found stuck job",
                    job_id=job.id,
                    started_at=job.started_at
                )
        
        return stuck_jobs
    
    # Private methods
    
    async def _save_job(self, job: Job):
        """Save job to database"""
        await self.initialize()
        
        try:
            doc = job.model_dump()
            doc["id"] = job.id  # Ensure ID is set
            
            # Check if exists
            existing = await self.get_job(job.id)
            
            if existing:
                await self.db_client.update(
                    collection="jobs",
                    doc_id=job.id,
                    updates=doc,
                    message=f"Update job {job.id}"
                )
            else:
                await self.db_client.create(
                    collection="jobs",
                    document=doc,
                    message=f"Create job {job.id}"
                )
        except Exception as e:
            logger.error(f"Error saving job {job.id}: {e}")
            raise
    
    async def _delete_job(self, job_id: str):
        """Delete job from database"""
        await self.initialize()
        
        try:
            await self.db_client.delete(
                collection="jobs",
                doc_id=job_id,
                message=f"Delete job {job_id}"
            )
        except Exception as e:
            logger.error(f"Error deleting job {job_id}: {e}")
            raise
    
    async def _find_job_by_idempotency_key(
        self,
        idempotency_key: str
    ) -> Optional[Job]:
        """Find job by idempotency key"""
        await self.initialize()
        
        try:
            docs = await self.db_client.read(
                collection="jobs",
                query={"idempotency_key": idempotency_key},
                limit=1
            )
            
            return Job(**docs[0]) if docs else None
        except Exception as e:
            logger.error(f"Error finding job by idempotency key {idempotency_key}: {e}")
            return None
    
    async def _publish_job_event(self, job: Job, event_type: str):
        """Publish job event to Redis"""
        if not self._redis_client:
            # Lazy load Redis client
            from bootstrap.providers import RedisProvider
            provider = RedisProvider()
            self._redis_client = await provider.provide()
        
        event = {
            "job_id": job.id,
            "event_type": event_type,
            "job_type": job.type.value if hasattr(job.type, 'value') else str(job.type),
            "status": job.status.value if hasattr(job.status, 'value') else str(job.status),
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # Publish to job-specific channel
        await self._redis_client.publish(
            f"job:events:{job.id}",
            json.dumps(event)
        )
        
        # Publish to global channel
        await self._redis_client.publish(
            "job:events:all",
            json.dumps(event)
        )
    
    def _get_queue_for_type(self, job_type: JobType) -> str:
        """Get queue name for job type"""
        queue_mapping = {
            JobType.BRANCH_MERGE: "merge",
            JobType.BRANCH_REBASE: "merge",
            JobType.BRANCH_SQUASH: "merge",
            JobType.SCHEMA_VALIDATION: "validation",
            JobType.BULK_IMPORT: "import"
        }
        
        return queue_mapping.get(job_type, "default")