# Audit Service Integration Guide

## Overview

This guide explains how to integrate the user-service with audit-service for comprehensive audit logging.

## Architecture

```
user-service (port 8001)
    ↓ HTTP POST
audit-service (port 8002)
    ↓ Store
PostgreSQL + InfluxDB + MinIO
```

## Quick Start

### 1. Start All Services

```bash
# Start basic services (Redis, PostgreSQL)
docker-compose up -d

# Start audit-service with its dependencies
docker-compose -f docker-compose.audit.yml up -d

# Verify all services are running
docker-compose ps
docker-compose -f docker-compose.audit.yml ps
```

### 2. Run Database Migrations

```bash
# For user-service (if not already done)
docker-compose exec user-service alembic upgrade head

# For audit-service
docker-compose -f docker-compose.audit.yml exec audit-service alembic upgrade head
```

### 3. Test the Integration

```bash
# Run the integration test script
python test_audit_integration.py
```

## Configuration

### User-Service Configuration

The user-service is pre-configured to send audit events to audit-service. Key settings:

```env
AUDIT_SERVICE_URL=http://audit-service:8002
REDIS_URL=redis://redis:6379
```

### Audit-Service Configuration

The audit-service uses the following ports:
- **8002**: Main HTTP API
- **5434**: PostgreSQL
- **8086**: InfluxDB
- **9000**: MinIO (Object Storage)
- **9001**: MinIO Console

## How It Works

### 1. Event Flow

1. User performs an action (login, create user, etc.)
2. User-service creates an audit event
3. User-service sends event to audit-service via HTTP POST
4. If HTTP fails, event is queued in Redis
5. Audit-service processes and stores the event

### 2. Event Format

User-service sends events in this format:

```json
{
    "event_type": "auth.login_success",
    "user_id": "user123",
    "username": "johndoe",
    "ip_address": "192.168.1.100",
    "user_agent": "Mozilla/5.0...",
    "service": "user-service",
    "action": "login_success",
    "result": "success",
    "details": {
        "mfa_used": false,
        "session_id": "sess_123"
    },
    "compliance_tags": ["SOX", "GDPR"],
    "data_classification": "internal"
}
```

### 3. Supported Event Types

- **Authentication**: login_success, login_failed, logout, token_refresh
- **User Management**: user_created, user_updated, user_deleted, user_locked
- **Password**: password_changed, password_reset_requested
- **MFA**: mfa_enabled, mfa_disabled, mfa_verified
- **Permissions**: permission_granted, role_assigned, role_removed
- **Security**: suspicious_activity, rate_limit_exceeded

## Querying Audit Logs

### Via API

```bash
# Query recent login events
curl "http://localhost:8002/api/v2/events/query?event_type=auth.login_success&limit=10"

# Query events for a specific user
curl "http://localhost:8002/api/v2/events/query?user_id=user123"

# Query failed login attempts
curl "http://localhost:8002/api/v2/events/query?event_type=auth.login_failed&limit=50"
```

### Via v1 API (Legacy)

```bash
# Search audit logs
curl "http://localhost:8002/api/v1/audit/logs?event_type=user_login&limit=100"

# Get dashboard statistics
curl "http://localhost:8002/api/v1/audit/statistics/dashboard?time_range=24h"
```

## Monitoring

### Health Checks

```bash
# Check audit-service health
curl http://localhost:8002/api/v2/events/health

# Check user-service health
curl http://localhost:8001/health
```

### Redis Queue Monitoring

```bash
# Check Redis for queued events
docker-compose exec redis redis-cli
> KEYS user-service:audit:retry_queue
> LLEN user-service:audit:retry_queue
```

## Troubleshooting

### Common Issues

1. **Audit events not appearing**
   - Check audit-service is running: `docker-compose -f docker-compose.audit.yml ps`
   - Check network connectivity: `docker-compose exec user-service curl http://audit-service:8002/api/v2/events/health`
   - Check Redis queue for failed events

2. **Database connection errors**
   - Ensure migrations have run
   - Check PostgreSQL is running: `docker-compose -f docker-compose.audit.yml exec audit-postgres pg_isready`

3. **Port conflicts**
   - User-service: 8001
   - Audit-service: 8002
   - Ensure no other services are using these ports

### Debug Mode

Enable debug logging:

```bash
# For user-service
docker-compose exec user-service bash
export LOG_LEVEL=DEBUG

# For audit-service
docker-compose -f docker-compose.audit.yml exec audit-service bash
export LOG_LEVEL=DEBUG
```

## Performance Optimization

### Future Improvements

1. **Message Queue Integration**
   - Replace HTTP with Kafka/RabbitMQ for better performance
   - Already supported by audit-service v2

2. **Batch Processing**
   - Send multiple events in one request
   - Use `/api/v2/events/batch` endpoint

3. **Circuit Breaker**
   - Implement circuit breaker pattern in user-service
   - Prevent cascading failures

## Security Considerations

1. **Network Security**
   - Services communicate over Docker internal network
   - Not exposed to external network by default

2. **Authentication**
   - Currently no authentication between services
   - Consider adding service-to-service auth tokens

3. **Data Privacy**
   - Audit logs may contain sensitive data
   - Implement data masking for PII

## Next Steps

1. **Production Deployment**
   - Use environment-specific configurations
   - Enable TLS between services
   - Set up proper authentication

2. **Monitoring Setup**
   - Configure Prometheus metrics
   - Set up Grafana dashboards
   - Configure alerts

3. **Backup Strategy**
   - Regular PostgreSQL backups
   - InfluxDB data retention policies
   - MinIO replication

## References

- [Audit Service API Documentation](http://localhost:8002/docs)
- [User Service API Documentation](http://localhost:8001/docs)
- [Docker Compose Documentation](https://docs.docker.com/compose/)