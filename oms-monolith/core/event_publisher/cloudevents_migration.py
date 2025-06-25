"""
CloudEvents Migration Utilities
기존 이벤트 시스템을 Enhanced CloudEvents로 마이그레이션하는 유틸리티
"""
import json
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

from .cloudevents_enhanced import EnhancedCloudEvent, EventType
from .cloudevents_adapter import CloudEventsAdapter, CloudEventsFactory
from .models import OutboxEvent


class EventSchemaMigrator:
    """이벤트 스키마 마이그레이션 도구"""
    
    def __init__(self):
        self.migration_stats = {
            'total_events': 0,
            'migrated_successfully': 0,
            'migration_failures': 0,
            'unsupported_types': set(),
            'validation_errors': []
        }
    
    def migrate_legacy_events(self, legacy_events: List[Dict[str, Any]]) -> List[EnhancedCloudEvent]:
        """레거시 이벤트를 Enhanced CloudEvents로 마이그레이션"""
        migrated_events = []
        
        for event_data in legacy_events:
            try:
                migrated_event = self._migrate_single_event(event_data)
                if migrated_event:
                    migrated_events.append(migrated_event)
                    self.migration_stats['migrated_successfully'] += 1
                else:
                    self.migration_stats['migration_failures'] += 1
            except Exception as e:
                self.migration_stats['migration_failures'] += 1
                self.migration_stats['validation_errors'].append(f"Event migration failed: {e}")
            
            self.migration_stats['total_events'] += 1
        
        return migrated_events
    
    def _migrate_single_event(self, event_data: Dict[str, Any]) -> Optional[EnhancedCloudEvent]:
        """단일 이벤트 마이그레이션"""
        # 다양한 레거시 이벤트 형식 지원
        
        # 1. 기존 CloudEvent 형식
        if self._is_cloudevent_format(event_data):
            return self._migrate_cloudevent_format(event_data)
        
        # 2. 기존 OutboxEvent 형식
        elif self._is_outbox_format(event_data):
            return self._migrate_outbox_format(event_data)
        
        # 3. 기존 Custom Event 형식
        elif self._is_custom_format(event_data):
            return self._migrate_custom_format(event_data)
        
        # 4. NATS 메시지 형식
        elif self._is_nats_format(event_data):
            return self._migrate_nats_format(event_data)
        
        else:
            self.migration_stats['unsupported_types'].add(
                event_data.get('type', 'unknown')
            )
            return None
    
    def _is_cloudevent_format(self, event_data: Dict[str, Any]) -> bool:
        """CloudEvent 형식인지 확인"""
        required_fields = ['specversion', 'type', 'source', 'id']
        return all(field in event_data for field in required_fields)
    
    def _is_outbox_format(self, event_data: Dict[str, Any]) -> bool:
        """OutboxEvent 형식인지 확인"""
        required_fields = ['id', 'type', 'payload', 'created_at']
        return all(field in event_data for field in required_fields)
    
    def _is_custom_format(self, event_data: Dict[str, Any]) -> bool:
        """Custom Event 형식인지 확인"""
        return 'event_type' in event_data and 'data' in event_data
    
    def _is_nats_format(self, event_data: Dict[str, Any]) -> bool:
        """NATS 메시지 형식인지 확인"""
        return 'subject' in event_data and 'data' in event_data
    
    def _migrate_cloudevent_format(self, event_data: Dict[str, Any]) -> EnhancedCloudEvent:
        """CloudEvent 형식 마이그레이션"""
        # 타임스탬프 처리
        if 'time' in event_data and isinstance(event_data['time'], str):
            event_data['time'] = datetime.fromisoformat(
                event_data['time'].replace('Z', '+00:00')
            )
        
        # 이벤트 타입 정규화
        if 'type' in event_data:
            event_data['type'] = self._normalize_event_type(event_data['type'])
        
        return EnhancedCloudEvent(**event_data)
    
    def _migrate_outbox_format(self, event_data: Dict[str, Any]) -> EnhancedCloudEvent:
        """OutboxEvent 형식 마이그레이션"""
        # JSON payload 파싱
        payload_data = {}
        if 'payload' in event_data:
            try:
                payload_data = json.loads(event_data['payload'])
            except json.JSONDecodeError:
                payload_data = {'raw_payload': event_data['payload']}
        
        # CloudEvent 생성
        return EnhancedCloudEvent(
            type=self._normalize_event_type(event_data['type']),
            source='/oms/outbox',
            id=event_data['id'],
            time=self._parse_timestamp(event_data.get('created_at')),
            data=payload_data
        )
    
    def _migrate_custom_format(self, event_data: Dict[str, Any]) -> EnhancedCloudEvent:
        """Custom Event 형식 마이그레이션"""
        return EnhancedCloudEvent(
            type=self._normalize_event_type(event_data['event_type']),
            source=event_data.get('source', '/oms/legacy'),
            id=event_data.get('id', self._generate_id()),
            time=self._parse_timestamp(event_data.get('timestamp')),
            data=event_data.get('data', {})
        )
    
    def _migrate_nats_format(self, event_data: Dict[str, Any]) -> EnhancedCloudEvent:
        """NATS 메시지 형식 마이그레이션"""
        # Subject에서 이벤트 타입 추출
        subject = event_data['subject']
        event_type = self._extract_type_from_subject(subject)
        
        return EnhancedCloudEvent(
            type=event_type,
            source=f'/oms/nats/{subject}',
            id=event_data.get('id', self._generate_id()),
            time=self._parse_timestamp(event_data.get('timestamp')),
            data=event_data.get('data', {})
        )
    
    def _normalize_event_type(self, event_type: str) -> str:
        """이벤트 타입 정규화"""
        # 기존 타입을 새로운 타입으로 매핑
        type_mapping = {
            # Schema events
            'schema_changed': EventType.SCHEMA_UPDATED.value,
            'schema.changed': EventType.SCHEMA_UPDATED.value,
            'com.oms.schema.changed': EventType.SCHEMA_UPDATED.value,
            
            # ObjectType events
            'object_type_created': EventType.OBJECT_TYPE_CREATED.value,
            'object_type_updated': EventType.OBJECT_TYPE_UPDATED.value,
            'object_type_deleted': EventType.OBJECT_TYPE_DELETED.value,
            
            # Property events
            'property_created': EventType.PROPERTY_CREATED.value,
            'property_updated': EventType.PROPERTY_UPDATED.value,
            'property_deleted': EventType.PROPERTY_DELETED.value,
            
            # LinkType events
            'link_type_created': EventType.LINK_TYPE_CREATED.value,
            'link_type_updated': EventType.LINK_TYPE_UPDATED.value,
            'link_type_deleted': EventType.LINK_TYPE_DELETED.value,
            
            # Branch events
            'branch_created': EventType.BRANCH_CREATED.value,
            'branch_updated': EventType.BRANCH_UPDATED.value,
            'branch_deleted': EventType.BRANCH_DELETED.value,
            'branch_merged': EventType.BRANCH_MERGED.value,
            
            # Proposal events
            'proposal_created': EventType.PROPOSAL_CREATED.value,
            'proposal_updated': EventType.PROPOSAL_UPDATED.value,
            'proposal_approved': EventType.PROPOSAL_APPROVED.value,
            'proposal_rejected': EventType.PROPOSAL_REJECTED.value,
            'proposal_merged': EventType.PROPOSAL_MERGED.value,
            
            # Action events
            'action_started': EventType.ACTION_STARTED.value,
            'action_completed': EventType.ACTION_COMPLETED.value,
            'action_failed': EventType.ACTION_FAILED.value,
            'action_cancelled': EventType.ACTION_CANCELLED.value,
        }
        
        return type_mapping.get(event_type, event_type)
    
    def _extract_type_from_subject(self, subject: str) -> str:
        """NATS subject에서 이벤트 타입 추출"""
        # oms.schema.created.object_type.main -> schema.created
        parts = subject.split('.')
        if len(parts) >= 3 and parts[0] == 'oms':
            return f"{parts[1]}.{parts[2]}"
        return subject
    
    def _parse_timestamp(self, timestamp: Any) -> datetime:
        """타임스탬프 파싱"""
        if timestamp is None:
            return datetime.now(timezone.utc)
        
        if isinstance(timestamp, datetime):
            if timestamp.tzinfo is None:
                return timestamp.replace(tzinfo=timezone.utc)
            return timestamp
        
        if isinstance(timestamp, str):
            try:
                # ISO 형식 파싱
                return datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            except ValueError:
                # 다른 형식 시도
                try:
                    return datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    return datetime.now(timezone.utc)
        
        if isinstance(timestamp, (int, float)):
            return datetime.fromtimestamp(timestamp, timezone.utc)
        
        return datetime.now(timezone.utc)
    
    def _generate_id(self) -> str:
        """이벤트 ID 생성"""
        import uuid
        return str(uuid.uuid4())
    
    def get_migration_report(self) -> Dict[str, Any]:
        """마이그레이션 리포트 생성"""
        success_rate = 0
        if self.migration_stats['total_events'] > 0:
            success_rate = (
                self.migration_stats['migrated_successfully'] / 
                self.migration_stats['total_events'] * 100
            )
        
        return {
            'summary': {
                'total_events': self.migration_stats['total_events'],
                'migrated_successfully': self.migration_stats['migrated_successfully'],
                'migration_failures': self.migration_stats['migration_failures'],
                'success_rate_percent': round(success_rate, 2)
            },
            'issues': {
                'unsupported_event_types': list(self.migration_stats['unsupported_types']),
                'validation_errors': self.migration_stats['validation_errors']
            },
            'recommendations': self._generate_recommendations()
        }
    
    def _generate_recommendations(self) -> List[str]:
        """마이그레이션 권장사항 생성"""
        recommendations = []
        
        if self.migration_stats['unsupported_types']:
            recommendations.append(
                f"다음 이벤트 타입들에 대한 마이그레이션 규칙 추가 필요: "
                f"{', '.join(self.migration_stats['unsupported_types'])}"
            )
        
        if self.migration_stats['validation_errors']:
            recommendations.append(
                "검증 오류가 발생한 이벤트들에 대한 데이터 정제 필요"
            )
        
        success_rate = (
            self.migration_stats['migrated_successfully'] / 
            max(self.migration_stats['total_events'], 1) * 100
        )
        
        if success_rate < 95:
            recommendations.append(
                "마이그레이션 성공률이 95% 미만입니다. 추가적인 데이터 검토 권장"
            )
        
        return recommendations


