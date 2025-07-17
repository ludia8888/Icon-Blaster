#!/usr/bin/env python3
"""
Test BFF Response Structure
"""

import httpx
import asyncio
import json
from test_config import TestConfig

async def test_bff_response():
    """Test BFF response structure"""
    
    test_db = "test_bff_response"
    
    async with httpx.AsyncClient(timeout=TestConfig.get_test_timeout()) as client:
        # 1. Create test database
        print("1. Creating test database...")
        await client.post(
            TestConfig.get_database_create_url(),
            json={"name": test_db, "description": "BFF response test"}
        )
        
        # 2. Create ontology and examine response
        print("\n2. Creating ontology and examining response...")
        test_ontology = {
            "label": "Simple Test",
            "properties": []
        }
        
        response = await client.post(
            TestConfig.get_bff_ontology_url(test_db),
            json=test_ontology
        )
        
        print(f"   Status: {response.status_code}")
        print(f"   Headers: {dict(response.headers)}")
        print(f"\n   Raw response text:")
        print(f"   {response.text}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"\n   Parsed JSON structure:")
                print(f"   {json.dumps(data, indent=2)}")
                
                # Check different possible ID locations
                print(f"\n   Checking ID locations:")
                print(f"   - data.id: {data.get('id', 'Not found')}")
                print(f"   - data.data.id: {data.get('data', {}).get('id', 'Not found')}")
                
                # Get the actual ID for query test
                actual_id = data.get('id') or data.get('data', {}).get('id')
                if actual_id:
                    print(f"\n3. Testing query with ID: {actual_id}")
                    query_response = await client.get(
                        TestConfig.get_bff_ontology_url(test_db, f"/{actual_id}")
                    )
                    print(f"   Query status: {query_response.status_code}")
            except Exception as e:
                print(f"   Error parsing JSON: {e}")
        
        # 3. Clean up
        print("\n4. Cleaning up...")
        await client.delete(TestConfig.get_database_delete_url(test_db))

if __name__ == "__main__":
    asyncio.run(test_bff_response())