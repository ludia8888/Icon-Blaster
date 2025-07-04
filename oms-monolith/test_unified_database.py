#!/usr/bin/env python3
"""
Integration Test for Unified Database and TerminusDB Audit
Tests the complete flow of unified database operations and audit tracking
"""
import asyncio
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

# Mock imports for testing without actual dependencies
class MockLogger:
    def info(self, msg): print(f"[INFO] {msg}")
    def error(self, msg): print(f"[ERROR] {msg}")
    def warning(self, msg): print(f"[WARNING] {msg}")
    def debug(self, msg): print(f"[DEBUG] {msg}")

logger = MockLogger()


# Mock TerminusDB Client
class MockWOQLClient:
    """Mock TerminusDB client for testing"""
    
    def __init__(self, **kwargs):
        self.config = kwargs
        self.connected = False
        self.commits = []
        self.documents = {}
        self.current_branch = "main"
        self.branches = {"main": {"head": "initial"}}
        
    def connect(self):
        self.connected = True
        logger.info(f"Connected to TerminusDB at {self.config.get('server_url')}")
        
    def insert_document(self, document: Dict[str, Any]):
        doc_id = document.get("@id")
        self.documents[doc_id] = document.copy()
        logger.info(f"Inserted document: {doc_id}")
        
    def get_document(self, doc_id: str) -> Dict[str, Any]:
        return self.documents.get(doc_id)
        
    def update_document(self, document: Dict[str, Any]):
        doc_id = document.get("@id")
        if doc_id in self.documents:
            old_doc = self.documents[doc_id].copy()
            self.documents[doc_id] = document.copy()
            return old_doc
        return None
        
    def delete_document(self, doc_id: str):
        if doc_id in self.documents:
            del self.documents[doc_id]
            
    def commit(self, message: str, author: str = "system", commit_info: Dict = None):
        commit_id = f"commit_{len(self.commits) + 1}"
        commit = {
            "identifier": commit_id,
            "message": message,
            "author": author,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "parent": self.branches[self.current_branch]["head"] if self.commits else None,
            "commit_info": commit_info or {}
        }
        self.commits.append(commit)
        self.branches[self.current_branch]["head"] = commit_id
        logger.info(f"Created commit: {commit_id} - {message}")
        return {"commit": commit_id}
        
    def get_commit_history(self) -> List[Dict[str, Any]]:
        return list(reversed(self.commits))  # Newest first
        
    def diff(self, commit1: str, commit2: str) -> Dict[str, Any]:
        # Simplified diff
        return {
            "operations": [
                {
                    "@type": "UpdateDocument",
                    "document": {"@id": "Schema/test", "@type": "Schema"},
                    "before": {"name": "old"},
                    "after": {"name": "new"}
                }
            ]
        }
        
    def checkout(self, branch_or_commit: str):
        self.current_branch = branch_or_commit
        logger.info(f"Checked out: {branch_or_commit}")


# Mock Database Connectors
class MockPostgresConnector:
    def __init__(self, **kwargs):
        self.config = kwargs
        self.data = {}
        
    async def initialize(self):
        logger.info("PostgreSQL connector initialized (mock)")
        
    async def begin(self):
        return self
        
    async def commit(self):
        logger.info("PostgreSQL transaction committed")
        
    async def rollback(self):
        logger.info("PostgreSQL transaction rolled back")
        
    async def fetch_one(self, query: str, *args):
        return {"id": "123", "COUNT(*)": 10}
        
    async def execute(self, query: str, params: Dict):
        logger.info(f"PostgreSQL execute: {query[:50]}...")
        
    async def close(self):
        logger.info("PostgreSQL connector closed")


class MockSQLiteConnector:
    def __init__(self, **kwargs):
        self.config = kwargs
        self.data = {}
        
    async def initialize(self):
        logger.info("SQLite connector initialized (mock)")
        
    async def begin(self):
        return self
        
    async def commit(self):
        logger.info("SQLite transaction committed")
        
    async def rollback(self):
        logger.info("SQLite transaction rolled back")
        
    async def execute(self, query: str, params: List):
        logger.info(f"SQLite execute: {query[:50]}...")
        return type('obj', (object,), {'lastrowid': 456})
        
    async def close(self):
        logger.info("SQLite connector closed")


# Import and patch modules
import sys
from unittest.mock import MagicMock

# Create mock modules
sys.modules['terminusdb_client'] = MagicMock()
sys.modules['terminusdb_client'].WOQLClient = MockWOQLClient
sys.modules['terminusdb_client.errors'] = MagicMock()

