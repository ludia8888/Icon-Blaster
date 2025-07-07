"""
Audit Service Proxy Metrics
audit-service와의 통신에 대한 Prometheus 메트릭
"""
from typing import Dict, Any, Optional
import os
import asyncio
from datetime import datetime, timezone

from prometheus_client import Counter, Histogram, Gauge, Info
from common_logging.setup import get_logger

logger = get_logger(__name__)

# Prometheus Metrics for Audit Service Proxy
audit_service_requests_total = Counter(
    'oms_audit_service_requests_total',
    'Total number of requests to audit service',
    ['method', 'endpoint', 'status']
)

audit_service_request_duration = Histogram(
    'oms_audit_service_request_duration_seconds',
    'Duration of requests to audit service',
    ['method', 'endpoint']
)

audit_service_errors_total = Counter(
    'oms_audit_service_errors_total',
    'Total number of audit service errors',
    ['error_type', 'endpoint']
)

audit_service_circuit_breaker_state = Gauge(
    'oms_audit_service_circuit_breaker_open',
    'Audit service circuit breaker state (1=open, 0=closed)'
)

audit_service_connection_pool = Gauge(
    'oms_audit_service_connection_pool_active',
    'Active connections in audit service pool'
)

# Legacy audit system metrics (deprecated)
legacy_audit_events_total = Counter(
    'oms_legacy_audit_events_total',
    'Total legacy audit events (deprecated)',
    ['source']
)

# Service info
audit_service_info = Info(
    'oms_audit_service_info',
    'Information about audit service integration'
)


class AuditServiceMetrics:
    """Audit Service 메트릭 수집기"""
    
    def __init__(self):
        self.use_audit_service = os.getenv('USE_AUDIT_SERVICE', 'false').lower() == 'true'
        
        # Service info 설정
        audit_service_info.info({
            'mode': 'proxy' if self.use_audit_service else 'disabled',
            'service_url': os.getenv('AUDIT_SERVICE_URL', 'unknown'),
            'migration_date': '2025-07-06',
            'version': 'v2'
        })
    
    def record_request(self, method: str, endpoint: str, status: str, duration: float):
        """Audit service 요청 기록"""
        audit_service_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status=status
        ).inc()
        
        audit_service_request_duration.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)
    
    def record_error(self, error_type: str, endpoint: str):
        """Audit service 에러 기록"""
        audit_service_errors_total.labels(
            error_type=error_type,
            endpoint=endpoint
        ).inc()
    
    def set_circuit_breaker_state(self, is_open: bool):
        """Circuit breaker 상태 설정"""
        audit_service_circuit_breaker_state.set(1 if is_open else 0)
    
    def set_connection_pool_active(self, count: int):
        """활성 연결 수 설정"""
        audit_service_connection_pool.set(count)
    
    def record_legacy_event(self, source: str):
        """레거시 audit 이벤트 기록 (deprecated)"""
        legacy_audit_events_total.labels(source=source).inc()
        logger.warning(f"Legacy audit event from {source} - consider migrating to audit-service")


# 전역 메트릭 인스턴스
_audit_metrics: Optional[AuditServiceMetrics] = None


def get_audit_metrics() -> AuditServiceMetrics:
    """Audit 메트릭 인스턴스 가져오기"""
    global _audit_metrics
    if _audit_metrics is None:
        _audit_metrics = AuditServiceMetrics()
    return _audit_metrics


# 편의 함수들
def record_audit_service_request(method: str, endpoint: str, status: str, duration: float):
    """Audit service 요청 기록"""
    metrics = get_audit_metrics()
    metrics.record_request(method, endpoint, status, duration)


def record_audit_service_error(error_type: str, endpoint: str):
    """Audit service 에러 기록"""
    metrics = get_audit_metrics()
    metrics.record_error(error_type, endpoint)


def set_audit_circuit_breaker_state(is_open: bool):
    """Circuit breaker 상태 설정"""
    metrics = get_audit_metrics()
    metrics.set_circuit_breaker_state(is_open)


# 백워드 호환성을 위한 deprecated 함수들
def record_audit_event(action: str, resource_type: str, success: bool = True, **kwargs):
    """Deprecated: Use audit-service directly"""
    logger.warning("record_audit_event is deprecated. Use audit-service client directly.")
    metrics = get_audit_metrics()
    metrics.record_legacy_event("monolith_legacy")


def record_audit_failure(action: str, resource_type: str, failure_reason: str, **kwargs):
    """Deprecated: Use audit-service directly"""
    logger.warning("record_audit_failure is deprecated. Use audit-service client directly.")
    metrics = get_audit_metrics()
    metrics.record_legacy_event("monolith_legacy")


async def get_audit_metrics_summary() -> Dict[str, Any]:
    """Audit 메트릭 요약 반환"""
    use_audit_service = os.getenv('USE_AUDIT_SERVICE', 'false').lower() == 'true'
    
    return {
        "audit_service_enabled": use_audit_service,
        "mode": "proxy" if use_audit_service else "disabled",
        "service_url": os.getenv('AUDIT_SERVICE_URL', 'unknown'),
        "migration_completed": True,
        "legacy_tables_removed": True,
        "metrics_available": [
            "oms_audit_service_requests_total",
            "oms_audit_service_request_duration_seconds", 
            "oms_audit_service_errors_total",
            "oms_audit_service_circuit_breaker_open",
            "oms_audit_service_connection_pool_active"
        ],
        "deprecated_metrics": [
            "oms_legacy_audit_events_total"
        ]
    }


# Initialize on import
_ = get_audit_metrics()