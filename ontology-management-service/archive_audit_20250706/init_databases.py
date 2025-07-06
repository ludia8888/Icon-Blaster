#!/usr/bin/env python3
"""
Initialize all database tables for OMS
Run this script to set up audit and issue tracking databases
"""
import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.audit.audit_database import get_audit_database
from core.issue_tracking.issue_database import get_issue_database
from utils.logger import get_logger

logger = get_logger(__name__)


async def initialize_databases():
    """Initialize all databases"""
    print("Initializing OMS databases...")
    
    # Initialize audit database
    print("- Initializing audit database...")
    audit_db = await get_audit_database()
    print("  ✓ Audit database initialized")
    
    # Initialize issue tracking database
    print("- Initializing issue tracking database...")
    issue_db = await get_issue_database()
    print("  ✓ Issue tracking database initialized")
    
    print("\nAll databases initialized successfully!")
    print(f"- Audit DB: {audit_db.db_path}")
    print(f"- Issue DB: {issue_db.db_path}")


if __name__ == "__main__":
    asyncio.run(initialize_databases())