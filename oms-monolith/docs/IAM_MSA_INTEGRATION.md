# IAM Microservice Architecture Integration

## Overview

This document describes the integration between OMS (Ontology Management System) and the IAM (Identity and Access Management) microservice, eliminating circular dependencies and establishing clean service boundaries.

## Problem Statement

The original implementation had a circular dependency:
- `models.scope_role_mapping` imported `IAMScope` from `core.iam.iam_integration`
- `core.iam.iam_integration` imported `ScopeRoleMatrix` from `models.scope_role_mapping`

This created tight coupling and prevented proper separation of concerns in the MSA architecture.

## Solution Architecture

```mermaid
graph TB
    subgraph "OMS Monolith"
        A[shared/iam_contracts.py<br/>DTOs & Interfaces]
        B[models/scope_role_mapping.py<br/>Role Mapping Logic]
        C[core/integrations/iam_service_client.py<br/>HTTP Client]
        D[core/iam/iam_integration_refactored.py<br/>Business Logic]
        E[middleware/auth_middleware_msa.py<br/>Auth Middleware]
    end
    
    subgraph "IAM Service"
        F[JWT Validation API]
        G[User Info API]
        H[Scope Check API]
        I[Service Auth API]
    end
    
    A --> B
    A --> C
    C --> D
    D --> B
    D --> E
    C -.HTTP.-> F
    C -.HTTP.-> G
    C -.HTTP.-> H
    C -.HTTP.-> I
```

### Key Components

#### 1. Shared Contracts (`shared/iam_contracts.py`)
- Defines DTOs and interfaces shared between services
- No business logic, only data structures
- Includes `IAMScope` enum used by both services

#### 2. IAM Service Client (`core/integrations/iam_service_client.py`)
- HTTP client for communication with IAM service
- Implements retry logic and circuit breaker patterns
- Handles service authentication and token caching

#### 3. Refactored IAM Integration (`core/iam/iam_integration_refactored.py`)
- Business logic for token validation and role mapping
- Uses the IAM client for external calls
- No circular dependencies

#### 4. MSA Auth Middleware (`middleware/auth_middleware_msa.py`)
- Replaces legacy authentication with MSA-based auth
- Validates tokens via IAM service
- Implements scope-based authorization

## Configuration

### Environment Variables

```bash
# Enable MSA Authentication
USE_MSA_AUTH=true

# IAM Service Configuration
IAM_SERVICE_URL=http://user-service:8000
IAM_JWKS_URL=http://user-service:8000/.well-known/jwks.json
IAM_SERVICE_ID=oms-service
IAM_SERVICE_SECRET=your-service-secret
JWT_ISSUER=iam.company
JWT_AUDIENCE=oms

# Performance Tuning
IAM_TIMEOUT=10
IAM_RETRY_COUNT=3
IAM_CACHE_TTL=300
AUTH_CACHE_TTL=300

# Circuit Breaker
CIRCUIT_BREAKER_ENABLED=true
CIRCUIT_BREAKER_FAILURE_THRESHOLD=5
CIRCUIT_BREAKER_RECOVERY_TIMEOUT=60
```

### Docker Compose Setup

```yaml
version: '3.8'

services:
  oms-monolith:
    build: .
    environment:
      - USE_MSA_AUTH=true
      - IAM_SERVICE_URL=http://user-service:8000
      - IAM_SERVICE_SECRET=${IAM_SERVICE_SECRET}
    depends_on:
      - user-service
      - redis
    networks:
      - app-network

  user-service:
    image: your-registry/user-service:latest
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/iam
    networks:
      - app-network

  redis:
    image: redis:7-alpine
    networks:
      - app-network

networks:
  app-network:
    driver: bridge
```

## API Contracts

### Token Validation

**Request:**
```json
POST /api/v1/auth/validate
{
  "token": "eyJhbGciOiJSUzI1NiIs...",
  "validate_scopes": true,
  "required_scopes": ["api:schemas:read"]
}
```

**Response:**
```json
{
  "valid": true,
  "user_id": "user123",
  "username": "john.doe",
  "email": "john@example.com",
  "scopes": ["api:schemas:read", "api:ontologies:write"],
  "roles": ["developer"],
  "tenant_id": "tenant1",
  "expires_at": "2024-12-31T23:59:59Z"
}
```

### User Information

**Request:**
```json
POST /api/v1/users/info
{
  "user_id": "user123",
  "include_permissions": true
}
```

