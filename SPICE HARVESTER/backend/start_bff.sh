#!/bin/bash
# 🔥 THINK ULTRA!! BFF Startup Script

# Set PYTHONPATH - Include both BFF and shared directories
export PYTHONPATH="/Users/isihyeon/Desktop/SPICE HARVESTER/backend/backend-for-frontend:/Users/isihyeon/Desktop/SPICE HARVESTER/backend:/Users/isihyeon/Desktop/SPICE HARVESTER/backend/shared:$PYTHONPATH"

# Change to BFF directory
cd "/Users/isihyeon/Desktop/SPICE HARVESTER/backend/backend-for-frontend"

# Debug: Show Python path
echo "🔥 THINK ULTRA!! PYTHONPATH configured:"
echo "$PYTHONPATH"

# Start BFF
echo "🔥 THINK ULTRA!! Starting BFF..."
python -m uvicorn main:app --host 0.0.0.0 --port 8002