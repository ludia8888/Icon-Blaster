#!/bin/bash

# Set Python path to include app directory
export PYTHONPATH=/app:$PYTHONPATH

# Enable verbose logging
export LOG_LEVEL=DEBUG
export PYTHONUNBUFFERED=1

# Change to app directory
cd /app

# Start multiple services in background
echo "Starting OMS services..."

# Start main API server
echo "Starting main API server on port 8000..."
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1 --log-level debug &
MAIN_PID=$!

# Temporarily disable GraphQL services due to import issues
# Will enable after fixing module import problems

# Run debug script
python /app/debug_imports.py > /tmp/debug_imports.log 2>&1 &

# Wait for services to start
sleep 5

echo "Services started:"
echo "  Main API: http://0.0.0.0:8000"

# Function to handle shutdown
shutdown() {
    echo "Shutting down services..."
    kill $MAIN_PID 2>/dev/null
    wait
    echo "All services stopped"
    exit 0
}

# Set up signal handling
trap shutdown SIGTERM SIGINT

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?