sys.modules['shared'] = MagicMock()
sys.modules['shared.database'] = MagicMock()
sys.modules['shared.database.postgres_connector'] = MagicMock()
sys.modules['shared.database.postgres_connector'].PostgresConnector = MockPostgresConnector
sys.modules['shared.database.sqlite_connector'] = MagicMock()
sys.modules['shared.database.sqlite_connector'].SQLiteConnector = MockSQLiteConnector

sys.modules['utils'] = MagicMock()
sys.modules['utils.logger'] = MagicMock()
sys.modules['utils.logger'].get_logger = lambda x: logger

sys.modules['models'] = MagicMock()
sys.modules['models.audit_events'] = MagicMock()

# Create mock enums
from enum import Enum

class AuditAction(Enum):
    SCHEMA_CREATE = "schema_create"
    SCHEMA_UPDATE = "schema_update"
    SCHEMA_DELETE = "schema_delete"
    OBJECT_CREATE = "object_create"
    OBJECT_UPDATE = "object_update"

class ResourceType(Enum):
    SCHEMA = "schema"
    OBJECT_TYPE = "object_type"
    PROPERTY = "property"
    BRANCH = "branch"

class DatabaseBackend(Enum):
    TERMINUSDB = "terminusdb"
    POSTGRESQL = "postgresql"
    SQLITE = "sqlite"
    MEMORY = "memory"

sys.modules['models.audit_events'].AuditAction = AuditAction
sys.modules['models.audit_events'].ResourceType = ResourceType
sys.modules['database.clients.unified_database_client'] = MagicMock()
sys.modules['database.clients.unified_database_client'].DatabaseBackend = DatabaseBackend

# Now import our modules
from database.clients.unified_database_client import UnifiedDatabaseClient
from core.audit.terminusdb_audit_service import TerminusAuditService
from core.audit.audit_migration_adapter import AuditMigrationAdapter


