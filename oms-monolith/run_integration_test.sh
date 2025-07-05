#!/bin/bash

echo "🚀 Starting Full Integration Test with Docker"
echo "=========================================="

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Stop any existing containers
echo "🛑 Stopping existing containers..."
docker-compose down -v

# Build images
echo -e "\n🏗️  Building Docker images..."

# Build OMS monolith
echo "Building OMS monolith..."
docker build -t oms-monolith:latest .

# Check if user-service exists locally, if not try to pull or build
echo "Checking user-service..."
if [[ "$(docker images -q user-service:latest 2> /dev/null)" == "" ]]; then
    echo "User service image not found. Building from local directory..."
    # Assume user-service is in a sibling directory
    if [ -d "../user-service" ]; then
        cd ../user-service
        docker build -t user-service:latest .
        cd ../oms-monolith
    else
        echo -e "${RED}❌ User service directory not found at ../user-service${NC}"
        echo "Please ensure user-service is built and tagged as user-service:latest"
        exit 1
    fi
fi

# Start services
echo -e "\n🚀 Starting services with docker-compose..."
docker-compose up -d

# Wait for services to be healthy
echo -e "\n⏳ Waiting for services to be healthy..."
sleep 10

# Check service status
echo -e "\n📊 Service Status:"
docker-compose ps

# Run database migrations
echo -e "\n🗄️  Running database migrations..."
docker-compose exec -T postgres psql -U oms_user -d oms_db -c "SELECT 1;" > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Database is ready${NC}"
else
    echo -e "${RED}❌ Database not ready${NC}"
fi

# Run integration tests
echo -e "\n🧪 Running integration tests..."
python test_full_integration.py

# Capture test result
TEST_RESULT=$?

# Show logs if tests failed
if [ $TEST_RESULT -ne 0 ]; then
    echo -e "\n📋 Service logs (last 50 lines):"
    echo "=== OMS Monolith ==="
    docker-compose logs --tail=50 oms-monolith
    echo -e "\n=== User Service ==="
    docker-compose logs --tail=50 user-service
fi

# Cleanup (optional)
read -p "Do you want to stop the services? (y/N) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🛑 Stopping services..."
    docker-compose down
fi

exit $TEST_RESULT