"""
EventBridge CloudEvents Adapter
CloudEvents와 AWS EventBridge 간의 양방향 변환
"""
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Union
from urllib.parse import urlparse

from .cloudevents_enhanced import EnhancedCloudEvent, EventType, CloudEventBuilder
from .models import OutboxEvent

logger = logging.getLogger(__name__)


class EventBridgeAdapter:
    """CloudEvents와 EventBridge 간 변환 어댑터"""
    
    @staticmethod
    def cloudevent_to_eventbridge(
        event: EnhancedCloudEvent,
        event_bus_name: str = "default",
        source_prefix: str = "oms"
    ) -> Dict[str, Any]:
        """
        CloudEvent를 EventBridge Entry로 변환
        
        Args:
            event: 변환할 CloudEvent
            event_bus_name: EventBridge 버스 이름
            source_prefix: EventBridge Source 접두사
            
        Returns:
            EventBridge PutEvents Entry 딕셔너리
        """
        
        # Source 생성 (DNS 역순 형식)
        source = EventBridgeAdapter._generate_eventbridge_source(event.source, source_prefix)
        
        # DetailType 생성 (사람이 읽기 쉬운 형식)
        detail_type = EventBridgeAdapter._generate_detail_type(event.type)
        
        # Detail 구성
        detail = {
            # CloudEvents 표준 필드
            'cloudEvents': {
                'specversion': event.specversion,
                'type': str(event.type),
                'source': event.source,
                'id': event.id,
                'time': event.time.isoformat() if event.time else None,
                'datacontenttype': event.datacontenttype,
                'subject': event.subject,
                'data': event.data or {}
            }
        }
        
        # OMS 확장 속성 추가
        oms_extensions = {}
        for field, value in event.model_dump(exclude_none=True).items():
            if field.startswith('ce_') and value is not None:
                oms_extensions[field[3:]] = value  # ce_ 접두사 제거
        
        if oms_extensions:
            detail['omsExtensions'] = oms_extensions
        
        # EventBridge 메타데이터
        detail['eventBridgeMetadata'] = {
            'convertedAt': datetime.now(timezone.utc).isoformat(),
            'converter': 'oms-cloudevents-adapter',
            'version': '1.0'
        }
        
        # EventBridge Entry 구성
        entry = {
            'Source': source,
            'DetailType': detail_type,
            'Detail': json.dumps(detail, default=str),
            'EventBusName': event_bus_name
        }
        
        # 선택적 필드들
        if event.time:
            entry['Time'] = event.time
            
        if event.subject:
            # Subject를 Resource ARN으로 변환
            entry['Resources'] = [EventBridgeAdapter._subject_to_arn(event.subject)]
        
        logger.debug(f"Converted CloudEvent {event.id} to EventBridge entry")
        return entry
    
    @staticmethod
    def eventbridge_to_cloudevent(
        event_bridge_event: Dict[str, Any],
        default_source: str = "/aws/eventbridge"
    ) -> Optional[EnhancedCloudEvent]:
        """
        EventBridge 이벤트를 CloudEvent로 변환
        
        Args:
            event_bridge_event: EventBridge 이벤트 딕셔너리
            default_source: 기본 CloudEvent source
            
        Returns:
            변환된 CloudEvent 또는 None (변환 실패시)
        """
        try:
            detail = event_bridge_event.get('detail', {})
            
            # CloudEvents 데이터가 있는지 확인
            if 'cloudEvents' in detail:
                # OMS에서 발행한 이벤트 (원본 CloudEvent 복원)
                ce_data = detail['cloudEvents']
                
                builder = CloudEventBuilder(
                    ce_data.get('type', 'unknown'),
                    ce_data.get('source', default_source)
                )
                
                if 'id' in ce_data:
                    builder.with_id(ce_data['id'])
                if 'subject' in ce_data and ce_data['subject']:
                    builder.with_subject(ce_data['subject'])
                if 'data' in ce_data:
                    builder.with_data(ce_data['data'])
                    
                # OMS 확장 속성 복원
                if 'omsExtensions' in detail:
                    for key, value in detail['omsExtensions'].items():
                        setattr(builder._event, f'ce_{key}', value)
                
                return builder.build()
                
            else:
                # 외부 EventBridge 이벤트를 CloudEvent로 변환
                event_type = EventBridgeAdapter._eventbridge_to_cloudevent_type(
                    event_bridge_event.get('detail-type', 'unknown'),
                    event_bridge_event.get('source', 'unknown')
                )
                
                source = EventBridgeAdapter._eventbridge_source_to_cloudevent_source(
                    event_bridge_event.get('source', 'unknown')
                )
                
                builder = CloudEventBuilder(event_type, source)
                
                # EventBridge 필드들을 CloudEvent로 매핑
                if 'time' in event_bridge_event:
                    # EventBridge time은 이미 datetime 객체
                    time_val = event_bridge_event['time']
                    if isinstance(time_val, str):
                        time_val = datetime.fromisoformat(time_val.replace('Z', '+00:00'))
                    builder._event.time = time_val
                
                # Detail을 data로 사용
                builder.with_data(detail)
                
                # Resources를 subject로 변환
                resources = event_bridge_event.get('resources', [])
                if resources:
                    builder.with_subject(resources[0])  # 첫 번째 리소스를 subject로
                
                return builder.build()
                
        except Exception as e:
            logger.error(f"Failed to convert EventBridge event to CloudEvent: {e}")
            return None
    
    @staticmethod
    def _generate_eventbridge_source(cloudevent_source: str, prefix: str = "oms") -> str:
        """CloudEvent source를 EventBridge source로 변환"""
        parsed = urlparse(cloudevent_source)
        
        if parsed.netloc:
            # URL 형식: https://oms.company.com/main -> oms.company.com
            return f"{prefix}.{parsed.netloc}"
        else:
            # 경로 형식: /oms/main -> oms.main
            path_parts = [p for p in parsed.path.split('/') if p and p != prefix]
            if path_parts:
                return f"{prefix}.{'.'.join(path_parts)}"
            return prefix
    
    @staticmethod
    def _generate_detail_type(cloudevent_type: Union[str, EventType]) -> str:
        """CloudEvent type을 EventBridge DetailType으로 변환"""
        type_str = str(cloudevent_type)
        
        # 도메인 네임스페이스 제거 및 사람이 읽기 쉬운 형식으로 변환
        # com.foundry.oms.objecttype.created -> ObjectType Created
        parts = type_str.split('.')
        
        if len(parts) >= 2:
            resource = parts[-2].replace('_', ' ').title()
            action = parts[-1].title()
            return f"{resource} {action}"
        else:
            return type_str.replace('.', ' ').replace('_', ' ').title()
    
    @staticmethod
    def _subject_to_arn(subject: str) -> str:
        """CloudEvent subject를 AWS ARN으로 변환"""
        # 간단한 변환: object_type/User -> arn:aws:oms::object_type/User
        return f"arn:aws:oms::{subject}"
    
    @staticmethod
    def _eventbridge_to_cloudevent_type(detail_type: str, source: str) -> str:
        """EventBridge DetailType과 Source를 CloudEvent type으로 변환"""
        # DetailType: "ObjectType Created" -> type: "com.foundry.oms.objecttype.created"
        
        # 기본 네임스페이스
        namespace = "com.foundry.oms"
        
        # DetailType 파싱
        parts = detail_type.lower().split()
        if len(parts) >= 2:
            resource = parts[0].replace(' ', '_')
            action = parts[-1]
            return f"{namespace}.{resource}.{action}"
        else:
            return f"{namespace}.{detail_type.lower().replace(' ', '_')}"
    
    @staticmethod
    def _eventbridge_source_to_cloudevent_source(eventbridge_source: str) -> str:
        """EventBridge source를 CloudEvent source로 변환"""
        # oms.company.com -> /oms/company/com 또는 적절한 URL
        if '.' in eventbridge_source:
            parts = eventbridge_source.split('.')
            return f"/{'/'.join(parts)}"
        return f"/aws/{eventbridge_source}"


