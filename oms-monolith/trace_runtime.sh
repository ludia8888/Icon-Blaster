#!/bin/bash
# Trace imports during actual runtime

echo "🔍 Starting import trace for OMS services..."

# Create trace directory
mkdir -p trace_results

# Trace main API server
echo "Tracing main API server..."
PYTHONPROFILEIMPORTTIME=1 python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1 2>&1 | tee trace_results/main_api_imports.log &
MAIN_PID=$!

# Let it start up
sleep 5

# Make some requests to trigger imports
echo "Making test requests..."
curl -s http://localhost:8000/health > /dev/null
curl -s http://localhost:8000/api/v1/schemas > /dev/null

# Kill the server
kill $MAIN_PID 2>/dev/null

# Trace GraphQL service
echo "Tracing GraphQL service..."
PYTHONPROFILEIMPORTTIME=1 python -m uvicorn api.graphql.modular_main:app --host 0.0.0.0 --port 8006 --workers 1 2>&1 | tee trace_results/graphql_imports.log &
GRAPHQL_PID=$!

sleep 5

# Test GraphQL
curl -s http://localhost:8006/health > /dev/null
curl -s -X POST http://localhost:8006/graphql -H "Content-Type: application/json" -d '{"query":"{ hello }"}' > /dev/null

kill $GRAPHQL_PID 2>/dev/null

echo "✅ Import traces saved to trace_results/"