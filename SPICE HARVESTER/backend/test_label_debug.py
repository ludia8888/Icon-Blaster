#!/usr/bin/env python3
"""
Debug Label Registration
"""

import httpx
import asyncio
import json
import sys
import os

# Add backend paths to properly import the label mapper
current_dir = os.path.dirname(os.path.abspath(__file__))
bff_dir = os.path.join(current_dir, 'backend-for-frontend')
shared_dir = os.path.join(current_dir, 'shared')
sys.path.insert(0, bff_dir)
sys.path.insert(0, shared_dir)

from utils.label_mapper import LabelMapper

async def test_direct_registration():
    """Test label registration directly"""
    
    mapper = LabelMapper()
    
    # Test registration
    print("1. Testing direct label registration...")
    test_db = "debugtest"
    test_id = "TestClass"
    test_label = "Test Class"
    
    try:
        await mapper.register_class(
            db_name=test_db,
            class_id=test_id,
            label=test_label,
            description="Debug test"
        )
        print("   Registration completed")
    except Exception as e:
        print(f"   Registration error: {e}")
        import traceback
        traceback.print_exc()
    
    # Test retrieval
    print("\n2. Testing retrieval...")
    try:
        result = await mapper.get_class_id(test_db, test_label, 'ko')
        print(f"   get_class_id('{test_label}', 'ko') = {result}")
        
        result = await mapper.get_class_id(test_db, test_label, 'en')
        print(f"   get_class_id('{test_label}', 'en') = {result}")
        
        # Try without language
        result = await mapper.get_class_id(test_db, test_id, 'ko')
        print(f"   get_class_id('{test_id}', 'ko') = {result}")
    except Exception as e:
        print(f"   Retrieval error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_direct_registration())