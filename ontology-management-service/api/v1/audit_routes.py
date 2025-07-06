"""
Audit API Routes - Proxy to Audit Service
audit-service로 프록시하는 REST 엔드포인트
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import JSONResponse
import httpx

from core.auth_utils import UserContext
from middleware.auth_middleware import get_current_user
from shared.audit_client import get_audit_client
from core.iam.dependencies import require_scope
from core.iam.iam_integration import IAMScope
from common_logging.setup import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/audit", tags=["Audit Management (Proxy)"])


@router.get("/events", summary="Query audit events (proxied to audit-service)", dependencies=[Depends(require_scope([IAMScope.AUDIT_READ]))])
async def query_audit_events(
    request: Request,
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    target_type: Optional[str] = Query(None, description="Filter by target type"),
    target_id: Optional[str] = Query(None, description="Filter by target ID"),
    operation: Optional[str] = Query(None, description="Filter by operation"),
    branch: Optional[str] = Query(None, description="Filter by branch"),
    from_date: Optional[datetime] = Query(None, description="Start date"),
    to_date: Optional[datetime] = Query(None, description="End date"),
    limit: int = Query(100, description="Maximum results", le=1000),
    offset: int = Query(0, description="Result offset"),
    current_user: UserContext = Depends(get_current_user)
):
    """
    감사 이벤트 조회 (audit-service로 프록시)
    
    이 엔드포인트는 audit-service의 API로 요청을 프록시합니다.
    """
    try:
        client = await get_audit_client()
        
        result = await client.query_events(
            user_id=user_id,
            target_type=target_type,
            target_id=target_id,
            operation=operation,
            branch=branch,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Audit query proxy failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Audit service unavailable: {str(e)}"
        )


@router.get("/events/{event_id}", summary="Get specific audit event", dependencies=[Depends(require_scope([IAMScope.AUDIT_READ]))])
async def get_audit_event(
    event_id: str,
    request: Request,
    current_user: UserContext = Depends(get_current_user)
):
    """특정 감사 이벤트 조회 (audit-service로 프록시)"""
    try:
        client = await get_audit_client()
        
        # 단일 이벤트 조회는 일반 쿼리로 구현
        result = await client.query_events(limit=1, offset=0)
        
        events = result.get("events", [])
        for event in events:
            if event.get("event_id") == event_id:
                return event
        
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audit event not found"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get audit event proxy failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Audit service unavailable: {str(e)}"
        )


@router.get("/users/{user_id}/events", summary="Get user's audit events", dependencies=[Depends(require_scope([IAMScope.AUDIT_READ]))])
async def get_user_audit_events(
    user_id: str,
    request: Request,
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    current_user: UserContext = Depends(get_current_user)
):
    """사용자별 감사 이벤트 조회 (audit-service로 프록시)"""
    try:
        client = await get_audit_client()
        
        result = await client.query_events(
            user_id=user_id,
            limit=limit,
            offset=offset
        )
        
        return result
        
    except Exception as e:
        logger.error(f"User audit events proxy failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Audit service unavailable: {str(e)}"
        )


@router.get("/targets/{target_type}/{target_id}/events", summary="Get target's audit events", dependencies=[Depends(require_scope([IAMScope.AUDIT_READ]))])
async def get_target_audit_events(
    target_type: str,
    target_id: str,
    request: Request,
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    current_user: UserContext = Depends(get_current_user)
):
    """대상별 감사 이벤트 조회 (audit-service로 프록시)"""
    try:
        client = await get_audit_client()
        
        result = await client.query_events(
            target_type=target_type,
            target_id=target_id,
            limit=limit,
            offset=offset
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Target audit events proxy failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Audit service unavailable: {str(e)}"
        )


@router.get("/health", summary="Audit service health check")
async def audit_service_health():
    """Audit service 헬스 체크"""
    try:
        client = await get_audit_client()
        health = await client.health_check()
        
        if health:
            return {
                "status": "healthy",
                "service": "audit-service",
                "proxy": "oms-monolith",
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Audit service is unhealthy"
            )
            
    except Exception as e:
        logger.error(f"Audit health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Audit service unavailable: {str(e)}"
        )


@router.get("/migration/status", summary="Audit migration status", dependencies=[Depends(require_scope([IAMScope.SYSTEM_ADMIN]))])
async def get_migration_status(
    request: Request,
    current_user: UserContext = Depends(get_current_user)
):
    """Audit 마이그레이션 상태 조회"""
    import os
    
    return {
        "migration_completed": True,
        "audit_service_enabled": os.getenv('USE_AUDIT_SERVICE', 'false').lower() == 'true',
        "proxy_mode": True,
        "legacy_tables_removed": True,
        "migration_date": "2025-07-06",
        "notes": [
            "All audit data has been migrated to audit-service",
            "Legacy audit tables have been removed from monolith",
            "Audit API routes now proxy to audit-service",
            "New audit events are stored in audit-service only"
        ]
    }


# Deprecated endpoint warnings
@router.post("/events", deprecated=True, summary="Create audit event (deprecated)")
async def create_audit_event_deprecated():
    """
    Deprecated: Direct audit event creation
    
    Audit events are now automatically created by the audit-service
    when operations are performed through the OMS API.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Direct audit event creation is no longer supported. "
               "Audit events are automatically created by audit-service."
    )