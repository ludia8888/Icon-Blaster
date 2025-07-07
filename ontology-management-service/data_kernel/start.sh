#!/bin/bash
set -e

echo "Starting Data-Kernel Gateway services..."

# Start FastAPI server in background
echo "Starting FastAPI server on port 8080..."
python -m uvicorn data_kernel.main:app --host 0.0.0.0 --port 8080 &
FASTAPI_PID=$!

# Give FastAPI time to start
sleep 2

# Start gRPC server
echo "Starting gRPC server on port 50051..."
python -m data_kernel.grpc_server &
GRPC_PID=$!

# Function to handle shutdown
shutdown() {
    echo "Shutting down services..."
    kill $FASTAPI_PID $GRPC_PID 2>/dev/null || true
    exit 0
}

# Set up signal handlers
trap shutdown SIGTERM SIGINT

# Wait for both processes
echo "Data-Kernel Gateway started successfully"
echo "FastAPI: http://0.0.0.0:8080"
echo "gRPC: 0.0.0.0:50051"

# Keep the script running
wait $FASTAPI_PID $GRPC_PID