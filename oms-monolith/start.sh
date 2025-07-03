#!/bin/bash

# Start multiple services in background
echo "Starting OMS services..."

# Start main API server
echo "Starting main API server on port 8000..."
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2 &
MAIN_PID=$!

# Start GraphQL HTTP service  
echo "Starting GraphQL HTTP service on port 8006..."
python -m uvicorn api.graphql.enhanced_main:app --host 0.0.0.0 --port 8006 --workers 1 &
GRAPHQL_HTTP_PID=$!

# Start GraphQL WebSocket service
echo "Starting GraphQL WebSocket service on port 8004..."
python -m uvicorn api.graphql.main:app --host 0.0.0.0 --port 8004 --workers 1 &
GRAPHQL_WS_PID=$!

# Wait for services to start
sleep 5

echo "Services started:"
echo "  Main API: http://0.0.0.0:8000"
echo "  GraphQL HTTP: http://0.0.0.0:8006"  
echo "  GraphQL WebSocket: http://0.0.0.0:8004"

# Function to handle shutdown
shutdown() {
    echo "Shutting down services..."
    kill $MAIN_PID $GRAPHQL_HTTP_PID $GRAPHQL_WS_PID 2>/dev/null
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