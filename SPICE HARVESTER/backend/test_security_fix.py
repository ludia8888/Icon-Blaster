#!/usr/bin/env python3
"""
Test Security Fix - check if 'id' is no longer blocked
"""

import httpx
import asyncio
import time

async def test_security_fix():
    """Test if security validation fix works"""
    
    print("Testing security validation fix...\n")
    
    async with httpx.AsyncClient(timeout=30) as client:
        
        test_cases = [
            {
                "name": "Database with 'id' in description",
                "url": "http://localhost:8000/api/v1/database/create",
                "data": {"name": f"testdb{int(time.time())}", "description": "Database with id field"}
            },
            {
                "name": "Database with 'Direct ID test' description",
                "url": "http://localhost:8000/api/v1/database/create", 
                "data": {"name": f"testdb2{int(time.time())}", "description": "Direct ID test"}
            },
            {
                "name": "Ontology with 'id' field",
                "url": f"http://localhost:8002/database/testdb{int(time.time())}/ontology",
                "data": {"label": "Test Class", "description": "Class with id information"}
            }
        ]
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"{i}. {test_case['name']}")
            
            # Create database first if needed
            if 'ontology' in test_case['url']:
                db_name = test_case['url'].split('/database/')[1].split('/')[0]
                await client.post(
                    "http://localhost:8000/api/v1/database/create",
                    json={"name": db_name, "description": "Test database"}
                )
            
            try:
                response = await client.post(test_case['url'], json=test_case['data'])
                if response.status_code in [200, 201]:
                    print(f"   ✅ SUCCESS: {response.status_code}")
                else:
                    print(f"   ❌ FAILED: {response.status_code}")
                    print(f"   Error: {response.text[:200]}...")
            except Exception as e:
                print(f"   💥 EXCEPTION: {e}")
            
            print()

if __name__ == "__main__":
    asyncio.run(test_security_fix())