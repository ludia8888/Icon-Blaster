#!/usr/bin/env python3
"""
Direct OMS Ontology Creation Test
"""

import httpx
import asyncio
import json
from test_config import TestConfig

async def test_direct_oms():
    """Test OMS ontology creation directly"""
    
    test_db = "test_direct_oms"
    
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Create test database
        print("1. Creating test database...")
        try:
            response = await client.post(
                "http://{TestConfig.get_oms_base_url()}/api/v1/database/create",
                json={"name": test_db, "description": "Direct OMS test"}
            )
            print(f"   DB creation: {response.status_code}")
        except Exception as e:
            print(f"   Error: {e}")
        
        # 2. Test OMS ontology creation with different formats
        print("\n2. Testing OMS ontology creation formats...")
        
        # Format 1: Basic format with properties as dict
        test_formats = [
            {
                "name": "Format 1: Basic with dict properties",
                "data": {
                    "id": "TestClass1",
                    "label": "Test Class 1",
                    "description": "Basic format test",
                    "properties": {
                        "name": "xsd:string",
                        "value": "xsd:integer"
                    }
                }
            },
            {
                "name": "Format 2: With @type",
                "data": {
                    "id": "TestClass2",
                    "@type": "Class",
                    "label": "Test Class 2",
                    "description": "With @type",
                    "properties": {
                        "name": "xsd:string"
                    }
                }
            },
            {
                "name": "Format 3: Array properties",
                "data": {
                    "id": "TestClass3",
                    "label": "Test Class 3",
                    "description": "Array properties",
                    "properties": [
                        {"name": "prop1", "type": "xsd:string", "label": "Property 1"},
                        {"name": "prop2", "type": "xsd:integer", "label": "Property 2"}
                    ]
                }
            },
            {
                "name": "Format 4: Multilingual",
                "data": {
                    "id": "TestClass4",
                    "label": {"en": "Test Class 4", "ko": "테스트 클래스 4"},
                    "description": {"en": "Multilingual test"},
                    "properties": []
                }
            }
        ]
        
        for test_format in test_formats:
            print(f"\n   Testing {test_format['name']}...")
            print(f"   Data: {json.dumps(test_format['data'], indent=2)}")
            
            try:
                response = await client.post(
                    f"{TestConfig.get_oms_base_url()}/api/v1/ontology/{test_db}/create",
                    json=test_format['data']
                )
                print(f"   Result: {response.status_code}")
                if response.status_code != 200:
                    print(f"   Response: {response.text}")
                else:
                    print(f"   Success: {response.json().get('message', 'Created')}")
            except Exception as e:
                print(f"   Error: {e}")
        
        # 3. Clean up
        print("\n3. Cleaning up...")
        try:
            await client.delete(f"{TestConfig.get_oms_base_url()}/api/v1/database/{test_db}")
            print("   Cleanup done")
        except (httpx.HTTPError, httpx.TimeoutException, ConnectionError):
            print("   Cleanup failed")

if __name__ == "__main__":
    asyncio.run(test_direct_oms())