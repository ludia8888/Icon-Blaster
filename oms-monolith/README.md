# OMS Monolith

Enterprise-grade Ontology Metadata Service - Monolithic Architecture

## Overview

This is a monolithic version of the OMS (Ontology Metadata Service) that integrates all microservices into a single deployable application while maintaining all enterprise features including TerminusDB integration, distributed caching, event streaming, and comprehensive monitoring.

## Architecture

The monolith integrates the following services:
- **API Gateway** - Request routing and rate limiting
- **Schema Service** - Ontology schema management
- **Branch Service** - Git-style branching for schemas
- **Validation Service** - Breaking change detection
- **Action Service** - Asynchronous job execution
- **Event Publisher/Subscriber** - Event streaming
- **GraphQL Service** - GraphQL API
- **Backup Service** - Automated backups

## Quick Start

### Prerequisites
- Python 3.11+
- Docker and Docker Compose
- 8GB RAM minimum

### Local Development

1. Clone the repository:
```bash
cd oms-monolith
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

4. Run locally:
```bash
python main.py
```

### Docker Deployment

1. Build and run with Docker Compose:
```bash
docker-compose up -d
```

2. Access the services:
- Main API: http://localhost:8000
- API Gateway: http://localhost:8090
- GraphQL: http://localhost:8006
- Metrics: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)
- Jaeger: http://localhost:16686

## API Documentation

### REST API
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### GraphQL
- GraphQL Playground: http://localhost:8006/graphql

## Key Features

### 1. Schema Management
- Create, update, delete object types, properties, and link types
- Support for 20+ data types including vectors and time series
- Git-style branching for schema versions

### 2. Breaking Change Detection
- 8 validation rules for data compatibility
- Automatic migration plan generation
- Impact analysis for schema changes

### 3. Enterprise Features
- JWT-based authentication with RBAC
- Distributed tracing with OpenTelemetry
- Prometheus metrics and Grafana dashboards
- Circuit breakers and rate limiting
- Multi-layer caching strategy

### 4. High Availability
- Connection pooling for all databases
- Automatic failover and retry logic
- Health checks and readiness probes
- Graceful shutdown handling

## Configuration

Key environment variables:

```env
# Application
APP_PORT=8000
APP_ENV=production

# Database
TERMINUSDB_URL=http://localhost:6363
REDIS_URL=redis://localhost:6379
NATS_URL=nats://localhost:4222

# Security
JWT_SECRET_KEY=your-secret-key
ENABLE_MTLS=false

# Features
ENABLE_BRANCH_PROTECTION=true
ENABLE_AUDIT_LOGGING=true
ENABLE_DISTRIBUTED_TRACING=true
```

## Monitoring

### Prometheus Metrics
- Request latency histograms
- Error rates and status codes
- Resource utilization
- Business metrics

### Health Checks
```bash
curl http://localhost:8000/health
```

### Distributed Tracing
Access Jaeger UI at http://localhost:16686 to view traces.

## Development

### Running Tests
```bash
pytest tests/
```

### Code Quality
```bash
# Format code
black .

# Lint
flake8 .

# Type checking
mypy .
```

## Production Deployment

### Kubernetes
```bash
kubectl apply -f k8s/
```

### Docker Swarm
```bash
docker stack deploy -c docker-compose.yml oms
```

## Performance

- **Response Time**: P99 < 200ms
- **Throughput**: 500 TPS reads, 50 TPS writes
- **Startup Time**: < 30 seconds
- **Memory Usage**: 512MB - 2GB

## Security

- JWT authentication with refresh tokens
- Role-based access control (RBAC)
- Request validation and sanitization
- Rate limiting per client
- Optional mTLS for service communication

## License

Proprietary - All rights reserved