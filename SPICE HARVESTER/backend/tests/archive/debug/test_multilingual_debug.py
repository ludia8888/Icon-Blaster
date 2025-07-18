#!/usr/bin/env python3
"""
Debug multilingual label handling
"""

import asyncio
import httpx
import json
import time


async def test_multilingual_debug():
    """Debug multilingual label handling"""
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
        
        # 2. Create multilingual ontology through BFF
        multilingual_ontology = {
            "label": {
                "ko": "테스트 제품",
                "en": "Test Product"
            },
            "description": {
                "ko": "테스트 설명",
                "en": "Test description"
            },
            "properties": [
                {"name": "name", "type": "xsd:string", "label": {"ko": "이름", "en": "Name"}}
            ]
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
            print(f"Created with ID: {created_data.get('id')}")
            created_id = created_data.get('id')
        else:
            print(f"Creation failed: {response.text}")
            return
        
        # 3. Try to retrieve by Korean label
        print("\n--- Testing retrieval by Korean label ---")
        response = await client.get(
            f"{bff_url}/database/{test_db}/ontology/테스트 제품",
            headers={"Accept-Language": "ko"}
        )
        print(f"Korean label retrieval: {response.status_code}")
        if response.status_code != 200:
            print(f"Error: {response.text}")
        
        # 4. Try to retrieve by English label
        print("\n--- Testing retrieval by English label ---")
        response = await client.get(
            f"{bff_url}/database/{test_db}/ontology/Test Product",
            headers={"Accept-Language": "en"}
        )
        print(f"English label retrieval: {response.status_code}")
        if response.status_code != 200:
            print(f"Error: {response.text}")
        
        # 5. Try to retrieve by ID
        print(f"\n--- Testing retrieval by ID: {created_id} ---")
        response = await client.get(
            f"{bff_url}/database/{test_db}/ontology/{created_id}",
            headers={"Accept-Language": "ko"}
        )
        print(f"ID retrieval: {response.status_code}")
        if response.status_code == 200:
            print("Success! Retrieved by ID")
        else:
            print(f"Error: {response.text}")
        
        # 6. Check label mappings
        print("\n--- Checking label mappings ---")
        # Direct query to check what's in the mapper database
        import sys
        sys.path.insert(0, '/Users/isihyeon/Desktop/SPICE HARVESTER/backend/backend-for-frontend')
        from utils.label_mapper import LabelMapper
        
        mapper = LabelMapper()
        
        # Check if Korean label is mapped
        ko_id = await mapper.get_class_id(test_db, "테스트 제품", "ko")
        print(f"Korean label '테스트 제품' mapped to: {ko_id}")
        
        # Check if English label is mapped
        en_id = await mapper.get_class_id(test_db, "Test Product", "en")
        print(f"English label 'Test Product' mapped to: {en_id}")
        
        # Export all mappings for this database
        mappings = await mapper.export_mappings(test_db)
        print(f"\nAll class mappings for {test_db}:")
        for mapping in mappings.get('classes', []):
            print(f"  - {mapping}")
        
        # Cleanup
        print(f"\nCleaning up test database: {test_db}")
        await client.delete(f"http://localhost:8000/api/v1/database/{test_db}")


if __name__ == "__main__":
    asyncio.run(test_multilingual_debug())