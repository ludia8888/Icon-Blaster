#!/usr/bin/env python3
"""
Debug BFF data flow and response formats
"""

import asyncio
import httpx
import json
import time


async def test_bff_data_flow():
    """Debug BFF data flow"""
    bff_url = "http://localhost:8002"
    oms_url = "http://localhost:8000"
    test_db = f"debug_test_{int(time.time())}"
    
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Create test database
        print(f"1. Creating test database: {test_db}")
        response = await client.post(
            f"{oms_url}/api/v1/database/create",
            json={"name": test_db}
        )
        print(f"   Database creation: {response.status_code}")
        
        # 2. Create simple ontology through BFF
        simple_ontology = {
            "label": "SimpleTest",
            "properties": [
                {"name": "name", "type": "xsd:string", "label": "Name"}
            ]
        }
        
        print("\n2. Creating simple ontology through BFF...")
        response = await client.post(
            f"{bff_url}/database/{test_db}/ontology",
            json=simple_ontology
        )
        print(f"   BFF creation response: {response.status_code}")
        
        if response.status_code == 200:
            bff_response = response.json()
            # Extract ID from the correct location
            if isinstance(bff_response, dict) and "data" in bff_response:
                created_id = bff_response["data"].get("id")
            else:
                created_id = bff_response.get("id")
            print(f"   Created ID: {created_id}")
        else:
            print(f"   Creation failed: {response.text}")
            return
        
        # 3. Get the ontology directly from OMS
        print(f"\n3. Getting ontology '{created_id}' directly from OMS...")
        response = await client.get(
            f"{oms_url}/api/v1/ontology/{test_db}/{created_id}"
        )
        print(f"   OMS response status: {response.status_code}")
        if response.status_code == 200:
            oms_data = response.json()
            print(f"   OMS response structure:")
            print(f"   - Keys: {list(oms_data.keys())}")
            if "data" in oms_data:
                print(f"   - Data keys: {list(oms_data['data'].keys())}")
                print(f"   - Full data: {json.dumps(oms_data['data'], indent=2)}")
        
        # 4. Get the ontology through BFF by ID
        print(f"\n4. Getting ontology '{created_id}' through BFF...")
        response = await client.get(
            f"{bff_url}/database/{test_db}/ontology/{created_id}"
        )
        print(f"   BFF response status: {response.status_code}")
        if response.status_code == 200:
            bff_data = response.json()
            print(f"   BFF response: {json.dumps(bff_data, indent=2)}")
        else:
            print(f"   BFF error: {response.text}")
        
        # 5. Try to get by label
        print(f"\n5. Getting ontology by label 'SimpleTest' through BFF...")
        response = await client.get(
            f"{bff_url}/database/{test_db}/ontology/SimpleTest"
        )
        print(f"   BFF response status: {response.status_code}")
        if response.status_code == 200:
            bff_data = response.json()
            print(f"   BFF response: {json.dumps(bff_data, indent=2)}")
        else:
            print(f"   BFF error: {response.text}")
        
        # Cleanup
        print(f"\n6. Cleaning up test database: {test_db}")
        await client.delete(f"{oms_url}/api/v1/database/{test_db}")


if __name__ == "__main__":
    asyncio.run(test_bff_data_flow())