#!/usr/bin/env python3
"""
Integration test script for OMS and User Service
Tests the actual communication between services
"""
import asyncio
import httpx
import sys
import time
from typing import Dict, Any

# Service URLs
USER_SERVICE_URL = "http://localhost:8001"
OMS_SERVICE_URL = "http://localhost:8000"

# Test credentials
TEST_USER = {
    "username": "test_user",
    "password": "Test123!@#",
    "email": "test@example.com"
}

SERVICE_CREDENTIALS = {
    "service_id": "oms-service",
    "service_secret": "oms-integration-secret"
}


class IntegrationTester:
    def __init__(self):
        self.user_token = None
        self.service_token = None
        
    async def wait_for_services(self, max_retries: int = 30):
        """Wait for services to be ready"""
        print("Waiting for services to be ready...")
        
        for i in range(max_retries):
            try:
                async with httpx.AsyncClient() as client:
                    # Check User Service health
                    user_resp = await client.get(f"{USER_SERVICE_URL}/health")
                    # Check OMS health
                    oms_resp = await client.get(f"{OMS_SERVICE_URL}/health")
                    
                    if user_resp.status_code == 200 and oms_resp.status_code == 200:
                        print("✓ Both services are ready!")
                        return True
            except:
                pass
            
            print(f"  Attempt {i+1}/{max_retries}...")
            await asyncio.sleep(2)
        
        print("✗ Services failed to start")
        return False
    
    async def test_user_login(self) -> bool:
        """Test user login on User Service"""
        print("\n1. Testing User Login on User Service...")
        
        async with httpx.AsyncClient() as client:
            try:
                # Try to login (user might not exist yet)
                response = await client.post(
                    f"{USER_SERVICE_URL}/api/v1/auth/login",
                    data={
                        "username": TEST_USER["username"],
                        "password": TEST_USER["password"]
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    self.user_token = data["access_token"]
                    print(f"✓ User login successful")
                    print(f"  Token: {self.user_token[:50]}...")
                    return True
                else:
                    print(f"✗ Login failed: {response.status_code} - {response.text}")
                    # In real scenario, we'd create the user first
                    return False
                    
            except Exception as e:
                print(f"✗ Login error: {e}")
                return False
    
    async def test_service_auth(self) -> bool:
        """Test service-to-service authentication"""
        print("\n2. Testing Service-to-Service Authentication...")
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{USER_SERVICE_URL}/api/v1/auth/service",
                    json={
                        "service_id": SERVICE_CREDENTIALS["service_id"],
                        "service_secret": SERVICE_CREDENTIALS["service_secret"],
                        "requested_scopes": ["api:users:read", "api:tokens:validate"]
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    self.service_token = data["access_token"]
                    print(f"✓ Service authentication successful")
                    print(f"  Service token: {self.service_token[:50]}...")
                    print(f"  Granted scopes: {data['scopes']}")
                    return True
                else:
                    print(f"✗ Service auth failed: {response.status_code} - {response.text}")
                    return False
                    
            except Exception as e:
                print(f"✗ Service auth error: {e}")
                return False
    
    async def test_token_validation_via_oms(self) -> bool:
        """Test OMS validating user token via IAM service"""
        print("\n3. Testing Token Validation via OMS...")
        
        if not self.user_token:
            print("✗ No user token available")
            return False
        
        async with httpx.AsyncClient() as client:
            try:
                # Call a protected OMS endpoint with the user token
                response = await client.get(
                    f"{OMS_SERVICE_URL}/api/v1/branches",
                    headers={"Authorization": f"Bearer {self.user_token}"}
                )
                
                if response.status_code in [200, 403]:  # 403 if user lacks permissions
                    print(f"✓ OMS successfully validated token via IAM service")
                    print(f"  Response status: {response.status_code}")
                    return True
                elif response.status_code == 401:
                    print(f"✗ Token validation failed: {response.text}")
                    return False
                else:
                    print(f"✗ Unexpected response: {response.status_code} - {response.text}")
                    return False
                    
            except Exception as e:
                print(f"✗ Token validation error: {e}")
                return False
    
    async def test_direct_token_validation(self) -> bool:
        """Test direct token validation endpoint"""
        print("\n4. Testing Direct Token Validation...")
        
        if not self.user_token:
            print("✗ No user token available")
            return False
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{USER_SERVICE_URL}/api/v1/auth/validate",
                    json={
                        "token": self.user_token,
                        "validate_scopes": True,
                        "required_scopes": ["api:schemas:read"]
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"✓ Direct token validation successful")
                    print(f"  Valid: {data['valid']}")
                    print(f"  User ID: {data.get('user_id')}")
                    print(f"  Scopes: {data.get('scopes', [])}")
                    return data["valid"]
                else:
                    print(f"✗ Validation failed: {response.status_code} - {response.text}")
                    return False
                    
            except Exception as e:
                print(f"✗ Validation error: {e}")
                return False
    
    async def test_user_info_lookup(self) -> bool:
        """Test user info lookup via service token"""
        print("\n5. Testing User Info Lookup...")
        
        if not self.service_token:
            print("✗ No service token available")
            return False
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{USER_SERVICE_URL}/api/v1/users/info",
                    json={"username": TEST_USER["username"]},
                    headers={"Authorization": f"Bearer {self.service_token}"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"✓ User info lookup successful")
                    print(f"  User ID: {data['user_id']}")
                    print(f"  Username: {data['username']}")
                    print(f"  Roles: {data['roles']}")
                    print(f"  Scopes: {data['scopes']}")
                    return True
                else:
                    print(f"✗ Lookup failed: {response.status_code} - {response.text}")
                    return False
                    
            except Exception as e:
                print(f"✗ Lookup error: {e}")
                return False
    
    async def run_all_tests(self):
        """Run all integration tests"""
        print("=" * 60)
        print("OMS + User Service Integration Tests")
        print("=" * 60)
        
        # Wait for services
        if not await self.wait_for_services():
            print("\n✗ Services not available. Make sure docker-compose is running.")
            return False
        
        # Run tests
        results = []
        
        # Note: In a real scenario, we'd need to create a test user first
        # For now, we'll test what we can
        
        # Test service authentication first
        results.append(await self.test_service_auth())
        
        # Test user login (might fail if user doesn't exist)
        results.append(await self.test_user_login())
        
        # If we have a user token, test OMS integration
        if self.user_token:
            results.append(await self.test_token_validation_via_oms())
            results.append(await self.test_direct_token_validation())
        
        # Test user lookup with service token
        if self.service_token:
            results.append(await self.test_user_info_lookup())
        
        # Summary
        print("\n" + "=" * 60)
        print("SUMMARY:")
        print(f"  Total tests: {len(results)}")
        print(f"  Passed: {sum(1 for r in results if r)}")
        print(f"  Failed: {sum(1 for r in results if not r)}")
        print("=" * 60)
        
        return all(results)


async def main():
    tester = IntegrationTester()
    success = await tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())