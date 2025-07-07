"""
Integration Tests for Async Merge Operations
Tests the complete async merge workflow including API, Queue, and Worker
"""
import pytest
import asyncio
import json
import time
from typing import Dict, Any
from fastapi.testclient import TestClient
from httpx import AsyncClient
import redis.asyncio as redis

from bootstrap.app import create_app
from workers.celery_app import app as celery_app
from services.job_service import JobService
from models.job import JobStatus, JobType
from core.branch.service import BranchService


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def app():
    """Create test FastAPI application"""
    app = create_app()
    yield app


@pytest.fixture
async def async_client(app):
    """Create async test client"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


@pytest.fixture
async def redis_client():
    """Create Redis test client"""
    client = redis.Redis.from_url("redis://localhost:6379/15")  # Test DB
    await client.flushdb()  # Clean test DB
    yield client
    await client.flushdb()  # Clean after test
    await client.close()


@pytest.fixture
async def job_service():
    """Create JobService for testing"""
    service = JobService()
    await service.initialize()
    yield service


@pytest.fixture
def mock_user_context():
    """Mock user context for API calls"""
    return {
        "user_id": "test_user_123",
        "username": "testuser",
        "tenant_id": "test_tenant",
        "roles": ["user"]
    }


class TestAsyncMergeWorkflow:
    """Test complete async merge workflow"""

    async def test_merge_request_returns_job_id(self, async_client, mock_user_context):
        """Test that merge request immediately returns job ID"""
        # Create test proposal
        proposal_data = {
            "title": "Test Merge Proposal",
            "source_branch": "feature/test",
            "target_branch": "main",
            "strategy": "merge"
        }
        
        # Mock authentication
        async_client.headers.update({
            "Authorization": "Bearer test_token"
        })
        
        # Submit merge request
        response = await async_client.post(
            "/api/v1/branches/feature%2Ftest/proposals/test_proposal/merge",
            json={
                "strategy": "merge",
                "idempotency_key": "test_merge_123"
            }
        )
        
        # Verify immediate response
        assert response.status_code == 202
        data = response.json()
        
        assert "job_id" in data
        assert "celery_task_id" in data
        assert data["status"] == "queued"
        assert "tracking_url" in data
        assert data["estimated_duration_minutes"] == 5

    async def test_job_status_tracking(self, async_client, job_service, mock_user_context):
        """Test job status tracking through API"""
        # Create test job
        job = await job_service.create_job(
            job_type=JobType.BRANCH_MERGE,
            created_by=mock_user_context["user_id"],
            metadata={
                "proposal_id": "test_proposal",
                "source_branch": "feature/test",
                "merge_strategy": "merge"
            }
        )
        
        # Check initial status
        response = await async_client.get(f"/api/v1/jobs/{job.id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["job_id"] == job.id
        assert data["status"] == "queued"
        assert data["progress"]["percentage"] == 0.0

    async def test_job_progress_updates(self, job_service, redis_client):
        """Test progress updates through Redis pub/sub"""
        # Create test job
        job = await job_service.create_job(
            job_type=JobType.BRANCH_MERGE,
            created_by="test_user"
        )
        
        # Subscribe to progress updates
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"job:progress:{job.id}")
        
        # Update progress
        from models.job import JobProgress
        progress = JobProgress(
            current_step="merging",
            completed_steps=3,
            total_steps=6,
            percentage=50.0,
            message="Performing merge operation"
        )
        
        await job_service.update_job_progress(job.id, progress)
        
        # Verify Redis message
        message = await pubsub.get_message(timeout=5.0)
        if message and message['type'] == 'message':
            progress_data = json.loads(message['data'])
            assert progress_data["percentage"] == 50.0
            assert progress_data["current_step"] == "merging"
        
        await pubsub.close()

    async def test_idempotency(self, async_client, job_service):
        """Test idempotency key prevents duplicate jobs"""
        idempotency_key = "unique_merge_operation_123"
        
        # Create first job
        job1 = await job_service.create_job(
            job_type=JobType.BRANCH_MERGE,
            created_by="test_user",
            idempotency_key=idempotency_key
        )
        
        # Attempt to create duplicate job
        job2 = await job_service.create_job(
            job_type=JobType.BRANCH_MERGE,
            created_by="test_user",
            idempotency_key=idempotency_key
        )
        
        # Should return same job
        assert job1.id == job2.id

    async def test_job_cancellation(self, async_client, job_service, mock_user_context):
        """Test job cancellation"""
        # Create test job
        job = await job_service.create_job(
            job_type=JobType.BRANCH_MERGE,
            created_by=mock_user_context["user_id"]
        )
        
        # Update to in_progress
        await job_service.update_job_status(job.id, JobStatus.IN_PROGRESS)
        
        # Cancel job
        response = await async_client.post(f"/api/v1/jobs/{job.id}/cancel")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "cancelled"
        
        # Verify job status updated
        updated_job = await job_service.get_job(job.id)
        assert updated_job.status == JobStatus.CANCELLED

    async def test_job_failure_and_retry(self, job_service):
        """Test job failure handling and retry logic"""
        # Create test job with retry settings
        job = await job_service.create_job(
            job_type=JobType.BRANCH_MERGE,
            created_by="test_user",
            metadata={"max_retries": 3}
        )
        
        # Simulate failure
        await job_service.fail_job(
            job.id,
            error_message="Test failure",
            error_stack="Mock stack trace"
        )
        
        # Check retry capability
        failed_job = await job_service.get_job(job.id)
        assert failed_job.status == JobStatus.FAILED
        assert failed_job.can_retry() is True
        assert failed_job.metadata.retry_count == 1
        
        # Exhaust retries
        for i in range(2):  # 2 more failures = 3 total
            await job_service.fail_job(job.id, "Another failure")
        
        # Should move to dead letter queue
        dead_job = await job_service.get_job(job.id)
        assert dead_job.status == JobStatus.DEAD_LETTER
        assert dead_job.can_retry() is False

    async def test_concurrent_merge_prevention(self, job_service, redis_client):
        """Test distributed lock prevents concurrent merges"""
        from workers.tasks.merge import acquire_distributed_lock, release_distributed_lock
        
        branch = "main"
        lock_key = f"merge:lock:{branch}"
        
        # Acquire first lock
        lock1 = await acquire_distributed_lock(redis_client, lock_key, timeout=60)
        assert lock1 is True
        
        # Try to acquire second lock (should fail)
        lock2 = await acquire_distributed_lock(redis_client, lock_key, timeout=60)
        assert lock2 is False
        
        # Release first lock
        await release_distributed_lock(redis_client, lock_key)
        
        # Now second lock should succeed
        lock3 = await acquire_distributed_lock(redis_client, lock_key, timeout=60)
        assert lock3 is True
        
        await release_distributed_lock(redis_client, lock_key)

    async def test_job_cleanup(self, job_service):
        """Test expired job cleanup"""
        from datetime import datetime, timedelta
        
        # Create expired job
        expired_job = await job_service.create_job(
            job_type=JobType.BRANCH_MERGE,
            created_by="test_user",
            expires_at=datetime.utcnow() - timedelta(hours=1)  # Already expired
        )
        
        # Run cleanup
        cleaned_count = await job_service.cleanup_expired_jobs(batch_size=10)
        
        # Verify job was cleaned
        assert cleaned_count >= 1
        
        # Job should no longer exist
        cleaned_job = await job_service.get_job(expired_job.id)
        assert cleaned_job is None

    @pytest.mark.skip(reason="Requires actual Celery worker running")
    async def test_full_worker_integration(self, async_client, mock_user_context):
        """
        Full integration test with actual Celery worker
        NOTE: Requires Celery worker to be running for this test
        """
        # Submit actual merge request
        response = await async_client.post(
            "/api/v1/branches/test-branch/proposals/test-proposal/merge",
            json={"strategy": "merge"}
        )
        
        assert response.status_code == 202
        job_data = response.json()
        job_id = job_data["job_id"]
        
        # Poll for completion (with timeout)
        max_wait = 60  # 60 seconds
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            status_response = await async_client.get(f"/api/v1/jobs/{job_id}")
            status_data = status_response.json()
            
            if status_data["status"] in ["completed", "failed"]:
                break
                
            await asyncio.sleep(2)  # Poll every 2 seconds
        
        # Verify final status
        assert status_data["status"] in ["completed", "failed"]
        if status_data["status"] == "completed":
            assert "result" in status_data
            assert status_data["result"]["success"] is True


class TestAsyncMergeEdgeCases:
    """Test edge cases and error scenarios"""

    async def test_invalid_merge_strategy(self, async_client):
        """Test invalid merge strategy rejection"""
        response = await async_client.post(
            "/api/v1/branches/test/proposals/test/merge",
            json={"strategy": "invalid_strategy"}
        )
        
        assert response.status_code == 400
        assert "Invalid merge strategy" in response.json()["detail"]

    async def test_unauthorized_access(self, async_client, job_service):
        """Test unauthorized job access"""
        # Create job for different user
        job = await job_service.create_job(
            job_type=JobType.BRANCH_MERGE,
            created_by="other_user"
        )
        
        # Try to access with different user (should fail)
        response = await async_client.get(f"/api/v1/jobs/{job.id}")
        assert response.status_code == 403

    async def test_nonexistent_job(self, async_client):
        """Test accessing nonexistent job"""
        response = await async_client.get("/api/v1/jobs/nonexistent_job_123")
        assert response.status_code == 404

    async def test_terminal_job_cancellation(self, async_client, job_service):
        """Test cancelling already completed job"""
        # Create and complete job
        job = await job_service.create_job(
            job_type=JobType.BRANCH_MERGE,
            created_by="test_user"
        )
        
        await job_service.complete_job(job.id, {"success": True})
        
        # Try to cancel completed job
        response = await async_client.post(f"/api/v1/jobs/{job.id}/cancel")
        assert response.status_code == 400
        assert "already completed" in response.json()["detail"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])