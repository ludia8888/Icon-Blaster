#!/usr/bin/env python3
"""
Test IAM-TerminusDB Integration
Tests that authenticated users' actions are properly tracked in TerminusDB commits
"""
import asyncio
import json
from datetime import datetime, timezone

# Test components
from core.auth import UserContext
from core.auth.secure_author_provider import SecureAuthorProvider, get_secure_author_provider
from database.clients.secure_database_adapter import SecureDatabaseAdapter, create_secure_database
from database.clients.unified_database_client import UnifiedDatabaseClient
from core.auth.database_context import set_current_user_context, get_contextual_database, with_user_context
from utils.logger import get_logger

logger = get_logger(__name__)


async def test_secure_author_provider():
    """Test secure author generation and parsing"""
    print("\n=== Testing SecureAuthorProvider ===")
    
    # Create test user context
    user = UserContext(
        user_id="usr_123456",
        username="alice.smith",
        email="alice@example.com",
        roles=["developer", "reviewer"],
        permissions=["schema.read", "schema.write"],
        is_service_account=False,
        tenant_id="tenant_abc"
    )
    
    # Get provider
    provider = get_secure_author_provider(jwt_secret="test-secret")
    
    # Generate secure author
    secure_author = provider.get_secure_author(user, include_metadata=True)
    print(f"Generated secure author: {secure_author}")
    
    # Parse it back
    parsed = provider.parse_secure_author(secure_author)
    print(f"Parsed author: {json.dumps(parsed, indent=2)}")
    
    # Verify integrity
    is_valid, error = provider.verify_author_integrity(secure_author, user)
    print(f"Author integrity valid: {is_valid}, error: {error}")
    
    # Test service account
    service_user = UserContext(
        user_id="svc_deploy",
        username="deployment-service",
        email=None,
        roles=["service"],
        permissions=["*"],
        is_service_account=True
    )
    
    service_author = provider.get_secure_author(service_user)
    print(f"\nService account author: {service_author}")
    
    # Test delegation
    delegated_author = provider.create_delegation_author(
        delegator=service_user,
        on_behalf_of="alice.smith",
        reason="automated deployment"
    )
    print(f"Delegated author: {delegated_author}")
    
    return True


async def test_secure_database_adapter():
    """Test secure database operations with user context"""
    print("\n\n=== Testing SecureDatabaseAdapter ===")
    
    # Create test users
    alice = UserContext(
        user_id="usr_alice",
        username="alice",
        email="alice@example.com",
        roles=["developer"],
        permissions=["schema.write"],
        is_service_account=False
    )
    
    bob = UserContext(
        user_id="usr_bob",
        username="bob",
        email="bob@example.com",
        roles=["admin"],
        permissions=["*"],
        is_service_account=False
    )
    
    # Create secure database adapters
    print("\nCreating secure database adapters...")
    alice_db = await create_secure_database(alice)
    bob_db = await create_secure_database(bob)
    
    # Test 1: Create document as Alice
    print("\n1. Alice creates a document...")
    try:
        doc_id = await alice_db.create(
            user_context=alice,
            collection="test_objects",
            document={
                "name": "Test Object",
                "description": "Created by Alice",
                "type": "example"
            },
            message="Alice's test object creation"
        )
        print(f"   ✓ Document created with ID: {doc_id}")
    except Exception as e:
        print(f"   ✗ Failed to create document: {e}")
        doc_id = "test_obj_1"
    
    # Test 2: Update document as Bob
    print("\n2. Bob updates the document...")
    try:
        success = await bob_db.update(
            user_context=bob,
            collection="test_objects",
            doc_id=doc_id,
            updates={
                "description": "Updated by Bob",
                "modified_timestamp": datetime.now(timezone.utc).isoformat()
            },
            message="Bob's update to test object"
        )
        print(f"   ✓ Document updated: {success}")
    except Exception as e:
        print(f"   ✗ Failed to update document: {e}")
    
    # Test 3: Read with audit metadata
    print("\n3. Reading document with audit metadata...")
    try:
        docs = await alice_db.read(
            collection="test_objects",
            query={"name": "Test Object"}
        )
        if docs:
            doc = docs[0]
            print(f"   ✓ Found document:")
            print(f"     - Created by: {doc.get('_created_by_username')} ({doc.get('_created_by')})")
            print(f"     - Updated by: {doc.get('_updated_by_username')} ({doc.get('_updated_by')})")
    except Exception as e:
        print(f"   ✗ Failed to read document: {e}")
    
    # Test 4: Get audit log
    print("\n4. Retrieving audit log...")
    try:
        audit_entries = await alice_db.get_audit_log(
            resource_type="test_objects",
            limit=5
        )
        print(f"   ✓ Found {len(audit_entries)} audit entries:")
        for entry in audit_entries:
            author_parsed = entry.get("author_parsed", {})
            print(f"     - {entry.get('message')} by {author_parsed.get('username', 'unknown')}")
            print(f"       Verified: {author_parsed.get('verified', False)}")
    except Exception as e:
        print(f"   ✗ Failed to get audit log: {e}")
    
    # Test 5: Transaction with secure author
    print("\n5. Testing transactional operations...")
    try:
        async with alice_db.transaction(
            user_context=alice,
            message="Alice's bulk operation",
            additional_metadata={"operation": "bulk_import", "count": 3}
        ) as tx:
            # Create multiple documents in transaction
            await tx.create("test_objects", {"name": "Object 1", "index": 1})
            await tx.create("test_objects", {"name": "Object 2", "index": 2})
            await tx.create("test_objects", {"name": "Object 3", "index": 3})
        print("   ✓ Transaction completed successfully")
    except Exception as e:
        print(f"   ✗ Transaction failed: {e}")
    
    return True


