#!/usr/bin/env python3
"""
BFF Detailed Debug Test
"""

import httpx
import asyncio
import json
from test_config import TestConfig

async def test_bff_detailed():
    """Test BFF with detailed debugging"""
    
    test_db = "test_bff_detailed"
    
    async with httpx.AsyncClient(timeout=TestConfig.get_test_timeout()) as client:
        # 1. Create test database
        print("1. Creating test database...")
        response = await client.post(
            TestConfig.get_database_create_url(),
            json={"name": test_db, "description": "BFF detailed test"}
        )
        print(f"   DB creation: {response.status_code}")
        
        # 2. Test simple ontology without properties first
        print("\n2. Testing simple ontology (no properties)...")
        simple_ontology = {
            "label": "Simple Test",
            "description": "Simple test without properties",
            "properties": []
        }
        
        response = await client.post(
            TestConfig.get_bff_ontology_url(test_db),
            json=simple_ontology
        )
        print(f"   Simple creation: {response.status_code}")
        if response.status_code != 200:
            print(f"   Response: {response.text}")
        else:
            print(f"   Success: Created simple ontology")
        
        # 3. Test with one property
        print("\n3. Testing with one property...")
        one_prop_ontology = {
            "label": "One Property Test",
            "description": "Test with one property",
            "properties": [
                {
                    "name": "testProp",
                    "type": "string",  # Try simple type first
                    "label": "Test Property"
                }
            ]
        }
        
        response = await client.post(
            TestConfig.get_bff_ontology_url(test_db),
            json=one_prop_ontology
        )
        print(f"   One property creation: {response.status_code}")
        if response.status_code != 200:
            print(f"   Response: {response.text}")
        else:
            print(f"   Success: Created ontology with one property")
        
        # 4. Test with xsd: prefix
        print("\n4. Testing with xsd: prefix...")
        xsd_ontology = {
            "label": "XSD Test",
            "properties": [
                {
                    "name": "xsdProp",
                    "type": "xsd:string",
                    "label": "XSD Property"
                }
            ]
        }
        
        response = await client.post(
            TestConfig.get_bff_ontology_url(test_db),
            json=xsd_ontology
        )
        print(f"   XSD creation: {response.status_code}")
        if response.status_code != 200:
            print(f"   Response: {response.text}")
        else:
            print(f"   Success: Created ontology with xsd:string type")
        
        # 5. Clean up
        print("\n5. Cleaning up...")
        await client.delete(TestConfig.get_database_delete_url(test_db))
        print("   Cleanup done")

if __name__ == "__main__":
    asyncio.run(test_bff_detailed())