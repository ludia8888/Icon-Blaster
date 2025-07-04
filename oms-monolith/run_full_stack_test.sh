#!/bin/bash
# Full Stack Test Runner with Docker Compose

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 OMS Full Stack Testing Suite${NC}"
echo "========================================"
echo "This will start all services and run comprehensive tests"
echo ""

# Function to check if docker is running
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        echo -e "${RED}❌ Docker is not running. Please start Docker first.${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ Docker is running${NC}"
}

# Function to check if docker-compose is installed
check_docker_compose() {
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null 2>&1; then
        echo -e "${RED}❌ Docker Compose is not installed.${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ Docker Compose is available${NC}"
}

# Function to stop services
stop_services() {
    echo -e "\n${YELLOW}🛑 Stopping services...${NC}"
    docker-compose down -v
}

# Trap to ensure services are stopped on exit
trap stop_services EXIT

# Check prerequisites
echo -e "${BLUE}📋 Checking prerequisites...${NC}"
check_docker
check_docker_compose

# Create test environment file
echo -e "\n${BLUE}📝 Creating test environment...${NC}"
cat > .env.test << EOF
# Test Environment Configuration
APP_ENV=test
LOG_LEVEL=INFO

# JWT Configuration
JWT_SECRET=test-secret-key-for-full-stack-testing
JWT_ISSUER=oms-test
JWT_AUDIENCE=oms-test-audience

# Database URLs
TERMINUS_SERVER=http://localhost:6363
TERMINUS_DATABASE=test_db
TERMINUS_USER=admin
TERMINUS_PASSWORD=root

DATABASE_URL=postgresql://oms_user:oms_password@localhost:5432/oms_db

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_URL=redis://localhost:6379

# NATS
NATS_URL=nats://localhost:4222

# Jaeger
JAEGER_AGENT_HOST=localhost
JAEGER_AGENT_PORT=6831
ENABLE_TRACING=true

# Feature Flags
ENABLE_VECTOR_EMBEDDINGS=true
ENABLE_TIME_TRAVEL=true
ENABLE_SMART_CACHE=true
ENABLE_AUDIT_LOGGING=true

# API Keys (for testing)
OPENAI_API_KEY=sk-test-mock
ANTHROPIC_API_KEY=sk-ant-test-mock
COHERE_API_KEY=test-cohere-key
HUGGINGFACE_API_KEY=hf_test_key
EOF

echo -e "${GREEN}✅ Test environment created${NC}"

# Build the application image
echo -e "\n${BLUE}🔨 Building application image...${NC}"
docker-compose build --no-cache oms-monolith

# Start services
echo -e "\n${BLUE}🚀 Starting services...${NC}"
docker-compose up -d

# Show running containers
echo -e "\n${BLUE}📦 Running containers:${NC}"
docker-compose ps

# Wait for services to be ready
echo -e "\n${YELLOW}⏳ Waiting for services to be ready...${NC}"
sleep 10

# Check service health
echo -e "\n${BLUE}🏥 Checking service health...${NC}"

# Function to check service health
check_service() {
    local name=$1
    local url=$2
    local max_retries=30
    local retry=0
    
    while [ $retry -lt $max_retries ]; do
        if curl -s -f "$url" > /dev/null 2>&1; then
            echo -e "  ${GREEN}✅ $name is ready${NC}"
            return 0
        fi
        retry=$((retry + 1))
        echo -e "  ${YELLOW}⏸️  $name not ready (attempt $retry/$max_retries)${NC}"
        sleep 2
    done
    
    echo -e "  ${RED}❌ $name failed to start${NC}"
    return 1
}

# Check each service
check_service "OMS API" "http://localhost:8000/health"
check_service "TerminusDB" "http://localhost:6363/_system"
check_service "Redis" "http://localhost:6379" || echo "  (Redis doesn't have HTTP, checking with redis-cli)"
check_service "PostgreSQL" "http://localhost:5432" || echo "  (PostgreSQL doesn't have HTTP, checking with pg_isready)"
check_service "Jaeger UI" "http://localhost:16686"

