FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY services/scheduler-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy proto files
COPY services/scheduler-service/proto/ ./proto/

# Copy application code
COPY services/scheduler-service/app/ ./app/
COPY shared/ ./shared/

# Set Python path
ENV PYTHONPATH=/app:$PYTHONPATH

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8002/health || exit 1

# Run the application
CMD ["python", "-m", "uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8002"]