class BackwardCompatibilityLayer:
    """하위 호환성 레이어"""
    
    @staticmethod
    def wrap_enhanced_as_legacy(enhanced_event: EnhancedCloudEvent) -> Dict[str, Any]:
        """Enhanced CloudEvent를 레거시 형식으로 래핑"""
        return {
            'specversion': enhanced_event.specversion,
            'type': str(enhanced_event.type),
            'source': enhanced_event.source,
            'id': enhanced_event.id,
            'time': enhanced_event.time,
            'datacontenttype': enhanced_event.datacontenttype,
            'data': enhanced_event.data,
            
            # 레거시 호환 필드
            'event_type': str(enhanced_event.type),
            'metadata': {
                'branch': enhanced_event.ce_branch,
                'commit_id': enhanced_event.ce_commit,
                'author': enhanced_event.ce_author,
                'timestamp': enhanced_event.time
            } if enhanced_event.ce_branch else None
        }
    
    @staticmethod
    def create_legacy_outbox_event(enhanced_event: EnhancedCloudEvent) -> OutboxEvent:
        """Enhanced CloudEvent를 레거시 OutboxEvent로 변환"""
        return CloudEventsAdapter.convert_cloudevent_to_outbox(enhanced_event)
    
    @staticmethod
    def extract_nats_subject(enhanced_event: EnhancedCloudEvent) -> str:
        """Enhanced CloudEvent에서 NATS subject 추출"""
        return enhanced_event.get_nats_subject()


