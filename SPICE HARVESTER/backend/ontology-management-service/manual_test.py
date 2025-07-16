#!/usr/bin/env python3
"""
Manual test script for quick verification of BFF -> OMS -> TerminusDB workflow
"""

import httpx
import json
import asyncio
from datetime import datetime

BFF_URL = "http://localhost:8002"

async def test_workflow():
    """Test the complete workflow manually"""
    async with httpx.AsyncClient(base_url=BFF_URL, timeout=30.0) as client:
        print("="*60)
        print("MANUAL BFF -> OMS -> TerminusDB TEST")
        print("="*60)
        
        # 1. Check health
        print("\n1. Checking service health...")
        try:
            response = await client.get("/health")
            health = response.json()
            print(f"✅ BFF Health: {health['status']}")
            print(f"   OMS Health: {health['backend']['oms']['status']}")
        except Exception as e:
            print(f"❌ Health check failed: {e}")
            return
            
        # 2. Create test database
        db_name = f"test_manual_{int(datetime.now().timestamp())}"
        print(f"\n2. Creating database '{db_name}'...")
        try:
            response = await client.post(
                "/api/v1/databases",
                json={
                    "name": db_name,
                    "description": "Manual test database"
                }
            )
            if response.status_code == 200:
                print(f"✅ Database created: {response.json()}")
            else:
                print(f"❌ Failed: {response.status_code} - {response.text}")
                return
        except Exception as e:
            print(f"❌ Database creation failed: {e}")
            return
            
        # 3. Create Person class with multilingual labels
        print("\n3. Creating Person class with multilingual labels...")
        person_class = {
            "@type": "Class",
            "@id": "Person",
            "@label": {
                "en": "Person",
                "es": "Persona",
                "fr": "Personne"
            },
            "@documentation": {
                "en": "A human being",
                "es": "Un ser humano"
            },
            "properties": {
                "name": {
                    "@type": "xsd:string",
                    "@label": {"en": "Name", "es": "Nombre"},
                    "@mandatory": True
                },
                "email": {
                    "@type": "xsd:string",
                    "@label": {"en": "Email", "es": "Correo electrónico"},
                    "@format": "email"
                }
            }
        }
        
        try:
            response = await client.post(
                f"/api/v1/databases/{db_name}/classes",
                json=person_class
            )
            if response.status_code == 200:
                print(f"✅ Person class created")
            else:
                print(f"❌ Failed: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"❌ Class creation failed: {e}")
            
        # 4. Retrieve class with Spanish labels
        print("\n4. Retrieving Person class with Spanish labels...")
        try:
            response = await client.get(
                f"/api/v1/databases/{db_name}/classes/Person",
                params={"language": "es"}
            )
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Retrieved with Spanish labels:")
                print(f"   Label: {data.get('@label', {}).get('es', 'N/A')}")
                print(f"   Documentation: {data.get('@documentation', {}).get('es', 'N/A')}")
            else:
                print(f"❌ Failed: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"❌ Retrieval failed: {e}")
            
        # 5. List all classes
        print("\n5. Listing all classes...")
        try:
            response = await client.get(f"/api/v1/databases/{db_name}/classes")
            if response.status_code == 200:
                data = response.json()
                classes = data.get("classes", [])
                print(f"✅ Found {len(classes)} classes")
                for cls in classes:
                    print(f"   - {cls.get('@id', 'Unknown')}")
            else:
                print(f"❌ Failed: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"❌ List failed: {e}")
            
        # 6. Create a branch
        print("\n6. Creating a feature branch...")
        try:
            response = await client.post(
                f"/api/v1/databases/{db_name}/branches",
                json={
                    "name": "feature_test",
                    "description": "Test feature branch"
                }
            )
            if response.status_code == 200:
                print(f"✅ Branch created: {response.json()}")
            else:
                print(f"❌ Failed: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"❌ Branch creation failed: {e}")
            
        # 7. Test error handling
        print("\n7. Testing error handling...")
        try:
            response = await client.post(
                f"/api/v1/databases/{db_name}/classes",
                json={"@type": "Class"}  # Missing @id
            )
            if response.status_code == 400:
                print(f"✅ Correctly rejected invalid class (missing @id)")
            else:
                print(f"❌ Should have failed but got: {response.status_code}")
        except Exception as e:
            print(f"❌ Error test failed: {e}")
            
        # 8. Clean up
        print("\n8. Cleaning up test database...")
        try:
            response = await client.delete(f"/api/v1/databases/{db_name}")
            if response.status_code in [200, 204]:
                print(f"✅ Database deleted")
            else:
                print(f"⚠️  Cleanup failed: {response.status_code}")
        except Exception as e:
            print(f"⚠️  Cleanup failed: {e}")
            
        print("\n" + "="*60)
        print("✅ MANUAL TEST COMPLETE")
        print("="*60)

if __name__ == "__main__":
    print("Starting manual test...")
    print("Make sure both BFF (port 8002) and OMS (port 8000) are running!")
    asyncio.run(test_workflow())