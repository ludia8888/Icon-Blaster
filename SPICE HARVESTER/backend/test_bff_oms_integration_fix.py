#!/usr/bin/env python3
"""
Test BFF-OMS ID generation integration after fix
"""

import httpx
import asyncio
import time

async def test_bff_oms_integration():
    """Test the fixed BFF-OMS ID generation integration"""
    
    print("=== BFF-OMS ID GENERATION INTEGRATION TEST ===\n")
    
    async with httpx.AsyncClient(timeout=30) as client:
        
        # Test database name
        test_db = f"testdb{int(time.time())}"
        
        # 1. Create test database
        print("1. Creating test database...")
        try:
            response = await client.post(
                "http://localhost:8000/api/v1/database/create",
                json={"name": test_db, "description": "Test database for ID generation"}
            )
            if response.status_code not in [200, 201]:
                print(f"❌ Database creation failed: {response.status_code}")
                return False
            print("✅ Database created successfully")
        except Exception as e:
            print(f"❌ Database creation failed: {e}")
            return False
        
        # 2. Test critical ID generation cases
        test_cases = [
            {
                "name": "TestClass preservation",
                "label": "TestClass",
                "expected_id": "TestClass"
            },
            {
                "name": "Space-separated words",
                "label": "Test Class",
                "expected_id": "TestClass"
            },
            {
                "name": "camelCase preservation",
                "label": "testClass",
                "expected_id": "testClass"
            },
            {
                "name": "All lowercase",
                "label": "test class",
                "expected_id": "TestClass"
            }
        ]
        
        results = []
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n{i+1}. Testing {test_case['name']}: '{test_case['label']}'")
            
            try:
                # Create ontology through BFF
                creation_response = await client.post(
                    f"http://localhost:8002/database/{test_db}/ontology",
                    json={
                        "label": test_case['label'],
                        "description": f"Test ontology for {test_case['name']}"
                    }
                )
                
                if creation_response.status_code not in [200, 201]:
                    print(f"   ❌ Creation failed: {creation_response.status_code}")
                    print(f"   Error: {creation_response.text[:200]}")
                    results.append(False)
                    continue
                
                creation_data = creation_response.json()
                created_id = creation_data.get('data', {}).get('id') or creation_data.get('id')
                
                print(f"   📝 BFF generated ID: '{created_id}'")
                
                # Check if ID matches expected
                if created_id == test_case['expected_id']:
                    print(f"   ✅ ID generation correct: '{created_id}'")
                    
                    # Try to retrieve it back
                    retrieval_response = await client.get(
                        f"http://localhost:8002/database/{test_db}/ontology/{created_id}"
                    )
                    
                    if retrieval_response.status_code == 200:
                        print(f"   ✅ Retrieval successful: Round-trip working")
                        results.append(True)
                    else:
                        print(f"   ❌ Retrieval failed: {retrieval_response.status_code}")
                        print(f"   This indicates ID mismatch between BFF and OMS")
                        results.append(False)
                        
                else:
                    print(f"   ❌ ID generation incorrect: got '{created_id}', expected '{test_case['expected_id']}'")
                    results.append(False)
                    
            except Exception as e:
                print(f"   💥 Exception: {e}")
                results.append(False)
        
        # Summary
        passed = sum(results)
        total = len(results)
        
        print(f"\n📊 INTEGRATION TEST RESULTS:")
        print(f"   Passed: {passed}/{total}")
        print(f"   Success Rate: {100*passed//total if total > 0 else 0}%")
        
        if passed == total:
            print("\n🎉 BFF-OMS ID GENERATION MISMATCH FULLY RESOLVED!")
            print("✅ All test cases passed")
            print("✅ Round-trip consistency verified")
            print("✅ CamelCase preservation working")
            return True
        else:
            print(f"\n⚠️  {total - passed} test cases still failing")
            return False

if __name__ == "__main__":
    success = asyncio.run(test_bff_oms_integration())
    exit(0 if success else 1)