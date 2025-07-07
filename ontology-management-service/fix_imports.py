#!/usr/bin/env python3
"""Fix import issues by setting up proper Python path"""
import sys
import os

def setup_python_path():
    """Add the project root to Python path"""
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Add it to the Python path if not already there
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
        print(f"Added {script_dir} to Python path")
    
    return script_dir

def test_imports():
    """Test if imports work correctly"""
    errors = []
    successes = []
    
    test_imports = [
        ("database.clients", "Database clients module"),
        ("database.clients.unified_database_client", "Unified database client"),
        ("database.clients.unified_http_client", "Unified HTTP client"),
        ("database.clients.terminus_db", "TerminusDB client"),
        ("shared.database.sqlite_connector", "SQLite connector"),
        ("shared.database.postgres_connector", "PostgreSQL connector"),
        ("core.audit.audit_database", "Audit database"),
        ("utils.logger", "Logger utility"),
    ]
    
    for module_path, description in test_imports:
        try:
            __import__(module_path)
            successes.append(f"✅ {description} ({module_path})")
        except ImportError as e:
            errors.append(f"❌ {description} ({module_path}): {e}")
        except Exception as e:
            errors.append(f"⚠️  {description} ({module_path}): {type(e).__name__}: {e}")
    
    return successes, errors

def create_fixed_start_script():
    """Create a fixed start.sh script with proper paths"""
    script_content = '''#!/bin/bash

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# Set Python path to include the project directory
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

# Enable verbose logging
export LOG_LEVEL=DEBUG
export PYTHONUNBUFFERED=1

echo "Working directory: $SCRIPT_DIR"
echo "Python path: $PYTHONPATH"

# Start multiple services in background
echo "Starting OMS services..."

# Start main API server
echo "Starting main API server on port 8000..."
cd "$SCRIPT_DIR" && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1 --log-level debug &
MAIN_PID=$!

# Start GraphQL HTTP service (Modular with enterprise features)
echo "Starting GraphQL HTTP service on port 8006..."
cd "$SCRIPT_DIR" && python -m uvicorn api.graphql.modular_main:app --host 0.0.0.0 --port 8006 --workers 1 --log-level debug &
GRAPHQL_HTTP_PID=$!

# Start GraphQL WebSocket service
echo "Starting GraphQL WebSocket service on port 8004..."
cd "$SCRIPT_DIR" && python -m uvicorn api.graphql.main:app --host 0.0.0.0 --port 8004 --workers 1 --log-level debug &
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
    kill $MAIN_PID 2>/dev/null
    kill $GRAPHQL_HTTP_PID 2>/dev/null
    kill $GRAPHQL_WS_PID 2>/dev/null
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
'''
    
    return script_content

def main():
    print("=== OMS Import Issue Fixer ===")
    print()
    
    # Setup Python path
    project_root = setup_python_path()
    print(f"Project root: {project_root}")
    print()
    
    # Test imports
    print("Testing imports...")
    successes, errors = test_imports()
    
    print("\nSuccessful imports:")
    for success in successes:
        print(f"  {success}")
    
    if errors:
        print("\nFailed imports:")
        for error in errors:
            print(f"  {error}")
    
    # Create fixed start script
    print("\nCreating fixed start script...")
    fixed_script = create_fixed_start_script()
    
    script_path = os.path.join(project_root, "start_fixed.sh")
    with open(script_path, "w") as f:
        f.write(fixed_script)
    
    # Make it executable
    os.chmod(script_path, 0o755)
    print(f"Created fixed start script: {script_path}")
    
    # Provide recommendations
    print("\n=== Recommendations ===")
    print("1. Use the fixed start script: ./start_fixed.sh")
    print("2. If running Python scripts directly, use:")
    print(f"   export PYTHONPATH={project_root}:$PYTHONPATH")
    print("3. Or run scripts from the project root with:")
    print(f"   cd {project_root} && python your_script.py")
    
    if errors:
        print("\n⚠️  Some imports are still failing. This might be due to:")
        print("   - Missing dependencies (run: pip install -r requirements.txt)")
        print("   - Syntax errors in the imported modules")
        print("   - Circular imports")

if __name__ == "__main__":
    main()