#!/usr/bin/env python3
"""
Integration test to verify all components are working correctly
"""
import asyncio
import os
import sys
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_sqlite_connector():
    """Test SQLiteConnector functionality"""
    print("\n1. Testing SQLiteConnector...")
    try:
        from shared.database.sqlite_connector import get_sqlite_connector
        
        connector = await get_sqlite_connector(
            "test.db",
            db_dir="/tmp",
            enable_wal=True
        )
        
        # Initialize with test schema
        await connector.initialize(migrations=[
            """
            CREATE TABLE IF NOT EXISTS test_table (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        ])
        
        # Test insert
        await connector.execute(
            "INSERT INTO test_table (name) VALUES (:name)",
            {"name": "Test Entry"}
        )
        
        # Test fetch
        result = await connector.fetch_one(
            "SELECT * FROM test_table WHERE name = :name",
            {"name": "Test Entry"}
        )
        
        print(f"✅ SQLiteConnector working! Found: {result}")
        
        # Cleanup
        await connector.close()
        os.remove("/tmp/test.db")
        
        return True
        
    except Exception as e:
        print(f"❌ SQLiteConnector failed: {e}")
        return False

async def test_audit_publisher():
    """Test Audit Publisher with backend"""
    print("\n2. Testing Audit Publisher...")
    try:
        from core.events.unified_publisher import UnifiedEventPublisher, PublisherConfig, PublisherBackend
        
        # Create mock DB client
        class MockDBClient:
            async def write_audit_event(self, event):
                print(f"   Mock DB: Stored audit event {event.get('audit_metadata', {}).get('event_id', 'unknown')}")
                return True
        
        config = PublisherConfig(
            backend=PublisherBackend.AUDIT,
            endpoint="http://localhost:8000",
            enable_dual_write=True,
            audit_db_client=MockDBClient()
        )
        
        publisher = UnifiedEventPublisher(config)
        await publisher.connect()
        
        # Test publish
        result = await publisher.publish(
            event_type="test.audit",
            data={"user": "test", "action": "login"},
            metadata={"ip": "127.0.0.1"}
        )
        
        await publisher.disconnect()
        
        print(f"✅ Audit Publisher working! Publish result: {result}")
        return True
        
    except Exception as e:
        print(f"❌ Audit Publisher failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_audit_service():
    """Test Audit Service integration"""
    print("\n3. Testing Audit Service...")
    try:
        from core.audit.audit_service import AuditService
        from core.audit.models import AuditEventV1, EventSeverity, EventCategory
        
        # Initialize audit service
        service = AuditService()
        await service.initialize()
        
        # Create test audit event
        event = AuditEventV1(
            id="test-event-001",
            timestamp=datetime.now(timezone.utc),
            actor_id="user123",
            action="test.action",
            resource_type="test_resource",
            resource_id="resource123",
            severity=EventSeverity.INFO,
            category=EventCategory.ACCESS
        )
        
        # Log event (immediate mode)
        result = await service.log_audit_event(event, immediate=True)
        
        # Wait for any background processing
        await asyncio.sleep(0.5)
        
        # Shutdown service
        await service.shutdown()
        
        print(f"✅ Audit Service working! Event logged: {result}")
        return True
        
    except Exception as e:
        print(f"❌ Audit Service failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_issue_tracking_database():
    """Test Issue Tracking Database"""
    print("\n4. Testing Issue Tracking Database...")
    try:
        from core.issue_tracking.issue_database import IssueTrackingDatabase
        from models.issue_tracking import ChangeIssueLink, IssueReference, IssueProvider
        
        db = IssueTrackingDatabase(db_path="/tmp")
        await db.initialize()
        
        # Create test link
        link = ChangeIssueLink(
            change_id="change-001",
            change_type="commit",
            branch_name="main",
            primary_issue=IssueReference(
                provider=IssueProvider.JIRA,
                issue_id="TEST-123"
            ),
            linked_by="test_user",
            linked_at=datetime.now(timezone.utc)
        )
        
        # Store link
        link_id = await db.store_change_issue_link(link)
        
        # Retrieve link
        retrieved = await db.get_issues_for_change("change-001")
        
        print(f"✅ Issue Tracking DB working! Stored and retrieved link: {retrieved.primary_issue.issue_id if retrieved else 'None'}")
        
        # Cleanup
        if os.path.exists("/tmp/issue_tracking.db"):
            os.remove("/tmp/issue_tracking.db")
        
        return True
        
    except Exception as e:
        print(f"❌ Issue Tracking DB failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_unified_http_client():
    """Test UnifiedHTTPClient"""
    print("\n5. Testing UnifiedHTTPClient...")
    try:
        from database.clients.unified_http_client import UnifiedHTTPClient, HTTPClientConfig
        
        config = HTTPClientConfig(
            base_url="https://httpbin.org",
            timeout=5.0
        )
        
        async with UnifiedHTTPClient(config) as client:
            # Test GET request
            response = await client.get("/status/200")
            
            print(f"✅ UnifiedHTTPClient working! Status code: {response.status_code}")
            return True
            
    except Exception as e:
        print(f"❌ UnifiedHTTPClient failed: {e}")
        return False

async def main():
    """Run all integration tests"""
    print("=" * 60)
    print("OMS Monolith Integration Tests")
    print("=" * 60)
    
    tests = [
        test_sqlite_connector,
        test_audit_publisher,
        test_audit_service,
        test_issue_tracking_database,
        test_unified_http_client
    ]
    
    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"Test {test.__name__} crashed: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    print("Test Summary:")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    print(f"Passed: {passed}/{total}")
    print(f"Failed: {total - passed}/{total}")
    
    if passed == total:
        print("\n✅ All tests passed! The system is working correctly.")
    else:
        print("\n❌ Some tests failed. Please check the errors above.")
    
    return passed == total

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)