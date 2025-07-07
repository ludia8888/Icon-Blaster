#!/usr/bin/env python3
"""
Audit Service Integration Test Script
Tests the integration between user-service and audit-service
"""
import asyncio
import httpx
import json
from datetime import datetime
from typing import Dict, Any

# Configuration
USER_SERVICE_URL = "http://localhost:8001"  # user-service port
AUDIT_SERVICE_URL = "http://localhost:8003"  # audit-service port (mapped from 8002)

async def test_audit_service_health():
    """Test if audit-service v2 is running"""
    print("1. Testing audit-service health...")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{AUDIT_SERVICE_URL}/api/v2/events/health")
            if response.status_code == 200:
                print("✅ Audit service v2 is running")
                print(f"   Response: {response.json()}")
                return True
            else:
                print(f"❌ Audit service returned status: {response.status_code}")
                return False
    except Exception as e:
        print(f"❌ Cannot connect to audit service: {e}")
        return False

async def test_send_audit_event():
    """Test sending an audit event directly to audit-service"""
    print("\n2. Testing direct audit event submission...")
    
    test_event = {
        "event_type": "auth.test_event",
        "user_id": "test_user_123",
        "username": "testuser",
        "ip_address": "127.0.0.1",
        "user_agent": "TestScript/1.0",
        "service": "user-service",
        "action": "test_action",
        "result": "success",
        "details": {
            "test": True,
            "timestamp": datetime.utcnow().isoformat()
        },
        "compliance_tags": ["TEST"],
        "data_classification": "internal"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{AUDIT_SERVICE_URL}/api/v2/events",
                json=test_event,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code in [200, 201]:
                print("✅ Successfully sent audit event")
                print(f"   Response: {response.json()}")
                return True
            else:
                print(f"❌ Failed to send event. Status: {response.status_code}")
                print(f"   Response: {response.text}")
                return False
    except Exception as e:
        print(f"❌ Error sending audit event: {e}")
        return False

async def test_query_audit_events():
    """Test querying audit events from audit-service"""
    print("\n3. Testing audit event query...")
    
    query_params = {
        "event_type": "auth.test_event",
        "limit": 10
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{AUDIT_SERVICE_URL}/api/v2/events/query",
                params=query_params
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Successfully queried audit events")
                print(f"   Total events: {data.get('total', 0)}")
                print(f"   Events returned: {len(data.get('events', []))}")
                return True
            else:
                print(f"❌ Failed to query events. Status: {response.status_code}")
                return False
    except Exception as e:
        print(f"❌ Error querying audit events: {e}")
        return False

async def test_user_service_audit():
    """Test if user-service can send audit events"""
    print("\n4. Testing user-service audit functionality...")
    
    # This would require user-service to be running
    # For now, we'll simulate what user-service would do
    print("   ⚠️  This test requires user-service to be running")
    print("   To fully test, perform a login action on user-service")
    return None

async def test_database_connection():
    """Check if audit-service can connect to database"""
    print("\n5. Testing database connectivity...")
    
    # Try to query events - if database is not connected, this will fail
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{AUDIT_SERVICE_URL}/api/v2/events/query",
                params={"limit": 1}
            )
            
            if response.status_code == 200:
                print("✅ Database connection appears to be working")
                return True
            elif response.status_code == 500:
                print("❌ Database connection error")
                return False
            else:
                print(f"⚠️  Unexpected status: {response.status_code}")
                return None
    except Exception as e:
        print(f"❌ Error testing database: {e}")
        return False

async def main():
    """Run all tests"""
    print("=== Audit Service Integration Test ===\n")
    
    results = {
        "audit_health": await test_audit_service_health(),
        "send_event": await test_send_audit_event(),
        "query_events": await test_query_audit_events(),
        "user_service": await test_user_service_audit(),
        "database": await test_database_connection()
    }
    
    print("\n=== Test Summary ===")
    passed = sum(1 for v in results.values() if v is True)
    failed = sum(1 for v in results.values() if v is False)
    skipped = sum(1 for v in results.values() if v is None)
    
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"⚠️  Skipped: {skipped}")
    
    if failed == 0 and passed > 0:
        print("\n🎉 Audit service integration is working!")
    else:
        print("\n⚠️  Some tests failed. Please check the configuration.")
        print("\nTroubleshooting:")
        print("1. Ensure audit-service is running on port 8003")
        print("2. Check database migrations have been run")
        print("3. Verify network connectivity between services")
        print("4. Check Redis is running and accessible")

if __name__ == "__main__":
    asyncio.run(main())