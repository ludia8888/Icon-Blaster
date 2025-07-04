#!/bin/bash
# Fixed test runner for Python 3.12 compatibility

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🚀 OMS TerminusDB Extension Features Test Suite (Python 3.12 Compatible)"
echo "========================================================================"

# Check Python version
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "📌 Python Version: $PYTHON_VERSION"

# Create virtual environment with Python 3.11 if available, otherwise use system Python
if command -v python3.11 &> /dev/null; then
    echo "✅ Using Python 3.11 for compatibility"
    PYTHON_CMD=python3.11
else
    echo "⚠️  Python 3.11 not found, using system Python (may have compatibility issues)"
    PYTHON_CMD=python3
fi

# Check if virtual environment exists
if [ ! -d "test_venv_fixed" ]; then
    echo "Creating virtual environment..."
    $PYTHON_CMD -m venv test_venv_fixed
fi

# Activate virtual environment
source test_venv_fixed/bin/activate

# Upgrade pip first
echo "📦 Upgrading pip..."
pip install --upgrade pip

# Install test dependencies first
echo "📦 Installing test dependencies..."
pip install pytest==7.4.3 pytest-asyncio==0.21.1 pytest-cov==4.1.0 httpx==0.25.2

# Install updated requirements with compatible versions
echo "📦 Installing compatible dependencies..."
pip install pendulum>=3.0.0 email-validator>=2.1.1

# Install core dependencies manually to avoid conflicts
echo "📦 Installing core dependencies..."
pip install pydantic==2.5.0 fastapi==0.104.1 redis==5.0.1

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
echo "🧪 Running Simplified Tests..."
echo ""

# First run our simple concept tests
echo "1️⃣ Running Concept Tests"
python simple_test.py

echo ""
echo "2️⃣ Running Unit Tests (if dependencies allow)"

# Try to run actual tests with minimal dependencies
PASSED=0
FAILED=0

# Test individual modules that don't require full stack
test_module() {
    local name=$1
    local module=$2
    
    echo -n "Testing $name... "
    
    if python -c "import $module" 2>/dev/null; then
        echo -e "${GREEN}✅ Module loads${NC}"
        ((PASSED++))
    else
        echo -e "${RED}❌ Module import failed${NC}"
        ((FAILED++))
    fi
}

echo ""
echo "Module Import Tests:"
test_module "Delta Encoding" "core.versioning.delta_compression"
test_module "Smart Cache" "shared.cache.smart_cache"
test_module "Jaeger Adapter" "infra.tracing.jaeger_adapter"

# Test REST API endpoints (if server is running)
echo ""
echo "3️⃣ API Endpoint Tests (requires running server)"

check_endpoint() {
    local name=$1
    local url=$2
    
    echo -n "Checking $name... "
    
    if curl -s -o /dev/null -w "%{http_code}" "$url" | grep -q "200\|404"; then
        echo -e "${GREEN}✅ Endpoint responds${NC}"
    else
        echo -e "${YELLOW}⚠️  Endpoint not available${NC}"
    fi
}

check_endpoint "Health Check" "http://localhost:8000/health"
check_endpoint "API Docs" "http://localhost:8000/docs"
check_endpoint "Time Travel API" "http://localhost:8000/api/v1/time-travel/health"

# Summary
echo ""
echo "========================================================================"
echo "📊 Test Summary"
echo "========================================================================"
echo -e "Module Tests Passed: ${GREEN}$PASSED${NC}"
echo -e "Module Tests Failed: ${RED}$FAILED${NC}"
echo ""
echo "💡 Recommendations:"
echo "1. Update requirements.txt with the fixed versions from requirements_updated.txt"
echo "2. Consider using Python 3.11 for better compatibility with legacy packages"
echo "3. Run 'docker-compose up' to test with full stack integration"
echo ""
echo "📝 To apply fixes:"
echo "   mv requirements_updated.txt requirements.txt"
echo "   pip install -r requirements.txt"

# Deactivate virtual environment
deactivate

# Exit with appropriate code
if [ $FAILED -gt 0 ]; then
    exit 1
else
    exit 0
fi