"""
SIEM 이벤트 직렬화 도구
복잡한 이벤트 변환 로직을 분리
"""
from typing import Dict, Any, Type
from datetime import datetime
import json

from core.validation.events import (
    TamperingEvent, 
    ValidationLogEntry, 
    SecurityAlert,
    EVENT_TYPE_MAPPING
)


class SiemEventSerializer:
    """SIEM 형식으로 이벤트를 직렬화하는 도구"""
    
    @staticmethod
    def serialize(event: Any) -> Dict[str, Any]:
        """
        이벤트 객체를 SIEM 형식으로 직렬화
        
        Args:
            event: 직렬화할 이벤트 객체
            
        Returns:
            SIEM 형식의 딕셔너리
        """
        event_type = type(event)
        
        # 이벤트 타입 매핑
        siem_event_type = EVENT_TYPE_MAPPING.get(
            event_type, 
            f"unknown.{event_type.__name__.lower()}"
        )
        
        # 기본 직렬화
        if hasattr(event, 'to_dict'):
            payload = event.to_dict()
        else:
            # 기본 딕셔너리 변환
            payload = {}
            for key, value in event.__dict__.items():
                if isinstance(value, datetime):
                    payload[key] = value.isoformat()
                elif hasattr(value, '__dict__'):
                    payload[key] = value.__dict__
                else:
                    payload[key] = value
        
        # SIEM 메타데이터 추가
        siem_event = {
            "event_type": siem_event_type,
            "event_class": event_type.__name__,
            "timestamp": datetime.utcnow().isoformat(),
            "source_system": "oms_validation",
            "data": payload
        }
        
        # 특별 처리가 필요한 이벤트별 커스터마이징
        if isinstance(event, TamperingEvent):
            siem_event["security_context"] = {
                "severity": event.severity.value,
                "detection_confidence": event.confidence_score,
                "requires_action": event.severity.value in ["critical", "high"]
            }
        elif isinstance(event, ValidationLogEntry):
            siem_event["validation_context"] = {
                "success": event.is_valid,
                "execution_time_ms": event.execution_time_ms,
                "branch": event.branch
            }
        elif isinstance(event, SecurityAlert):
            siem_event["alert_context"] = {
                "severity": event.severity.value,
                "action_required": event.recommended_action is not None
            }
        
        return siem_event
    
    @staticmethod
    def serialize_batch(events: list) -> list:
        """여러 이벤트를 배치로 직렬화"""
        return [SiemEventSerializer.serialize(event) for event in events]
    
    @staticmethod
    def to_cef(event: Dict[str, Any]) -> str:
        """
        Common Event Format (CEF) 형식으로 변환
        ArcSight 등에서 사용
        """
        # CEF:Version|Device Vendor|Device Product|Device Version|Signature ID|Name|Severity|Extension
        cef_parts = [
            "CEF:0",  # Version
            "Foundry",  # Vendor
            "OMS",  # Product
            "1.0",  # Version
            event.get("event_type", "unknown"),  # Signature ID
            event.get("event_class", "Event"),  # Name
            _severity_to_cef(event.get("data", {}).get("severity", "info")),  # Severity
        ]
        
        # Extension fields
        extensions = []
        for key, value in event.get("data", {}).items():
            if key != "severity":
                extensions.append(f"{key}={value}")
        
        cef_string = "|".join(cef_parts) + "|" + " ".join(extensions)
        return cef_string
    
    @staticmethod
    def to_leef(event: Dict[str, Any]) -> str:
        """
        Log Event Extended Format (LEEF) 형식으로 변환
        IBM QRadar에서 사용
        """
        # LEEF:Version|Vendor|Product|Version|EventID|
        leef_parts = [
            "LEEF:2.0",
            "Foundry",
            "OMS", 
            "1.0",
            event.get("event_type", "unknown")
        ]
        
        # Key-value pairs
        data_parts = []
        for key, value in event.get("data", {}).items():
            data_parts.append(f"{key}={value}")
        
        leef_string = "|".join(leef_parts) + "|" + "|".join(data_parts)
        return leef_string


def _severity_to_cef(severity: str) -> str:
    """심각도를 CEF 숫자로 변환 (0-10)"""
    mapping = {
        "critical": "10",
        "high": "8",
        "medium": "5",
        "low": "3",
        "info": "1"
    }
    return mapping.get(severity.lower(), "1")