**Response:**
```json
{
  "user_id": "user123",
  "username": "john.doe",
  "email": "john@example.com",
  "full_name": "John Doe",
  "roles": ["developer", "reviewer"],
  "scopes": ["api:schemas:write", "api:proposals:approve"],
  "teams": ["backend", "api"],
  "mfa_enabled": true,
  "active": true,
  "created_at": "2023-01-01T00:00:00Z",
  "updated_at": "2024-01-01T00:00:00Z"
}
```

## Scope to Role Mapping

The system maps IAM scopes to OMS roles:

| IAM Scopes | OMS Role |
|-----------|----------|
| `api:system:admin` | `admin` |
| `api:ontologies:write` + `api:schemas:read` | `developer` |
| `api:proposals:approve` + `api:proposals:read` | `reviewer` |
| `api:*:read` (any read scope) | `viewer` |
| `api:service:account` | `service_account` |

## Migration Guide

### 1. Install Dependencies

```bash
pip install httpx pyjwt cryptography redis
```

### 2. Run Migration Script

```bash
python scripts/migrate_to_msa_auth.py
```

This will:
- Update import statements
- Create environment template
- Show files that were modified

### 3. Update Configuration

```bash
# Copy environment template
cp .env.msa.example .env

# Edit with your values
vim .env
```

### 4. Test Integration

```bash
# Run integration tests
pytest tests/test_iam_msa_integration.py -v

# Test with curl
TOKEN="your-jwt-token"
curl -H "Authorization: Bearer $TOKEN" http://localhost:8002/api/v1/schemas
```

### 5. Monitor Health

```bash
# Check OMS health (includes IAM status)
curl http://localhost:8002/health

# Response includes:
{
  "status": "healthy",
  "components": {
    "iam": {
      "status": "healthy",
      "latency_ms": 45
    }
  }
}
```

## Troubleshooting

### Common Issues

1. **Token Validation Fails**
   - Check IAM service is running: `curl http://user-service:8000/health`
   - Verify JWT issuer and audience match
   - Check service credentials in environment

2. **Circular Import Error**
   - Ensure using `shared.iam_contracts.IAMScope` not `core.iam.iam_integration.IAMScope`
   - Run migration script to update imports

3. **Performance Issues**
   - Enable Redis caching: `REDIS_URL=redis://redis:6379`
   - Increase cache TTL: `AUTH_CACHE_TTL=600`
   - Check circuit breaker settings

4. **Service Discovery**
   - If using Consul: `SERVICE_DISCOVERY_ENABLED=true`
   - Otherwise use direct URLs in environment

## Security Considerations

1. **Service Authentication**
   - Use strong service secrets
   - Rotate secrets regularly
   - Store secrets in secure vault

2. **Network Security**
   - Use TLS for service communication
   - Implement network policies
   - Use service mesh if available

3. **Token Security**
   - Validate token expiration
   - Check token audience
   - Implement token revocation

## Performance Optimization

1. **Caching Strategy**
   - Token validation: 5 min cache
   - User info: 10 min cache
   - Service token: 55 min cache (refresh at 55 min for 1 hour tokens)

2. **Connection Pooling**
   - HTTP client uses connection pooling
   - Redis connection pool configured
   - Database connection pooling

3. **Circuit Breaker**
   - Fails fast after 5 consecutive failures
   - Recovers after 60 seconds
   - Prevents cascade failures

## Monitoring

### Metrics to Track

1. **Authentication Metrics**
   - Token validation rate
   - Token validation latency
   - Cache hit rate
   - Failed authentications

2. **Service Health**
   - IAM service availability
   - Response times
   - Error rates
   - Circuit breaker state

3. **Resource Usage**
   - Redis memory usage
   - HTTP connection pool usage
   - Cache entry count

### Alerts to Configure

```yaml
# Prometheus alerts
groups:
  - name: iam_integration
    rules:
      - alert: IAMServiceDown
        expr: up{job="user-service"} == 0
        for: 5m
        
      - alert: HighAuthLatency
        expr: auth_validation_duration_seconds > 0.5
        for: 10m
        
      - alert: LowCacheHitRate
        expr: auth_cache_hit_rate < 0.5
        for: 15m
```

## Future Enhancements

1. **gRPC Integration**
   - Replace HTTP with gRPC for better performance
   - Implement streaming for bulk operations

2. **Event-Driven Updates**
   - Subscribe to user/role change events
   - Invalidate cache on changes

3. **Multi-Region Support**
   - Regional IAM endpoints
   - Geo-distributed caching

4. **Advanced Security**
   - Mutual TLS between services
   - Zero-trust networking
   - Hardware security module integration