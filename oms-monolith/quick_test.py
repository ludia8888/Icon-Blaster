#!/usr/bin/env python3
"""
Quick test of User Service endpoints
"""
import asyncio
import httpx
import json


async def test_user_service():
    print("Testing User Service Integration...")
    
    base_url = "http://localhost:8001"
    
    async with httpx.AsyncClient() as client:
        # Test 1: Health Check
        print("\n1. Testing Health Check...")
        try:
            response = await client.get(f"{base_url}/health")
            print(f"  Status: {response.status_code}")
            print(f"  Response: {json.dumps(response.json(), indent=2)}")
        except Exception as e:
            print(f"  Error: {e}")
        
        # Test 2: Root endpoint
        print("\n2. Testing Root Endpoint...")
        try:
            response = await client.get(f"{base_url}/")
            print(f"  Status: {response.status_code}")
            print(f"  Response: {json.dumps(response.json(), indent=2)}")
        except Exception as e:
            print(f"  Error: {e}")
        
        # Test 3: Service Authentication
        print("\n3. Testing Service Authentication...")
        try:
            response = await client.post(
                f"{base_url}/api/v1/auth/service",
                json={
                    "service_id": "oms-service",
                    "service_secret": "oms-integration-secret",
                    "requested_scopes": ["api:users:read", "api:tokens:validate"]
                }
            )
            print(f"  Status: {response.status_code}")
            result = response.json()
            print(f"  Response: {json.dumps(result, indent=2)}")
            
            if response.status_code == 200:
                service_token = result.get("access_token")
                print(f"  Service token acquired: {service_token[:50]}...")
                
                # Test 4: Token Validation with service token
                print("\n4. Testing Token Validation...")
                validate_response = await client.post(
                    f"{base_url}/api/v1/auth/validate",
                    json={
                        "token": service_token,
                        "validate_scopes": True,
                        "required_scopes": ["api:users:read"]
                    }
                )
                print(f"  Status: {validate_response.status_code}")
                print(f"  Response: {json.dumps(validate_response.json(), indent=2)}")
                
        except Exception as e:
            print(f"  Error: {e}")
        
        # Test 5: Invalid service authentication
        print("\n5. Testing Invalid Service Authentication...")
        try:
            response = await client.post(
                f"{base_url}/api/v1/auth/service",
                json={
                    "service_id": "invalid-service",
                    "service_secret": "wrong-secret",
                    "requested_scopes": ["api:users:read"]
                }
            )
            print(f"  Status: {response.status_code}")
            print(f"  Response: {json.dumps(response.json(), indent=2)}")
        except Exception as e:
            print(f"  Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_user_service())