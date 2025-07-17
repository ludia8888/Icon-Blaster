#!/usr/bin/env python3
"""
BFF Ontology Creation Debug Test
"""

import httpx
import asyncio
import json
from test_config import TestConfig

async def test_bff_ontology_creation():
    """Test BFF ontology creation with debug output"""
    
    # Test database
    test_db = "test_bff_debug"
    
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Create test database
        print("1. Creating test database...")
        try:
            response = await client.post(
                "http://{TestConfig.get_oms_base_url()}/api/v1/database/create",
                json={"name": test_db, "description": "BFF debug test"}
            )
            print(f"   DB creation: {response.status_code}")
            if response.status_code != 200:
                print(f"   Response: {response.text}")
        except Exception as e:
            print(f"   Error: {e}")
        
        # 2. Test BFF ontology creation
        print("\n2. Testing BFF ontology creation...")
        test_ontology = {
            "label": {
                "ko": "테스트 클래스",
                "en": "Test Class"
            },
            "description": {
                "ko": "BFF 디버그 테스트",
                "en": "BFF debug test"
            },
            "properties": [
                {
                    "name": "testProp",
                    "type": "xsd:string",
                    "label": {"en": "Test Property", "ko": "테스트 속성"}
                }
            ]
        }
        
        try:
            response = await client.post(
                f"{TestConfig.get_bff_base_url()}/database/{test_db}/ontology",
                json=test_ontology,
                headers={"Accept-Language": "ko"}
            )
            print(f"   BFF creation: {response.status_code}")
            print(f"   Response: {response.text}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   Created ID: {data.get('id', 'Unknown')}")
        except Exception as e:
            print(f"   Error: {e}")
            import traceback
            traceback.print_exc()
        
        # 3. Clean up
        print("\n3. Cleaning up...")
        try:
            await client.delete(f"{TestConfig.get_oms_base_url()}/api/v1/database/{test_db}")
            print("   Cleanup done")
        except (httpx.HTTPError, httpx.TimeoutException, ConnectionError):
            print("   Cleanup failed")

if __name__ == "__main__":
    asyncio.run(test_bff_ontology_creation())