# Additional checks for non-HTTP services
echo -e "\n${BLUE}🔍 Additional service checks...${NC}"

# Check Redis
if docker exec oms-redis redis-cli ping > /dev/null 2>&1; then
    echo -e "  ${GREEN}✅ Redis is responding to PING${NC}"
else
    echo -e "  ${RED}❌ Redis is not responding${NC}"
fi

# Check PostgreSQL
if docker exec oms-postgres pg_isready -U oms_user -d oms_db > /dev/null 2>&1; then
    echo -e "  ${GREEN}✅ PostgreSQL is ready${NC}"
else
    echo -e "  ${RED}❌ PostgreSQL is not ready${NC}"
fi

# Check NATS
if docker exec oms-nats nats-server --version > /dev/null 2>&1; then
    echo -e "  ${GREEN}✅ NATS is running${NC}"
else
    echo -e "  ${RED}❌ NATS is not running${NC}"
fi

# Run the full stack tests
echo -e "\n${BLUE}🧪 Running full stack tests...${NC}"
echo "========================================"

# Install test dependencies if needed
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating virtual environment...${NC}"
    python3 -m venv venv
fi

source venv/bin/activate
pip install httpx asyncio python-dotenv

# Run the test suite
python3 full_stack_test.py

TEST_EXIT_CODE=$?

# Show logs if tests failed
if [ $TEST_EXIT_CODE -ne 0 ]; then
    echo -e "\n${RED}❌ Tests failed. Showing recent logs...${NC}"
    echo -e "\n${YELLOW}OMS Monolith logs:${NC}"
    docker-compose logs --tail=50 oms-monolith
fi

# Generate performance report
echo -e "\n${BLUE}📊 Generating performance report...${NC}"

# Check Prometheus metrics
if curl -s "http://localhost:9090/api/v1/query?query=up" > /dev/null 2>&1; then
    echo -e "  ${GREEN}✅ Prometheus metrics available${NC}"
    echo "  View metrics at: http://localhost:9090"
fi

# Check Grafana dashboards
if curl -s "http://localhost:3000" > /dev/null 2>&1; then
    echo -e "  ${GREEN}✅ Grafana dashboards available${NC}"
    echo "  View dashboards at: http://localhost:3000 (admin/admin)"
fi

# Check Jaeger traces
if curl -s "http://localhost:16686" > /dev/null 2>&1; then
    echo -e "  ${GREEN}✅ Jaeger traces available${NC}"
    echo "  View traces at: http://localhost:16686"
fi

# Summary
echo -e "\n${BLUE}📋 Test Summary${NC}"
echo "========================================"
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ All tests passed!${NC}"
else
    echo -e "${RED}❌ Some tests failed. Check the output above.${NC}"
fi

echo -e "\n${BLUE}📌 Service URLs:${NC}"
echo "  - API: http://localhost:8000"
echo "  - API Docs: http://localhost:8000/docs"
echo "  - GraphQL: http://localhost:8006/graphql"
echo "  - TerminusDB: http://localhost:6363"
echo "  - Jaeger: http://localhost:16686"
echo "  - Prometheus: http://localhost:9090"
echo "  - Grafana: http://localhost:3000"

echo -e "\n${YELLOW}💡 Tips:${NC}"
echo "  - View logs: docker-compose logs -f [service-name]"
echo "  - Stop services: docker-compose down"
echo "  - Clean up: docker-compose down -v"

# Keep services running if tests passed
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "\n${GREEN}✅ Services are still running for manual testing.${NC}"
    echo -e "${YELLOW}Press Ctrl+C to stop all services.${NC}"
    
    # Remove the trap so services stay running
    trap - EXIT
    
    # Wait for user input
    read -n 1 -s -r -p ""
fi

exit $TEST_EXIT_CODE