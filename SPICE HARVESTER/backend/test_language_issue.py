#!/usr/bin/env python3
"""
Test Language Registration Issue
"""

import httpx
import asyncio
import sqlite3
from test_config import TestConfig

async def check_registrations():
    """Check what's registered in SQLite"""
    
    # Check BFF's database
    db_path = "data/label_mappings.db"
    
    print("1. Checking recent registrations in BFF database...")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT db_name, class_id, label, label_lang
            FROM class_mappings 
            ORDER BY created_at DESC 
            LIMIT 10
        """)
        
        print("   Recent registrations:")
        for row in cursor.fetchall():
            print(f"   - DB: {row[0]}, ID: {row[1]}, Label: {row[2]}, Lang: {row[3]}")
        
        conn.close()
    except Exception as e:
        print(f"   Error: {e}")

async def test_with_explicit_lang():
    """Test with explicit language"""
    
    test_db = "testlang"
    
    async with httpx.AsyncClient(timeout=30) as client:
        # Create database
        print("\n2. Creating test database...")
        await client.post(
            "http://{TestConfig.get_oms_base_url()}/api/v1/database/create",
            json={"name": test_db, "description": "Language test"}
        )
        
        # Create ontology
        print("\n3. Creating ontology with explicit headers...")
        response = await client.post(
            f"{TestConfig.get_bff_base_url()}/database/{test_db}/ontology",
            json={
                "label": "TestClass",
                "properties": []
            },
            headers={"Accept-Language": "en"}  # Explicit English
        )
        print(f"   Creation status: {response.status_code}")
        
        if response.status_code == 200:
            # Check registrations again
            await check_registrations()
            
            # Try queries with different Accept-Language headers
            print("\n4. Testing queries with different languages...")
            
            for lang in ["en", "ko", ""]:
                headers = {"Accept-Language": lang} if lang else {}
                response = await client.get(
                    f"{TestConfig.get_bff_base_url()}/database/{test_db}/ontology/TestClass",
                    headers=headers
                )
                print(f"   Lang '{lang}': {response.status_code}")
        
        # Cleanup
        await client.delete(f"{TestConfig.get_oms_base_url()}/api/v1/database/{test_db}")

if __name__ == "__main__":
    asyncio.run(check_registrations())
    print("\n" + "="*50 + "\n")
    asyncio.run(test_with_explicit_lang())