# OMS + User Service Integration Testing

This guide explains how to run integration tests between the OMS monolith and the User Service (IAM).

## Prerequisites

- Docker and Docker Compose installed
- Python 3.11+ installed (for running test scripts)
- Port 5432, 5433, 6379, 8000, and 8001 available

## Architecture

The integration test setup includes:
- **User Service (IAM)**: Running on port 8001
- **OMS Monolith**: Running on port 8000  
- **PostgreSQL for User Service**: Port 5433
- **PostgreSQL for OMS**: Port 5432
- **Redis**: Port 6379 (shared)

## Running the Integration Tests

### 1. Start the Services

```bash
# From the SPICE directory
docker-compose up -d
```

Wait for all services to be healthy:
```bash
docker-compose ps
```

### 2. Initialize Test Data

```bash
# Install required Python packages
pip install sqlalchemy psycopg2-binary passlib[argon2]

# Initialize databases with test users
python init_test_data.py
```

This creates test users:
- `test_user` (password: `Test123!@#`, role: developer)
- `admin` (password: `Admin123!@#`, role: admin)  
- `reviewer` (password: `Review123!@#`, role: reviewer)

### 3. Run Integration Tests

```bash
# Install test dependencies
pip install httpx

# Run the integration tests
python test_integration.py
```

## What the Tests Verify

1. **Service Health**: Both services are running and healthy
2. **Service Authentication**: OMS can authenticate as a service with IAM
3. **User Login**: Users can login via the User Service
4. **Token Validation**: OMS validates user tokens via IAM service
5. **User Info Lookup**: OMS can lookup user information via IAM

## Monitoring the Services

View logs:
```bash
# User Service logs
docker-compose logs -f user-service

# OMS logs  
docker-compose logs -f oms-monolith
```

## Troubleshooting

### Services won't start
- Check if ports are already in use
- Ensure Docker has enough resources allocated
- Check logs: `docker-compose logs`

### Database connection errors
- Wait for PostgreSQL to be fully ready
- Check database credentials in docker-compose.yml
- Verify network connectivity between containers

### Authentication failures
- Ensure JWT secrets match between services
- Check that test users were created successfully
- Verify service credentials are correct

## Cleanup

Stop and remove all containers:
```bash
docker-compose down -v
```

## Configuration

Key environment variables in `docker-compose.yml`:
- `USE_MSA_AUTH=true`: Enables MSA authentication in OMS
- `IAM_SERVICE_URL`: URL for IAM service communication
- `JWT_SECRET`: Shared secret for JWT validation
- `OMS_SERVICE_SECRET`: Secret for service-to-service auth