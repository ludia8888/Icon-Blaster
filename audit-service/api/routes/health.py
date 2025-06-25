"""
Health Check API Routes
서비스 상태 확인 API
"""
from fastapi import APIRouter, Depends
from typing import Dict, Any

from core.services.audit_service import AuditService
from models.siem import SiemHealthCheck

router = APIRouter(prefix="/api/v1/health", tags=["health"])


@router.get(
    "/",
    summary="Basic health check",
    description="서비스 기본 상태를 확인합니다."
)
async def health_check() -> Dict[str, str]:
    """기본 헬스체크"""
    return {
        "status": "healthy",
        "service": "audit-service",
        "version": "1.0.0"
    }


@router.get(
    "/detailed",
    summary="Detailed health check",
    description="서비스 상세 상태를 확인합니다."
)
async def detailed_health_check() -> Dict[str, Any]:
    """상세 헬스체크"""
    # TODO: 실제 구현에서는 각 컴포넌트 상태 확인
    return {
        "status": "healthy",
        "service": "audit-service",
        "version": "1.0.0",
        "timestamp": "2025-06-25T10:30:00Z",
        "components": {
            "database": {"status": "healthy", "response_time_ms": 5},
            "event_subscriber": {"status": "healthy", "last_event": "2025-06-25T10:29:00Z"},
            "siem_integration": {"status": "healthy", "success_rate": 0.99},
            "file_storage": {"status": "healthy", "available_space_gb": 1024}
        },
        "metrics": {
            "total_audit_logs": 150000,
            "logs_last_24h": 2500,
            "active_exports": 3,
            "scheduled_reports": 15
        }
    }


@router.get(
    "/siem",
    response_model=SiemHealthCheck,
    summary="SIEM connection health",
    description="SIEM 연동 상태를 확인합니다."
)
async def check_siem_health() -> SiemHealthCheck:
    """SIEM 연동 상태 확인"""
    # TODO: 실제 SIEM 연결 상태 확인
    from datetime import datetime, timezone
    from models.siem import SiemProvider
    
    return SiemHealthCheck(
        provider=SiemProvider.ELASTIC,
        endpoint_url="https://siem.company.com/api",
        is_healthy=True,
        last_check_time=datetime.now(timezone.utc),
        response_time_ms=125,
        total_events_sent=150000,
        success_rate=0.992,
        average_response_time_ms=110.5,
        consecutive_failures=0
    )


@router.get(
    "/readiness",
    summary="Readiness check",
    description="서비스 준비 상태를 확인합니다."
)
async def readiness_check() -> Dict[str, Any]:
    """준비 상태 확인 (Kubernetes 용)"""
    # TODO: 실제 구현에서는 의존성 서비스들 확인
    dependencies_ready = True
    
    return {
        "ready": dependencies_ready,
        "dependencies": {
            "database": True,
            "event_broker": True,
            "siem": True,
            "storage": True
        }
    }


@router.get(
    "/liveness",
    summary="Liveness check", 
    description="서비스 생존 상태를 확인합니다."
)
async def liveness_check() -> Dict[str, str]:
    """생존 상태 확인 (Kubernetes 용)"""
    return {
        "alive": "true",
        "timestamp": "2025-06-25T10:30:00Z"
    }