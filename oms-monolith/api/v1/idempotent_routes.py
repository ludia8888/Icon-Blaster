"""
Idempotent Consumer API Routes
Endpoints for event processing and consumer management
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from datetime import datetime, timezone

from core.auth import UserContext
from middleware.auth_middleware import get_current_user
from core.idempotent.schema_event_consumer import get_schema_consumer
from models.idempotency import (
    EventEnvelope, IdempotentResult, EventReplayRequest,
    generate_event_id
)
from utils.logger import get_logger
from utils.git_utils import get_current_commit_hash

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/idempotent", tags=["Idempotent Processing"])


# Request/Response Models

class ProcessEventRequest(BaseModel):
    """Request to process an event"""
    event_type: str = Field(..., description="Type of event")
    payload: Dict[str, Any] = Field(..., description="Event payload")
    
    # Optional fields
    event_id: Optional[str] = Field(None, description="Event ID (generated if not provided)")
    correlation_id: Optional[str] = Field(None, description="Correlation ID")
    causation_id: Optional[str] = Field(None, description="ID of causing event")
    idempotency_token: Optional[str] = Field(None, description="Client idempotency token")


class ProcessBatchRequest(BaseModel):
    """Request to process multiple events"""
    events: List[ProcessEventRequest] = Field(..., description="Events to process")
    stop_on_error: bool = Field(False, description="Stop processing on first error")


class ConsumerStatusResponse(BaseModel):
    """Consumer status information"""
    consumer_id: str
    consumer_version: str
    state: Dict[str, Any]
    processing: Dict[str, Any]
    health: Dict[str, Any]
    checkpoints_available: int
    last_checkpoint: Optional[datetime]


class ReplayStatusResponse(BaseModel):
    """Replay operation status"""
    replay_id: str
    status: str
    events_replayed: int
    events_skipped: int
    started_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]


# Event Processing Endpoints

@router.post("/process")
async def process_event(
    request: ProcessEventRequest,
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Process a single event idempotently"""
    consumer = await get_schema_consumer()
    
    # Create event envelope
    event_data = {
        "event_id": request.event_id or generate_event_id(),
        "event_type": request.event_type,
        "source_service": "oms_api",
        "source_version": "1.0.0",
        "source_commit_hash": get_current_commit_hash(),
        "payload": request.payload
    }
    
    # Add optional fields only if they are not None
    if request.correlation_id is not None:
        event_data["correlation_id"] = request.correlation_id
    if request.causation_id is not None:
        event_data["causation_id"] = request.causation_id
    if request.idempotency_token is not None:
        event_data["idempotency_token"] = request.idempotency_token
    
    event = EventEnvelope(**event_data)
    
    # Process event
    result = await consumer.process_event(event)
    
    return {
        "event_id": event.event_id,
        "processed": result.processed,
        "was_duplicate": result.was_duplicate,
        "commit_transition": {
            "from": result.previous_commit_hash[:12] if result.previous_commit_hash else None,
            "to": result.new_commit_hash[:12] if result.new_commit_hash else None
        },
        "processing_time_ms": result.processing_time_ms,
        "side_effects": result.side_effects,
        "error": result.error
    }


@router.post("/process-batch")
async def process_batch(
    request: ProcessBatchRequest,
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Process multiple events as a batch"""
    consumer = await get_schema_consumer()
    
    # Create event envelopes
    events = []
    for i, event_req in enumerate(request.events):
        event_data = {
            "event_id": event_req.event_id or generate_event_id(),
            "event_type": event_req.event_type,
            "source_service": "oms_api",
            "source_version": "1.0.0",
            "source_commit_hash": get_current_commit_hash(),
            "payload": event_req.payload,
            "sequence_number": i
        }
        
        # Add optional fields only if they are not None
        if event_req.correlation_id is not None:
            event_data["correlation_id"] = event_req.correlation_id
        if event_req.causation_id is not None:
            event_data["causation_id"] = event_req.causation_id
        if event_req.idempotency_token is not None:
            event_data["idempotency_token"] = event_req.idempotency_token
        
        event = EventEnvelope(**event_data)
        events.append(event)
    
    # Process batch
    results = await consumer.process_batch(events)
    
    # Summarize results
    processed_count = sum(1 for r in results if r.processed)
    duplicate_count = sum(1 for r in results if r.was_duplicate)
    error_count = sum(1 for r in results if r.error)
    
    return {
        "batch_size": len(events),
        "processed": processed_count,
        "duplicates": duplicate_count,
        "errors": error_count,
        "results": [
            {
                "event_id": events[i].event_id,
                "processed": result.processed,
                "was_duplicate": result.was_duplicate,
                "error": result.error
            }
            for i, result in enumerate(results)
        ]
    }


# Consumer Management Endpoints

@router.get("/consumers/{consumer_id}/status")
async def get_consumer_status(
    consumer_id: str,
    user: UserContext = Depends(get_current_user)
) -> ConsumerStatusResponse:
    """Get status of a specific consumer"""
    if consumer_id != "schema_consumer":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consumer {consumer_id} not found"
        )
    
    consumer = await get_schema_consumer()
    stats = await consumer.get_stats()
    
    return ConsumerStatusResponse(
        consumer_id=stats["consumer_id"],
        consumer_version=stats["consumer_version"],
        state=stats["state"],
        processing=stats["processing"],
        health=stats["health"],
        checkpoints_available=0,  # Would query from DB
        last_checkpoint=None  # Would query from DB
    )


@router.get("/consumers/{consumer_id}/state")
async def get_consumer_state(
    consumer_id: str,
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Get current state of a consumer"""
    if consumer_id != "schema_consumer":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consumer {consumer_id} not found"
        )
    
    consumer = await get_schema_consumer()
    state = await consumer.get_state()
    
    return {
        "consumer_id": consumer_id,
        "state": state.model_dump() if hasattr(state, 'model_dump') else state.dict(),
        "state_hash": consumer.consumer._consumer_state.state_commit_hash[:12],
        "state_version": consumer.consumer._consumer_state.state_version
    }


