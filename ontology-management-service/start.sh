#!/bin/bash
# Enterprise-grade startup script for OMS

# Explicitly set PYTHONPATH to ensure all imports work reliably
export PYTHONPATH=.

set -e

# --- Graceful Shutdown ---
shutdown() {
  echo "Shutting down OMS..."
  # Send TERM signal to all child processes of this script
  pkill -P $$
  wait
  echo "All processes stopped."
}

trap shutdown SIGTERM SIGINT

echo "Starting Ontology Management Service..."

# --- Core Setup ---
# Ensure Python dependencies are installed and project is installed in editable mode
# This is the key to solving all import path issues reliably.
echo "1. Installing dependencies and setting up the project..."
pip install -r requirements.txt
pip install -e .

# --- Start Main API Server ---
echo "2. Starting main FastAPI server..."
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4 &

# --- Start GraphQL API Server ---
# Re-enabled after fixing the import system.
# The GraphQL server runs on a different port as a separate process.
echo "3. Starting GraphQL server..."
python -m uvicorn api.graphql.modular_main:app --host 0.0.0.0 --port 8001 --workers 2 &

# --- Start Background Worker (Example - To be enabled with ComponentManager) ---
# echo "4. Starting background worker..."
# python -m workers.main &

# --- Finalization ---
echo "Ontology Management Service started successfully."
echo "API server running on port 8000"
echo "GraphQL server running on port 8001"

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?