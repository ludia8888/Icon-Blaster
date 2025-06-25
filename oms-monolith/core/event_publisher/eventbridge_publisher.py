"""
AWS EventBridge CloudEvents Publisher
AWS EventBridge와 CloudEvents 1.0 표준 연동
"""
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError, BotoCoreError

from .cloudevents_enhanced import EnhancedCloudEvent, CloudEventValidator
from .models import PublishResult

logger = logging.getLogger(__name__)


class EventBridgeConfig:
    """EventBridge 설정"""
    
    def __init__(
        self,
        event_bus_name: str = "default",
        aws_region: str = "us-east-1",
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_session_token: Optional[str] = None,
        endpoint_url: Optional[str] = None,  # LocalStack 등 테스트용
        max_entries_per_batch: int = 10,     # EventBridge 제한
        enable_dlq: bool = True,
        source_prefix: str = "oms"
    ):
        self.event_bus_name = event_bus_name
        self.aws_region = aws_region
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.aws_session_token = aws_session_token
        self.endpoint_url = endpoint_url
        self.max_entries_per_batch = max_entries_per_batch
        self.enable_dlq = enable_dlq
        self.source_prefix = source_prefix


class EventBridgeCloudEventsPublisher:
    """AWS EventBridge용 CloudEvents 발행자"""
    
    def __init__(self, config: EventBridgeConfig):
        self.config = config
        self._client = None
        self._init_client()
        
    def _init_client(self):
        """EventBridge 클라이언트 초기화"""
        try:
            session_kwargs = {
                'region_name': self.config.aws_region
            }
            
            if self.config.aws_access_key_id:
                session_kwargs['aws_access_key_id'] = self.config.aws_access_key_id
            if self.config.aws_secret_access_key:
                session_kwargs['aws_secret_access_key'] = self.config.aws_secret_access_key
            if self.config.aws_session_token:
                session_kwargs['aws_session_token'] = self.config.aws_session_token
                
            session = boto3.Session(**session_kwargs)
            
            client_kwargs = {}
            if self.config.endpoint_url:
                client_kwargs['endpoint_url'] = self.config.endpoint_url
                
            self._client = session.client('events', **client_kwargs)
            
            # 연결 테스트
            self._client.describe_event_bus(Name=self.config.event_bus_name)
            logger.info(f"Successfully initialized EventBridge client for bus: {self.config.event_bus_name}")
            
        except Exception as e:
            logger.error(f"Failed to initialize EventBridge client: {e}")
            raise
    
    async def publish_event(self, event: EnhancedCloudEvent) -> PublishResult:
        """단일 CloudEvent를 EventBridge로 발행"""
        return await self.publish_events([event])
    
    async def publish_events(self, events: List[EnhancedCloudEvent]) -> List[PublishResult]:
        """배치로 CloudEvent들을 EventBridge로 발행"""
        if not events:
            return []
        
        # CloudEvent 유효성 검증
        validated_events = []
        results = []
        
        for event in events:
            validation_errors = CloudEventValidator.validate_cloudevent(event)
            if validation_errors:
                logger.warning(f"CloudEvent validation failed for {event.id}: {validation_errors}")
                results.append(PublishResult(
                    event_id=event.id,
                    success=False,
                    subject=event.subject or "",
                    error=f"Validation failed: {', '.join(validation_errors)}"
                ))
            else:
                validated_events.append(event)
        
        if not validated_events:
            return results
        
        # EventBridge 배치 크기 제한에 따라 분할
        batch_size = self.config.max_entries_per_batch
        batches = [validated_events[i:i + batch_size] 
                  for i in range(0, len(validated_events), batch_size)]
        
        for batch in batches:
            batch_results = await self._publish_batch(batch)
            results.extend(batch_results)
        
        return results
    
    async def _publish_batch(self, events: List[EnhancedCloudEvent]) -> List[PublishResult]:
        """EventBridge 배치 발행"""
        start_time = datetime.utcnow()
        
        try:
            # CloudEvents를 EventBridge 엔트리로 변환
            entries = []
            for event in events:
                entry = self._convert_to_eventbridge_entry(event)
                entries.append(entry)
            
            # EventBridge에 발행
            response = self._client.put_events(Entries=entries)
            
            # 결과 처리
            results = []
            failed_count = response.get('FailedEntryCount', 0)
            
            for i, event in enumerate(events):
                entry_response = response['Entries'][i] if i < len(response.get('Entries', [])) else {}
                
                if 'EventId' in entry_response:
                    # 성공
                    latency = (datetime.utcnow() - start_time).total_seconds() * 1000
                    results.append(PublishResult(
                        event_id=event.id,
                        success=True,
                        subject=self._get_eventbridge_source(event),
                        latency_ms=latency
                    ))
                    logger.debug(f"Successfully published CloudEvent {event.id} to EventBridge")
                else:
                    # 실패
                    error_code = entry_response.get('ErrorCode', 'Unknown')
                    error_message = entry_response.get('ErrorMessage', 'Unknown error')
                    results.append(PublishResult(
                        event_id=event.id,
                        success=False,
                        subject=self._get_eventbridge_source(event),
                        error=f"{error_code}: {error_message}"
                    ))
                    logger.error(f"Failed to publish CloudEvent {event.id}: {error_code} - {error_message}")
            
            if failed_count > 0:
                logger.warning(f"EventBridge batch had {failed_count} failed entries out of {len(events)}")
            
            return results
            
        except (ClientError, BotoCoreError) as e:
            logger.error(f"AWS EventBridge API error: {e}")
            # 모든 이벤트를 실패로 처리
            return [
                PublishResult(
                    event_id=event.id,
                    success=False,
                    subject=self._get_eventbridge_source(event),
                    error=f"AWS API Error: {str(e)}"
                )
                for event in events
            ]
        except Exception as e:
            logger.error(f"Unexpected error in EventBridge publishing: {e}")
            return [
                PublishResult(
                    event_id=event.id,
                    success=False,
                    subject=self._get_eventbridge_source(event),
                    error=f"Unexpected error: {str(e)}"
                )
                for event in events
            ]
    
    def _convert_to_eventbridge_entry(self, event: EnhancedCloudEvent) -> Dict[str, Any]:
        """CloudEvent를 EventBridge Entry로 변환"""
        
        # EventBridge Source 생성 (DNS 역순 형식 권장)
        source = self._get_eventbridge_source(event)
        
        # EventBridge DetailType (사람이 읽기 쉬운 형식)
        detail_type = self._get_eventbridge_detail_type(event)
        
        # Detail (CloudEvent 전체를 포함)
        detail = self._create_eventbridge_detail(event)
        
        # EventBridge Entry 구성
        entry = {
            'Source': source,
            'DetailType': detail_type,
            'Detail': json.dumps(detail),
            'EventBusName': self.config.event_bus_name,
        }
        
        # 선택적 필드들
        if event.time:
            entry['Time'] = event.time
        
        # Resources (subject가 있으면 리소스로 추가)
        if event.subject:
            entry['Resources'] = [f"arn:aws:oms::{event.subject}"]
        
        logger.debug(f"Converted CloudEvent {event.id} to EventBridge entry: {source}/{detail_type}")
        
        return entry
    
    def _get_eventbridge_source(self, event: EnhancedCloudEvent) -> str:
        """EventBridge Source 생성"""
        # CloudEvents source에서 도메인 추출
        parsed = urlparse(event.source)
        if parsed.netloc:
            # URL 형식인 경우: https://oms.company.com/main -> oms.company.com
            return f"{self.config.source_prefix}.{parsed.netloc}"
        else:
            # 경로 형식인 경우: /oms/main -> oms.main
            path_parts = [p for p in parsed.path.split('/') if p]
            if path_parts:
                return f"{self.config.source_prefix}.{'.'.join(path_parts)}"
            else:
                return self.config.source_prefix
    
    def _get_eventbridge_detail_type(self, event: EnhancedCloudEvent) -> str:
        """EventBridge DetailType 생성 (사람이 읽기 쉬운 형식)"""
        if isinstance(event.type, str):
            # com.foundry.oms.objecttype.created -> ObjectType Created
            parts = event.type.split('.')
            if len(parts) >= 2:
                resource = parts[-2].replace('_', ' ').title()
                action = parts[-1].title()
                return f"{resource} {action}"
            else:
                return event.type.replace('.', ' ').title()
        else:
            return str(event.type).replace('_', ' ').title()
    
    def _create_eventbridge_detail(self, event: EnhancedCloudEvent) -> Dict[str, Any]:
        """EventBridge Detail 생성 (CloudEvent + 추가 메타데이터)"""
        
        # CloudEvent 표준 필드들
        detail = {
            'cloudEvents': {
                'specversion': event.specversion,
                'type': str(event.type),
                'source': event.source,
                'id': event.id,
                'time': event.time.isoformat() if event.time else None,
                'datacontenttype': event.datacontenttype,
                'subject': event.subject,
                'data': event.data
            }
        }
        
        # OMS 확장 속성들
        oms_context = {}
        for field_name, value in event.model_dump(exclude_none=True).items():
            if field_name.startswith('ce_') and value is not None:
                context_key = field_name[3:]  # ce_ 제거
                oms_context[context_key] = value
        
        if oms_context:
            detail['omsContext'] = oms_context
        
        # EventBridge 메타데이터
        detail['eventBridge'] = {
            'publishedAt': datetime.utcnow().isoformat(),
            'eventBusName': self.config.event_bus_name,
            'publisher': 'oms-monolith',
            'version': '1.0'
        }
        
        return detail
    
    def get_health_status(self) -> Dict[str, Any]:
        """EventBridge 연결 상태 확인"""
        try:
            # EventBus 존재 확인
            response = self._client.describe_event_bus(Name=self.config.event_bus_name)
            
            return {
                'status': 'healthy',
                'event_bus_name': self.config.event_bus_name,
                'event_bus_arn': response.get('Arn'),
                'region': self.config.aws_region,
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'event_bus_name': self.config.event_bus_name,
                'region': self.config.aws_region,
                'timestamp': datetime.utcnow().isoformat()
            }


# 편의 함수
def create_eventbridge_publisher(
    event_bus_name: str = "oms-events",
    aws_region: str = "us-east-1",
    **kwargs
) -> EventBridgeCloudEventsPublisher:
    """EventBridge Publisher 생성 헬퍼 함수"""
    config = EventBridgeConfig(
        event_bus_name=event_bus_name,
        aws_region=aws_region,
        **kwargs
    )
    return EventBridgeCloudEventsPublisher(config)