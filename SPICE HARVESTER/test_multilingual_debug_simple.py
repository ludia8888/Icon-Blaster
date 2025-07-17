#!/usr/bin/env python3
"""
Simple debug for multilingual label handling
"""

import asyncio
import httpx
import json
import time
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)


async def test_multilingual_simple():
    """Simple multilingual test"""
    bff_url = "http://localhost:8002"
    test_db = f"debug_test_{int(time.time())}"
    
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Create test database
        print(f"Creating test database: {test_db}")
        response = await client.post(
            f"http://localhost:8000/api/v1/database/create",
            json={"name": test_db}
        )
        print(f"Database creation: {response.status_code}")
        
        # 2. Create simple multilingual ontology through BFF
        multilingual_ontology = {
            "label": {
                "ko": "테스트",
                "en": "Test"
            },
            "properties": []
        }
        
        print("\nCreating multilingual ontology...")
        response = await client.post(
            f"{bff_url}/database/{test_db}/ontology",
            json=multilingual_ontology,
            headers={"Accept-Language": "ko"}
        )
        print(f"Creation response: {response.status_code}")
        
        if response.status_code == 200:
            created_data = response.json()
            print(f"Response data: {json.dumps(created_data, indent=2, ensure_ascii=False)}")
            created_id = created_data.get('id')
            print(f"Created with ID: {created_id}")
        else:
            print(f"Creation failed: {response.text}")
            return
        
        # 3. Try to retrieve by Korean label
        print("\n--- Testing retrieval by Korean label '테스트' ---")
        response = await client.get(
            f"{bff_url}/database/{test_db}/ontology/테스트",
            headers={"Accept-Language": "ko"}
        )
        print(f"Korean label retrieval: {response.status_code}")
        if response.status_code != 200:
            print(f"Error: {response.text}")
        else:
            print(f"Success: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        
        # 4. Try to retrieve by ID directly
        if created_id:
            print(f"\n--- Testing retrieval by ID '{created_id}' ---")
            response = await client.get(
                f"{bff_url}/database/{test_db}/ontology/{created_id}",
                headers={"Accept-Language": "ko"}
            )
            print(f"ID retrieval: {response.status_code}")
            if response.status_code == 200:
                print(f"Success: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
            else:
                print(f"Error: {response.text}")
        
        # 5. Check BFF logs to see what's happening
        print("\n--- Check BFF console logs for debug information ---")
        
        # Cleanup
        print(f"\nCleaning up test database: {test_db}")
        await client.delete(f"http://localhost:8000/api/v1/database/{test_db}")


if __name__ == "__main__":
    asyncio.run(test_multilingual_simple())