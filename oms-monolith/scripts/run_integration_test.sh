#!/bin/bash
# Integration test runner script

set -e

echo "🚀 OMS MSA Integration Test Runner"
echo "=================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check dependencies
echo -e "\n${YELLOW}📋 Checking dependencies...${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ Docker Compose is not installed${NC}"
    exit 1
fi

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✅ All dependencies found${NC}"

# Function to cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}🧹 Cleaning up...${NC}"
    docker-compose -f docker-compose.integration.yml down -v
    echo -e "${GREEN}✅ Cleanup complete${NC}"
}

# Set trap to cleanup on exit
trap cleanup EXIT

# Start services
echo -e "\n${YELLOW}🚀 Starting services...${NC}"
docker-compose -f docker-compose.integration.yml up -d

# Wait for services to be ready
echo -e "\n${YELLOW}⏳ Waiting for services to be healthy...${NC}"

# Function to check service health
check_service() {
    local service_name=$1
    local health_url=$2
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if curl -s -f "$health_url" > /dev/null 2>&1; then
            echo -e "${GREEN}✅ $service_name is ready${NC}"
            return 0
        fi
        attempt=$((attempt + 1))
        echo -n "."
        sleep 2
    done
    
    echo -e "\n${RED}❌ $service_name failed to start${NC}"
    return 1
}

# Check each service
check_service "OMS" "http://localhost:18000/health" || exit 1
check_service "Audit Service" "http://localhost:18001/health" || exit 1
check_service "TerminusDB" "http://localhost:16363/api/status" || exit 1
check_service "NATS" "http://localhost:18222/healthz" || exit 1

# Check PostgreSQL
echo -n "Checking PostgreSQL"
max_attempts=30
attempt=0
while [ $attempt -lt $max_attempts ]; do
    if docker exec oms-test-postgres pg_isready -U audit_user -d audit_db > /dev/null 2>&1; then
        echo -e "\n${GREEN}✅ PostgreSQL is ready${NC}"
        break
    fi
    attempt=$((attempt + 1))
    echo -n "."
    sleep 2
done

if [ $attempt -eq $max_attempts ]; then
    echo -e "\n${RED}❌ PostgreSQL failed to start${NC}"
    exit 1
fi

# Check Redis
echo -n "Checking Redis"
if docker exec oms-test-redis redis-cli -a redis123 ping > /dev/null 2>&1; then
    echo -e "\n${GREEN}✅ Redis is ready${NC}"
else
    echo -e "\n${RED}❌ Redis failed to start${NC}"
    exit 1
fi

echo -e "\n${GREEN}✅ All services are healthy!${NC}"

# Show service logs in background
echo -e "\n${YELLOW}📝 Showing service logs (in background)...${NC}"
docker-compose -f docker-compose.integration.yml logs -f &
LOGS_PID=$!

# Run integration tests
echo -e "\n${YELLOW}🧪 Running integration tests...${NC}"
echo "=================================="

# Set environment variables
export OMS_URL="http://localhost:18000"
export AUDIT_SERVICE_URL="http://localhost:18001"
export NATS_URL="nats://localhost:14222"
export POSTGRES_URL="postgresql://audit_user:audit_pass@localhost:15432/audit_db"
export REDIS_URL="redis://:redis123@localhost:16379"
export TERMINUSDB_SERVER="http://localhost:16363"

# Install test dependencies if needed
if ! python3 -c "import pytest" 2>/dev/null; then
    echo -e "${YELLOW}Installing test dependencies...${NC}"
    pip3 install pytest pytest-asyncio httpx asyncpg redis nats-py
fi

# Run the tests
python3 -m pytest tests/integration/test_real_msa_flow.py -v -s --tb=short

TEST_RESULT=$?

# Stop logs
kill $LOGS_PID 2>/dev/null || true

# Show results
echo -e "\n=================================="
if [ $TEST_RESULT -eq 0 ]; then
    echo -e "${GREEN}🎉 All integration tests passed!${NC}"
    
    # Show some statistics
    echo -e "\n${YELLOW}📊 Test Statistics:${NC}"
    docker exec oms-test-postgres psql -U audit_user -d audit_db -c "SELECT COUNT(*) as total_events FROM audit_events;" 2>/dev/null || true
    docker exec oms-test-postgres psql -U audit_user -d audit_db -c "SELECT status, COUNT(*) FROM outbox_events GROUP BY status;" 2>/dev/null || true
    
else
    echo -e "${RED}❌ Integration tests failed${NC}"
    
    # Show recent logs for debugging
    echo -e "\n${YELLOW}📋 Recent OMS logs:${NC}"
    docker logs oms-test-service --tail 50
    
    echo -e "\n${YELLOW}📋 Recent Audit Service logs:${NC}"
    docker logs oms-test-audit-service --tail 50
fi

exit $TEST_RESULT