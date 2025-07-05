# 🚀 OMS Full Stack Test Guide

## Prerequisites

1. **Docker Desktop** must be installed and running
   - macOS: Install from https://www.docker.com/products/docker-desktop/
   - Verify: `docker version` should show both client and server info

2. **Python 3.11+** for running test scripts
   - Install httpx: `pip install httpx`

## Quick Start

```bash
# 1. Start Docker Desktop (if not running)
# On macOS: Open Docker Desktop from Applications

# 2. Start the full stack
./start_full_stack.sh

# 3. Wait for services to be ready (about 30 seconds)

# 4. Run the test suite
python test_full_stack.py
```

## Service Architecture

The full stack includes:

| Service | Port | Purpose |
|---------|------|---------|
| Main API | 8000 | REST API with secure authentication |
| API Gateway | 8090 | Unified entry point |
| GraphQL HTTP | 8006 | GraphQL queries and mutations |
| GraphQL WebSocket | 8004 | Real-time subscriptions |
| TerminusDB | 6363 | Graph database for ontologies |
| PostgreSQL | 5432 | Audit logs and user management |
| Redis | 6379 | Caching and message broker |
| NATS | 4222 | Event streaming |
| Prometheus | 9090 | Metrics collection |
| Grafana | 3000 | Metrics visualization (optional) |
| Jaeger | 16686 | Distributed tracing (optional) |

## Testing Features

### 1. Authentication Flow
- User registration with secure password
- JWT token generation
- Token-based API access

### 2. Secure Database Operations
- Automatic audit field tracking
- Cryptographic author verification
- Service account support

### 3. Schema Management
- Create ontology schemas
- Automatic audit metadata
- Version tracking

### 4. Document Operations
- CRUD operations with audit trails
- Secure author attribution
- Soft delete support

### 5. Monitoring
- Prometheus metrics
- DLQ monitoring
- Audit event tracking

## Manual Testing

### API Documentation
Visit http://localhost:8000/docs for interactive API documentation

### Test Authentication
```bash
# Register a user
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "TestPass123!",
    "full_name": "Test User"
  }'

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=testuser&password=TestPass123!"

# Use the token from login response
export TOKEN="<your-token>"

# Get user info
curl http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN"
```

### Test Schema Operations
```bash
# Create a schema
curl -X POST http://localhost:8000/api/v1/schema \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "@context": {
      "@type": "@context",
      "@base": "http://example.com/",
      "@schema": "http://example.com/schema#"
    },
    "Person": {
      "@type": "Class",
      "name": "xsd:string",
      "age": "xsd:integer"
    }
  }'
```

### GraphQL Testing
Visit http://localhost:8006/graphql for GraphQL playground

Example query:
```graphql
query {
  __schema {
    types {
      name
      description
    }
  }
}
```

## Monitoring

### View Metrics
```bash
# Prometheus metrics
curl http://localhost:9090/metrics | grep audit

# Check DLQ status
curl http://localhost:9090/metrics | grep dlq
```

### View Logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f oms-monolith

# With timestamps
docker-compose logs -f -t oms-monolith
```

## Troubleshooting

### Services not starting
```bash
# Check Docker status
docker info

# View detailed logs
docker-compose logs

# Check specific service
docker-compose ps
docker-compose logs <service-name>
```

### Port conflicts
```bash
# Check if ports are in use
lsof -i :8000
lsof -i :6363
lsof -i :5432

# Stop conflicting services or change ports in docker-compose.yml
```

### Database connection issues
```bash
# Check PostgreSQL
docker-compose exec postgres pg_isready -U oms_user

# Check TerminusDB
curl http://localhost:6363

# Check Redis
docker-compose exec redis redis-cli ping
```

## Clean Up

```bash
# Stop all services
docker-compose down

# Stop and remove all data
docker-compose down -v

# Remove all images
docker-compose down --rmi all
```

## Performance Testing

For load testing, you can use the included test script with concurrent requests:

```python
# Modify test_full_stack.py to add concurrent testing
async def load_test(token: str, num_requests: int = 100):
    """Simple load test"""
    tasks = []
    for i in range(num_requests):
        task = test_document_operations(token)
        tasks.append(task)
    
    start = time.time()
    await asyncio.gather(*tasks)
    duration = time.time() - start
    
    print(f"Completed {num_requests} requests in {duration:.2f} seconds")
    print(f"Requests per second: {num_requests/duration:.2f}")
```

## Security Features Tested

1. **JWT Authentication**: Secure token-based auth
2. **Audit Trails**: All operations tracked with user attribution
3. **Secure Author Strings**: Cryptographic verification of document authors
4. **Service Account Identification**: Proper tagging of automated operations
5. **DLQ for Failed Audits**: No audit events are lost
6. **Role-Based Access Control**: Permission checks on all endpoints

## Next Steps

1. Explore the API documentation at http://localhost:8000/docs
2. Test GraphQL subscriptions for real-time updates
3. Configure Grafana dashboards for monitoring
4. Set up Jaeger for distributed tracing
5. Run integration tests with `docker-compose -f docker-compose.integration.yml up`