class EventBridgeOutboxAdapter:
    """EventBridge와 Outbox 패턴 통합"""
    
    @staticmethod
    def cloudevent_to_outbox_for_eventbridge(
        event: EnhancedCloudEvent,
        event_bus_name: str = "default"
    ) -> OutboxEvent:
        """
        CloudEvent를 EventBridge용 OutboxEvent로 변환
        
        Args:
            event: 변환할 CloudEvent
            event_bus_name: EventBridge 버스 이름
            
        Returns:
            EventBridge 발행용 OutboxEvent
        """
        
        # EventBridge Entry 생성
        eventbridge_entry = EventBridgeAdapter.cloudevent_to_eventbridge(
            event, event_bus_name
        )
        
        # OutboxEvent 생성
        outbox_event = OutboxEvent(
            id=event.id,
            type=f"eventbridge.{eventbridge_entry['Source']}.{eventbridge_entry['DetailType'].replace(' ', '_').lower()}",
            payload=json.dumps(eventbridge_entry, default=str),
            created_at=event.time or datetime.now(timezone.utc),
            status="pending"
        )
        
        return outbox_event
    
    @staticmethod
    def extract_cloudevent_from_outbox(outbox_event: OutboxEvent) -> Optional[EnhancedCloudEvent]:
        """
        EventBridge용 OutboxEvent에서 원본 CloudEvent 추출
        
        Args:
            outbox_event: EventBridge용 OutboxEvent
            
        Returns:
            추출된 CloudEvent 또는 None
        """
        try:
            # Payload에서 EventBridge Entry 파싱
            entry_data = json.loads(outbox_event.payload)
            detail_data = json.loads(entry_data['Detail'])
            
            # CloudEvents 데이터가 있으면 복원
            if 'cloudEvents' in detail_data:
                ce_data = detail_data['cloudEvents']
                
                builder = CloudEventBuilder(
                    ce_data.get('type', 'unknown'),
                    ce_data.get('source', '/oms/unknown')
                )
                
                if 'id' in ce_data:
                    builder.with_id(ce_data['id'])
                if 'subject' in ce_data and ce_data['subject']:
                    builder.with_subject(ce_data['subject'])
                if 'data' in ce_data:
                    builder.with_data(ce_data['data'])
                
                # 시간 설정
                if 'time' in ce_data and ce_data['time']:
                    time_val = datetime.fromisoformat(ce_data['time'].replace('Z', '+00:00'))
                    builder._event.time = time_val
                
                # OMS 확장 속성 복원
                if 'omsExtensions' in detail_data:
                    for key, value in detail_data['omsExtensions'].items():
                        setattr(builder._event, f'ce_{key}', value)
                
                return builder.build()
            
        except Exception as e:
            logger.error(f"Failed to extract CloudEvent from EventBridge outbox: {e}")
        
        return None


