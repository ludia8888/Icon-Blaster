# MSA Integration Guide

## Overview
This guide explains how to run the complete MSA (Microservices Architecture) integration with:
- **OMS (Order Management System)** - Port 18000
- **User Service (IAM)** - Port 18002
- **Audit Service** - Port 18001

## Architecture

```
┌─────────────┐     JWT Token      ┌─────────────┐
│   Client    │ ──────────────────► │     OMS     │
└─────────────┘                     └──────┬──────┘
                                           │
                                    ┌──────┴──────┐
                                    │             │
                              ┌─────▼──────┐ ┌───▼────────┐
                              │User Service│ │Audit Service│
                              └────────────┘ └────────────┘
                                    │             │
                                    └──────┬──────┘
                                           │
                                    ┌──────▼──────┐
                                    │    NATS     │
                                    │  (Events)   │
                                    └─────────────┘
```

## Quick Start

### 1. Prerequisites
- Docker and Docker Compose installed
- Python 3.9+ (for running tests locally)
- At least 4GB of available RAM

### 2. Start All Services
```bash
# From the oms-monolith directory
./scripts/run_msa_integration_test.sh
```

Or manually:
```bash
# Start all services
docker-compose -f docker-compose.integration.yml up -d

# Check health
docker-compose -f docker-compose.integration.yml ps

# View logs
docker-compose -f docker-compose.integration.yml logs -f
```

### 3. Run Integration Tests
```bash
# Install test dependencies
pip install httpx pytest asyncio

# Run tests
python tests/test_msa_integration.py
```

## Service Endpoints

### User Service (Port 18002)
- `POST /api/v1/auth/login` - User login
- `GET /api/v1/auth/userinfo` - Get user info
- `POST /api/v1/auth/check-permission` - Check permissions

### OMS Service (Port 18000)
- `GET /health` - Health check
- `GET /api/v1/schemas/{branch}/object-types` - Get schemas
- `POST /api/v1/branches` - Create branch
- `GET /api/v1/rbac/roles` - Get RBAC roles

### Audit Service (Port 18001)
- `GET /api/v1/health` - Health check
- `GET /api/v1/audit` - Get audit logs
- `GET /api/v1/history` - Get history

## Test Flow

1. **Authentication**
   - Login to User Service
   - Receive JWT token
   
2. **OMS Access**
   - Use JWT token to access OMS endpoints
   - OMS validates token with User Service
   
3. **Event Flow**
   - OMS publishes events to NATS
   - Audit Service subscribes and stores events
   
4. **RBAC Validation**
   - User permissions checked via User Service
   - Role-based access control enforced

## Environment Variables

### Common
- `JWT_SECRET=test-jwt-secret-key` - Shared JWT secret
- `NATS_URL=nats://nats:4222` - NATS connection

### OMS Specific
- `USE_MSA_AUTH=true` - Enable MSA authentication
- `USER_SERVICE_URL=http://user-service:8000` - User service URL
- `ENABLE_AUDIT=true` - Enable audit events

## Troubleshooting

### Services not starting
```bash
# Check service logs
docker-compose -f docker-compose.integration.yml logs [service-name]

# Restart specific service
docker-compose -f docker-compose.integration.yml restart [service-name]
```

### Port conflicts
If you have port conflicts, modify the ports in `docker-compose.integration.yml`

### Database issues
```bash
# Reset databases
docker-compose -f docker-compose.integration.yml down -v
docker-compose -f docker-compose.integration.yml up -d
```

## Development

### Adding New Tests
1. Add test methods to `tests/test_msa_integration.py`
2. Follow the pattern of existing tests
3. Use the provided JWT token for authenticated requests

### Debugging
- Set `LOG_LEVEL=DEBUG` in docker-compose
- Check NATS monitoring at http://localhost:18222
- Use `docker exec` to access service containers

## Cleanup
```bash
# Stop and remove all containers, volumes
docker-compose -f docker-compose.integration.yml down -v
```