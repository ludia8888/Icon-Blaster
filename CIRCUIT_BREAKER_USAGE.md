# Circuit Breaker Pattern Implementation

## Overview

The enhanced audit service (`audit_service_enhanced.py`) implements the Circuit Breaker pattern to improve resilience and prevent cascading failures.

## How to Use

### 1. Replace the existing audit service

To use the enhanced version with circuit breaker:

```python
# In your service initialization or dependency injection
from services.audit_service_enhanced import get_audit_service

audit_service = get_audit_service()
```

### 2. Update main.py to use enhanced service

```python
# In main.py
from services.audit_service_enhanced import get_audit_service, cleanup_audit_service

@app.on_event("startup")
async def startup_event():
    audit_service = get_audit_service()
    await audit_service.initialize()

@app.on_event("shutdown")
async def shutdown_event():
    await cleanup_audit_service()
```

### 3. Monitor circuit breaker status

Add an endpoint to monitor the circuit breaker:

```python
@router.get("/audit/metrics")
async def get_audit_metrics():
    audit_service = get_audit_service()
    return await audit_service.get_metrics()
```

## Circuit Breaker States

1. **CLOSED** (Normal)
   - All requests pass through
   - Failures are counted

2. **OPEN** (Failure)
   - Requests are blocked
   - Events are queued in Redis
   - After timeout, moves to HALF_OPEN

3. **HALF_OPEN** (Recovery)
   - Limited requests allowed
   - Testing if service recovered
   - Success → CLOSED
   - Failure → OPEN

## Configuration

Default settings:
- **Failure Threshold**: 5 consecutive failures
- **Recovery Timeout**: 60 seconds
- **Success Threshold**: 2 successes to close circuit

## Benefits

1. **Fault Tolerance**: Prevents cascading failures
2. **Automatic Recovery**: Self-healing when service recovers
3. **Queue Management**: Failed events are queued and retried
4. **Performance**: Avoids unnecessary calls to failing service
5. **Monitoring**: Built-in metrics for observability

## Metrics

The enhanced service provides:
- Total events sent
- Total events failed
- Total events queued
- Circuit breaker opens count
- Current queue length
- Circuit breaker state

## Migration Guide

1. **Test in Development**
   ```bash
   # Update import in one service file
   # Test thoroughly
   # Monitor metrics
   ```

2. **Gradual Rollout**
   - Start with non-critical services
   - Monitor circuit breaker behavior
   - Adjust thresholds if needed

3. **Full Migration**
   - Replace all audit_service imports
   - Update startup/shutdown hooks
   - Add monitoring dashboards