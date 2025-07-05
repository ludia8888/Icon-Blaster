"""FastAPI application for scheduler service."""

import logging
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, generate_latest
from fastapi.responses import PlainTextResponse

from .scheduler.service import SchedulerService
from .scheduler.models import (
    Job, JobExecution, CreateJobRequest, UpdateJobRequest,
    ListJobsRequest, RunJobRequest, JobHistoryRequest,
    JobStatus, ExecutionStatus
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prometheus metrics
job_created_counter = Counter("scheduler_jobs_created_total", "Total number of jobs created")
job_executed_counter = Counter("scheduler_jobs_executed_total", "Total number of jobs executed", ["job_type", "status"])
job_duration_histogram = Histogram("scheduler_job_duration_seconds", "Job execution duration", ["job_type"])

# Global scheduler service instance
scheduler_service: Optional[SchedulerService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global scheduler_service
    
    # Startup
    logger.info("Starting scheduler service...")
    scheduler_service = SchedulerService()
    await scheduler_service.initialize()
    logger.info("Scheduler service started")
    
    yield
    
    # Shutdown
    logger.info("Shutting down scheduler service...")
    if scheduler_service:
        await scheduler_service.shutdown()
    logger.info("Scheduler service stopped")


# Create FastAPI app
app = FastAPI(
    title="Scheduler Service",
    description="APScheduler-based job scheduling microservice",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_scheduler() -> SchedulerService:
    """Dependency to get scheduler service."""
    if not scheduler_service:
        raise HTTPException(status_code=503, detail="Scheduler service not initialized")
    return scheduler_service


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    if not scheduler_service or not scheduler_service._is_initialized:
        raise HTTPException(status_code=503, detail="Service not healthy")
    
    return {
        "status": "healthy",
        "service": "scheduler-service",
        "scheduler_running": scheduler_service.scheduler.running
    }


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    """Prometheus metrics endpoint."""
    return generate_latest()


# Job management endpoints
@app.post("/api/v1/jobs", response_model=Job)
async def create_job(
    request: CreateJobRequest,
    scheduler: SchedulerService = Depends(get_scheduler)
):
    """Create a new scheduled job."""
    try:
        job = await scheduler.create_job(request.job)
        job_created_counter.inc()
        return job
    except Exception as e:
        logger.error(f"Failed to create job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/jobs/{job_id}", response_model=Job)
async def get_job(
    job_id: str,
    scheduler: SchedulerService = Depends(get_scheduler)
):
    """Get a job by ID."""
    job = await scheduler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.put("/api/v1/jobs/{job_id}", response_model=Job)
async def update_job(
    job_id: str,
    request: UpdateJobRequest,
    scheduler: SchedulerService = Depends(get_scheduler)
):
    """Update an existing job."""
    try:
        job = await scheduler.update_job(job_id, request.job)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job
    except Exception as e:
        logger.error(f"Failed to update job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/jobs/{job_id}")
async def delete_job(
    job_id: str,
    scheduler: SchedulerService = Depends(get_scheduler)
):
    """Delete a job."""
    success = await scheduler.delete_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"message": "Job deleted successfully"}


@app.get("/api/v1/jobs", response_model=dict)
async def list_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    tags: Optional[List[str]] = Query(None),
    status: Optional[JobStatus] = None,
    enabled_only: bool = False,
    scheduler: SchedulerService = Depends(get_scheduler)
):
    """List jobs with filtering and pagination."""
    jobs, total = await scheduler.list_jobs(
        page=page,
        page_size=page_size,
        tags=tags,
        status=status,
        enabled_only=enabled_only
    )
    
    return {
        "jobs": jobs,
        "total": total,
        "page": page,
        "page_size": page_size
    }


# Job execution endpoints
@app.post("/api/v1/jobs/{job_id}/run")
async def run_job(
    job_id: str,
    request: RunJobRequest = RunJobRequest(),
    scheduler: SchedulerService = Depends(get_scheduler)
):
    """Manually trigger a job execution."""
    try:
        execution_id = await scheduler.run_job(job_id, request.override_parameters)
        return {
            "execution_id": execution_id,
            "message": "Job execution started"
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to run job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/jobs/{job_id}/status")
async def get_job_status(
    job_id: str,
    scheduler: SchedulerService = Depends(get_scheduler)
):
    """Get current status of a job."""
    status = await scheduler.get_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    return status


@app.get("/api/v1/jobs/{job_id}/history", response_model=List[JobExecution])
async def get_job_history(
    job_id: str,
    limit: int = Query(50, ge=1, le=100),
    status_filter: Optional[ExecutionStatus] = None,
    scheduler: SchedulerService = Depends(get_scheduler)
):
    """Get execution history for a job."""
    history = await scheduler.get_job_history(job_id, limit, status_filter)
    return history


# Scheduler control endpoints
@app.post("/api/v1/scheduler/pause")
async def pause_scheduler(
    job_ids: Optional[List[str]] = None,
    scheduler: SchedulerService = Depends(get_scheduler)
):
    """Pause specified jobs or all jobs."""
    count = await scheduler.pause_jobs(job_ids)
    return {
        "success": True,
        "jobs_paused": count
    }


@app.post("/api/v1/scheduler/resume")
async def resume_scheduler(
    job_ids: Optional[List[str]] = None,
    scheduler: SchedulerService = Depends(get_scheduler)
):
    """Resume specified jobs or all jobs."""
    count = await scheduler.resume_jobs(job_ids)
    return {
        "success": True,
        "jobs_resumed": count
    }


@app.get("/api/v1/scheduler/status")
async def get_scheduler_status(
    scheduler: SchedulerService = Depends(get_scheduler)
):
    """Get overall scheduler status."""
    status = await scheduler.get_scheduler_status()
    return status


# gRPC server would be started here if needed
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)