#!/usr/bin/env python3
"""
Test Direct ID Query
"""

import httpx
import asyncio
import json
import time
from test_config import TestConfig

async def test_direct_id():
    """Test querying with direct ID vs label"""
    
    test_db = f"testdb{int(time.time())}"
    
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Create test database
        print(f"1. Creating test database: {test_db}")
        response = await client.post(
            "http://{TestConfig.get_oms_base_url()}/api/v1/database/create",
            json={"name": test_db, "description": "Direct query test"}
        )
        print(f"   DB creation status: {response.status_code}")
        if response.status_code != 200:
            print(f"   DB creation error: {response.text}")
        
        # 1.5 Verify database exists
        print("\n1.5. Verifying database exists...")
        response = await client.get(f"{TestConfig.get_oms_base_url()}/api/v1/database/exists/{test_db}")
        print(f"   DB exists check: {response.status_code}")
        
        # Add small delay to ensure DB is ready
        await asyncio.sleep(0.5)
        
        # 2. Create simple ontology
        print("\n2. Creating simple ontology...")
        test_ontology = {
            "label": "Test Product",
            "properties": []
        }
        
        response = await client.post(
            f"{TestConfig.get_bff_base_url()}/database/{test_db}/ontology",
            json=test_ontology
        )
        print(f"   Creation status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            created_id = data.get('data', {}).get('id')
            print(f"   Created with ID: {created_id}")
            
            # 3. Test different query approaches
            print("\n3. Testing queries...")
            
            # a) Direct OMS query by ID
            print(f"\n   a) Direct OMS query by ID: {created_id}")
            response = await client.get(
                f"{TestConfig.get_oms_base_url()}/api/v1/ontology/{test_db}/{created_id}"
            )
            print(f"      OMS result: {response.status_code}")
            
            # b) BFF query by ID
            print(f"\n   b) BFF query by ID: {created_id}")
            response = await client.get(
                f"{TestConfig.get_bff_base_url()}/database/{test_db}/ontology/{created_id}"
            )
            print(f"      BFF result: {response.status_code}")
            if response.status_code != 200:
                print(f"      Error: {response.text[:200]}...")
            
            # c) BFF query by label
            print(f"\n   c) BFF query by label: Test Product")
            response = await client.get(
                f"{TestConfig.get_bff_base_url()}/database/{test_db}/ontology/Test Product"
            )
            print(f"      BFF result: {response.status_code}")
            
            # d) BFF query by label without space
            print(f"\n   d) BFF query by label without space: TestProduct")
            response = await client.get(
                f"{TestConfig.get_bff_base_url()}/database/{test_db}/ontology/TestProduct"
            )
            print(f"      BFF result: {response.status_code}")
        else:
            print(f"   Creation failed: {response.text}")
        
        # 4. Clean up
        print("\n4. Cleaning up...")
        await client.delete(f"{TestConfig.get_oms_base_url()}/api/v1/database/{test_db}")

if __name__ == "__main__":
    asyncio.run(test_direct_id())