@router.post("/consumers/{consumer_id}/checkpoint")
async def create_checkpoint(
    consumer_id: str,
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Manually create a checkpoint for a consumer"""
    if consumer_id != "schema_consumer":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Consumer {consumer_id} not found"
        )
    
    consumer = await get_schema_consumer()
    
    # Force checkpoint creation
    await consumer.consumer._create_checkpoint()
    
    return {
        "success": True,
        "message": f"Checkpoint created for {consumer_id}",
        "state_version": consumer.consumer._consumer_state.state_version
    }


# Event Replay Endpoints

@router.post("/replay")
async def start_replay(
    request: EventReplayRequest,
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Start event replay for a consumer"""
    # This would be implemented to replay events from event store
    # For now, return mock response
    
    import uuid
    replay_id = str(uuid.uuid4())
    
    return {
        "replay_id": replay_id,
        "status": "started",
        "consumer_id": request.consumer_id,
        "replay_range": {
            "from_event": request.from_event_id,
            "to_event": request.to_event_id,
            "from_time": request.from_timestamp.isoformat() if request.from_timestamp else None,
            "to_time": request.to_timestamp.isoformat() if request.to_timestamp else None
        },
        "options": {
            "skip_side_effects": request.skip_side_effects,
            "force_reprocess": request.force_reprocess,
            "dry_run": request.dry_run
        }
    }


@router.get("/replay/{replay_id}")
async def get_replay_status(
    replay_id: str,
    user: UserContext = Depends(get_current_user)
) -> ReplayStatusResponse:
    """Get status of a replay operation"""
    # This would query actual replay status
    # For now, return mock response
    
    return ReplayStatusResponse(
        replay_id=replay_id,
        status="completed",
        events_replayed=100,
        events_skipped=5,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        error_message=None
    )


# Testing Endpoints

@router.post("/test/generate-events")
async def generate_test_events(
    event_type: str = Query(..., description="Type of events to generate"),
    count: int = Query(10, ge=1, le=100, description="Number of events"),
    user: UserContext = Depends(get_current_user)
) -> Dict[str, Any]:
    """Generate test events for testing idempotency"""
    consumer = await get_schema_consumer()
    
    events = []
    results = []
    
    for i in range(count):
        if event_type == "object_type.created":
            event = EventEnvelope(
                event_type=event_type,
                source_service="test_generator",
                source_version="1.0.0",
                source_commit_hash="test123",
                payload={
                    "type_id": f"test_type_{i}",
                    "type_data": {
                        "name": f"TestType{i}",
                        "description": f"Test object type {i}"
                    }
                }
            )
        elif event_type == "schema.reset":
            event = EventEnvelope(
                event_type=event_type,
                source_service="test_generator",
                source_version="1.0.0",
                source_commit_hash="test123",
                payload={}
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown event type: {event_type}"
            )
        
        events.append(event)
        result = await consumer.process_event(event)
        results.append(result)
    
    processed = sum(1 for r in results if r.processed)
    duplicates = sum(1 for r in results if r.was_duplicate)
    
    return {
        "generated": count,
        "processed": processed,
        "duplicates": duplicates,
        "state_after": {
            "object_types": (await consumer.get_state()).total_object_types,
            "link_types": (await consumer.get_state()).total_link_types,
            "schema_version": (await consumer.get_state()).schema_version
        }
    }