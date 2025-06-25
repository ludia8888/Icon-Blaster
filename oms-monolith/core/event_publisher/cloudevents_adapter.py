"""
CloudEvents Adapter
기존 이벤트 시스템과 Enhanced CloudEvents 간의 호환성 제공
"""
from typing import Dict, Any, Optional, Union, List
from datetime import datetime

from .models import CloudEvent, Change, EventMetadata, OutboxEvent
from .cloudevents_enhanced import (
    EnhancedCloudEvent, EventType, CloudEventBuilder, 
    CloudEventValidator, create_schema_event, create_action_event
)


class CloudEventsAdapter:
    """CloudEvents 호환성 어댑터"""
    
    @staticmethod
    def convert_legacy_to_enhanced(legacy_event: CloudEvent) -> EnhancedCloudEvent:
        """레거시 CloudEvent를 Enhanced CloudEvent로 변환"""
        return legacy_event.to_enhanced_cloudevent()
    
    @staticmethod
    def convert_enhanced_to_legacy(enhanced_event: EnhancedCloudEvent) -> CloudEvent:
        """Enhanced CloudEvent를 레거시 CloudEvent로 변환"""
        return CloudEvent(
            specversion=enhanced_event.specversion,
            type=str(enhanced_event.type),
            source=enhanced_event.source,
            id=enhanced_event.id,
            time=enhanced_event.time,
            datacontenttype=enhanced_event.datacontenttype,
            dataschema=enhanced_event.dataschema,
            subject=enhanced_event.subject,
            data=enhanced_event.data or {}
        )
    
    @staticmethod
    def convert_change_to_cloudevent(
        change: Change, 
        metadata: EventMetadata,
        event_id: Optional[str] = None
    ) -> EnhancedCloudEvent:
        """Change 객체를 CloudEvent로 변환"""
        
        # 이벤트 타입 매핑
        operation_type_map = {
            ('create', 'object_type'): EventType.OBJECT_TYPE_CREATED,
            ('update', 'object_type'): EventType.OBJECT_TYPE_UPDATED,
            ('delete', 'object_type'): EventType.OBJECT_TYPE_DELETED,
            ('create', 'property'): EventType.PROPERTY_CREATED,
            ('update', 'property'): EventType.PROPERTY_UPDATED,
            ('delete', 'property'): EventType.PROPERTY_DELETED,
            ('create', 'link_type'): EventType.LINK_TYPE_CREATED,
            ('update', 'link_type'): EventType.LINK_TYPE_UPDATED,
            ('delete', 'link_type'): EventType.LINK_TYPE_DELETED,
        }
        
        event_type = operation_type_map.get(
            (change.operation, change.resource_type),
            EventType.SCHEMA_UPDATED
        )
        
        builder = CloudEventBuilder(event_type, f"/oms/{metadata.branch}")
        
        if event_id:
            builder.with_id(event_id)
        
        builder.with_subject(f"{change.resource_type}/{change.resource_id}")
        
        # 데이터 구성
        data = {
            "operation": change.operation,
            "resource_type": change.resource_type,
            "resource_id": change.resource_id
        }
        
        if change.old_value is not None:
            data["old_value"] = change.old_value
        if change.new_value is not None:
            data["new_value"] = change.new_value
        
        builder.with_data(data)
        builder.with_oms_context(
            branch=metadata.branch,
            commit=metadata.commit_id,
            author=metadata.author
        )
        
        return builder.build()
    
    @staticmethod
    def convert_outbox_to_cloudevent(outbox_event: OutboxEvent) -> EnhancedCloudEvent:
        """OutboxEvent를 CloudEvent로 변환"""
        import json
        
        # JSON payload 파싱
        try:
            payload_data = json.loads(outbox_event.payload)
        except json.JSONDecodeError:
            payload_data = {"raw_payload": outbox_event.payload}
        
        return CloudEventBuilder(outbox_event.type, "/oms/outbox") \
            .with_id(outbox_event.id) \
            .with_data(payload_data) \
            .build()
    
    @staticmethod
    def convert_cloudevent_to_outbox(
        cloud_event: EnhancedCloudEvent,
        status: str = "pending"
    ) -> OutboxEvent:
        """CloudEvent를 OutboxEvent로 변환"""
        import json
        
        return OutboxEvent(
            id=cloud_event.id,
            type=str(cloud_event.type),
            payload=json.dumps(cloud_event.data or {}),
            created_at=cloud_event.time,
            status=status
        )


