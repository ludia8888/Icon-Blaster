"""
Structured Logger Module for ELK/GCP Stack
ELK/GCP Stack 호환 구조화 로거 모듈
"""
import json
import logging
import sys
import os
import time
from datetime import datetime, timezone

def get_logger(name):
    """표준 로거 반환"""
    return logging.getLogger(name)
from typing import Optional, Dict, Any, Union
from enum import Enum


class LogLevel(str, Enum):
    """로그 레벨 Enum"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class StructuredFormatter(logging.Formatter):
    """ELK/GCP Stack 호환 JSON 로거 포맷터"""
    
    def __init__(self, service_name: str = "oms-monolith", version: str = "1.0.0"):
        super().__init__()
        self.service_name = service_name
        self.version = version
    
    def format(self, record: logging.LogRecord) -> str:
        """로그 레코드를 JSON 형태로 포맷"""
        # UTC 타임스탬프 생성
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc)
        
        # 기본 구조화 로그 데이터
        log_data = {
            "@timestamp": timestamp.isoformat(),
            "@version": "1",
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "thread": record.thread,
            "thread_name": record.threadName,
            "service": {
                "name": self.service_name,
                "version": self.version
            },
            "host": {
                "name": os.environ.get("HOSTNAME", "localhost"),
                "ip": os.environ.get("HOST_IP", "127.0.0.1")
            },
            "process": {
                "pid": os.getpid(),
                "name": record.processName
            }
        }
        
        # 파일 정보 추가 (가능한 경우)
        if hasattr(record, 'pathname'):
            log_data["source"] = {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName
            }
        
        # 예외 정보 추가
        if record.exc_info:
            log_data["exception"] = {
                "class": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "stack_trace": self.formatException(record.exc_info) if record.exc_info else None
            }
        
        # 커스텀 필드 추가 (record에 추가된 속성들)
        custom_fields = {}
        for key, value in record.__dict__.items():
            if key not in {
                'name', 'msg', 'args', 'levelname', 'levelno', 'pathname', 'filename',
                'module', 'exc_info', 'exc_text', 'stack_info', 'lineno', 'funcName',
                'created', 'msecs', 'relativeCreated', 'thread', 'threadName',
                'processName', 'process', 'message'
            }:
                custom_fields[key] = value
        
        if custom_fields:
            log_data["fields"] = custom_fields
        
        # 환경 정보 추가
        log_data["environment"] = {
            "stage": os.environ.get("ENVIRONMENT", "development"),
            "region": os.environ.get("AWS_REGION", os.environ.get("REGION", "unknown")),
            "deployment": os.environ.get("DEPLOYMENT_ID", "local")
        }
        
        # JSON 직렬화 (예외 처리 포함)
        try:
            return json.dumps(log_data, ensure_ascii=False, separators=(',', ':'))
        except (TypeError, ValueError) as e:
            # JSON 직렬화 실패 시 fallback
            fallback_data = {
                "@timestamp": timestamp.isoformat(),
                "level": record.levelname,
                "message": record.getMessage(),
                "logger": record.name,
                "error": f"JSON serialization failed: {e}"
            }
            return json.dumps(fallback_data, ensure_ascii=False, separators=(',', ':'))


class StructuredLoggerAdapter(logging.LoggerAdapter):
    """컨텍스트 정보를 포함한 구조화 로거 어댑터"""
    
    def __init__(self, logger: logging.Logger, extra: Dict[str, Any] = None):
        super().__init__(logger, extra or {})
    
    def process(self, msg: Any, kwargs: Dict[str, Any]) -> tuple:
        """로그 메시지 처리 시 컨텍스트 정보 추가"""
        if 'extra' in kwargs:
            kwargs['extra'].update(self.extra)
        else:
            kwargs['extra'] = self.extra.copy()
        return msg, kwargs
    
    def with_context(self, **context) -> 'StructuredLoggerAdapter':
        """새로운 컨텍스트를 추가한 로거 어댑터 반환"""
        new_extra = self.extra.copy()
        new_extra.update(context)
        return StructuredLoggerAdapter(self.logger, new_extra)


def get_logger(
    name: Optional[str] = None,
    level: Union[str, LogLevel] = LogLevel.INFO,
    use_json: bool = None,
    service_name: str = "oms-monolith",
    version: str = "1.0.0"
) -> logging.Logger:
    """
    구조화 로거 인스턴스 반환
    
    Args:
        name: 로거 이름
        level: 로그 레벨
        use_json: JSON 포맷 사용 여부 (None이면 환경변수로 결정)
        service_name: 서비스 이름
        version: 서비스 버전
        
    Returns:
        Logger instance
    """
    logger = logging.getLogger(name or __name__)
    
    # 이미 설정된 로거는 재사용
    if logger.handlers:
        return logger
    
    # JSON 포맷 사용 여부 결정
    if use_json is None:
        use_json = os.environ.get("LOG_FORMAT", "text").lower() == "json"
    
    # 로그 레벨 설정
    if isinstance(level, str):
        level = getattr(logging, level.upper(), logging.INFO)
    elif isinstance(level, LogLevel):
        level = getattr(logging, level.value, logging.INFO)
    
    logger.setLevel(level)
    
    # 핸들러 생성
    handler = logging.StreamHandler(sys.stdout)
    
    if use_json:
        # JSON 포맷터 사용 (ELK/GCP Stack 호환)
        formatter = StructuredFormatter(service_name, version)
    else:
        # 개발용 텍스트 포맷터
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger


def get_structured_logger(
    name: Optional[str] = None,
    context: Dict[str, Any] = None,
    **kwargs
) -> StructuredLoggerAdapter:
    """
    구조화 로거 어댑터 반환
    
    Args:
        name: 로거 이름
        context: 기본 컨텍스트 정보
        **kwargs: get_logger에 전달할 추가 인자
        
    Returns:
        StructuredLoggerAdapter instance
    """
    logger = get_logger(name, **kwargs)
    return StructuredLoggerAdapter(logger, context or {})


# 편의 함수들
def log_operation_start(logger: logging.Logger, operation: str, **context):
    """작업 시작 로그"""
    logger.info(f"Starting operation: {operation}", extra={
        "operation": operation,
        "operation_status": "started",
        "start_time": datetime.now(timezone.utc).isoformat(),
        **context
    })


def log_operation_end(logger: logging.Logger, operation: str, success: bool = True, duration: float = None, **context):
    """작업 완료 로그"""
    status = "completed" if success else "failed"
    log_data = {
        "operation": operation,
        "operation_status": status,
        "end_time": datetime.now(timezone.utc).isoformat(),
        **context
    }
    
    if duration is not None:
        log_data["duration_ms"] = duration * 1000
    
    if success:
        logger.info(f"Operation completed: {operation}", extra=log_data)
    else:
        logger.error(f"Operation failed: {operation}", extra=log_data)


def log_validation_result(logger: logging.Logger, entity_type: str, entity_id: str, 
                         is_valid: bool, errors: list = None, **context):
    """검증 결과 로그"""
    log_data = {
        "validation_target": entity_type,
        "entity_id": entity_id,
        "validation_result": "valid" if is_valid else "invalid",
        "validation_time": datetime.now(timezone.utc).isoformat(),
        **context
    }
    
    if not is_valid and errors:
        log_data["validation_errors"] = errors
    
    if is_valid:
        logger.info(f"Validation passed for {entity_type}: {entity_id}", extra=log_data)
    else:
        logger.warning(f"Validation failed for {entity_type}: {entity_id}", extra=log_data)


def log_performance_metric(logger: logging.Logger, metric_name: str, value: Union[int, float], 
                          unit: str = "ms", **context):
    """성능 메트릭 로그"""
    logger.info(f"Performance metric: {metric_name}", extra={
        "metric_type": "performance",
        "metric_name": metric_name,
        "metric_value": value,
        "metric_unit": unit,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **context
    })


# 환경별 로거 설정
def configure_production_logging():
    """프로덕션 환경 로깅 설정"""
    os.environ["LOG_FORMAT"] = "json"
    # 불필요한 로그 레벨 조정
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)


def configure_development_logging():
    """개발 환경 로깅 설정"""
    os.environ["LOG_FORMAT"] = "text"


# 환경 자동 감지 및 설정
if os.environ.get("ENVIRONMENT", "development").lower() in ["production", "prod", "staging"]:
    configure_production_logging()
else:
    configure_development_logging()