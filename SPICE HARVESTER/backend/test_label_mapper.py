#!/usr/bin/env python3
"""
Test Label Mapper Functionality
"""

import httpx
import asyncio
import json
from test_config import TestConfig

async def test_label_mapper():
    """Test label mapping for multilingual queries"""
    
    test_db = "test_label_mapper"
    
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Create test database
        print("1. Creating test database...")
        response = await client.post(
            "http://{TestConfig.get_oms_base_url()}/api/v1/database/create",
            json={"name": test_db, "description": "Label mapper test"}
        )
        print(f"   DB creation: {response.status_code}")
        
        # 2. Create multilingual ontology via BFF
        print("\n2. Creating multilingual ontology...")
        multilingual_ontology = {
            "label": {
                "ko": "테스트 클래스",
                "en": "Test Class",
                "ja": "テストクラス"
            },
            "description": {
                "ko": "레이블 매퍼 테스트",
                "en": "Label mapper test"
            },
            "properties": []
        }
        
        response = await client.post(
            f"{TestConfig.get_bff_base_url()}/database/{test_db}/ontology",
            json=multilingual_ontology
        )
        print(f"   Creation: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Created ID: {data.get('id', 'Unknown')}")
            created_id = data.get('id')
        else:
            print(f"   Error: {response.text}")
            created_id = None
        
        if created_id:
            # 3. Try different query methods
            print("\n3. Testing different query methods...")
            
            # Query by ID
            print(f"\n   a) Query by ID: {created_id}")
            response = await client.get(
                f"{TestConfig.get_bff_base_url()}/database/{test_db}/ontology/{created_id}"
            )
            print(f"      Result: {response.status_code}")
            
            # Query by Korean label
            print("\n   b) Query by Korean label: 테스트 클래스")
            response = await client.get(
                f"{TestConfig.get_bff_base_url()}/database/{test_db}/ontology/테스트 클래스",
                headers={"Accept-Language": "ko"}
            )
            print(f"      Result: {response.status_code}")
            if response.status_code != 200:
                print(f"      Error: {response.text}")
            
            # Query by English label
            print("\n   c) Query by English label: Test Class")
            response = await client.get(
                f"{TestConfig.get_bff_base_url()}/database/{test_db}/ontology/Test Class",
                headers={"Accept-Language": "en"}
            )
            print(f"      Result: {response.status_code}")
            if response.status_code != 200:
                print(f"      Error: {response.text}")
            
            # URL-encoded Korean label
            print("\n   d) Query by URL-encoded Korean label")
            import urllib.parse
            encoded_label = urllib.parse.quote("테스트 클래스")
            response = await client.get(
                f"{TestConfig.get_bff_base_url()}/database/{test_db}/ontology/{encoded_label}",
                headers={"Accept-Language": "ko"}
            )
            print(f"      Result: {response.status_code}")
        
        # 4. Clean up
        print("\n4. Cleaning up...")
        await client.delete(f"{TestConfig.get_oms_base_url()}/api/v1/database/{test_db}")

if __name__ == "__main__":
    asyncio.run(test_label_mapper())