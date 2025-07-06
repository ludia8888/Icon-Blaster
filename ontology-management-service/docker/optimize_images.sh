#!/bin/bash
# Optimize Docker images for faster cold start

set -e

echo "🚀 Optimizing Docker images for microservices..."

# Function to build optimized image
build_optimized_image() {
    local service=$1
    local dockerfile=$2
    local tag=$3
    
    echo "Building optimized image for $service..."
    
    # Multi-stage build with minimal final image
    cat > $dockerfile.optimized << EOF
# Build stage
FROM python:3.9-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY services/$service/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.9-slim

WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /root/.local

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY services/$service/app/ ./app/
COPY services/$service/proto/ ./proto/
COPY shared/ ./shared/

# Set Python path
ENV PYTHONPATH=/app:$PYTHONPATH

# Optimize Python for production
ENV PYTHONOPTIMIZE=1
ENV PYTHONDONTWRITEBYTECODE=1

# Pre-compile Python files
RUN python -m compileall -q /app

# Run as non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Default command
CMD ["python", "-m", "uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "${PORT:-8000}"]
EOF

    # Build the optimized image
    docker build -f $dockerfile.optimized -t $tag .
    
    # Clean up
    rm $dockerfile.optimized
    
    # Show image size
    echo "Image size for $service:"
    docker images $tag --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
}

# Build optimized images for each service
build_optimized_image "embedding-service" "services/embedding-service/Dockerfile" "oms/embedding-service:optimized"
build_optimized_image "scheduler-service" "services/scheduler-service/Dockerfile" "oms/scheduler-service:optimized"
build_optimized_image "event-gateway" "services/event-gateway/Dockerfile" "oms/event-gateway:optimized"

echo "✅ Image optimization complete!"

# Create docker-compose override for optimized images
cat > docker-compose.optimized.yml << EOF
version: '3.8'

services:
  embedding-service:
    image: oms/embedding-service:optimized
    
  scheduler-service:
    image: oms/scheduler-service:optimized
    
  event-gateway:
    image: oms/event-gateway:optimized
EOF

echo "📝 Created docker-compose.optimized.yml for using optimized images"
echo ""
echo "To use optimized images, run:"
echo "  docker-compose -f docker-compose.yml -f docker-compose.microservices.yml -f docker-compose.optimized.yml up"