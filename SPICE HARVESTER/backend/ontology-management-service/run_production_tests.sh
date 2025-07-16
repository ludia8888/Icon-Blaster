#!/bin/bash

# Production Readiness Test Runner
# This script sets up the environment, starts services, and runs comprehensive tests

set -e

echo "=========================================="
echo "PRODUCTION READINESS TEST SUITE"
echo "=========================================="
echo "Time: $(date)"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Paths
OMS_PATH="/Users/isihyeon/Desktop/SPICE HARVESTER/backend/ontology-management-service"
BFF_PATH="/Users/isihyeon/Desktop/SPICE FOUNDRY/backend/backend-for-frontend"

# Function to check if a port is in use
check_port() {
    lsof -i :$1 >/dev/null 2>&1
}

# Function to kill process on port
kill_port() {
    if check_port $1; then
        echo "Killing process on port $1..."
        lsof -ti :$1 | xargs kill -9 2>/dev/null || true
        sleep 2
    fi
}

# Function to install dependencies
install_deps() {
    echo -e "${YELLOW}Installing dependencies...${NC}"
    
    # Install BFF dependencies
    if [ -f "$BFF_PATH/requirements.txt" ]; then
        echo "Installing BFF dependencies..."
        pip install -r "$BFF_PATH/requirements.txt" --quiet
    fi
    
    # Install OMS dependencies  
    if [ -f "$OMS_PATH/requirements.txt" ]; then
        echo "Installing OMS dependencies..."
        pip install -r "$OMS_PATH/requirements.txt" --quiet
    fi
    
    # Install test dependencies
    pip install httpx pytest pytest-asyncio --quiet
    
    echo -e "${GREEN}✓ Dependencies installed${NC}"
}

# Function to start a service
start_service() {
    local name=$1
    local path=$2
    local port=$3
    local log_file="${name}_$(date +%Y%m%d_%H%M%S).log"
    
    echo -e "${YELLOW}Starting $name on port $port...${NC}"
    
    cd "$path"
    nohup python -m uvicorn main:app --host 0.0.0.0 --port $port > "$log_file" 2>&1 &
    local pid=$!
    
    # Wait for service to be ready
    local max_attempts=30
    local attempt=0
    
    while [ $attempt -lt $max_attempts ]; do
        if curl -s "http://localhost:$port/health" >/dev/null 2>&1; then
            echo -e "${GREEN}✓ $name started successfully (PID: $pid)${NC}"
            echo $pid
            return 0
        fi
        
        # Check if process is still running
        if ! ps -p $pid > /dev/null; then
            echo -e "${RED}✗ $name failed to start. Check $path/$log_file for details${NC}"
            tail -20 "$path/$log_file"
            return 1
        fi
        
        sleep 1
        attempt=$((attempt + 1))
    done
    
    echo -e "${RED}✗ $name failed to respond after $max_attempts seconds${NC}"
    return 1
}

# Function to stop services
stop_services() {
    echo -e "\n${YELLOW}Stopping services...${NC}"
    
    # Kill services by port
    kill_port 8000
    kill_port 8002
    
    echo -e "${GREEN}✓ Services stopped${NC}"
}

# Main execution
main() {
    # Trap to ensure cleanup on exit
    trap stop_services EXIT
    
    # Clean up any existing services
    echo -e "${YELLOW}Cleaning up existing services...${NC}"
    stop_services
    
    # Install dependencies
    install_deps
    
    # Start OMS
    OMS_PID=$(start_service "OMS" "$OMS_PATH" 8000)
    if [ $? -ne 0 ]; then
        echo -e "${RED}Failed to start OMS${NC}"
        exit 1
    fi
    
    # Start BFF
    BFF_PID=$(start_service "BFF" "$BFF_PATH" 8002)
    if [ $? -ne 0 ]; then
        echo -e "${RED}Failed to start BFF${NC}"
        exit 1
    fi
    
    echo -e "\n${GREEN}✓ All services running${NC}"
    echo "  - OMS: http://localhost:8000"
    echo "  - BFF: http://localhost:8002"
    
    # Give services time to stabilize
    echo -e "\n${YELLOW}Waiting for services to stabilize...${NC}"
    sleep 5
    
    # Run production tests
    echo -e "\n${YELLOW}Running production readiness tests...${NC}"
    echo "=========================================="
    
    cd "$OMS_PATH"
    python test_production_ready.py
    TEST_EXIT_CODE=$?
    
    echo "=========================================="
    
    if [ $TEST_EXIT_CODE -eq 0 ]; then
        echo -e "\n${GREEN}✅ PRODUCTION READINESS TESTS PASSED!${NC}"
        echo "The system is ready for production deployment."
    else
        echo -e "\n${RED}❌ PRODUCTION READINESS TESTS FAILED!${NC}"
        echo "Please review the test report and fix the issues before deployment."
    fi
    
    # Show service logs if tests failed
    if [ $TEST_EXIT_CODE -ne 0 ]; then
        echo -e "\n${YELLOW}Recent service logs:${NC}"
        echo "--- OMS Logs ---"
        tail -50 "$OMS_PATH"/OMS_*.log | tail -20
        echo "--- BFF Logs ---"
        tail -50 "$BFF_PATH"/BFF_*.log | tail -20
    fi
    
    return $TEST_EXIT_CODE
}

# Run main function
main
EXIT_CODE=$?

# Final summary
echo -e "\n${YELLOW}Test Summary:${NC}"
echo "- Start time: $(date)"
echo "- Exit code: $EXIT_CODE"

if [ -f "production_test_report_*.json" ]; then
    echo "- Test report: $(ls -t production_test_report_*.json | head -1)"
fi

exit $EXIT_CODE