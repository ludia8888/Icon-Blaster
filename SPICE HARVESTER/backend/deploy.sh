#!/bin/bash

# SPICE System Deployment Script
# This script builds and deploys the complete SPICE system

set -e

echo "🚀 Starting SPICE System Deployment..."

# Check if docker and docker-compose are installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Parse command line arguments
ACTION=${1:-"up"}
ENVIRONMENT=${2:-"production"}

# Function to build images
build_images() {
    echo "🔨 Building Docker images..."
    docker-compose build --no-cache
}

# Function to start services
start_services() {
    echo "🚀 Starting services..."
    docker-compose up -d
    
    echo "⏳ Waiting for services to be healthy..."
    sleep 10
    
    # Check service health
    if docker-compose ps | grep -q "unhealthy"; then
        echo "❌ Some services are unhealthy. Check logs with: docker-compose logs"
        exit 1
    fi
    
    echo "✅ All services are running!"
    echo ""
    echo "📍 Service URLs:"
    echo "   - TerminusDB: http://localhost:6363"
    echo "   - OMS API: http://localhost:8000"
    echo "   - BFF API: http://localhost:8002"
    echo ""
    echo "📊 View logs: docker-compose logs -f"
}

# Function to stop services
stop_services() {
    echo "🛑 Stopping services..."
    docker-compose down
}

# Function to clean up
cleanup() {
    echo "🧹 Cleaning up..."
    docker-compose down -v
    docker system prune -f
}

# Function to show logs
show_logs() {
    docker-compose logs -f
}

# Function to run tests
run_tests() {
    echo "🧪 Running production tests..."
    
    # Wait for services to be ready
    sleep 15
    
    # Run test script
    if [ -f "run_production_tests.sh" ]; then
        ./run_production_tests.sh
    else
        echo "⚠️  Test script not found. Skipping tests."
    fi
}

# Main deployment logic
case $ACTION in
    "build")
        build_images
        ;;
    "up")
        build_images
        start_services
        ;;
    "start")
        start_services
        ;;
    "stop")
        stop_services
        ;;
    "restart")
        stop_services
        start_services
        ;;
    "clean")
        cleanup
        ;;
    "logs")
        show_logs
        ;;
    "test")
        start_services
        run_tests
        ;;
    "deploy")
        # Full deployment with tests
        build_images
        start_services
        run_tests
        echo "✅ Deployment complete!"
        ;;
    *)
        echo "Usage: $0 [build|up|start|stop|restart|clean|logs|test|deploy] [environment]"
        echo ""
        echo "Commands:"
        echo "  build   - Build Docker images"
        echo "  up      - Build and start all services (default)"
        echo "  start   - Start services without building"
        echo "  stop    - Stop all services"
        echo "  restart - Restart all services"
        echo "  clean   - Stop services and remove volumes"
        echo "  logs    - Show service logs"
        echo "  test    - Run production tests"
        echo "  deploy  - Full deployment with tests"
        exit 1
        ;;
esac