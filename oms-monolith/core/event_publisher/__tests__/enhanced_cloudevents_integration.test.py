"""
Enhanced CloudEvents Integration Tests
CloudEvents 1.0 표준 구현 및 하위 호환성 테스트
"""
import pytest
import json
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.event_publisher.enhanced_event_service import EnhancedEventService
from core.event_publisher.cloudevents_enhanced import (
    EnhancedCloudEvent, EventType, CloudEventBuilder, CloudEventValidator
)
from core.event_publisher.cloudevents_adapter import CloudEventsAdapter, CloudEventsFactory
from core.event_publisher.cloudevents_migration import EventSchemaMigrator, BackwardCompatibilityLayer
from models import Change, EventMetadata, OutboxEvent


class TestEnhancedCloudEventsIntegration:
    """Enhanced CloudEvents 통합 테스트"""
    
    @pytest.fixture
    def mock_outbox_repository(self):
        """Mock Outbox Repository"""
        repository = Mock()
        repository.save = AsyncMock()
        return repository
    
    @pytest.fixture
    def event_service(self, mock_outbox_repository):
        """Event Service 인스턴스"""
        return EnhancedEventService(outbox_repository=mock_outbox_repository)
    
    @pytest.fixture
    def sample_legacy_events(self):
        """샘플 레거시 이벤트들"""
        return [
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
            },
            {
                "event_type": "branch_created",
                "data": {
                    "branch_name": "feature/new-feature",
                    "author": "developer@example.com"
                },
                "timestamp": "2024-01-01T02:00:00Z"
            }
        ]
    
    def test_enhanced_cloudevent_creation(self):
        """Enhanced CloudEvent 생성 테스트"""
        event = EnhancedCloudEvent(
            type=EventType.SCHEMA_UPDATED,
            source="/oms/test",
            data={"test": "data"}
        )
        
        assert event.specversion == "1.0"
        assert event.type == EventType.SCHEMA_UPDATED
        assert event.source == "/oms/test"
        assert event.id is not None
        assert event.time is not None
        assert event.data == {"test": "data"}
    
    def test_cloudevent_builder_pattern(self):
        """CloudEvent Builder 패턴 테스트"""
        event = CloudEventBuilder(EventType.OBJECT_TYPE_CREATED, "/oms/main") \
            .with_subject("object_type/User") \
            .with_data({"name": "User", "description": "User object type"}) \
            .with_oms_context("main", "abc123", "developer@example.com") \
            .with_correlation("corr-123", "cause-456") \
            .build()
        
        assert event.type == EventType.OBJECT_TYPE_CREATED
        assert event.source == "/oms/main"
        assert event.subject == "object_type/User"
        assert event.ce_branch == "main"
        assert event.ce_commit == "abc123"
        assert event.ce_author == "developer@example.com"
        assert event.ce_correlationid == "corr-123"
        assert event.ce_causationid == "cause-456"
    
    def test_cloudevent_validation(self):
        """CloudEvent 유효성 검증 테스트"""
        # 유효한 이벤트
        valid_event = EnhancedCloudEvent(
            type=EventType.SCHEMA_UPDATED,
            source="/oms/test",
            data={"test": "data"}
        )
        
        errors = CloudEventValidator.validate_cloudevent(valid_event)
        assert len(errors) == 0
        assert CloudEventValidator.is_valid_cloudevent(valid_event)
        
        # 무효한 이벤트
        invalid_event = EnhancedCloudEvent(
            type="invalid-type",  # reverse domain notation 위반
            source="invalid-source",  # URI 형식 위반
            id="",  # 빈 ID
            data={"test": "data"}
        )
        
        errors = CloudEventValidator.validate_cloudevent(invalid_event)
        assert len(errors) > 0
        assert not CloudEventValidator.is_valid_cloudevent(invalid_event)
    
    def test_binary_content_mode_headers(self):
        """Binary Content Mode 헤더 생성 테스트"""
        event = CloudEventBuilder(EventType.BRANCH_CREATED, "/oms/main") \
            .with_subject("branch/feature") \
            .with_oms_context("main", "abc123", "developer@example.com") \
            .build()
        
        headers = event.to_binary_headers()
        
        assert headers['ce-specversion'] == "1.0"
        assert headers['ce-type'] == EventType.BRANCH_CREATED.value
        assert headers['ce-source'] == "/oms/main"
        assert headers['ce-id'] == event.id
        assert headers['ce-subject'] == "branch/feature"
        assert headers['ce-branch'] == "main"
        assert headers['ce-commit'] == "abc123"
        assert headers['ce-author'] == "developer@example.com"
    
    def test_nats_subject_generation(self):
        """NATS subject 생성 테스트"""
        event = EnhancedCloudEvent(
            type=EventType.OBJECT_TYPE_CREATED,
            source="/oms/main"
        )
        
        subject = event.get_nats_subject()
        assert subject == "oms.objecttype.created"
        
        # Custom type
        custom_event = EnhancedCloudEvent(
            type="custom.event.type",
            source="/oms/main"
        )
        
        custom_subject = custom_event.get_nats_subject()
        assert custom_subject == "oms.custom.event.type"
    
    def test_legacy_event_migration(self, sample_legacy_events):
        """레거시 이벤트 마이그레이션 테스트"""
        migrator = EventSchemaMigrator()
        
        migrated_events = migrator.migrate_legacy_events(sample_legacy_events)
        
        assert len(migrated_events) == 3
        
        # CloudEvent 형식 마이그레이션
        event1 = migrated_events[0]
        assert isinstance(event1, EnhancedCloudEvent)
        assert event1.id == "test-event-1"
        assert event1.type == EventType.SCHEMA_UPDATED.value
        
        # OutboxEvent 형식 마이그레이션
        event2 = migrated_events[1]
        assert event2.id == "test-event-2"
        assert event2.type == EventType.OBJECT_TYPE_CREATED.value
        
        # Custom 형식 마이그레이션
        event3 = migrated_events[2]
        assert event3.type == EventType.BRANCH_CREATED.value
        
        # 마이그레이션 리포트 확인
        report = migrator.get_migration_report()
        assert report['summary']['total_events'] == 3
        assert report['summary']['migrated_successfully'] == 3
        assert report['summary']['success_rate_percent'] == 100.0
    
    def test_backward_compatibility_layer(self):
        """하위 호환성 레이어 테스트"""
        # Enhanced CloudEvent 생성
        enhanced_event = CloudEventBuilder(EventType.PROPOSAL_CREATED, "/oms/main") \
            .with_subject("proposal/123") \
            .with_data({"title": "Test Proposal"}) \
            .with_oms_context("main", "abc123", "developer@example.com") \
            .build()
        
        # 레거시 형식으로 변환
        legacy_format = BackwardCompatibilityLayer.wrap_enhanced_as_legacy(enhanced_event)
        
        assert legacy_format['specversion'] == "1.0"
        assert legacy_format['type'] == EventType.PROPOSAL_CREATED.value
        assert legacy_format['event_type'] == EventType.PROPOSAL_CREATED.value
        assert legacy_format['metadata']['branch'] == "main"
        assert legacy_format['metadata']['author'] == "developer@example.com"
        
        # OutboxEvent로 변환
        outbox_event = BackwardCompatibilityLayer.create_legacy_outbox_event(enhanced_event)
        assert isinstance(outbox_event, OutboxEvent)
        assert outbox_event.id == enhanced_event.id
        assert outbox_event.type == str(enhanced_event.type)
    
    def test_event_service_schema_change_creation(self, event_service):
        """Event Service 스키마 변경 이벤트 생성 테스트"""
        event = event_service.create_schema_change_event(
            operation="create",
            resource_type="object_type",
            resource_id="User",
            branch="main",
            commit_id="abc123",
            author="developer@example.com",
            new_value={"name": "User", "description": "User entity"}
        )
        
        assert isinstance(event, EnhancedCloudEvent)
        assert event.ce_branch == "main"
        assert event.ce_commit == "abc123"
        assert event.ce_author == "developer@example.com"
        assert event.data['operation'] == "create"
        assert event.data['resource_type'] == "object_type"
        assert event.data['resource_id'] == "User"
    
    def test_event_service_branch_event_creation(self, event_service):
        """Event Service 브랜치 이벤트 생성 테스트"""
        event = event_service.create_branch_event(
            operation="created",
            branch_name="feature/new-feature",
            author="developer@example.com",
            metadata={"description": "New feature branch"}
        )
        
        assert event.type == EventType.BRANCH_CREATED
        assert event.data['branch_name'] == "feature/new-feature"
        assert event.data['author'] == "developer@example.com"
        assert event.data['metadata']['description'] == "New feature branch"
    
    @pytest.mark.asyncio
    async def test_event_service_outbox_publishing(self, event_service, mock_outbox_repository):
        """Event Service Outbox 발행 테스트"""
        event = event_service.create_schema_change_event(
            operation="update",
            resource_type="property",
            resource_id="name",
            branch="main",
            commit_id="def456",
            author="developer@example.com"
        )
        
        event_id = await event_service.publish_event(event, immediate=False)
        
        assert event_id == event.id
        mock_outbox_repository.save.assert_called_once()
        
        # 저장된 OutboxEvent 확인
        saved_outbox_event = mock_outbox_repository.save.call_args[0][0]
        assert isinstance(saved_outbox_event, OutboxEvent)
        assert saved_outbox_event.id == event.id
    
    def test_event_batch_creation(self, event_service):
        """이벤트 배치 생성 테스트"""
        events_data = [
            {
                "event_type": "schema_change",
                "operation": "create",
                "resource_type": "object_type",
                "resource_id": "Product",
                "branch": "main",
                "commit_id": "abc123",
                "author": "developer@example.com"
            },
            {
                "event_type": "branch",
                "operation": "created",
                "branch_name": "feature/products",
                "author": "developer@example.com"
            }
        ]
        
        events = event_service.create_event_batch(events_data)
        
        assert len(events) == 2
        assert isinstance(events[0], EnhancedCloudEvent)
        assert isinstance(events[1], EnhancedCloudEvent)
        assert events[0].data['resource_type'] == "object_type"
        assert events[1].data['branch_name'] == "feature/products"
    
    def test_change_to_cloudevent_conversion(self):
        """Change 객체를 CloudEvent로 변환 테스트"""
        change = Change(
            operation="update",
            resource_type="property",
            resource_id="description",
            old_value="Old description",
            new_value="New description"
        )
        
        metadata = EventMetadata(
            branch="main",
            commit_id="ghi789",
            author="developer@example.com",
            timestamp=datetime.now(timezone.utc)
        )
        
        event = CloudEventsAdapter.convert_change_to_cloudevent(change, metadata)
        
        assert isinstance(event, EnhancedCloudEvent)
        assert event.type == EventType.PROPERTY_UPDATED
        assert event.subject == "property/description"
        assert event.data['operation'] == "update"
        assert event.data['old_value'] == "Old description"
        assert event.data['new_value'] == "New description"
    
    def test_event_statistics(self, event_service):
        """이벤트 통계 정보 테스트"""
        stats = event_service.get_event_statistics()
        
        assert "supported_event_types" in stats
        assert "cloudevents_version" in stats
        assert "enhanced_features" in stats
        
        assert stats["cloudevents_version"] == "1.0"
        assert "correlation_tracking" in stats["enhanced_features"]
        assert "backward_compatibility" in stats["enhanced_features"]
        
        # 모든 EventType이 포함되어 있는지 확인
        supported_types = stats["supported_event_types"]
        assert EventType.SCHEMA_CREATED.value in supported_types
        assert EventType.OBJECT_TYPE_CREATED.value in supported_types
        assert EventType.BRANCH_CREATED.value in supported_types
    
    def test_full_integration_workflow(self, event_service):
        """전체 통합 워크플로우 테스트"""
        # 1. 레거시 이벤트에서 시작
        legacy_event = {
            "type": "schema.changed",
            "source": "/oms/main",
            "data": {
                "operation": "create",
                "resource_type": "link_type",
                "resource_id": "userToProduct"
            },
            "metadata": {
                "branch": "main",
                "commit_id": "xyz789",
                "author": "developer@example.com"
            }
        }
        
        # 2. Enhanced CloudEvent로 변환
        enhanced_event = event_service.convert_legacy_event(legacy_event)
        
        # 3. 유효성 검증
        errors = CloudEventValidator.validate_cloudevent(enhanced_event)
        assert len(errors) == 0
        
        # 4. NATS subject 생성
        subject = enhanced_event.get_nats_subject()
        assert subject.startswith("oms.")
        
        # 5. Binary headers 생성
        headers = enhanced_event.to_binary_headers()
        assert "ce-type" in headers
        assert "ce-source" in headers
        
        # 6. 하위 호환성 형식으로 변환
        legacy_format = BackwardCompatibilityLayer.wrap_enhanced_as_legacy(enhanced_event)
        assert "event_type" in legacy_format
        assert "metadata" in legacy_format
        
        # 7. 전체 프로세스가 성공적으로 완료됨
        assert enhanced_event.id is not None
        assert enhanced_event.time is not None