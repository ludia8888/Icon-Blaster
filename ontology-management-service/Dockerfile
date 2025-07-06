FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements-minimal.txt requirements-otel.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements-minimal.txt -r requirements-otel.txt

# Copy application code
COPY . .

# Copy and set up start script before changing user
COPY start.sh .
RUN chmod +x start.sh

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose ports
EXPOSE 8000 8090 8006 8004 9090

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run all services
CMD ["./start.sh"]