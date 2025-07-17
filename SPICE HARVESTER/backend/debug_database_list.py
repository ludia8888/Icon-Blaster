#!/usr/bin/env python3
"""
Debug script to understand database list response format
"""

import asyncio
import httpx
import json
import time


async def debug_database_list():
    """Debug database list functionality"""
    oms_url = "http://localhost:8000"
    test_db = f"debug_test_{int(time.time())}"
    
    async with httpx.AsyncClient(timeout=30) as client:
        # 1. Create a test database
        print(f"Creating test database: {test_db}")
        try:
            response = await client.post(
                f"{oms_url}/api/v1/database/create",
                json={"name": test_db, "description": "Debug test database"}
            )
            print(f"Create response: {response.status_code}")
            if response.status_code == 200:
                print(f"Create data: {json.dumps(response.json(), indent=2)}")
        except Exception as e:
            print(f"Create error: {e}")
        
        # 2. List databases
        print("\nListing databases...")
        try:
            response = await client.get(f"{oms_url}/api/v1/database/list")
            print(f"List response: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"List data structure: {json.dumps(data, indent=2)}")
                
                # Check how to properly find the database
                databases = data.get("data", {}).get("databases", [])
                print(f"\nNumber of databases: {len(databases)}")
                print(f"Database type: {type(databases)}")
                
                if databases:
                    print(f"First database item type: {type(databases[0])}")
                    print(f"First database item: {json.dumps(databases[0], indent=2)}")
                
                # Check if our test database is in the list
                found = False
                for db in databases:
                    if isinstance(db, dict) and db.get("name") == test_db:
                        found = True
                        print(f"\n✅ Found {test_db} in database list!")
                        break
                    elif isinstance(db, str) and db == test_db:
                        found = True
                        print(f"\n✅ Found {test_db} in database list (as string)!")
                        break
                
                if not found:
                    print(f"\n❌ {test_db} NOT found in database list")
                    print("\nDatabase names in list:")
                    for db in databases:
                        if isinstance(db, dict):
                            print(f"  - {db.get('name', 'NO NAME KEY')}")
                        else:
                            print(f"  - {db}")
                            
        except Exception as e:
            print(f"List error: {e}")
        
        # 3. Clean up
        print(f"\nDeleting test database: {test_db}")
        try:
            response = await client.delete(f"{oms_url}/api/v1/database/{test_db}")
            print(f"Delete response: {response.status_code}")
        except Exception as e:
            print(f"Delete error: {e}")


if __name__ == "__main__":
    asyncio.run(debug_database_list())