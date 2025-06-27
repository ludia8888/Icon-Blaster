#!/bin/bash

# MSA Integration Test Runner Script
# This script orchestrates the full MSA integration test

set -e

echo "🚀 MSA Integration Test Runner"
echo "=============================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Check if docker-compose is installed
if ! command -v docker-compose &> /dev/null; then
    print_error "docker-compose is not installed. Please install it first."
    exit 1
fi

# Change to the OMS directory
cd "$(dirname "$0")/.."
OMS_DIR=$(pwd)

print_status "Working directory: $OMS_DIR"

# Step 1: Clean up previous test environment
print_status "Cleaning up previous test environment..."
docker-compose -f docker-compose.integration.yml down -v --remove-orphans || true

# Step 2: Build all services
print_status "Building all services..."
docker-compose -f docker-compose.integration.yml build --parallel

# Step 3: Start all services
print_status "Starting all services..."
docker-compose -f docker-compose.integration.yml up -d

# Step 4: Wait for services to be healthy
print_status "Waiting for services to be healthy..."
MAX_WAIT=120
WAITED=0

while [ $WAITED -lt $MAX_WAIT ]; do
    if docker-compose -f docker-compose.integration.yml ps | grep -q "unhealthy\|starting"; then
        echo -n "."
        sleep 2
        WAITED=$((WAITED + 2))
    else
        break
    fi
done

echo ""

# Check if all services are healthy
if docker-compose -f docker-compose.integration.yml ps | grep -q "unhealthy"; then
    print_error "Some services failed to become healthy:"
    docker-compose -f docker-compose.integration.yml ps
    
    print_status "Checking logs for failed services..."
    docker-compose -f docker-compose.integration.yml logs --tail=50
    
    exit 1
fi

print_success "All services are healthy!"

# Step 5: Run the integration test
print_status "Running MSA integration tests..."

# Run the test from host (requires Python environment)
if command -v python3 &> /dev/null; then
    python3 tests/test_msa_integration.py
else
    # Alternative: Run test inside a container
    docker run --rm \
        --network oms-integration-network \
        -v "$OMS_DIR:/app" \
        -w /app \
        python:3.11-slim \
        bash -c "pip install httpx pytest asyncio && python tests/test_msa_integration.py"
fi

TEST_RESULT=$?

# Step 6: Collect logs regardless of test result
print_status "Collecting service logs..."
mkdir -p test-logs
docker-compose -f docker-compose.integration.yml logs > test-logs/integration-test-$(date +%Y%m%d-%H%M%S).log

# Step 7: Show test results
if [ $TEST_RESULT -eq 0 ]; then
    print_success "Integration tests passed! 🎉"
else
    print_error "Integration tests failed!"
    
    print_status "Recent logs from failed services:"
    docker-compose -f docker-compose.integration.yml logs --tail=50
fi

# Step 8: Cleanup (optional)
read -p "Do you want to keep the test environment running? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_status "Cleaning up test environment..."
    docker-compose -f docker-compose.integration.yml down -v
    print_success "Cleanup complete"
else
    print_warning "Test environment is still running. Remember to clean up with:"
    echo "  docker-compose -f docker-compose.integration.yml down -v"
fi

exit $TEST_RESULT