class CloudEventsFactory:
    """CloudEvents 팩토리"""
    
    @staticmethod
    def create_schema_change_event(
        operation: str,
        resource_type: str,
        resource_id: str,
        branch: str,
        commit_id: str,
        author: str,
        old_value: Any = None,
        new_value: Any = None,
        correlation_id: Optional[str] = None
    ) -> EnhancedCloudEvent:
        """스키마 변경 이벤트 생성"""
        event = create_schema_event(
            operation=operation,
            resource_type=resource_type,
            resource_id=resource_id,
            branch=branch,
            commit=commit_id,
            author=author,
            old_value=old_value,
            new_value=new_value
        )
        
        if correlation_id:
            event.add_correlation_context(correlation_id)
        
        return event
    
    @staticmethod
    def create_branch_event(
        operation: str,  # created, updated, deleted, merged
        branch_name: str,
        author: str,
        target_branch: Optional[str] = None,  # merge의 경우
        metadata: Optional[Dict[str, Any]] = None
    ) -> EnhancedCloudEvent:
        """브랜치 이벤트 생성"""
        operation_type_map = {
            'created': EventType.BRANCH_CREATED,
            'updated': EventType.BRANCH_UPDATED,
            'deleted': EventType.BRANCH_DELETED,
            'merged': EventType.BRANCH_MERGED
        }
        
        event_type = operation_type_map.get(operation, EventType.BRANCH_UPDATED)
        
        data = {
            "operation": operation,
            "branch_name": branch_name,
            "author": author
        }
        
        if target_branch:
            data["target_branch"] = target_branch
        
        if metadata:
            data["metadata"] = metadata
        
        return CloudEventBuilder(event_type, f"/oms/branches") \
            .with_subject(branch_name) \
            .with_data(data) \
            .build()
    
    @staticmethod
    def create_proposal_event(
        operation: str,  # created, updated, approved, rejected, merged
        proposal_id: str,
        branch: str,
        author: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        reviewers: Optional[List[str]] = None
    ) -> EnhancedCloudEvent:
        """제안 이벤트 생성"""
        operation_type_map = {
            'created': EventType.PROPOSAL_CREATED,
            'updated': EventType.PROPOSAL_UPDATED,
            'approved': EventType.PROPOSAL_APPROVED,
            'rejected': EventType.PROPOSAL_REJECTED,
            'merged': EventType.PROPOSAL_MERGED
        }
        
        event_type = operation_type_map.get(operation, EventType.PROPOSAL_UPDATED)
        
        data = {
            "operation": operation,
            "proposal_id": proposal_id,
            "branch": branch,
            "author": author
        }
        
        if title:
            data["title"] = title
        if description:
            data["description"] = description
        if reviewers:
            data["reviewers"] = reviewers
        
        return CloudEventBuilder(event_type, f"/oms/proposals") \
            .with_subject(proposal_id) \
            .with_data(data) \
            .build()
    
    @staticmethod
    def create_action_progress_event(
        job_id: str,
        action_type: str,
        status: str,  # started, progress, completed, failed, cancelled
        progress: Optional[float] = None,
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> EnhancedCloudEvent:
        """액션 진행 이벤트 생성"""
        return create_action_event(
            action_type=action_type,
            job_id=job_id,
            status=status,
            result=result,
            error=error_message
        )
    
    @staticmethod
    def create_system_event(
        event_subtype: str,  # healthcheck, error, maintenance
        component: str,
        status: str,
        details: Optional[Dict[str, Any]] = None
    ) -> EnhancedCloudEvent:
        """시스템 이벤트 생성"""
        type_map = {
            'healthcheck': EventType.SYSTEM_HEALTH_CHECK,
            'error': EventType.SYSTEM_ERROR,
            'maintenance': EventType.SYSTEM_MAINTENANCE
        }
        
        event_type = type_map.get(event_subtype, EventType.SYSTEM_ERROR)
        
        data = {
            "component": component,
            "status": status
        }
        
        if details:
            data["details"] = details
        
        return CloudEventBuilder(event_type, f"/oms/system") \
            .with_subject(component) \
            .with_data(data) \
            .build()


class CloudEventsValidator:
    """CloudEvents 검증 및 변환 유틸리티"""
    
    @staticmethod
    def validate_and_convert(event_data: Dict[str, Any]) -> EnhancedCloudEvent:
        """이벤트 데이터 검증 후 CloudEvent로 변환"""
        # 기본 CloudEvent 생성
        cloud_event = EnhancedCloudEvent(**event_data)
        
        # 유효성 검증
        errors = CloudEventValidator.validate_cloudevent(cloud_event)
        if errors:
            raise ValueError(f"Invalid CloudEvent: {', '.join(errors)}")
        
        return cloud_event
    
    @staticmethod
    def normalize_event_type(event_type: str) -> str:
        """이벤트 타입 정규화"""
        # 기존 형식을 새로운 형식으로 변환
        type_mapping = {
            "schema.changed": EventType.SCHEMA_UPDATED.value,
            "object_type.created": EventType.OBJECT_TYPE_CREATED.value,
            "object_type.updated": EventType.OBJECT_TYPE_UPDATED.value,
            "object_type.deleted": EventType.OBJECT_TYPE_DELETED.value,
            "property.created": EventType.PROPERTY_CREATED.value,
            "property.updated": EventType.PROPERTY_UPDATED.value,
            "property.deleted": EventType.PROPERTY_DELETED.value,
            "link_type.created": EventType.LINK_TYPE_CREATED.value,
            "link_type.updated": EventType.LINK_TYPE_UPDATED.value,
            "link_type.deleted": EventType.LINK_TYPE_DELETED.value,
            "branch.created": EventType.BRANCH_CREATED.value,
            "branch.updated": EventType.BRANCH_UPDATED.value,
            "branch.deleted": EventType.BRANCH_DELETED.value,
            "proposal.created": EventType.PROPOSAL_CREATED.value,
            "proposal.updated": EventType.PROPOSAL_UPDATED.value,
            "action.started": EventType.ACTION_STARTED.value,
            "action.completed": EventType.ACTION_COMPLETED.value,
            "action.failed": EventType.ACTION_FAILED.value
        }
        
        return type_mapping.get(event_type, event_type)
    
    @staticmethod
    def batch_validate_events(events: List[Dict[str, Any]]) -> List[EnhancedCloudEvent]:
        """여러 이벤트를 배치로 검증"""
        validated_events = []
        
        for i, event_data in enumerate(events):
            try:
                validated_event = CloudEventsValidator.validate_and_convert(event_data)
                validated_events.append(validated_event)
            except ValueError as e:
                raise ValueError(f"Event {i} validation failed: {e}")
        
        return validated_events


# 편의 함수들
def convert_legacy_event(legacy_event: Dict[str, Any]) -> EnhancedCloudEvent:
    """레거시 이벤트를 CloudEvent로 변환하는 편의 함수"""
    return EnhancedCloudEvent.from_legacy_event(legacy_event)


def create_standard_headers(event: EnhancedCloudEvent) -> Dict[str, str]:
    """표준 HTTP 헤더 생성"""
    headers = event.to_binary_headers()
    
    # 추가 표준 헤더
    headers['User-Agent'] = 'OMS-EventPublisher/1.0'
    headers['X-Event-Version'] = '1.0'
    headers['X-OMS-Version'] = '2024.1'
    
    return headers