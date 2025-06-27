"""
FORENSIC DEBUG: Check what routes actually exist and how auth middleware responds
"""
import asyncio
import subprocess
import time
import httpx
import jwt as jwt_lib
from datetime import datetime, timezone, timedelta
import json

async def forensic_auth_debug():
    """Debug authentication by actually starting server and checking routes"""
    
    print("🚨 STARTING FORENSIC AUTH DEBUG")
    print("=" * 50)
    
    # Start server
    print("📡 Starting server...")
    server_process = subprocess.Popen(
        ["python", "-m", "uvicorn", "main:app", "--port", "8001", "--log-level", "debug"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for server startup
    await asyncio.sleep(3)
    base_url = "http://localhost:8001"
    
    try:
        # Test 1: Check if server is running
        print("\\n🔍 STEP 1: Server health check")
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.get(f"{base_url}/health")
                print(f"   Health check: {response.status_code}")
            except Exception as e:
                print(f"   Health check failed: {e}")
        
        # Test 2: Check what routes exist
        print("\\n🔍 STEP 2: Route discovery")
        routes_to_test = [
            "/",
            "/docs", 
            "/openapi.json",
            "/api/v1/schemas",
            "/api/v1/branches",
            "/api/v1/audit"
        ]
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            for route in routes_to_test:
                try:
                    response = await client.get(f"{base_url}{route}")
                    print(f"   {route}: {response.status_code}")
                except Exception as e:
                    print(f"   {route}: ERROR - {e}")
        
        # Test 3: Create a JWT and test authentication
        print("\\n🔍 STEP 3: JWT Authentication test")
        jwt_secret = "test-jwt-secret-for-comprehensive-validation"
        payload = {
            "user_id": "test-user-123",
            "username": "test-user",
            "roles": ["developer"],
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "iat": datetime.now(timezone.utc)
        }
        
        token = jwt_lib.encode(payload, jwt_secret, algorithm="HS256")
        print(f"   Created JWT: {token[:50]}...")
        
        async with httpx.AsyncClient(timeout=5.0) as client:
            headers = {"Authorization": f"Bearer {token}"}
            
            for route in ["/api/v1/schemas", "/api/v1/branches"]:
                try:
                    response = await client.get(f"{base_url}{route}", headers=headers)
                    print(f"   {route} with JWT: {response.status_code}")
                    if response.status_code != 200:
                        print(f"      Response: {response.text[:200]}")
                except Exception as e:
                    print(f"   {route} with JWT: ERROR - {e}")
        
        # Test 4: Check server logs
        print("\\n🔍 STEP 4: Server stderr logs")
        try:
            # Get some stderr output
            server_process.poll()
            if server_process.stderr:
                import select
                if select.select([server_process.stderr], [], [], 0)[0]:
                    stderr_output = server_process.stderr.read(1000).decode()
                    print(f"   Server stderr: {stderr_output}")
        except:
            pass
            
    finally:
        # Clean up
        print("\\n🧹 Cleaning up...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()
    
    print("\\n✅ Forensic debug complete")

if __name__ == "__main__":
    asyncio.run(forensic_auth_debug())