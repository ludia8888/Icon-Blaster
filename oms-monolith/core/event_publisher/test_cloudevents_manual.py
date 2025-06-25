#!/usr/bin/env python3
"""
Manual test script for Enhanced CloudEvents implementation
"""
import json
from datetime import datetime, timezone

# Import our modules
from cloudevents_enhanced import (
    EnhancedCloudEvent, EventType, CloudEventBuilder, CloudEventValidator
)
from cloudevents_adapter import CloudEventsFactory
from cloudevents_migration import EventSchemaMigrator
from enhanced_event_service import EnhancedEventService


def test_basic_cloudevent_creation():
    """Test basic CloudEvent creation"""
    print("=== Testing Basic CloudEvent Creation ===")
    
    event = EnhancedCloudEvent(
        type=EventType.SCHEMA_UPDATED,
        source="/oms/test",
        data={"test": "data"}
    )
    
    print(f"Event ID: {event.id}")
    print(f"Event Type: {event.type}")
    print(f"Event Source: {event.source}")
    print(f"Event Time: {event.time}")
    print(f"Event Data: {event.data}")
    
    # Validation
    errors = CloudEventValidator.validate_cloudevent(event)
    print(f"Validation Errors: {errors}")
    print(f"Is Valid: {CloudEventValidator.is_valid_cloudevent(event)}")
    print()


def test_builder_pattern():
    """Test CloudEvent Builder pattern"""
    print("=== Testing Builder Pattern ===")
    
    event = CloudEventBuilder(EventType.OBJECT_TYPE_CREATED, "/oms/main") \
        .with_subject("object_type/User") \
        .with_data({"name": "User", "description": "User object type"}) \
        .with_oms_context("main", "abc123", "developer@example.com") \
        .with_correlation("corr-123", "cause-456") \
        .build()
    
    print(f"Event Type: {event.type}")
    print(f"Event Subject: {event.subject}")
    print(f"Event Branch: {event.ce_branch}")
    print(f"Event Commit: {event.ce_commit}")
    print(f"Event Author: {event.ce_author}")
    print(f"Correlation ID: {event.ce_correlationid}")
    print(f"Causation ID: {event.ce_causationid}")
    print()


def test_binary_headers():
    """Test Binary Content Mode headers"""
    print("=== Testing Binary Headers ===")
    
    event = CloudEventBuilder(EventType.BRANCH_CREATED, "/oms/main") \
        .with_subject("branch/feature") \
        .with_oms_context("main", "abc123", "developer@example.com") \
        .build()
    
    headers = event.to_binary_headers()
    
    print("Binary Headers:")
    for key, value in headers.items():
        print(f"  {key}: {value}")
    print()


def test_nats_subject():
    """Test NATS subject generation"""
    print("=== Testing NATS Subject Generation ===")
    
    events = [
        EnhancedCloudEvent(type=EventType.OBJECT_TYPE_CREATED, source="/oms/main"),
        EnhancedCloudEvent(type=EventType.SCHEMA_UPDATED, source="/oms/main"),
        EnhancedCloudEvent(type=EventType.BRANCH_MERGED, source="/oms/main"),
        EnhancedCloudEvent(type="custom.event.type", source="/oms/main")
    ]
    
    for event in events:
        subject = event.get_nats_subject()
        print(f"Type: {event.type} -> Subject: {subject}")
    print()


def test_legacy_migration():
    """Test legacy event migration"""
    print("=== Testing Legacy Event Migration ===")
    
    legacy_events = [
        {
            "specversion": "1.0",
            "type": "schema.changed",
            "source": "/oms/main",
            "id": "test-event-1",
            "time": "2024-01-01T00:00:00Z",
            "data": {
                "operation": "create",
                "resource_type": "object_type",
                "resource_id": "User"
            }
        },
        {
            "id": "test-event-2",
            "type": "object_type_created",
            "payload": json.dumps({
                "object_type_id": "Product",
                "branch": "feature/products"
            }),
            "created_at": "2024-01-01T01:00:00Z"
        }
    ]
    
    migrator = EventSchemaMigrator()
    migrated_events = migrator.migrate_legacy_events(legacy_events)
    
    print(f"Original events: {len(legacy_events)}")
    print(f"Migrated events: {len(migrated_events)}")
    
    for i, event in enumerate(migrated_events):
        print(f"Event {i+1}:")
        print(f"  ID: {event.id}")
        print(f"  Type: {event.type}")
        print(f"  Source: {event.source}")
        print(f"  Data: {event.data}")
    
    # Migration report
    report = migrator.get_migration_report()
    print(f"\nMigration Report:")
    print(f"  Success Rate: {report['summary']['success_rate_percent']}%")
    print(f"  Total Events: {report['summary']['total_events']}")
    print(f"  Successful: {report['summary']['migrated_successfully']}")
    print(f"  Failed: {report['summary']['migration_failures']}")
    print()


def test_event_service():
    """Test Enhanced Event Service"""
    print("=== Testing Enhanced Event Service ===")
    
    service = EnhancedEventService()
    
    # Create schema change event
    schema_event = service.create_schema_change_event(
        operation="create",
        resource_type="object_type",
        resource_id="User",
        branch="main",
        commit_id="abc123",
        author="developer@example.com",
        new_value={"name": "User", "description": "User entity"}
    )
    
    print(f"Schema Event:")
    print(f"  Type: {schema_event.type}")
    print(f"  Branch: {schema_event.ce_branch}")
    print(f"  Author: {schema_event.ce_author}")
    print(f"  Operation: {schema_event.data['operation']}")
    
    # Create branch event
    branch_event = service.create_branch_event(
        operation="created",
        branch_name="feature/new-feature",
        author="developer@example.com"
    )
    
    print(f"\nBranch Event:")
    print(f"  Type: {branch_event.type}")
    print(f"  Branch Name: {branch_event.data['branch_name']}")
    print(f"  Author: {branch_event.data['author']}")
    
    # Statistics
    stats = service.get_event_statistics()
    print(f"\nService Statistics:")
    print(f"  CloudEvents Version: {stats['cloudevents_version']}")
    print(f"  Supported Event Types: {len(stats['supported_event_types'])}")
    print(f"  Enhanced Features: {', '.join(stats['enhanced_features'])}")
    print()


def test_structured_format():
    """Test Structured Content Mode"""
    print("=== Testing Structured Format ===")
    
    event = CloudEventBuilder(EventType.PROPOSAL_CREATED, "/oms/main") \
        .with_subject("proposal/123") \
        .with_data({"title": "Test Proposal", "description": "A test proposal"}) \
        .with_oms_context("main", "abc123", "developer@example.com") \
        .build()
    
    structured = event.to_structured_format()
    
    print("Structured Format (JSON):")
    print(json.dumps(structured, indent=2, default=str))
    print()


def main():
    """Run all tests"""
    print("Enhanced CloudEvents Implementation Test")
    print("=" * 50)
    
    try:
        test_basic_cloudevent_creation()
        test_builder_pattern()
        test_binary_headers()
        test_nats_subject()
        test_legacy_migration()
        test_event_service()
        test_structured_format()
        
        print("✅ All tests completed successfully!")
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()