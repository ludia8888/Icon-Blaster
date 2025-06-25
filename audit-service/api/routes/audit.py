"""
Audit Log API Routes
감사 로그 조회/관리 API
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from models.audit import (
    AuditSearchQuery, AuditSearchResponse, AuditExportRequest, AuditExportResponse
)
from core.services.audit_service import AuditService
from utils.auth import get_current_user, require_permissions

router = APIRouter(prefix="/api/v1/audit", tags=["audit"])


def get_audit_service() -> AuditService:
    """Audit Service 의존성 주입"""
    # TODO: 실제 구현에서는 DI 컨테이너 사용
    from core.services.audit_service import AuditService
    return AuditService()


@router.get(
    "/logs",
    response_model=AuditSearchResponse,
    summary="Search audit logs",
    description="""
    감사 로그를 검색합니다.
    
    **권한**: `audit:read`
    
    **검색 기능**:
    - 시간 범위별 검색
    - 사용자별 검색
    - 이벤트 타입별 검색
    - 텍스트 검색
    - 복합 필터링
    
    **집계 기능**:
    - 시간별/일별 집계
    - 사용자별 집계
    - 이벤트 타입별 집계
    """
)
async def search_audit_logs(
    # 시간 범위
    from_date: Optional[str] = Query(None, description="시작 날짜 (ISO 8601)"),
    to_date: Optional[str] = Query(None, description="종료 날짜 (ISO 8601)"),
    
    # 필터링
    user_id: Optional[str] = Query(None, description="사용자 ID 필터"),
    event_type: Optional[str] = Query(None, description="이벤트 타입 필터"),
    severity: Optional[str] = Query(None, description="심각도 필터"),
    service: Optional[str] = Query(None, description="서비스 필터"),
    action: Optional[str] = Query(None, description="액션 필터"),
    resource_type: Optional[str] = Query(None, description="리소스 타입 필터"),
    resource_id: Optional[str] = Query(None, description="리소스 ID 필터"),
    result: Optional[str] = Query(None, description="결과 필터 (success/failure)"),
    ip_address: Optional[str] = Query(None, description="IP 주소 필터"),
    
    # 규제 준수 필터
    compliance_tags: Optional[str] = Query(None, description="규제 준수 태그 (콤마 구분)"),
    data_classification: Optional[str] = Query(None, description="데이터 분류 필터"),
    legal_hold: Optional[bool] = Query(None, description="법적 보존 대상 필터"),
    
    # 검색
    search_text: Optional[str] = Query(None, description="텍스트 검색"),
    correlation_id: Optional[str] = Query(None, description="연관 이벤트 ID"),
    transaction_id: Optional[str] = Query(None, description="트랜잭션 ID"),
    
    # 페이지네이션
    limit: int = Query(100, ge=1, le=10000, description="결과 제한"),
    offset: int = Query(0, ge=0, description="결과 시작 위치"),
    cursor: Optional[str] = Query(None, description="커서 기반 페이지네이션"),
    
    # 정렬
    sort_by: str = Query("timestamp", description="정렬 기준"),
    sort_order: str = Query("desc", description="정렬 순서 (asc/desc)"),
    
    # 집계 옵션
    include_aggregations: bool = Query(False, description="집계 정보 포함 여부"),
    aggregation_fields: Optional[str] = Query(None, description="집계할 필드 (콤마 구분)"),
    
    # 의존성
    current_user: dict = Depends(get_current_user),
    audit_service: AuditService = Depends(get_audit_service)
) -> AuditSearchResponse:
    """감사 로그 검색"""
    
    # 권한 확인
    require_permissions(current_user, ["audit:read"])
    
    try:
        # 검색 쿼리 객체 생성
        query = AuditSearchQuery(
            from_date=from_date,
            to_date=to_date,
            user_id=user_id,
            event_type=event_type,
            severity=severity,
            service=service,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            result=result,
            ip_address=ip_address,
            compliance_tags=compliance_tags.split(",") if compliance_tags else None,
            data_classification=data_classification,
            legal_hold=legal_hold,
            search_text=search_text,
            correlation_id=correlation_id,
            transaction_id=transaction_id,
            limit=limit,
            offset=offset,
            cursor=cursor,
            sort_by=sort_by,
            sort_order=sort_order,
            include_aggregations=include_aggregations,
            aggregation_fields=aggregation_fields.split(",") if aggregation_fields else None
        )
        
        # 감사 로그 검색
        result = await audit_service.search_logs(query, current_user)
        
        return result
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search audit logs"
        )


@router.get(
    "/logs/{log_id}",
    summary="Get audit log details",
    description="""
    특정 감사 로그의 상세 정보를 조회합니다.
    
    **권한**: `audit:read`
    """
)
async def get_audit_log_details(
    log_id: str,
    include_metadata: bool = Query(True, description="메타데이터 포함 여부"),
    include_states: bool = Query(False, description="before/after 상태 포함 여부"),
    current_user: dict = Depends(get_current_user),
    audit_service: AuditService = Depends(get_audit_service)
):
    """감사 로그 상세 조회"""
    
    # 권한 확인
    require_permissions(current_user, ["audit:read"])
    
    try:
        result = await audit_service.get_log_details(
            log_id=log_id,
            include_metadata=include_metadata,
            include_states=include_states,
            user_context=current_user
        )
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Audit log {log_id} not found"
            )
        
        return result
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audit log details"
        )


@router.post(
    "/export",
    response_model=AuditExportResponse,
    summary="Export audit logs",
    description="""
    감사 로그를 내보냅니다 (OMS에서 이관된 기능).
    
    **권한**: `audit:export`
    
    **지원 형식**: JSON, CSV, Excel, PDF
    **배달 방식**: 다운로드, 이메일, S3, SFTP
    
    **규제 준수**:
    - 개인정보 마스킹 지원
    - 감사 목적 기록
    - 접근 로그 생성
    """
)
async def export_audit_logs(
    export_request: AuditExportRequest,
    current_user: dict = Depends(get_current_user),
    audit_service: AuditService = Depends(get_audit_service)
) -> AuditExportResponse:
    """감사 로그 내보내기"""
    
    # 권한 확인
    require_permissions(current_user, ["audit:export"])
    
    try:
        # 내보내기 작업 시작
        result = await audit_service.start_export(export_request, current_user)
        
        return result
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start export"
        )


@router.get(
    "/export/{export_id}",
    response_model=AuditExportResponse,
    summary="Get export status",
    description="""
    감사 로그 내보내기 작업 상태를 조회합니다.
    
    **권한**: `audit:export`
    """
)
async def get_export_status(
    export_id: str,
    current_user: dict = Depends(get_current_user),
    audit_service: AuditService = Depends(get_audit_service)
) -> AuditExportResponse:
    """내보내기 상태 조회"""
    
    # 권한 확인
    require_permissions(current_user, ["audit:export"])
    
    try:
        result = await audit_service.get_export_status(export_id, current_user)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Export {export_id} not found"
            )
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve export status"
        )


@router.get(
    "/export/{export_id}/download",
    summary="Download exported file",
    description="""
    내보낸 감사 로그 파일을 다운로드합니다.
    
    **권한**: `audit:export`
    """
)
async def download_exported_file(
    export_id: str,
    current_user: dict = Depends(get_current_user),
    audit_service: AuditService = Depends(get_audit_service)
):
    """내보낸 파일 다운로드"""
    
    # 권한 확인
    require_permissions(current_user, ["audit:export"])
    
    try:
        file_stream, filename, media_type = await audit_service.download_export(
            export_id, current_user
        )
        
        return StreamingResponse(
            file_stream,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Export file {export_id} not found or expired"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to download export file"
        )


@router.get(
    "/statistics/dashboard",
    summary="Get audit dashboard statistics",
    description="""
    감사 대시보드용 통계 정보를 조회합니다.
    
    **권한**: `audit:read`
    """
)
async def get_audit_dashboard(
    time_range: str = Query("24h", description="시간 범위 (1h/24h/7d/30d)"),
    include_trends: bool = Query(True, description="트렌드 정보 포함"),
    include_top_users: bool = Query(True, description="상위 사용자 포함"),
    include_top_actions: bool = Query(True, description="상위 액션 포함"),
    current_user: dict = Depends(get_current_user),
    audit_service: AuditService = Depends(get_audit_service)
):
    """감사 대시보드 통계"""
    
    # 권한 확인
    require_permissions(current_user, ["audit:read"])
    
    try:
        dashboard_data = await audit_service.get_dashboard_statistics(
            time_range=time_range,
            include_trends=include_trends,
            include_top_users=include_top_users,
            include_top_actions=include_top_actions,
            user_context=current_user
        )
        
        return dashboard_data
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve dashboard statistics"
        )


@router.get(
    "/retention/status",
    summary="Get data retention status",
    description="""
    데이터 보존 정책 상태를 조회합니다.
    
    **권한**: `audit:admin`
    """
)
async def get_retention_status(
    compliance_standard: Optional[str] = Query(None, description="규제 준수 표준"),
    current_user: dict = Depends(get_current_user),
    audit_service: AuditService = Depends(get_audit_service)
):
    """데이터 보존 상태 조회"""
    
    # 권한 확인
    require_permissions(current_user, ["audit:admin"])
    
    try:
        retention_status = await audit_service.get_retention_status(
            compliance_standard=compliance_standard,
            user_context=current_user
        )
        
        return retention_status
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve retention status"
        )