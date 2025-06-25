"""
Validation 도메인 이벤트 정의
순환 참조 해결을 위해 모든 이벤트 데이터 클래스를 중앙화
"""
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, List


class EventSeverity(str, Enum):
    """이벤트 심각도"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class TamperingType(str, Enum):
    """변조 유형"""
    SCHEMA_MODIFICATION = "schema_modification"
    DATA_MANIPULATION = "data_manipulation"
    RULE_BYPASS = "rule_bypass"
    TIMESTAMP_FORGERY = "timestamp_forgery"
    SIGNATURE_MISMATCH = "signature_mismatch"


@dataclass
class TamperingEvent:
    """변조 탐지 이벤트"""
    event_id: str
    validator: str
    object_type: str
    field: str
    old_value: Any
    new_value: Any
    tampering_type: TamperingType
    severity: EventSeverity
    detected_at: datetime
    detection_method: str
    confidence_score: float
    affected_records: int
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """SIEM 전송을 위한 직렬화"""
        data = asdict(self)
        # datetime 객체를 ISO 형식 문자열로 변환
        data['detected_at'] = self.detected_at.isoformat()
        data['severity'] = self.severity.value
        data['tampering_type'] = self.tampering_type.value
        return data


@dataclass
class ValidationLogEntry:
    """검증 로그 엔트리"""
    log_id: str
    validation_id: str
    branch: str
    rule_id: str
    rule_name: str
    is_valid: bool
    error_message: Optional[str]
    execution_time_ms: float
    affected_objects: List[str]
    created_at: datetime
    user_id: Optional[str] = None
    correlation_id: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """SIEM 전송을 위한 직렬화"""
        data = asdict(self)
        data['created_at'] = self.created_at.isoformat()
        return data


@dataclass
class SecurityAlert:
    """보안 경고 이벤트 (공통)"""
    alert_id: str
    alert_type: str  # "tampering", "validation_failure", "anomaly"
    severity: EventSeverity
    source_system: str
    target_object: str
    description: str
    detected_at: datetime
    recommended_action: Optional[str] = None
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """SIEM 전송을 위한 직렬화"""
        data = asdict(self)
        data['detected_at'] = self.detected_at.isoformat()
        data['severity'] = self.severity.value
        return data


# 이벤트 타입 매핑 (SIEM에서 사용)
EVENT_TYPE_MAPPING = {
    TamperingEvent: "security.tampering",
    ValidationLogEntry: "validation.log",
    SecurityAlert: "security.alert"
}