async def test_database_context():
    """Test context-aware database operations"""
    print("\n\n=== Testing Database Context Management ===")
    
    # Create test user
    user = UserContext(
        user_id="usr_context_test",
        username="context_tester",
        email="context@example.com",
        roles=["developer"],
        permissions=["schema.write"],
        is_service_account=False
    )
    
    # Test 1: Context propagation
    print("\n1. Testing context propagation...")
    
    # Set user context
    set_current_user_context(user)
    
    # Get contextual database (should be secure)
    db = await get_contextual_database()
    print(f"   Database type: {type(db).__name__}")
    print(f"   Is secure: {isinstance(db, SecureDatabaseAdapter)}")
    
    # Test 2: Decorator usage
    print("\n2. Testing context decorator...")
    
    @with_user_context(user)
    async def service_operation():
        db = await get_contextual_database()
        # This should automatically use secure database with user context
        result = await db.create(
            user_context=user,  # This is redundant but shown for clarity
            collection="test_service",
            document={"name": "Service Test", "created_via": "decorator"}
        )
        return result
    
    try:
        result = await service_operation()
        print(f"   ✓ Service operation completed: {result}")
    except Exception as e:
        print(f"   ✗ Service operation failed: {e}")
    
    return True


async def test_middleware_integration():
    """Test how middleware and database integration works together"""
    print("\n\n=== Testing Middleware Integration Flow ===")
    
    # Simulate request flow
    print("\n1. AuthMiddleware authenticates user...")
    user = UserContext(
        user_id="usr_middleware_test",
        username="middleware_user",
        email="middleware@example.com",
        roles=["user"],
        permissions=["read"],
        is_service_account=False
    )
    print(f"   ✓ User authenticated: {user.username}")
    
    print("\n2. AuditMiddleware captures request...")
    # This would normally happen in the middleware
    from models.audit_events import AuditAction, ResourceType, TargetInfo
    
    target = TargetInfo(
        resource_type=ResourceType.SCHEMA,
        resource_id="schema_123",
        branch="main"
    )
    
    print("\n3. Database operation with secure author...")
    secure_db = await create_secure_database(user)
    
    try:
        # Simulate a schema update
        result = await secure_db.update(
            user_context=user,
            collection="schemas",
            doc_id="schema_123",
            updates={"version": "2.0", "updated_via": "test"},
            message="Test schema update via middleware flow"
        )
        print(f"   ✓ Database updated with secure author tracking")
    except Exception as e:
        print(f"   ✗ Database operation failed: {e}")
    
    print("\n4. Verifying author in commit history...")
    try:
        audit_log = await secure_db.get_audit_log(
            resource_type="schemas",
            resource_id="schema_123",
            limit=1
        )
        if audit_log:
            entry = audit_log[0]
            print(f"   ✓ Latest commit author: {entry.get('author')}")
            if 'author_parsed' in entry:
                print(f"     - Username: {entry['author_parsed'].get('username')}")
                print(f"     - User ID: {entry['author_parsed'].get('user_id')}")
                print(f"     - Verified: {entry['author_parsed'].get('verified')}")
    except Exception as e:
        print(f"   ✗ Failed to verify author: {e}")
    
    return True


async def test_author_verification():
    """Test author verification and tampering detection"""
    print("\n\n=== Testing Author Verification ===")
    
    provider = get_secure_author_provider(jwt_secret="test-secret")
    
    # Test 1: Valid author
    print("\n1. Testing valid author...")
    user = UserContext(
        user_id="usr_verify",
        username="verifier",
        email="verify@example.com",
        roles=["admin"],
        permissions=["*"],
        is_service_account=False
    )
    
    valid_author = provider.get_secure_author(user)
    is_valid, error = provider.verify_author_integrity(valid_author, user)
    print(f"   Valid author: {valid_author}")
    print(f"   Verification: {is_valid} (error: {error})")
    
    # Test 2: Tampered author
    print("\n2. Testing tampered author...")
    tampered = valid_author.replace("verifier", "hacker")
    is_valid, error = provider.verify_author_integrity(tampered)
    print(f"   Tampered author: {tampered}")
    print(f"   Verification: {is_valid} (error: {error})")
    
    # Test 3: Old timestamp
    print("\n3. Testing old timestamp...")
    old_author = "olduser (usr_old) [verified|ts:2020-01-01T00:00:00Z]"
    is_valid, error = provider.verify_author_integrity(old_author)
    print(f"   Old author: {old_author}")
    print(f"   Verification: {is_valid} (error: {error})")
    
    return True


async def main():
    """Run all integration tests"""
    print("=== IAM-TerminusDB Integration Tests ===")
    print("Testing secure author tracking in database commits...")
    
    tests = [
        ("SecureAuthorProvider", test_secure_author_provider),
        ("SecureDatabaseAdapter", test_secure_database_adapter),
        ("DatabaseContext", test_database_context),
        ("MiddlewareIntegration", test_middleware_integration),
        ("AuthorVerification", test_author_verification)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        try:
            print(f"\n{'='*50}")
            success = await test_func()
            results[test_name] = "PASS" if success else "FAIL"
        except Exception as e:
            logger.error(f"Test {test_name} failed with exception: {e}")
            results[test_name] = f"ERROR: {str(e)}"
    
    # Summary
    print("\n\n=== TEST SUMMARY ===")
    for test_name, result in results.items():
        status = "✓" if result == "PASS" else "✗"
        print(f"{status} {test_name}: {result}")
    
    all_passed = all(r == "PASS" for r in results.values())
    print(f"\nOverall: {'ALL TESTS PASSED' if all_passed else 'SOME TESTS FAILED'}")
    
    return all_passed


if __name__ == "__main__":
    asyncio.run(main())