#!/usr/bin/env python3
"""Debug Python path and module import issues"""
import sys
import os

print("=== Python Path Debug ===")
print(f"Python executable: {sys.executable}")
print(f"Current working directory: {os.getcwd()}")
print(f"\nPython path:")
for path in sys.path:
    print(f"  - {path}")

print("\n=== Checking database.clients module ===")
database_path = os.path.join(os.getcwd(), 'database')
clients_path = os.path.join(database_path, 'clients')

print(f"database/ exists: {os.path.exists(database_path)}")
print(f"database/clients/ exists: {os.path.exists(clients_path)}")
print(f"database/__init__.py exists: {os.path.exists(os.path.join(database_path, '__init__.py'))}")
print(f"database/clients/__init__.py exists: {os.path.exists(os.path.join(clients_path, '__init__.py'))}")

if os.path.exists(clients_path):
    print(f"\nFiles in database/clients/:")
    for file in os.listdir(clients_path):
        print(f"  - {file}")

print("\n=== Trying to import database.clients ===")
try:
    import database.clients
    print("✓ Successfully imported database.clients")
    print(f"  Module path: {database.clients.__file__}")
except ImportError as e:
    print(f"✗ Failed to import database.clients: {e}")

print("\n=== Trying direct import from current directory ===")
sys.path.insert(0, os.getcwd())
try:
    import database.clients
    print("✓ Successfully imported database.clients after adding cwd to sys.path")
    print(f"  Module path: {database.clients.__file__}")
except ImportError as e:
    print(f"✗ Still failed to import database.clients: {e}")