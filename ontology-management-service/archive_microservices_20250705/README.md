# Archived Microservice Implementations

This directory contains the original monolith implementations that have been extracted into microservices.

## Archived on: 2025-07-05

## Contents:

### 1. Embeddings (`embeddings/`)
- **Original location**: `/core/embeddings/`
- **Replaced with**: `shared.embedding_stub.EmbeddingStub`
- **Microservice**: `services/embedding-service/`
- **Environment variable**: `USE_EMBEDDING_MS=true/false`

### 2. Scheduler (`scheduler/`)
- **Original location**: `/core/scheduler/`
- **Replaced with**: `shared.scheduler_stub.SchedulerServiceStub`
- **Microservice**: `services/scheduler-service/`
- **Environment variable**: `USE_SCHEDULER_MS=true/false`

### 3. Event Backends (`backends/`)
- **Original location**: `/core/events/backends/`
- **Replaced with**: `shared.event_gateway_stub.EventGatewayStub`
- **Microservice**: `services/event-gateway/`
- **Environment variable**: `USE_EVENT_GATEWAY=true/false`

### 4. Unified Publisher (`unified_publisher.py`)
- **Original location**: `/core/events/unified_publisher.py`
- **Replaced with**: Event Gateway Stub
- **Functionality**: Event publishing and distribution

## Restoration

If you need to restore any of these implementations:

```bash
# Restore embeddings
cp -r archive_microservices_20250705/embeddings/ core/

# Restore scheduler
cp -r archive_microservices_20250705/scheduler/ core/

# Restore event backends
cp -r archive_microservices_20250705/backends/ core/events/

# Restore unified publisher
cp archive_microservices_20250705/unified_publisher.py core/events/
```

## Migration Path

The monolith now uses stub implementations that route to either:
1. **Local implementations** (embedded in the monolith) 
2. **Microservice implementations** (via gRPC)

The routing is controlled by environment variables and allows for gradual migration.

## Benefits of Migration

1. **Independent scaling** of compute-intensive services
2. **Language diversity** (microservices can use different languages)
3. **Team autonomy** (different teams can own different services)
4. **Resource optimization** (GPU allocation for ML services)
5. **Fault isolation** (service failures don't affect the entire system)