#!/usr/bin/env python3
"""
Final Debug Test - Comprehensive check
"""

import httpx
import asyncio
import time

async def test_final():
    """Final comprehensive test"""
    
    test_db = f"finaltest{int(time.time())}"
    
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Create database
        print("1. Creating database...")
        response = await client.post(
            "http://localhost:8000/api/v1/database/create",
            json={"name": test_db, "description": "Final test"}
        )
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            # 2. Create simple ontology via BFF
            print("\n2. Creating ontology 'SimpleTest' via BFF...")
            response = await client.post(
                f"http://localhost:8002/database/{test_db}/ontology",
                json={
                    "label": "SimpleTest",
                    "properties": []
                }
            )
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                created_id = data.get('data', {}).get('id')
                print(f"   Created ID: {created_id}")
                
                # 3. Test queries
                print("\n3. Testing queries...")
                
                # Main.py endpoint
                print(f"\n   a) BFF main.py endpoint (async):")
                response = await client.get(
                    f"http://localhost:8002/database/{test_db}/ontology/SimpleTest"
                )
                print(f"      Status: {response.status_code}")
                if response.status_code != 200:
                    print(f"      Error: {response.text[:300]}...")
                
                # Try with the created ID
                if created_id:
                    print(f"\n   b) BFF with created ID '{created_id}':")
                    response = await client.get(
                        f"http://localhost:8002/database/{test_db}/ontology/{created_id}"
                    )
                    print(f"      Status: {response.status_code}")
                
                # Direct OMS query to verify data exists
                print(f"\n   c) Direct OMS query:")
                response = await client.get(
                    f"http://localhost:8000/api/v1/ontology/{test_db}/{created_id or 'SimpleTest'}"
                )
                print(f"      Status: {response.status_code}")
        
        # 4. Cleanup
        print("\n4. Cleaning up...")
        await client.delete(f"http://localhost:8000/api/v1/database/{test_db}")

if __name__ == "__main__":
    asyncio.run(test_final())