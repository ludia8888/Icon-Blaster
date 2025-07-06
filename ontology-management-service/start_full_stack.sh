#!/bin/bash

echo "🚀 Starting OMS Full Stack with Docker Compose"
echo "=============================================="

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop first."
    echo "   On macOS: Open Docker Desktop from Applications"
    echo "   Then run this script again."
    exit 1
fi

echo "✅ Docker is running"

# Clean up any existing containers
echo "🧹 Cleaning up existing containers..."
docker-compose down -v 2>/dev/null || true

# Build the application image
echo "🔨 Building application image..."
docker-compose build

# Start all services
echo "🚀 Starting all services..."
docker-compose up -d

# Show running containers
echo ""
echo "📦 Running containers:"
docker-compose ps

# Wait for services to be ready
echo ""
echo "⏳ Waiting for services to be ready..."
sleep 10

# Check service health
echo ""
echo "🏥 Checking service health:"
echo -n "  Main API (8000): "
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health || echo "Not ready"
echo ""
echo -n "  TerminusDB (6363): "
curl -s -o /dev/null -w "%{http_code}" http://localhost:6363 || echo "Not ready"
echo ""
echo -n "  PostgreSQL (5432): "
docker-compose exec -T postgres pg_isready -U oms_user > /dev/null 2>&1 && echo "Ready" || echo "Not ready"
echo -n "  Redis (6379): "
docker-compose exec -T redis redis-cli ping > /dev/null 2>&1 && echo "Ready" || echo "Not ready"

echo ""
echo "🌐 Service URLs:"
echo "  - Main API: http://localhost:8000"
echo "  - API Documentation: http://localhost:8000/docs"
echo "  - GraphQL HTTP: http://localhost:8006/graphql"
echo "  - GraphQL WebSocket: ws://localhost:8004/graphql"
echo "  - TerminusDB: http://localhost:6363"
echo "  - Prometheus Metrics: http://localhost:9090/metrics"
echo "  - Grafana (if enabled): http://localhost:3000 (admin/admin)"
echo "  - Jaeger UI (if enabled): http://localhost:16686"

echo ""
echo "📋 Next steps:"
echo "  1. Run the test script: python test_full_stack.py"
echo "  2. View logs: docker-compose logs -f oms-monolith"
echo "  3. Stop all services: docker-compose down"
echo "  4. Stop and remove volumes: docker-compose down -v"

echo ""
echo "✅ Full stack is starting up!"