class EventBridgeRuleGenerator:
    """EventBridge Rule 자동 생성"""
    
    @staticmethod
    def generate_rule_for_event_type(
        event_type: Union[str, EventType],
        rule_name: Optional[str] = None,
        description: Optional[str] = None,
        target_arn: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        특정 이벤트 타입에 대한 EventBridge Rule 생성
        
        Args:
            event_type: CloudEvent 타입
            rule_name: Rule 이름 (자동 생성 가능)
            description: Rule 설명
            target_arn: 타겟 ARN (Lambda, SQS 등)
            
        Returns:
            EventBridge Rule 정의 딕셔너리
        """
        type_str = str(event_type)
        
        if not rule_name:
            # 자동 Rule 이름 생성
            clean_type = type_str.replace('.', '_').replace('-', '_')
            rule_name = f"oms_{clean_type}_rule"
        
        if not description:
            description = f"Route events of type {type_str}"
        
        # EventPattern 생성
        detail_type = EventBridgeAdapter._generate_detail_type(event_type)
        
        event_pattern = {
            "source": ["oms"],  # OMS에서 발생한 이벤트만
            "detail-type": [detail_type],
            "detail": {
                "cloudEvents": {
                    "type": [type_str]
                }
            }
        }
        
        rule_definition = {
            "Name": rule_name,
            "Description": description,
            "EventPattern": json.dumps(event_pattern),
            "State": "ENABLED"
        }
        
        if target_arn:
            rule_definition["Targets"] = [
                {
                    "Id": "1",
                    "Arn": target_arn
                }
            ]
        
        return rule_definition
    
    @staticmethod
    def generate_rules_for_oms_events() -> List[Dict[str, Any]]:
        """OMS의 모든 이벤트 타입에 대한 Rule 생성"""
        rules = []
        
        for event_type in EventType:
            rule = EventBridgeRuleGenerator.generate_rule_for_event_type(event_type)
            rules.append(rule)
        
        return rules


# 편의 함수들
def convert_cloudevent_to_eventbridge(
    event: EnhancedCloudEvent,
    event_bus_name: str = "oms-events"
) -> Dict[str, Any]:
    """CloudEvent를 EventBridge Entry로 변환하는 편의 함수"""
    return EventBridgeAdapter.cloudevent_to_eventbridge(event, event_bus_name)


def convert_eventbridge_to_cloudevent(
    eventbridge_event: Dict[str, Any]
) -> Optional[EnhancedCloudEvent]:
    """EventBridge 이벤트를 CloudEvent로 변환하는 편의 함수"""
    return EventBridgeAdapter.eventbridge_to_cloudevent(eventbridge_event)