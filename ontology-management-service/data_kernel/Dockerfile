FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including curl for health checks
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
COPY data_kernel/requirements.txt data_kernel/
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r data_kernel/requirements.txt

# Copy the application code
COPY . .

# Generate proto stubs
RUN python -m grpc_tools.protoc \
    -I data_kernel/proto \
    --python_out=data_kernel/proto \
    --grpc_python_out=data_kernel/proto \
    --pyi_out=data_kernel/proto \
    data_kernel/proto/data_kernel.proto

# Make start script executable
RUN chmod +x data_kernel/start.sh

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose ports for both services
EXPOSE 8080 50051

# Health check for FastAPI
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run both services
CMD ["./data_kernel/start.sh"]