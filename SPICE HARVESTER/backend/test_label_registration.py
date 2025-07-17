#!/usr/bin/env python3
"""
Test Label Registration
"""

import httpx
import asyncio
import aiosqlite
import json

async def check_label_database():
    """Check what's in the label mapper database"""
    
    db_path = "data/label_mappings.db"
    
    try:
        async with aiosqlite.connect(db_path) as db:
            # Check if tables exist
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = await cursor.fetchall()
            print(f"Tables in database: {tables}")
            
            # Check class_mappings table
            if any('class_mappings' in t for t in tables):
                print("\nContents of class_mappings table:")
                cursor = await db.execute(
                    "SELECT * FROM class_mappings ORDER BY created_at DESC LIMIT 10"
                )
                rows = await cursor.fetchall()
                
                # Get column names
                column_names = [description[0] for description in cursor.description]
                print(f"Columns: {column_names}")
                
                for row in rows:
                    print(f"Row: {dict(zip(column_names, row))}")
            else:
                print("No class_mappings table found")
                
    except Exception as e:
        print(f"Error checking database: {e}")

async def test_label_registration():
    """Test label registration process"""
    
    test_db = f"testlabel{int(time.time())}"
    
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Create database
        print(f"1. Creating database: {test_db}")
        response = await client.post(
            "http://{TestConfig.get_oms_base_url()}/api/v1/database/create",
            json={"name": test_db, "description": "Label test"}
        )
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            # 2. Create ontology with simple label
            print("\n2. Creating ontology with label 'Test Class'")
            response = await client.post(
                f"{TestConfig.get_bff_base_url()}/database/{test_db}/ontology",
                json={
                    "label": "Test Class",
                    "properties": []
                }
            )
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   Created ID: {data.get('data', {}).get('id')}")
            
            # 3. Check label database
            print("\n3. Checking label database after creation:")
            await check_label_database()
            
            # 4. Try to query by label
            print(f"\n4. Querying by label 'Test Class':")
            response = await client.get(
                f"{TestConfig.get_bff_base_url()}/database/{test_db}/ontology/Test Class"
            )
            print(f"   Status: {response.status_code}")
            if response.status_code != 200:
                print(f"   Error: {response.text[:200]}...")
        
        # 5. Cleanup
        print("\n5. Cleaning up...")
        await client.delete(f"{TestConfig.get_oms_base_url()}/api/v1/database/{test_db}")

import time
from test_config import TestConfig

if __name__ == "__main__":
    print("=== Testing Label Registration ===\n")
    asyncio.run(test_label_registration())