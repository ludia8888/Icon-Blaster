#!/usr/bin/env python3
"""Check imports in Docker environment"""
import sys
import os

print("=== Docker Import Debug ===")
print(f"Python executable: {sys.executable}")
print(f"Working directory: {os.getcwd()}")
print(f"__file__ location: {__file__}")

# Check various path configurations
print("\n=== Python Path ===")
for idx, path in enumerate(sys.path):
    print(f"{idx}: {path}")

# Test if we're in Docker
in_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_CONTAINER')
print(f"\nRunning in Docker: {in_docker}")

# Test imports
print("\n=== Testing Imports ===")

# Test 1: Direct import
try:
    import database.clients.unified_http_client
    print("✅ Direct import of database.clients.unified_http_client: SUCCESS")
except ImportError as e:
    print(f"❌ Direct import failed: {e}")

# Test 2: Adding /app to path
if in_docker:
    sys.path.insert(0, '/app')
    print("\nAdded /app to sys.path")
    try:
        import database.clients.unified_http_client
        print("✅ Import after adding /app: SUCCESS")
    except ImportError as e:
        print(f"❌ Import still failed: {e}")

# Test 3: Check file existence
print("\n=== File System Check ===")
paths_to_check = [
    "/app/database",
    "/app/database/__init__.py",
    "/app/database/clients",
    "/app/database/clients/__init__.py",
    "/app/database/clients/unified_http_client.py",
    "./database",
    "./database/__init__.py",
    "./database/clients",
    "./database/clients/__init__.py",
    "./database/clients/unified_http_client.py",
]

for path in paths_to_check:
    exists = os.path.exists(path)
    is_file = os.path.isfile(path) if exists else False
    is_dir = os.path.isdir(path) if exists else False
    
    status = "✅" if exists else "❌"
    type_info = "FILE" if is_file else "DIR" if is_dir else "MISSING"
    print(f"{status} {path} [{type_info}]")

# Test 4: List contents of database/clients if it exists
client_dirs = ["/app/database/clients", "./database/clients"]
for client_dir in client_dirs:
    if os.path.exists(client_dir):
        print(f"\n=== Contents of {client_dir} ===")
        for item in os.listdir(client_dir):
            print(f"  - {item}")
        break