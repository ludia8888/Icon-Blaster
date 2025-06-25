"""
Secure Event Publisher with PII Protection
PII 보호 기능이 포함된 보안 이벤트 발행자
"""
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from .cloudevents_enhanced import EnhancedCloudEvent
from core.event_publisher import EventPublisher
from ..security.pii_handler import PIIHandler, PIIHandlingStrategy, PIIMatch
from shared.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SecurityConfig:
    """보안 설정"""
    pii_handling_strategy: PIIHandlingStrategy = PIIHandlingStrategy.ANONYMIZE
    enable_pii_detection: bool = True
    pii_detection_fields: List[str] = None
    encryption_key: Optional[bytes] = None
    audit_log_enabled: bool = True
    allowed_event_types: Optional[List[str]] = None
    blocked_event_types: Optional[List[str]] = None


class SecureEventPublisher:
    """보안 강화된 이벤트 발행자"""
    
    def __init__(
        self,
        publisher: EventPublisher,
        pii_handler: PIIHandler,
        security_config: Optional[SecurityConfig] = None
    ):
        """
        Args:
            publisher: 기본 이벤트 발행자
            pii_handler: PII 처리 핸들러
            security_config: 보안 설정
        """
        self.publisher = publisher
        self.pii_handler = pii_handler
        self.config = security_config or SecurityConfig()
        self._event_count = 0
        self._pii_detected_count = 0
        self._blocked_count = 0
    
    async def publish_event(self, event: EnhancedCloudEvent) -> None:
        """
        보안 검사를 거친 이벤트 발행
        
        Args:
            event: 발행할 이벤트
            
        Raises:
            ValueError: PII 감지 시 (BLOCK 전략인 경우)
            PermissionError: 허용되지 않은 이벤트 타입
        """
        self._event_count += 1
        
        # 1. 이벤트 타입 검증
        self._validate_event_type(event)
        
        # 2. PII 검사 및 처리
        if self.config.enable_pii_detection:
            event = await self._handle_pii(event)
        
        # 3. 감사 로그
        if self.config.audit_log_enabled:
            self._audit_log_event(event)
        
        # 4. 안전한 이벤트 발행
        try:
            await self.publisher.publish_event(event)
            logger.info(f"Secure event published: {event.type} (id: {event.id})")
        except Exception as e:
            logger.error(f"Failed to publish secure event: {e}")
            raise
    
    async def publish_events_batch(self, events: List[EnhancedCloudEvent]) -> List[bool]:
        """
        배치 이벤트 보안 발행
        
        Args:
            events: 발행할 이벤트 목록
            
        Returns:
            각 이벤트의 발행 성공 여부
        """
        results = []
        
        for event in events:
            try:
                await self.publish_event(event)
                results.append(True)
            except Exception as e:
                logger.error(f"Failed to publish event {event.id}: {e}")
                results.append(False)
        
        return results
    
    def _validate_event_type(self, event: EnhancedCloudEvent):
        """이벤트 타입 검증"""
        event_type = event.type
        
        # 차단된 이벤트 타입 확인
        if self.config.blocked_event_types and event_type in self.config.blocked_event_types:
            self._blocked_count += 1
            raise PermissionError(f"Event type '{event_type}' is blocked")
        
        # 허용된 이벤트 타입 확인
        if self.config.allowed_event_types and event_type not in self.config.allowed_event_types:
            self._blocked_count += 1
            raise PermissionError(f"Event type '{event_type}' is not allowed")
    
    async def _handle_pii(self, event: EnhancedCloudEvent) -> EnhancedCloudEvent:
        """PII 처리"""
        # 이벤트 데이터에서 PII 검사
        pii_matches = self.pii_handler.detect_pii(event.data)
        
        if pii_matches:
            self._pii_detected_count += 1
            logger.warning(
                f"PII detected in event {event.id}: "
                f"{len(pii_matches)} sensitive fields found"
            )
            
            # PII 상세 정보 로깅 (개발 환경에서만)
            if settings.DEBUG:
                for match in pii_matches:
                    logger.debug(
                        f"  - {match.field_path}: {match.pii_type.value} "
                        f"(confidence: {match.confidence})"
                    )
            
            # 전략에 따른 처리
            strategy = self.config.pii_handling_strategy
            
            if strategy == PIIHandlingStrategy.BLOCK:
                raise ValueError(
                    f"PII detected in event data. Fields: "
                    f"{[m.field_path for m in pii_matches]}"
                )
            
            # 데이터 처리
            processed_data = self.pii_handler.handle_pii(event.data, strategy)
            
            # 새 이벤트 생성 (원본 변경 방지)
            event_dict = event.to_dict()
            event_dict['data'] = processed_data
            
            # PII 처리 메타데이터 추가
            event_dict['ce_pii_processed'] = True
            event_dict['ce_pii_strategy'] = strategy.value
            event_dict['ce_pii_fields_count'] = len(pii_matches)
            
            return EnhancedCloudEvent(**event_dict)
        
        return event
    
    def _audit_log_event(self, event: EnhancedCloudEvent):
        """감사 로그 기록"""
        audit_entry = {
            "timestamp": event.time,
            "event_id": event.id,
            "event_type": event.type,
            "source": event.source,
            "subject": event.subject,
            "author": getattr(event, 'ce_author', 'unknown'),
            "pii_processed": getattr(event, 'ce_pii_processed', False),
            "correlation_id": getattr(event, 'ce_correlationid', None),
        }
        
        # 실제 구현에서는 전용 감사 로그 시스템으로 전송
        logger.info(f"AUDIT: {audit_entry}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """보안 통계 반환"""
        return {
            "total_events": self._event_count,
            "pii_detected_events": self._pii_detected_count,
            "blocked_events": self._blocked_count,
            "pii_detection_rate": (
                self._pii_detected_count / self._event_count 
                if self._event_count > 0 else 0
            ),
            "block_rate": (
                self._blocked_count / self._event_count 
                if self._event_count > 0 else 0
            ),
        }


# 환경별 보안 발행자 생성
def create_secure_publisher(
    publisher: EventPublisher,
    environment: str = "development"
) -> SecureEventPublisher:
    """환경별 보안 발행자 생성"""
    
    # PII 핸들러 생성
    from ..security.pii_handler import create_pii_handler
    pii_handler = create_pii_handler(environment)
    
    # 환경별 보안 설정
    if environment == "production":
        config = SecurityConfig(
            pii_handling_strategy=PIIHandlingStrategy.ENCRYPT,
            enable_pii_detection=True,
            audit_log_enabled=True,
            encryption_key=settings.PII_ENCRYPTION_KEY.encode() if hasattr(settings, 'PII_ENCRYPTION_KEY') else None
        )
    elif environment == "staging":
        config = SecurityConfig(
            pii_handling_strategy=PIIHandlingStrategy.ANONYMIZE,
            enable_pii_detection=True,
            audit_log_enabled=True
        )
    else:  # development
        config = SecurityConfig(
            pii_handling_strategy=PIIHandlingStrategy.LOG,
            enable_pii_detection=True,
            audit_log_enabled=False
        )
    
    return SecureEventPublisher(publisher, pii_handler, config)