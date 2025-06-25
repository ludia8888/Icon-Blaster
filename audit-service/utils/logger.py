"""
Structured Logging Utilities
ELK/GCP Stack 호환 JSON 로거
"""
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import structlog


def get_logger(name: str) -> logging.Logger:
    """구조화 로거 생성"""
    return logging.getLogger(name)


def setup_logging(log_level: str = "INFO", service_name: str = "audit-service"):
    """로깅 설정 초기화"""
    
    # 로그 레벨 설정
    level = getattr(logging, log_level.upper(), logging.INFO)
    
    # 루트 로거 설정
    logging.basicConfig(
        level=level,
        format="%(message)s",
        stream=sys.stdout
    )
    
    # structlog 설정
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            StructuredProcessor(service_name=service_name),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        logger_factory=structlog.WriteLoggerFactory(),
        cache_logger_on_first_use=True,
    )


class StructuredProcessor:
    """구조화 로그 프로세서"""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
    
    def __call__(self, logger, method_name, event_dict):
        """로그 이벤트 처리"""
        
        # 기본 필드 추가
        structured = {
            "@timestamp": datetime.now(timezone.utc).isoformat(),
            "service": self.service_name,
            "level": event_dict.get("level", "info").upper(),
            "message": event_dict.get("event", ""),
            "logger": event_dict.get("logger", ""),
        }
        
        # 추가 필드 병합
        for key, value in event_dict.items():
            if key not in ["event", "level", "logger", "timestamp"]:
                structured[key] = value
        
        # 예외 정보 처리
        if "exc_info" in event_dict and event_dict["exc_info"]:
            exc_info = event_dict["exc_info"]
            structured["exception"] = {
                "type": exc_info[0].__name__ if exc_info[0] else None,
                "message": str(exc_info[1]) if exc_info[1] else None,
                "traceback": event_dict.get("exception", "")
            }
        
        # JSON 직렬화
        return json.dumps(structured, ensure_ascii=False, default=str)


def log_operation_start(
    logger: logging.Logger,
    operation: str,
    **context
):
    """작업 시작 로그"""
    logger.info(
        f"Operation started: {operation}",
        extra={
            "operation": operation,
            "operation_status": "started",
            **context
        }
    )


def log_operation_end(
    logger: logging.Logger,
    operation: str,
    success: bool = True,
    duration_ms: Optional[float] = None,
    **context
):
    """작업 완료 로그"""
    status = "completed" if success else "failed"
    
    extra = {
        "operation": operation,
        "operation_status": status,
        "success": success,
        **context
    }
    
    if duration_ms is not None:
        extra["duration_ms"] = duration_ms
    
    level = logging.INFO if success else logging.ERROR
    logger.log(
        level,
        f"Operation {status}: {operation}",
        extra=extra
    )


def log_audit_event(
    logger: logging.Logger,
    event_type: str,
    user_id: str,
    resource_type: str,
    resource_id: str,
    action: str,
    result: str = "success",
    **context
):
    """감사 이벤트 로그"""
    logger.info(
        f"Audit event: {event_type}",
        extra={
            "audit_event": True,
            "event_type": event_type,
            "user_id": user_id,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "action": action,
            "result": result,
            **context
        }
    )


def log_siem_transmission(
    logger: logging.Logger,
    transmission_id: str,
    events_count: int,
    success: bool = True,
    response_time_ms: Optional[float] = None,
    **context
):
    """SIEM 전송 로그"""
    status = "success" if success else "failed"
    
    extra = {
        "siem_transmission": True,
        "transmission_id": transmission_id,
        "events_count": events_count,
        "status": status,
        "success": success,
        **context
    }
    
    if response_time_ms is not None:
        extra["response_time_ms"] = response_time_ms
    
    level = logging.INFO if success else logging.ERROR
    logger.log(
        level,
        f"SIEM transmission {status}: {transmission_id}",
        extra=extra
    )


def log_security_event(
    logger: logging.Logger,
    event_type: str,
    severity: str = "medium",
    description: str = "",
    **context
):
    """보안 이벤트 로그"""
    logger.warning(
        f"Security event: {event_type}",
        extra={
            "security_event": True,
            "event_type": event_type,
            "severity": severity,
            "description": description,
            **context
        }
    )


def log_performance_metric(
    logger: logging.Logger,
    metric_name: str,
    value: float,
    unit: str = "",
    **context
):
    """성능 메트릭 로그"""
    logger.info(
        f"Performance metric: {metric_name}",
        extra={
            "performance_metric": True,
            "metric_name": metric_name,
            "value": value,
            "unit": unit,
            **context
        }
    )


class AuditLogger:
    """감사 전용 로거"""
    
    def __init__(self, service_name: str = "audit-service"):
        self.service_name = service_name
        self.logger = get_logger(f"{service_name}.audit")
    
    def log_user_action(
        self,
        user_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        result: str = "success",
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        session_id: Optional[str] = None,
        **context
    ):
        """사용자 액션 감사 로그"""
        self.logger.info(
            f"User action: {action}",
            extra={
                "audit_type": "user_action",
                "user_id": user_id,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "result": result,
                "ip_address": ip_address,
                "user_agent": user_agent,
                "session_id": session_id,
                **context
            }
        )
    
    def log_data_access(
        self,
        user_id: str,
        data_type: str,
        data_id: str,
        access_type: str = "read",
        classification: Optional[str] = None,
        **context
    ):
        """데이터 접근 감사 로그"""
        self.logger.info(
            f"Data access: {access_type}",
            extra={
                "audit_type": "data_access",
                "user_id": user_id,
                "data_type": data_type,
                "data_id": data_id,
                "access_type": access_type,
                "classification": classification,
                **context
            }
        )
    
    def log_system_event(
        self,
        event_type: str,
        component: str,
        description: str,
        severity: str = "info",
        **context
    ):
        """시스템 이벤트 감사 로그"""
        self.logger.info(
            f"System event: {event_type}",
            extra={
                "audit_type": "system_event",
                "event_type": event_type,
                "component": component,
                "description": description,
                "severity": severity,
                **context
            }
        )
    
    def log_compliance_event(
        self,
        standard: str,
        control_id: str,
        status: str,
        description: str,
        **context
    ):
        """규제 준수 이벤트 로그"""
        self.logger.info(
            f"Compliance event: {standard}",
            extra={
                "audit_type": "compliance",
                "standard": standard,
                "control_id": control_id,
                "status": status,
                "description": description,
                **context
            }
        )


# 전역 감사 로거 인스턴스
audit_logger = AuditLogger()


def get_audit_logger() -> AuditLogger:
    """감사 로거 인스턴스 반환"""
    return audit_logger