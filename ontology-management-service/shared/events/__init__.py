"""
Shared Events Module
공유 이벤트 모듈
"""
from typing import Dict, Any, Optional
from datetime import datetime
from enum import Enum

class EventType(str, Enum):
    """이벤트 유형"""
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    MERGED = "merged"
    VALIDATED = "validated"
    PUBLISHED = "published"

class Event:
    """기본 이벤트 클래스"""
    
    def __init__(
        self,
        event_type: EventType,
        source: str,
        data: Dict[str, Any],
        user_id: Optional[str] = None,
        correlation_id: Optional[str] = None
    ):
        self.event_type = event_type
        self.source = source
        self.data = data
        self.user_id = user_id
        self.correlation_id = correlation_id
        self.timestamp = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """이벤트를 딕셔너리로 변환"""
        return {
            "event_type": self.event_type.value,
            "source": self.source,
            "data": self.data,
            "user_id": self.user_id,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp.isoformat()
        }

__all__ = ["EventType", "Event"]