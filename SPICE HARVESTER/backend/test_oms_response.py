#!/usr/bin/env python3
"""
Test OMS Response Structure
"""

import httpx
import asyncio
import json
from test_config import TestConfig

async def test_oms_response():
    """Test OMS response structure"""
    
    test_db = "test_oms_response"
    
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Create test database
        print("1. Creating test database...")
        response = await client.post(
            "http://{TestConfig.get_oms_base_url()}/api/v1/database/create",
            json={"name": test_db, "description": "OMS response test"}
        )
        print(f"   DB creation: {response.status_code}")
        
        # 2. Create ontology directly with OMS
        print("\n2. Creating ontology with OMS...")
        test_ontology = {
            "id": "TestResponseClass",
            "label": "Test Response Class",
            "description": "Testing OMS response structure",
            "properties": [
                {"name": "prop1", "type": "xsd:string", "label": "Property 1"}
            ]
        }
        
        response = await client.post(
            f"{TestConfig.get_oms_base_url()}/api/v1/ontology/{test_db}/create",
            json=test_ontology
        )
        
        print(f"   OMS creation: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"\n   OMS Response Structure:")
            print(f"   {json.dumps(result, indent=2)}")
            
            # Check specific fields
            print(f"\n   Checking response fields:")
            print(f"   - result type: {type(result)}")
            print(f"   - has 'data' key: {'data' in result}")
            if 'data' in result:
                print(f"   - data type: {type(result['data'])}")
                print(f"   - data content: {result['data']}")
        
        # 3. Clean up
        print("\n3. Cleaning up...")
        await client.delete(f"{TestConfig.get_oms_base_url()}/api/v1/database/{test_db}")

if __name__ == "__main__":
    asyncio.run(test_oms_response())