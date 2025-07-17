#!/bin/bash
# 🔥 THINK ULTRA!! OMS Startup Script

# Set PYTHONPATH - Include OMS directory first
export PYTHONPATH="/Users/isihyeon/Desktop/SPICE HARVESTER/backend/ontology-management-service:/Users/isihyeon/Desktop/SPICE HARVESTER/backend:/Users/isihyeon/Desktop/SPICE HARVESTER/backend/shared:$PYTHONPATH"

# Change to OMS directory
cd "/Users/isihyeon/Desktop/SPICE HARVESTER/backend/ontology-management-service"

# Debug: Show Python path
echo "🔥 THINK ULTRA!! PYTHONPATH configured:"
echo "$PYTHONPATH"

# Start OMS
echo "🔥 THINK ULTRA!! Starting OMS..."
python -m uvicorn main:app --host 0.0.0.0 --port 8000