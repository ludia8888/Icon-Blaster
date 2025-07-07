"""
Job Progress Routes
Real-time job progress tracking via WebSocket and Server-Sent Events
"""
import json
import asyncio
from typing import Dict, Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse
from sse_starlette.sse import EventSourceResponse
import redis.asyncio as redis

from core.auth_utils import UserContext
from core.iam.dependencies import require_scope
from core.iam.iam_integration import IAMScope
from middleware.auth_middleware import get_current_user
from services.job_service import JobService
from bootstrap.dependencies import get_redis_client
from common_logging.setup import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/jobs", tags=["Job Progress"])


class JobProgressManager:
    """Manages job progress subscriptions"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.redis_client: Optional[redis.Redis] = None
    
    async def initialize(self):
        """Initialize Redis connection"""
        if not self.redis_client:
            from bootstrap.providers import RedisProvider
            provider = RedisProvider()
            self.redis_client = await provider.provide()
    
    async def connect(self, websocket: WebSocket, job_id: str, user_id: str):
        """Connect to job progress updates"""
        await websocket.accept()
        connection_key = f"{job_id}:{user_id}"
        self.active_connections[connection_key] = websocket
        
        logger.info(f"WebSocket connected for job {job_id} by user {user_id}")
        
        # Send initial job status
        job_service = JobService()
        await job_service.initialize()
        job = await job_service.get_job(job_id)
        
        if job:
            await websocket.send_text(json.dumps({
                "type": "initial_status",
                "job_id": job_id,
                "status": job.status,
                "progress": job.progress.model_dump() if job.progress else None,
                "result": job.result
            }))
    
    def disconnect(self, job_id: str, user_id: str):
        """Disconnect from job progress updates"""
        connection_key = f"{job_id}:{user_id}"
        if connection_key in self.active_connections:
            del self.active_connections[connection_key]
            logger.info(f"WebSocket disconnected for job {job_id} by user {user_id}")
    
    async def broadcast_to_job(self, job_id: str, message: Dict[str, Any]):
        """Broadcast message to all connections for a job"""
        message_json = json.dumps(message)
        disconnected = []
        
        for connection_key, websocket in self.active_connections.items():
            if connection_key.startswith(f"{job_id}:"):
                try:
                    await websocket.send_text(message_json)
                except:
                    disconnected.append(connection_key)
        
        # Clean up disconnected connections
        for key in disconnected:
            del self.active_connections[key]


# Global progress manager
progress_manager = JobProgressManager()


@router.websocket("/ws/{job_id}/progress")
async def job_progress_websocket(
    websocket: WebSocket,
    job_id: str,
    user_id: str
):
    """
    WebSocket endpoint for real-time job progress updates
    
    Query parameters:
    - user_id: User ID for authentication (in production, use JWT)
    """
    await progress_manager.initialize()
    
    # Verify job exists and user has access
    job_service = JobService()
    await job_service.initialize()
    job = await job_service.get_job(job_id)
    
    if not job:
        await websocket.close(code=4004, reason="Job not found")
        return
    
    # Check access (simplified - in production, validate JWT)
    if job.created_by != user_id:
        await websocket.close(code=4003, reason="Access denied")
        return
    
    await progress_manager.connect(websocket, job_id, user_id)
    
    try:
        # Listen for Redis pub/sub messages
        redis_client = progress_manager.redis_client
        pubsub = redis_client.pubsub()
        
        # Subscribe to job-specific progress channel
        await pubsub.subscribe(f"job:progress:{job_id}")
        await pubsub.subscribe(f"job:events:{job_id}")
        
        # Keep connection alive and listen for messages
        async def redis_listener():
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])
                        await websocket.send_text(json.dumps({
                            "type": "progress_update",
                            "job_id": job_id,
                            "data": data,
                            "timestamp": data.get("timestamp")
                        }))
                    except Exception as e:
                        logger.error(f"Error processing Redis message: {e}")
        
        # Start Redis listener
        listener_task = asyncio.create_task(redis_listener())
        
        # Keep connection alive
        while True:
            try:
                # Wait for client message (ping/pong)
                message = await websocket.receive_text()
                if message == "ping":
                    await websocket.send_text("pong")
            except WebSocketDisconnect:
                break
    
    except WebSocketDisconnect:
        pass
    finally:
        progress_manager.disconnect(job_id, user_id)
        if 'listener_task' in locals():
            listener_task.cancel()
        await pubsub.unsubscribe(f"job:progress:{job_id}")
        await pubsub.unsubscribe(f"job:events:{job_id}")
        await pubsub.close()


@router.get("/{job_id}/progress/stream")
async def job_progress_sse(
    job_id: str,
    request: Request,
    current_user: UserContext = Depends(get_current_user)
):
    """
    Server-Sent Events endpoint for job progress updates
    Alternative to WebSocket for browsers that prefer SSE
    """
    # Verify job exists and user has access
    job_service = JobService()
    await job_service.initialize()
    job = await job_service.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.created_by != current_user.user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    async def event_generator():
        """Generate Server-Sent Events"""
        # Initialize Redis
        from bootstrap.providers import RedisProvider
        provider = RedisProvider()
        redis_client = await provider.provide()
        
        pubsub = redis_client.pubsub()
        await pubsub.subscribe(f"job:progress:{job_id}")
        await pubsub.subscribe(f"job:events:{job_id}")
        
        try:
            # Send initial status
            yield {
                "event": "initial",
                "data": json.dumps({
                    "job_id": job_id,
                    "status": job.status,
                    "progress": job.progress.model_dump() if job.progress else None
                })
            }
            
            # Listen for updates
            async for message in pubsub.listen():
                if message['type'] == 'message':
                    try:
                        data = json.loads(message['data'])
                        yield {
                            "event": "progress",
                            "data": json.dumps({
                                "job_id": job_id,
                                "update": data
                            })
                        }
                    except Exception as e:
                        logger.error(f"Error processing SSE message: {e}")
                
                # Check if client disconnected
                if await request.is_disconnected():
                    break
        
        finally:
            await pubsub.unsubscribe(f"job:progress:{job_id}")
            await pubsub.unsubscribe(f"job:events:{job_id}")
            await pubsub.close()
    
    return EventSourceResponse(event_generator())


@router.get("/{job_id}/logs", dependencies=[Depends(require_scope([IAMScope.PROPOSALS_READ]))])
async def get_job_logs(
    job_id: str,
    limit: int = 100,
    offset: int = 0,
    current_user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get job execution logs"""
    # Verify job exists and user has access
    job_service = JobService()
    await job_service.initialize()
    job = await job_service.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.created_by != current_user.user_id and not current_user.metadata.get("admin"):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Get logs from Redis (stored by worker)
    from bootstrap.providers import RedisProvider
    provider = RedisProvider()
    redis_client = await provider.provide()
    
    log_key = f"job:logs:{job_id}"
    logs = await redis_client.lrange(log_key, offset, offset + limit - 1)
    
    parsed_logs = []
    for log_entry in logs:
        try:
            parsed_logs.append(json.loads(log_entry))
        except:
            parsed_logs.append({"message": log_entry.decode(), "timestamp": None})
    
    return {
        "job_id": job_id,
        "logs": parsed_logs,
        "total": await redis_client.llen(log_key),
        "limit": limit,
        "offset": offset
    }


# Background task to clean up old progress data
async def cleanup_old_progress_data():
    """Clean up old job progress data from Redis"""
    from bootstrap.providers import RedisProvider
    provider = RedisProvider()
    redis_client = await provider.provide()
    
    # Find and delete old job progress keys
    pattern = "job:progress:*"
    keys = await redis_client.keys(pattern)
    
    # Keep only recent data (last 24 hours)
    import time
    cutoff_time = time.time() - (24 * 60 * 60)  # 24 hours ago
    
    for key in keys:
        # Check key age and delete if old
        ttl = await redis_client.ttl(key)
        if ttl > 0 and ttl < cutoff_time:
            await redis_client.delete(key)