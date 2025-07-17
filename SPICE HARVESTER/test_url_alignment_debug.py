#!/usr/bin/env python3
"""
Debug URL alignment issue between OMS and BFF
"""

import asyncio
import httpx
import json
import time


async def test_url_alignment():
    """Debug URL alignment issue"""
    oms_url = "http://localhost:8000"
    bff_url = "http://localhost:8002"
    test_db = f"url_test_{int(time.time())}"
    
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Create test database
        print(f"1. Creating test database: {test_db}")
        response = await client.post(
            f"{oms_url}/api/v1/database/create",
            json={"name": test_db}
        )
        print(f"   Database creation: {response.status_code}")
        
        # 2. Test OMS direct ontology creation
        print("\n2. Testing OMS direct ontology creation...")
        oms_ontology = {
            "id": "DirectOMS",
            "label": "Direct OMS Test",
            "properties": {
                "test_prop": "string"
            }
        }
        
        response = await client.post(
            f"{oms_url}/api/v1/ontology/{test_db}/create",
            json=oms_ontology
        )
        print(f"   OMS response: {response.status_code}")
        if response.status_code != 200:
            print(f"   OMS error: {response.text}")
        else:
            print(f"   OMS success: {json.dumps(response.json(), indent=2)}")
        
        # 3. Test BFF ontology creation (simple format)
        print("\n3. Testing BFF ontology creation (simple format)...")
        bff_simple = {
            "label": "Simple BFF Test",
            "properties": [
                {"name": "test", "type": "xsd:string", "label": "Test Property"}
            ]
        }
        
        response = await client.post(
            f"{bff_url}/database/{test_db}/ontology",
            json=bff_simple
        )
        print(f"   BFF response: {response.status_code}")
        if response.status_code != 200:
            print(f"   BFF error: {response.text}")
        else:
            print(f"   BFF success")
        
        # 4. Test BFF ontology creation (multilingual format)
        print("\n4. Testing BFF ontology creation (multilingual format)...")
        bff_multilingual = {
            "label": {
                "ko": "다국어 BFF 테스트",
                "en": "Multilingual BFF Test"
            },
            "properties": [
                {"name": "test", "type": "xsd:string", "label": {"en": "Test Property"}}
            ]
        }
        
        response = await client.post(
            f"{bff_url}/database/{test_db}/ontology",
            json=bff_multilingual
        )
        print(f"   BFF response: {response.status_code}")
        if response.status_code != 200:
            print(f"   BFF error: {response.text}")
        else:
            print(f"   BFF success")
        
        # 5. Check what format BFF sends to OMS
        print("\n5. Checking BFF logs to see what it sends to OMS...")
        print("   (Check BFF console output for logging messages)")
        
        # Cleanup
        print(f"\n6. Cleaning up test database: {test_db}")
        await client.delete(f"{oms_url}/api/v1/database/{test_db}")


if __name__ == "__main__":
    asyncio.run(test_url_alignment())