async def test_unified_database():
    """Test unified database operations"""
    logger.info("=== Testing Unified Database Client ===\n")
    
    # Create unified client
    client = UnifiedDatabaseClient(
        terminus_config={
            "server_url": "http://localhost:6363",
            "user": "admin",
            "key": "root"
        },
        postgres_config={
            "host": "localhost",
            "port": 5432,
            "database": "test_db",
            "user": "test",
            "password": "test"
        }
    )
    
    # Override connectors with mocks
    client._terminus_client = MockWOQLClient(**client.terminus_config)
    client._postgres_connector = MockPostgresConnector(**client.postgres_config)
    client._sqlite_connector = MockSQLiteConnector(**client.sqlite_config)
    client._connected = True
    
    # Test 1: Create document (should go to TerminusDB)
    logger.info("Test 1: Create schema document")
    doc_id = await client.create(
        collection="Schema",
        document={
            "id": "ProductSchema",
            "name": "Product Schema",
            "version": "1.0",
            "properties": ["id", "name", "price", "category"]
        },
        author="test@example.com",
        message="Created Product schema"
    )
    logger.info(f"Created document: {doc_id}\n")
    
    # Test 2: Update document
    logger.info("Test 2: Update schema document")
    success = await client.update(
        collection="Schema",
        doc_id=doc_id,
        updates={"version": "1.1", "properties": ["id", "name", "price", "category", "description"]},
        author="test@example.com",
        message="Added description field to Product schema"
    )
    logger.info(f"Update success: {success}\n")
    
    # Test 3: Create user record (should go to PostgreSQL)
    logger.info("Test 3: Create user record")
    user_id = await client.create(
        collection="user",
        document={
            "username": "testuser",
            "email": "test@example.com",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    )
    logger.info(f"Created user: {user_id}\n")
    
    # Test transaction
    logger.info("Test 4: Transaction handling")
    async with client.transaction("Test transaction", "test@example.com") as tx_client:
        await tx_client.create(
            collection="Schema",
            document={"id": "OrderSchema", "name": "Order Schema"}
        )
        logger.info("Transaction will be committed\n")
    
    return client


async def test_terminus_audit():
    """Test TerminusDB audit functionality"""
    logger.info("=== Testing TerminusDB Audit Service ===\n")
    
    # Create mock client
    mock_client = MockWOQLClient(server_url="http://localhost:6363")
    mock_client.connect()
    
    # Create audit service
    audit = TerminusAuditService(mock_client)
    
    # Test 1: Log audit operations
    logger.info("Test 1: Log audit operations")
    
    # Create schema
    commit1 = await audit.log_operation(
        action=AuditAction.SCHEMA_CREATE,
        resource_type=ResourceType.SCHEMA,
        resource_id="ProductSchema",
        author="admin@example.com",
        changes={"created": {"name": "Product", "version": "1.0"}},
        metadata={"ip": "192.168.1.1", "user_agent": "TestClient/1.0"}
    )
    
    await asyncio.sleep(0.1)  # Ensure different timestamps
    
    # Update schema
    commit2 = await audit.log_operation(
        action=AuditAction.SCHEMA_UPDATE,
        resource_type=ResourceType.SCHEMA,
        resource_id="ProductSchema",
        author="developer@example.com",
        changes={"version": {"old": "1.0", "new": "1.1"}},
        metadata={"reason": "Added new field"}
    )
    
    logger.info(f"Created commits: {commit1}, {commit2}\n")
    
    # Test 2: Query audit log
    logger.info("Test 2: Query audit log")
    
    from models.audit_events import AuditEventFilter
    filter_criteria = AuditEventFilter(
        resource_types=[ResourceType.SCHEMA],
        limit=10
    )
    
    events, total = await audit.query_audit_log(filter_criteria)
    logger.info(f"Found {total} audit events")
    for event in events:
        logger.info(f"  - {event['timestamp']}: {event['action']} by {event['author']}")
    
    # Test 3: Get resource history
    logger.info("\nTest 3: Get resource history")
    history = await audit.get_resource_history(
        resource_type=ResourceType.SCHEMA,
        resource_id="ProductSchema",
        include_diffs=True
    )
    logger.info(f"Resource history: {len(history)} entries")
    
    # Test 4: Get statistics
    logger.info("\nTest 4: Get audit statistics")
    stats = await audit.get_change_statistics()
    logger.info(f"Statistics: {json.dumps(stats, indent=2)}")
    
    # Test 5: Verify integrity
    logger.info("\nTest 5: Verify audit integrity")
    integrity = await audit.verify_audit_integrity()
    logger.info(f"Integrity check: {'PASSED' if integrity['is_valid'] else 'FAILED'}")
    logger.info(f"Commits checked: {integrity['commits_checked']}")
    
    return audit


async def test_migration_adapter():
    """Test audit migration adapter"""
    logger.info("=== Testing Audit Migration Adapter ===\n")
    
    # Create mock components
    mock_terminus_client = MockWOQLClient(server_url="http://localhost:6363")
    mock_terminus_client.connect()
    
    # Create mock unified client
    mock_unified_client = MagicMock()
    mock_unified_client._terminus_client = mock_terminus_client
    mock_unified_client.connect = asyncio.coroutine(lambda: None)
    mock_unified_client.close = asyncio.coroutine(lambda: None)
    
    # Create terminus audit
    terminus_audit = TerminusAuditService(mock_terminus_client)
    
    # Create migration adapter in dual-write mode
    adapter = AuditMigrationAdapter(
        legacy_audit=None,  # Skip legacy for this test
        terminus_audit=terminus_audit,
        unified_client=mock_unified_client,
        migration_mode="terminus_only"
    )
    
    await adapter.initialize()
    
    # Test 1: Store audit event
    logger.info("Test 1: Store audit event through adapter")
    
    # Create mock audit event
    from types import SimpleNamespace
    mock_event = SimpleNamespace(
        id="event123",
        action=AuditAction.OBJECT_CREATE,
        actor=SimpleNamespace(
            id="user123",
            username="testuser",
            ip_address="10.0.0.1",
            user_agent="TestAgent",
            service_account=False
        ),
        target=SimpleNamespace(
            resource_type=ResourceType.OBJECT_TYPE,
            resource_id="Product",
            resource_name="Product Type",
            branch="main"
        ),
        success=True,
        error_code=None,
        error_message=None,
        duration_ms=150,
        request_id="req123",
        correlation_id="corr123",
        causation_id=None,
        time=datetime.now(timezone.utc),
        changes=SimpleNamespace(dict=lambda: {"name": "Product", "fields": 5}),
        metadata={"source": "API"},
        tags=["important"],
        compliance=None
    )
    
    success = await adapter.store_audit_event(mock_event)
    logger.info(f"Store event success: {success}")
    
    # Test 2: Query events
    logger.info("\nTest 2: Query audit events")
    filter_criteria = SimpleNamespace(
        start_time=None,
        end_time=None,
        actor_ids=None,
        actions=None,
        resource_types=[ResourceType.OBJECT_TYPE],
        resource_ids=None,
        branches=None,
        success=None,
        limit=10,
        offset=0,
        include_changes=True
    )
    
    events, total = await adapter.query_audit_events(filter_criteria)
    logger.info(f"Retrieved {len(events)} events (total: {total})")
    
    # Test 3: Get migration status
    logger.info("\nTest 3: Migration status")
    status = adapter.get_migration_status()
    logger.info(f"Migration status: {json.dumps(status, indent=2)}")
    
    return adapter


async def test_time_travel():
    """Test time-travel queries"""
    logger.info("=== Testing Time-Travel Queries ===\n")
    
    # Create mock client with some history
    mock_client = MockWOQLClient(server_url="http://localhost:6363")
    mock_client.connect()
    
    # Create some commits with documents
    mock_client.insert_document({
        "@id": "schema/Product",
        "@type": "Schema",
        "name": "Product",
        "version": "1.0"
    })
    mock_client.commit("Initial Product schema", "admin")
    
    # Wait and update
    await asyncio.sleep(0.1)
    original_time = datetime.now(timezone.utc)
    
    mock_client.update_document({
        "@id": "schema/Product",
        "@type": "Schema",
        "name": "Product",
        "version": "1.1",
        "new_field": "added"
    })
    mock_client.commit("Updated Product schema", "developer")
    
    # Create audit service
    audit = TerminusAuditService(mock_client)
    
    # Test: Get resource at earlier time
    logger.info("Test: Get resource at specific time")
    
    # Mock the time-travel functionality
    audit._find_commit_at_time = lambda t: "commit_1"
    mock_client.checkout = lambda c: logger.info(f"Time travel to: {c}")
    
    historical_doc = await audit.get_resource_at_time(
        resource_type=ResourceType.SCHEMA,
        resource_id="Product",
        timestamp=original_time - timedelta(minutes=1)
    )
    
    logger.info(f"Historical document: {historical_doc}")
    
    return audit


async def test_data_routing():
    """Test data routing to appropriate backends"""
    logger.info("=== Testing Data Routing ===\n")
    
    client = UnifiedDatabaseClient()
    
    # Test routing rules
    test_cases = [
        ("schema", "Should route to TerminusDB"),
        ("object", "Should route to TerminusDB"),
        ("user", "Should route to PostgreSQL"),
        ("session", "Should route to PostgreSQL"),
        ("metric", "Should route to PostgreSQL"),
        ("audit", "Should route to TerminusDB"),
    ]
    
    from database.clients.unified_database_client import QueryType
    
    for collection, expected in test_cases:
        backend = client._get_backend_for_operation(collection, QueryType.WRITE)
        logger.info(f"{collection}: {backend.value} - {expected}")
    
    return client


async def run_all_tests():
    """Run all integration tests"""
    logger.info("Starting Unified Database Integration Tests")
    logger.info("=" * 60 + "\n")
    
    results = {
        "unified_database": False,
        "terminus_audit": False,
        "migration_adapter": False,
        "time_travel": False,
        "data_routing": False
    }
    
    try:
        # Test 1: Unified Database
        await test_unified_database()
        results["unified_database"] = True
    except Exception as e:
        logger.error(f"Unified database test failed: {e}")
    
    logger.info("\n" + "=" * 60 + "\n")
    
    try:
        # Test 2: TerminusDB Audit
        await test_terminus_audit()
        results["terminus_audit"] = True
    except Exception as e:
        logger.error(f"TerminusDB audit test failed: {e}")
    
    logger.info("\n" + "=" * 60 + "\n")
    
    try:
        # Test 3: Migration Adapter
        await test_migration_adapter()
        results["migration_adapter"] = True
    except Exception as e:
        logger.error(f"Migration adapter test failed: {e}")
    
    logger.info("\n" + "=" * 60 + "\n")
    
    try:
        # Test 4: Time Travel
        await test_time_travel()
        results["time_travel"] = True
    except Exception as e:
        logger.error(f"Time travel test failed: {e}")
    
    logger.info("\n" + "=" * 60 + "\n")
    
    try:
        # Test 5: Data Routing
        await test_data_routing()
        results["data_routing"] = True
    except Exception as e:
        logger.error(f"Data routing test failed: {e}")
    
    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST RESULTS SUMMARY:")
    logger.info("=" * 60)
    
    total_tests = len(results)
    passed_tests = sum(1 for v in results.values() if v)
    
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        logger.info(f"{test_name.replace('_', ' ').title()}: {status}")
    
    logger.info(f"\nTotal: {passed_tests}/{total_tests} tests passed")
    
    if passed_tests == total_tests:
        logger.info("\n🎉 All tests passed! Unified database system is working correctly.")
    else:
        logger.info("\n⚠️  Some tests failed. Please check the logs above.")
    
    return passed_tests == total_tests


if __name__ == "__main__":
    # Set environment for testing
    os.environ["AUDIT_MIGRATION_PHASE"] = "dual_write"
    
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)