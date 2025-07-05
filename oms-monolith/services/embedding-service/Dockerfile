FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Generate proto stubs
RUN python -m grpc_tools.protoc \
    -I proto \
    --python_out=proto \
    --grpc_python_out=proto \
    --pyi_out=proto \
    proto/embedding_service.proto

# Create startup script
RUN echo '#!/bin/bash\n\
set -e\n\
echo "Starting Embedding Service..."\n\
python -m uvicorn app.api:app --host 0.0.0.0 --port 8001 &\n\
FASTAPI_PID=$!\n\
sleep 2\n\
python app/grpc_server.py &\n\
GRPC_PID=$!\n\
echo "Embedding Service started"\n\
echo "FastAPI: http://0.0.0.0:8001"\n\
echo "gRPC: 0.0.0.0:50055"\n\
wait $FASTAPI_PID $GRPC_PID' > /app/start.sh && chmod +x /app/start.sh

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose ports
EXPOSE 8001 50055

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Run both servers
CMD ["./start.sh"]