# 마이그레이션 편의 함수들
def migrate_legacy_events_batch(legacy_events: List[Dict[str, Any]]) -> Tuple[List[EnhancedCloudEvent], Dict[str, Any]]:
    """레거시 이벤트 배치 마이그레이션"""
    migrator = EventSchemaMigrator()
    migrated_events = migrator.migrate_legacy_events(legacy_events)
    report = migrator.get_migration_report()
    
    return migrated_events, report


def create_migration_plan(event_types: List[str]) -> Dict[str, str]:
    """이벤트 타입별 마이그레이션 계획 생성"""
    migrator = EventSchemaMigrator()
    
    migration_plan = {}
    for event_type in event_types:
        normalized_type = migrator._normalize_event_type(event_type)
        if normalized_type != event_type:
            migration_plan[event_type] = normalized_type
    
    return migration_plan


def validate_migration_compatibility(source_events: List[Dict[str, Any]], 
                                   target_events: List[EnhancedCloudEvent]) -> Dict[str, Any]:
    """마이그레이션 호환성 검증"""
    compatibility_report = {
        'total_source_events': len(source_events),
        'total_target_events': len(target_events),
        'data_integrity_check': True,
        'issues': []
    }
    
    # 데이터 무결성 검사
    if len(source_events) != len(target_events):
        compatibility_report['data_integrity_check'] = False
        compatibility_report['issues'].append(
            f"Event count mismatch: {len(source_events)} -> {len(target_events)}"
        )
    
    # 필수 필드 검사
    for i, (source, target) in enumerate(zip(source_events, target_events)):
        if source.get('id') != target.id:
            compatibility_report['issues'].append(
                f"Event {i}: ID mismatch {source.get('id')} != {target.id}"
            )
    
    return compatibility_report