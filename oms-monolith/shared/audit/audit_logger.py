"""
Audit Logger Module
감사 로그 기록을 위한 모듈
"""
import logging
from datetime import datetime
from typing import Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)

class AuditEventType(str, Enum):
    """감사 이벤트 유형"""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    ACCESS = "access"
    LOGIN = "login"
    LOGOUT = "logout"
    ERROR = "error"

class AuditLogger:
    """감사 로그 기록자"""
    
    def __init__(self):
        self.logger = logger
        
    async def log_event(
        self,
        event_type: AuditEventType,
        resource_type: str,
        resource_id: str,
        user_id: str,
        details: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """감사 이벤트 로그 기록"""
        audit_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type.value,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "user_id": user_id,
            "details": details or {},
            "metadata": metadata or {}
        }
        
        self.logger.info(f"AUDIT: {audit_entry}")
        
        # TODO: 실제 구현에서는 데이터베이스나 외부 로깅 시스템에 저장
        
    def log_sync(
        self,
        event_type: AuditEventType,
        resource_type: str,
        resource_id: str,
        user_id: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """동기식 감사 로그 기록"""
        audit_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type.value,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "user_id": user_id,
            "details": details or {}
        }
        
        self.logger.info(f"AUDIT_SYNC: {audit_entry}")

# 전역 인스턴스
_audit_logger = AuditLogger()

def get_audit_logger() -> AuditLogger:
    """감사 로거 인스턴스 반환"""
    return _audit_logger