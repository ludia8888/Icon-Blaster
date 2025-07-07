#!/usr/bin/env python3
"""Debug script to check import paths and modules"""
import sys
import os

print("=" * 80)
print("PYTHON IMPORT DEBUG INFORMATION")
print("=" * 80)

print("\n1. Python version:")
print(sys.version)

print("\n2. Current working directory:")
print(os.getcwd())

print("\n3. PYTHONPATH environment variable:")
print(os.environ.get('PYTHONPATH', 'Not set'))

print("\n4. sys.path contents:")
for i, path in enumerate(sys.path):
    print(f"  [{i}] {path}")

print("\n5. Checking if database module exists:")
database_path = os.path.join(os.getcwd(), 'database')
print(f"  database directory exists: {os.path.exists(database_path)}")
if os.path.exists(database_path):
    print(f"  database/__init__.py exists: {os.path.exists(os.path.join(database_path, '__init__.py'))}")
    clients_path = os.path.join(database_path, 'clients')
    print(f"  database/clients directory exists: {os.path.exists(clients_path)}")
    if os.path.exists(clients_path):
        print(f"  database/clients/__init__.py exists: {os.path.exists(os.path.join(clients_path, '__init__.py'))}")

print("\n6. Trying to import database.clients:")
try:
    import database.clients
    print("  SUCCESS: database.clients imported")
except ImportError as e:
    print(f"  FAILED: {e}")

print("\n7. Trying direct import after adding to path:")
sys.path.insert(0, '/app')
try:
    import database.clients
    print("  SUCCESS: database.clients imported after adding /app to path")
except ImportError as e:
    print(f"  FAILED: {e}")

print("\n8. Environment variables:")
for key, value in os.environ.items():
    if key.startswith(('PYTHON', 'PATH', 'LOG')):
        print(f"  {key}={value}")

print("=" * 80)