"""FastAPI application for event gateway service."""

import logging
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any
import asyncio

from fastapi import FastAPI, HTTPException, Depends, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, PlainTextResponse
from prometheus_client import Counter, Histogram, generate_latest
from cloudevents.http import CloudEvent, from_dict

from .events.service import EventGatewayService
from .events.models import (
    Event, Webhook, Stream,
    PublishEventRequest, PublishEventsBatchRequest,
    SubscribeRequest, ListEventsRequest,
    RegisterWebhookRequest, UpdateWebhookRequest,
    CreateStreamRequest
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prometheus metrics
events_published_counter = Counter("event_gateway_events_published_total", "Total events published", ["stream", "type"])
events_delivered_counter = Counter("event_gateway_events_delivered_total", "Total events delivered", ["consumer"])
webhook_deliveries_counter = Counter("event_gateway_webhook_deliveries_total", "Total webhook deliveries", ["webhook", "status"])
event_processing_histogram = Histogram("event_gateway_processing_seconds", "Event processing time")

# Global service instance
event_service: Optional[EventGatewayService] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global event_service
    
    # Startup
    logger.info("Starting event gateway service...")
    event_service = EventGatewayService()
    await event_service.initialize()
    logger.info("Event gateway service started")
    
    yield
    
    # Shutdown
    logger.info("Shutting down event gateway service...")
    if event_service:
        await event_service.shutdown()
    logger.info("Event gateway service stopped")


# Create FastAPI app
app = FastAPI(
    title="Event Gateway Service",
    description="NATS-based event distribution with CloudEvents",
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


def get_event_service() -> EventGatewayService:
    """Dependency to get event service."""
    if not event_service:
        raise HTTPException(status_code=503, detail="Event service not initialized")
    return event_service


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    if not event_service or not event_service._is_initialized:
        raise HTTPException(status_code=503, detail="Service not healthy")
    
    return {
        "status": "healthy",
        "service": "event-gateway",
        "nats_connected": event_service.nc.is_connected if event_service.nc else False
    }


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    """Prometheus metrics endpoint."""
    return generate_latest()


# Event publishing endpoints
@app.post("/api/v1/events")
async def publish_event(
    request: PublishEventRequest,
    service: EventGatewayService = Depends(get_event_service)
):
    """Publish a single event."""
    try:
        # Convert dict to CloudEvent
        cloud_event = from_dict(request.event)
        
        # Publish event
        result = await service.publish_event(
            cloud_event,
            request.stream,
            request.headers
        )
        
        # Update metrics
        events_published_counter.labels(
            stream=request.stream,
            type=cloud_event["type"]
        ).inc()
        
        return {
            "event_id": result.event_id,
            "sequence": result.sequence,
            "published_at": result.published_at.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to publish event: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/events/batch")
async def publish_events_batch(
    request: PublishEventsBatchRequest,
    service: EventGatewayService = Depends(get_event_service)
):
    """Publish multiple events."""
    try:
        # Convert dicts to CloudEvents
        cloud_events = [from_dict(event_dict) for event_dict in request.events]
        
        # Publish events
        results = await service.publish_events_batch(
            cloud_events,
            request.stream,
            request.headers
        )
        
        # Update metrics
        for event in cloud_events:
            events_published_counter.labels(
                stream=request.stream,
                type=event["type"]
            ).inc()
        
        return {
            "results": [
                {
                    "event_id": r.event_id,
                    "sequence": r.sequence,
                    "published_at": r.published_at.isoformat()
                }
                for r in results
            ],
            "succeeded": len(results),
            "failed": len(request.events) - len(results)
        }
        
    except Exception as e:
        logger.error(f"Failed to publish events batch: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Event subscription endpoints
@app.post("/api/v1/subscriptions")
async def create_subscription(
    request: SubscribeRequest,
    service: EventGatewayService = Depends(get_event_service)
):
    """Create a new subscription."""
    try:
        subscription_id = await service.subscribe(
            consumer_id=request.consumer_id,
            event_types=request.event_types,
            stream=request.stream,
            durable_name=request.durable_name,
            start_sequence=request.start_sequence,
            deliver_new=request.deliver_new,
            max_in_flight=request.max_in_flight,
            ack_wait_seconds=request.ack_wait_seconds
        )
        
        return {
            "subscription_id": subscription_id,
            "consumer_id": request.consumer_id,
            "stream": request.stream
        }
        
    except Exception as e:
        logger.error(f"Failed to create subscription: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/subscriptions/{subscription_id}")
async def delete_subscription(
    subscription_id: str,
    consumer_id: str = Query(...),
    service: EventGatewayService = Depends(get_event_service)
):
    """Delete a subscription."""
    success = await service.unsubscribe(consumer_id, subscription_id)
    if not success:
        raise HTTPException(status_code=404, detail="Subscription not found")
    
    return {"message": "Subscription deleted"}


@app.get("/api/v1/events/stream/{subscription_id}")
async def stream_events(
    subscription_id: str,
    batch_size: int = Query(10, ge=1, le=100),
    service: EventGatewayService = Depends(get_event_service)
):
    """Stream events for a subscription (SSE)."""
    async def event_generator():
        try:
            async for event in service.stream_events(subscription_id, batch_size):
                # Convert to SSE format
                yield f"data: {event.json()}\n\n"
                
                # Update metrics
                events_delivered_counter.labels(
                    consumer=subscription_id
                ).inc()
                
        except Exception as e:
            logger.error(f"Error streaming events: {e}")
            yield f"event: error\ndata: {str(e)}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )


# WebSocket endpoint for real-time events
@app.websocket("/ws/events/{subscription_id}")
async def websocket_events(
    websocket: WebSocket,
    subscription_id: str,
    service: EventGatewayService = Depends(get_event_service)
):
    """WebSocket endpoint for real-time event streaming."""
    await websocket.accept()
    
    try:
        async for event in service.stream_events(subscription_id):
            await websocket.send_json({
                "event": event.cloud_event,
                "metadata": event.metadata.model_dump()
            })
            
            # Update metrics
            events_delivered_counter.labels(
                consumer=subscription_id
            ).inc()
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {subscription_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.close(code=1011, reason=str(e))


# Webhook management endpoints
@app.post("/api/v1/webhooks", response_model=Webhook)
async def register_webhook(
    request: RegisterWebhookRequest,
    service: EventGatewayService = Depends(get_event_service)
):
    """Register a new webhook."""
    try:
        webhook = await service.register_webhook(request.webhook)
        return webhook
    except Exception as e:
        logger.error(f"Failed to register webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/webhooks/{webhook_id}", response_model=Webhook)
async def get_webhook(
    webhook_id: str,
    service: EventGatewayService = Depends(get_event_service)
):
    """Get a webhook by ID."""
    webhook = await service.get_webhook(webhook_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return webhook


@app.put("/api/v1/webhooks/{webhook_id}", response_model=Webhook)
async def update_webhook(
    webhook_id: str,
    request: UpdateWebhookRequest,
    service: EventGatewayService = Depends(get_event_service)
):
    """Update a webhook."""
    try:
        webhook = await service.update_webhook(webhook_id, request.webhook)
        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook not found")
        return webhook
    except Exception as e:
        logger.error(f"Failed to update webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/webhooks/{webhook_id}")
async def delete_webhook(
    webhook_id: str,
    service: EventGatewayService = Depends(get_event_service)
):
    """Delete a webhook."""
    success = await service.delete_webhook(webhook_id)
    if not success:
        raise HTTPException(status_code=404, detail="Webhook not found")
    return {"message": "Webhook deleted"}


@app.get("/api/v1/webhooks", response_model=List[Webhook])
async def list_webhooks(
    event_types: Optional[List[str]] = Query(None),
    enabled_only: bool = False,
    service: EventGatewayService = Depends(get_event_service)
):
    """List webhooks."""
    webhooks = await service.list_webhooks(event_types, enabled_only)
    return webhooks


# Stream management endpoints
@app.post("/api/v1/streams", response_model=Stream)
async def create_stream(
    request: CreateStreamRequest,
    service: EventGatewayService = Depends(get_event_service)
):
    """Create a new stream."""
    try:
        stream = await service.create_stream(request.stream)
        return stream
    except Exception as e:
        logger.error(f"Failed to create stream: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/v1/streams/{stream_name}")
async def delete_stream(
    stream_name: str,
    service: EventGatewayService = Depends(get_event_service)
):
    """Delete a stream."""
    success = await service.delete_stream(stream_name)
    if not success:
        raise HTTPException(status_code=404, detail="Stream not found")
    return {"message": "Stream deleted"}


@app.get("/api/v1/streams", response_model=List[Stream])
async def list_streams(
    service: EventGatewayService = Depends(get_event_service)
):
    """List all streams."""
    streams = await service.list_streams()
    return streams


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)