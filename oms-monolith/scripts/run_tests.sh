#!/bin/bash
# Comprehensive test runner script

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🚀 OMS TerminusDB Extension Features Test Suite"
echo "=============================================="

# Check if virtual environment exists
if [ ! -d "test_venv" ]; then
    echo "Creating virtual environment..."
    python -m venv test_venv
fi

# Activate virtual environment
source test_venv/bin/activate

# Install dependencies
echo "📦 Installing test dependencies..."
pip install -q pytest pytest-asyncio pytest-cov httpx redis

# Install project dependencies if requirements.txt exists
if [ -f "requirements.txt" ]; then
    echo "📦 Installing project dependencies..."
    pip install -q -r requirements.txt
fi

# Set test environment variables
export APP_ENV=test
export JWT_SECRET=test-secret-key
export JWT_ISSUER=test-issuer
export JWT_AUDIENCE=test-audience
export TERMINUS_SERVER=http://localhost:6363
export TERMINUS_DATABASE=test_db
export REDIS_HOST=localhost
export REDIS_PORT=6379
export JAEGER_AGENT_HOST=localhost
export ENABLE_TRACING=false
export LOG_LEVEL=INFO

# Mock API keys for testing
export OPENAI_API_KEY=sk-test-mock
export ANTHROPIC_API_KEY=sk-ant-test-mock

echo ""
echo "🧪 Running Tests..."
echo ""

# Function to run test and report result
run_test() {
    local test_name=$1
    local test_path=$2
    
    echo -n "Testing $test_name... "
    
    if python -m pytest "$test_path" -v --tb=short > /tmp/test_output.txt 2>&1; then
        echo -e "${GREEN}✅ PASSED${NC}"
        return 0
    else
        echo -e "${RED}❌ FAILED${NC}"
        echo "Error output:"
        tail -20 /tmp/test_output.txt
        return 1
    fi
}

# Track results
PASSED=0
FAILED=0

echo "1️⃣ Delta Encoding Tests"
if run_test "Delta Encoding" "tests/integration/test_delta_encoding.py"; then
    ((PASSED++))
else
    ((FAILED++))
fi

echo ""
echo "2️⃣ @unfoldable Documents Tests"
if run_test "@unfoldable Documents" "tests/integration/test_unfoldable_documents.py"; then
    ((PASSED++))
else
    ((FAILED++))
fi

echo ""
echo "3️⃣ @metadata Frames Tests"
if run_test "@metadata Frames" "tests/integration/test_metadata_frames.py"; then
    ((PASSED++))
else
    ((FAILED++))
fi

echo ""
echo "4️⃣ Time Travel Queries Tests"
if run_test "Time Travel Queries" "tests/integration/test_time_travel_queries.py"; then
    ((PASSED++))
else
    ((FAILED++))
fi

echo ""
echo "5️⃣ Vector Embeddings Tests"
if run_test "Vector Embeddings" "tests/unit/test_embedding_providers.py"; then
    ((PASSED++))
else
    ((FAILED++))
fi

echo ""
echo "6️⃣ Graph Analysis Tests (includes Deep Linking, Cache, Tracing)"
if run_test "Graph Analysis" "tests/integration/test_graph_analysis_tracing_cache.py"; then
    ((PASSED++))
else
    ((FAILED++))
fi

# Summary
echo ""
echo "=============================================="
echo "📊 Test Summary"
echo "=============================================="
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
echo -e "Total: $((PASSED + FAILED))"

# Run coverage if all tests pass
if [ $FAILED -eq 0 ]; then
    echo ""
    echo "📈 Running coverage analysis..."
    python -m pytest --cov=core --cov=api --cov=shared --cov-report=term-missing tests/
fi

# Deactivate virtual environment
deactivate

# Exit with appropriate code
if [ $FAILED -gt 0 ]; then
    exit 1
else
    exit 0
fi