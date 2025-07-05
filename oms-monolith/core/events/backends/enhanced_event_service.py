"""
Enhanced Event Service
CloudEvents 1.0 표준을 기반으로 한 향상된 이벤트 서비스
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from .cloudevents_enhanced import (
    EnhancedCloudEvent, EventType, CloudEventBuilder, 
    CloudEventValidator, create_schema_event, create_action_event
)
from .cloudevents_adapter import CloudEventsAdapter, CloudEventsFactory
from .cloudevents_migration import BackwardCompatibilityLayer
from .models import Change, EventMetadata, OutboxEvent

logger = logging.getLogger(__name__)


class EnhancedEventService:
    """Enhanced CloudEvents 기반 이벤트 서비스"""
    
    def __init__(self, outbox_repository=None):
        """
        초기화
        
        Args:
            outbox_repository: OutboxEvent 저장소 (의존성 주입)
        """
        self.outbox_repository = outbox_repository
        self.compatibility_layer = BackwardCompatibilityLayer()
        self._initialized = False
        
    async def initialize(self) -> bool:
        """서비스 비동기 초기화.
        - Outbox 저장소가 제공되면 해당 저장소도 초기화합니다.
        - 여러 번 호출되어도 한 번만 실행되도록 가드합니다.
        """
        if self._initialized:
            return True
        try:
            if self.outbox_repository and hasattr(self.outbox_repository, "initialize") and callable(getattr(self.outbox_repository, "initialize")):
                await self.outbox_repository.initialize()
            self._initialized = True
            logger.info("EnhancedEventService initialized")
            return True
        except Exception as e:
            logger.error(f"EnhancedEventService initialization failed: {e}")
            return False

    async def close(self):
        """리소스 정리용 메서드 (Provider shutdown 훅과 호환).
        Outbox 저장소에 close 메서드가 있으면 해당 메서드도 호출합니다.
        """
        try:
            if self.outbox_repository and hasattr(self.outbox_repository, "close") and callable(getattr(self.outbox_repository, "close")):
                await self.outbox_repository.close()
            logger.info("EnhancedEventService closed")
        except Exception as e:
            logger.warning(f"Error while closing EnhancedEventService: {e}")

    def create_schema_change_event(
        self,
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
        """
        스키마 변경 이벤트 생성
        
        Args:
            operation: create, update, delete
            resource_type: object_type, property, link_type 등
            resource_id: 리소스 ID
            branch: Git 브랜치
            commit_id: 커밋 ID
            author: 작성자
            old_value: 이전 값 (update/delete의 경우)
            new_value: 새 값 (create/update의 경우)
            correlation_id: 연관 이벤트 ID
            
        Returns:
            EnhancedCloudEvent 인스턴스
        """
        event = CloudEventsFactory.create_schema_change_event(
            operation=operation,
            resource_type=resource_type,
            resource_id=resource_id,
            branch=branch,
            commit_id=commit_id,
            author=author,
            old_value=old_value,
            new_value=new_value,
            correlation_id=correlation_id
        )
        
        # 유효성 검증
        validation_errors = CloudEventValidator.validate_cloudevent(event)
        if validation_errors:
            logger.warning(f"CloudEvent validation warnings: {validation_errors}")
        
        return event
    
    def create_branch_event(
        self,
        operation: str,
        branch_name: str,
        author: str,
        target_branch: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> EnhancedCloudEvent:
        """브랜치 이벤트 생성"""
        return CloudEventsFactory.create_branch_event(
            operation=operation,
            branch_name=branch_name,
            author=author,
            target_branch=target_branch,
            metadata=metadata
        )
    
    def create_proposal_event(
        self,
        operation: str,
        proposal_id: str,
        branch: str,
        author: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        reviewers: Optional[List[str]] = None
    ) -> EnhancedCloudEvent:
        """제안 이벤트 생성"""
        return CloudEventsFactory.create_proposal_event(
            operation=operation,
            proposal_id=proposal_id,
            branch=branch,
            author=author,
            title=title,
            description=description,
            reviewers=reviewers
        )
    
    def create_action_event(
        self,
        action_type: str,
        job_id: str,
        status: str,
        progress: Optional[float] = None,
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> EnhancedCloudEvent:
        """액션 이벤트 생성"""
        return CloudEventsFactory.create_action_progress_event(
            job_id=job_id,
            action_type=action_type,
            status=status,
            progress=progress,
            result=result,
            error_message=error_message
        )
    
    def create_system_event(
        self,
        event_subtype: str,
        component: str,
        status: str,
        details: Optional[Dict[str, Any]] = None
    ) -> EnhancedCloudEvent:
        """시스템 이벤트 생성"""
        return CloudEventsFactory.create_system_event(
            event_subtype=event_subtype,
            component=component,
            status=status,
            details=details
        )
    
    async def publish_event(
        self,
        event: EnhancedCloudEvent,
        immediate: bool = False
    ) -> str:
        """
        이벤트 발행
        
        Args:
            event: 발행할 CloudEvent
            immediate: 즉시 발행 여부 (True면 직접 발행, False면 Outbox에 저장)
            
        Returns:
            이벤트 ID
        """
        if immediate:
            # 직접 발행 (실시간)
            return await self._publish_immediate(event)
        else:
            # Outbox 패턴으로 발행 (트랜잭션 보장)
            return await self._publish_via_outbox(event)
    
    async def _publish_immediate(self, event: EnhancedCloudEvent) -> str:
        """즉시 발행 (실시간)"""
        # 실제 구현에서는 NATS client 등을 사용
        logger.info(f"Publishing event immediately: {event.id}")
        # TODO: NATS publisher 연동
        return event.id
    
    async def _publish_via_outbox(self, event: EnhancedCloudEvent) -> str:
        """Outbox 패턴으로 발행"""
        if not self.outbox_repository:
            raise ValueError("Outbox repository not configured")
        
        # CloudEvent를 OutboxEvent로 변환
        outbox_event = self.compatibility_layer.create_legacy_outbox_event(event)
        
        # Outbox에 저장
        await self.outbox_repository.save(outbox_event)
        
        logger.debug(f"Event {event.id} stored in outbox")
        return event.id
    
    def convert_change_to_event(
        self,
        change: Change,
        metadata: EventMetadata,
        correlation_id: Optional[str] = None
    ) -> EnhancedCloudEvent:
        """Change 객체를 CloudEvent로 변환"""
        event = CloudEventsAdapter.convert_change_to_cloudevent(
            change=change,
            metadata=metadata
        )
        
        if correlation_id:
            event.add_correlation_context(correlation_id)
        
        return event
    
    def convert_legacy_event(self, legacy_event: Dict[str, Any]) -> EnhancedCloudEvent:
        """레거시 이벤트를 Enhanced CloudEvent로 변환"""
        return EnhancedCloudEvent.from_legacy_event(legacy_event)
    
    def create_event_batch(
        self,
        events_data: List[Dict[str, Any]]
    ) -> List[EnhancedCloudEvent]:
        """배치로 이벤트 생성"""
        events = []
        
        for event_data in events_data:
            try:
                event_type = event_data.get('event_type', 'schema_change')
                
                if event_type == 'schema_change':
                    event = self.create_schema_change_event(**event_data)
                elif event_type == 'branch':
                    event = self.create_branch_event(**event_data)
                elif event_type == 'proposal':
                    event = self.create_proposal_event(**event_data)
                elif event_type == 'action':
                    event = self.create_action_event(**event_data)
                elif event_type == 'system':
                    event = self.create_system_event(**event_data)
                else:
                    # 일반 이벤트 생성
                    event = CloudEventBuilder(
                        event_data.get('type', EventType.SCHEMA_UPDATED),
                        event_data.get('source', '/oms')
                    ).with_data(event_data.get('data', {})).build()
                
                events.append(event)
                
            except Exception as e:
                logger.error(f"Failed to create event from data {event_data}: {e}")
                continue
        
        return events
    
    async def publish_event_batch(
        self,
        events: List[EnhancedCloudEvent],
        immediate: bool = False
    ) -> List[str]:
        """배치로 이벤트 발행"""
        published_ids = []
        
        for event in events:
            try:
                event_id = await self.publish_event(event, immediate=immediate)
                published_ids.append(event_id)
            except Exception as e:
                logger.error(f"Failed to publish event {event.id}: {e}")
                continue
        
        return published_ids
    
    def get_event_statistics(self) -> Dict[str, Any]:
        """이벤트 통계 정보 반환"""
        # 실제 구현에서는 메트릭 서비스나 DB에서 조회
        return {
            "supported_event_types": [et.value for et in EventType],
            "cloudevents_version": "1.0",
            "enhanced_features": [
                "correlation_tracking",
                "causation_tracking",
                "distributed_tracing",
                "oms_domain_context",
                "backward_compatibility"
            ]
        }


# 편의 함수들
def create_quick_schema_event(
    operation: str,
    resource_type: str,
    resource_id: str,
    branch: str = "main",
    author: str = "system"
) -> EnhancedCloudEvent:
    """빠른 스키마 이벤트 생성"""
    service = EnhancedEventService()
    return service.create_schema_change_event(
        operation=operation,
        resource_type=resource_type,
        resource_id=resource_id,
        branch=branch,
        commit_id="unknown",
        author=author
    )


def create_quick_action_event(
    action_type: str,
    job_id: str,
    status: str
) -> EnhancedCloudEvent:
    """빠른 액션 이벤트 생성"""
    service = EnhancedEventService()
    return service.create_action_event(
        action_type=action_type,
        job_id=job_id,
        status=status
    )