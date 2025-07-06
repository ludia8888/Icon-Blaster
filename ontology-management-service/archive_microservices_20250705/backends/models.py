"""
Event Publisher 도메인 모델
섹션 8.5의 Event Publisher Service 명세 구현
"""
from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel


class Change(BaseModel):
    """변경사항"""
    operation: str  # create, update, delete
    resource_type: str  # object_type, property, link_type, action_type
    resource_id: str
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None


class OutboxEvent(BaseModel):
    """Outbox 이벤트"""
    id: str
    type: str
    payload: str  # JSON string
    created_at: datetime
    status: str = "pending"  # pending, published, failed
    retry_count: int = 0
    last_error: Optional[str] = None


class EventMetadata(BaseModel):
    """이벤트 메타데이터"""
    branch: str
    commit_id: str
    author: str
    timestamp: datetime


class CloudEvent(BaseModel):
    """CloudEvents 형식 (레거시 호환)"""
    specversion: str = "1.0"
    type: str
    source: str
    id: str
    time: datetime
    datacontenttype: str = "application/json"
    data: Dict[str, Any]
    
    # 선택적 CloudEvents 표준 속성
    dataschema: Optional[str] = None
    subject: Optional[str] = None
    
    def to_enhanced_cloudevent(self):
        """Enhanced CloudEvent로 변환"""
        from .cloudevents_enhanced import EnhancedCloudEvent
        
        return EnhancedCloudEvent(
            specversion=self.specversion,
            type=self.type,
            source=self.source,
            id=self.id,
            time=self.time,
            datacontenttype=self.datacontenttype,
            dataschema=self.dataschema,
            subject=self.subject,
            data=self.data
        )


class PublishResult(BaseModel):
    """발행 결과"""
    event_id: str
    success: bool
    subject: str
    error: Optional[str] = None
    latency_ms: Optional[float] = None
