#!/usr/bin/env python3
"""
Test the database list fix
"""

import asyncio
import httpx
import json
import time


async def test_database_list_fix():
    """Test that newly created databases appear in the list"""
    oms_url = "http://localhost:8000"
    test_db = f"list_test_{int(time.time())}"
    
    print(f"🧪 Testing database list fix with database: {test_db}")
    print("="*60)
    
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Create database
        print("\n1️⃣ Creating database...")
        response = await client.post(
            f"{oms_url}/api/v1/database/create",
            json={"name": test_db, "description": "Test database list fix"}
        )
        print(f"   Status: {response.status_code}")
        if response.status_code != 200:
            print(f"   ❌ Failed to create database: {response.text}")
            return
        
        # 2. Check if exists
        print("\n2️⃣ Checking if database exists...")
        response = await client.get(f"{oms_url}/api/v1/database/exists/{test_db}")
        print(f"   Status: {response.status_code}")
        
        # 3. List databases and check
        print("\n3️⃣ Listing databases...")
        response = await client.get(f"{oms_url}/api/v1/database/list")
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            databases = data.get("data", {}).get("databases", [])
            print(f"   Total databases: {len(databases)}")
            
            # Check if our database is in the list
            found = False
            for db in databases:
                if isinstance(db, str) and db == test_db:
                    found = True
                    print(f"   ✅ Found {test_db} as string in list!")
                    break
                elif isinstance(db, dict) and db.get("name") == test_db:
                    found = True
                    print(f"   ✅ Found {test_db} as dict in list!")
                    print(f"      Database info: {json.dumps(db, indent=6)}")
                    break
            
            if not found:
                print(f"   ❌ Database {test_db} NOT found in list!")
                print("\n   First few databases in list:")
                for i, db in enumerate(databases[:5]):
                    if isinstance(db, dict):
                        print(f"      {i+1}. {db.get('name', 'NO NAME')} (dict)")
                    else:
                        print(f"      {i+1}. {db} (string)")
        
        # 4. Cleanup
        print("\n4️⃣ Cleaning up...")
        response = await client.delete(f"{oms_url}/api/v1/database/{test_db}")
        print(f"   Delete status: {response.status_code}")
    
    print("\n" + "="*60)
    print("✅ Test completed!")


if __name__ == "__main__":
    asyncio.run(test_database_list_fix())