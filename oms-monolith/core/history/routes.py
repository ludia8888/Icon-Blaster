"""
OMS History Event API 라우트
OMS 핵심 책임: 스키마 복원 및 이벤트 발행만 담당
감사 로그 조회는 별도 Audit Service MSA로 분리
"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from core.auth.context import get_user_context
from utils.logger import get_logger
from .models import (
    RevertRequest, RevertResult, ChangeOperation, ResourceType
)
from .service import HistoryEventPublisher

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/schema", tags=["schema-events"])


def get_history_event_publisher() -> HistoryEventPublisher:
    """History Event Publisher 의존성 주입"""
    # TODO: 실제 구현에서는 DI 컨테이너 사용
    from database.clients.terminus_db import get_terminus_client
    from core.event.publisher import get_event_publisher
    
    return HistoryEventPublisher(
        terminus_client=get_terminus_client(),
        event_publisher=get_event_publisher()
    )


@router.post(
    "/revert",
    response_model=RevertResult,
    summary="Revert schema to specific commit",
    description="""
    스키마를 특정 커밋으로 복원합니다 (OMS 핵심 기능).
    
    **주의**: 스키마 메타데이터만 복원됩니다.
    - 데이터 복원: OSv2 서비스 담당
    - 파이프라인 복원: Funnel 서비스 담당
    
    **권한**: `schema:write` 또는 `admin`
    
    **복원 전략**:
    - `soft`: 새 커밋으로 이전 상태 적용 (권장)
    - `hard`: HEAD 이동 (테스트 환경에서만 허용)
    
    """
)
async def revert_schema(
    request: RevertRequest,
    branch: str = Query("main", description="대상 브랜치"),
    user_context: dict = Depends(get_user_context),
    publisher: HistoryEventPublisher = Depends(get_history_event_publisher)
) -> RevertResult:
    """
    스키마를 특정 커밋으로 복원 (OMS 핵심 기능)
    
    실제 데이터 복원은 다른 MSA 서비스로 위임됩니다:
    - OSv2: 객체 데이터 복원
    - Funnel: 파이프라인 복원
    """
    try:
        # 스키마 복원 수행
        result = await publisher.revert_schema_to_commit(
            branch=branch,
            request=request,
            user_context=user_context
        )
        
        return result
        
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Schema revert failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during schema revert"
        )


@router.post(
    "/events/audit",
    summary="Publish audit event",
    description="""
    감사 이벤트를 발행합니다 (내부 서비스용).
    
    실제 감사 로그 저장/조회는 Audit Service MSA에서 담당합니다.
    OMS는 이벤트 발행만 담당합니다.
    
    **권한**: 내부 서비스 토큰 필요
    """
)
async def publish_audit_event(
    event_type: str,
    operation: str,
    resource_type: str,
    resource_id: str,
    result: str = "success",
    details: Optional[dict] = None,
    user_context: dict = Depends(get_user_context),
    publisher: HistoryEventPublisher = Depends(get_history_event_publisher)
) -> dict:
    """내부 서비스용 감사 이벤트 발행"""
    try:
        event_id = await publisher.publish_audit_event(
            event_type=event_type,
            operation=operation,
            resource_type=resource_type,
            resource_id=resource_id,
            user_context=user_context,
            result=result,
            details=details
        )
        
        return {"event_id": event_id, "status": "published"}
        
    except Exception as e:
        logger.error(f"Failed to publish audit event: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to publish audit event"
        )