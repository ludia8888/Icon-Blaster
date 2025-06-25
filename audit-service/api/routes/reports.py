"""
Reports API Routes
규제 준수 및 감사 리포트 API
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from models.reports import (
    ComplianceReport, AuditReport, ReportTemplate, ReportSchedule
)
from core.services.report_service import ReportService
from utils.auth import get_current_user, require_permissions

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])


def get_report_service() -> ReportService:
    """Report Service 의존성 주입"""
    # TODO: 실제 구현에서는 DI 컨테이너 사용
    from core.services.report_service import ReportService
    return ReportService()


@router.post(
    "/compliance",
    response_model=ComplianceReport,
    summary="Generate compliance report",
    description="""
    규제 준수 리포트를 생성합니다.
    
    **권한**: `reports:create` 또는 `compliance:read`
    
    **지원 표준**:
    - SOX (Sarbanes-Oxley Act)
    - GDPR (General Data Protection Regulation)
    - HIPAA (Health Insurance Portability and Accountability Act)
    - PCI-DSS (Payment Card Industry Data Security Standard)
    - ISO 27001
    - NIST
    """
)
async def generate_compliance_report(
    compliance_standard: str = Query(..., description="준수 표준"),
    period_start: str = Query(..., description="리포트 기간 시작 (ISO 8601)"),
    period_end: str = Query(..., description="리포트 기간 종료 (ISO 8601)"),
    include_findings: bool = Query(True, description="발견사항 포함 여부"),
    include_recommendations: bool = Query(True, description="권고사항 포함 여부"),
    template_id: Optional[str] = Query(None, description="사용할 템플릿 ID"),
    current_user: dict = Depends(get_current_user),
    report_service: ReportService = Depends(get_report_service)
) -> ComplianceReport:
    """규제 준수 리포트 생성"""
    
    # 권한 확인
    require_permissions(current_user, ["reports:create", "compliance:read"])
    
    try:
        result = await report_service.generate_compliance_report(
            compliance_standard=compliance_standard,
            period_start=period_start,
            period_end=period_end,
            include_findings=include_findings,
            include_recommendations=include_recommendations,
            template_id=template_id,
            user_context=current_user
        )
        
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
            detail="Failed to generate compliance report"
        )


@router.post(
    "/audit",
    response_model=AuditReport,
    summary="Generate audit report",
    description="""
    감사 리포트를 생성합니다.
    
    **권한**: `reports:create` 또는 `audit:report`
    
    **리포트 타입**:
    - audit_trail: 감사 추적 리포트
    - access_report: 접근 리포트
    - change_report: 변경 리포트
    - security_report: 보안 리포트
    - executive_summary: 경영진 요약
    """
)
async def generate_audit_report(
    report_type: str = Query(..., description="리포트 타입"),
    period_start: str = Query(..., description="리포트 기간 시작 (ISO 8601)"),
    period_end: str = Query(..., description="리포트 기간 종료 (ISO 8601)"),
    include_systems: Optional[str] = Query(None, description="포함할 시스템 (콤마 구분)"),
    include_users: Optional[str] = Query(None, description="포함할 사용자 (콤마 구분)"),
    event_types: Optional[str] = Query(None, description="포함할 이벤트 타입 (콤마 구분)"),
    template_id: Optional[str] = Query(None, description="사용할 템플릿 ID"),
    current_user: dict = Depends(get_current_user),
    report_service: ReportService = Depends(get_report_service)
) -> AuditReport:
    """감사 리포트 생성"""
    
    # 권한 확인
    require_permissions(current_user, ["reports:create", "audit:report"])
    
    try:
        result = await report_service.generate_audit_report(
            report_type=report_type,
            period_start=period_start,
            period_end=period_end,
            include_systems=include_systems.split(",") if include_systems else None,
            include_users=include_users.split(",") if include_users else None,
            event_types=event_types.split(",") if event_types else None,
            template_id=template_id,
            user_context=current_user
        )
        
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
            detail="Failed to generate audit report"
        )


@router.get(
    "/",
    summary="List reports",
    description="""
    생성된 리포트 목록을 조회합니다.
    
    **권한**: `reports:read`
    """
)
async def list_reports(
    report_type: Optional[str] = Query(None, description="리포트 타입 필터"),
    status: Optional[str] = Query(None, description="상태 필터"),
    generated_by: Optional[str] = Query(None, description="생성자 필터"),
    from_date: Optional[str] = Query(None, description="생성일 시작"),
    to_date: Optional[str] = Query(None, description="생성일 종료"),
    limit: int = Query(50, ge=1, le=1000, description="결과 제한"),
    offset: int = Query(0, ge=0, description="결과 시작 위치"),
    current_user: dict = Depends(get_current_user),
    report_service: ReportService = Depends(get_report_service)
):
    """리포트 목록 조회"""
    
    # 권한 확인
    require_permissions(current_user, ["reports:read"])
    
    try:
        result = await report_service.list_reports(
            report_type=report_type,
            status=status,
            generated_by=generated_by,
            from_date=from_date,
            to_date=to_date,
            limit=limit,
            offset=offset,
            user_context=current_user
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
            detail="Failed to retrieve reports"
        )


@router.get(
    "/{report_id}",
    summary="Get report details",
    description="""
    특정 리포트의 상세 정보를 조회합니다.
    
    **권한**: `reports:read`
    """
)
async def get_report_details(
    report_id: str,
    current_user: dict = Depends(get_current_user),
    report_service: ReportService = Depends(get_report_service)
):
    """리포트 상세 조회"""
    
    # 권한 확인
    require_permissions(current_user, ["reports:read"])
    
    try:
        result = await report_service.get_report_details(report_id, current_user)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report {report_id} not found"
            )
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve report details"
        )


@router.get(
    "/{report_id}/download",
    summary="Download report file",
    description="""
    리포트 파일을 다운로드합니다.
    
    **권한**: `reports:read`
    """
)
async def download_report(
    report_id: str,
    format: Optional[str] = Query(None, description="다운로드 형식 (원본 형식 사용 시 None)"),
    current_user: dict = Depends(get_current_user),
    report_service: ReportService = Depends(get_report_service)
):
    """리포트 파일 다운로드"""
    
    # 권한 확인
    require_permissions(current_user, ["reports:read"])
    
    try:
        file_stream, filename, media_type = await report_service.download_report(
            report_id, format, current_user
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
            detail=f"Report file {report_id} not found or expired"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to download report"
        )


@router.get(
    "/templates",
    response_model=List[ReportTemplate],
    summary="List report templates",
    description="""
    리포트 템플릿 목록을 조회합니다.
    
    **권한**: `reports:read` 또는 `templates:read`
    """
)
async def list_report_templates(
    report_type: Optional[str] = Query(None, description="리포트 타입 필터"),
    compliance_standard: Optional[str] = Query(None, description="준수 표준 필터"),
    is_active: bool = Query(True, description="활성 템플릿만 조회"),
    current_user: dict = Depends(get_current_user),
    report_service: ReportService = Depends(get_report_service)
) -> List[ReportTemplate]:
    """리포트 템플릿 목록 조회"""
    
    # 권한 확인
    require_permissions(current_user, ["reports:read", "templates:read"])
    
    try:
        result = await report_service.list_templates(
            report_type=report_type,
            compliance_standard=compliance_standard,
            is_active=is_active,
            user_context=current_user
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve templates"
        )


@router.post(
    "/schedules",
    response_model=ReportSchedule,
    summary="Create report schedule",
    description="""
    리포트 자동 생성 스케줄을 생성합니다.
    
    **권한**: `reports:schedule` 또는 `admin`
    """
)
async def create_report_schedule(
    schedule_data: ReportSchedule,
    current_user: dict = Depends(get_current_user),
    report_service: ReportService = Depends(get_report_service)
) -> ReportSchedule:
    """리포트 스케줄 생성"""
    
    # 권한 확인
    require_permissions(current_user, ["reports:schedule", "admin"])
    
    try:
        result = await report_service.create_schedule(schedule_data, current_user)
        
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
            detail="Failed to create report schedule"
        )


@router.get(
    "/schedules",
    response_model=List[ReportSchedule],
    summary="List report schedules",
    description="""
    리포트 스케줄 목록을 조회합니다.
    
    **권한**: `reports:schedule` 또는 `reports:read`
    """
)
async def list_report_schedules(
    enabled: Optional[bool] = Query(None, description="활성화 상태 필터"),
    template_id: Optional[str] = Query(None, description="템플릿 ID 필터"),
    current_user: dict = Depends(get_current_user),
    report_service: ReportService = Depends(get_report_service)
) -> List[ReportSchedule]:
    """리포트 스케줄 목록 조회"""
    
    # 권한 확인
    require_permissions(current_user, ["reports:schedule", "reports:read"])
    
    try:
        result = await report_service.list_schedules(
            enabled=enabled,
            template_id=template_id,
            user_context=current_user
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve schedules"
        )


@router.delete(
    "/{report_id}",
    summary="Delete report",
    description="""
    리포트를 삭제합니다.
    
    **권한**: `reports:delete` 또는 `admin`
    """
)
async def delete_report(
    report_id: str,
    current_user: dict = Depends(get_current_user),
    report_service: ReportService = Depends(get_report_service)
):
    """리포트 삭제"""
    
    # 권한 확인
    require_permissions(current_user, ["reports:delete", "admin"])
    
    try:
        await report_service.delete_report(report_id, current_user)
        
        return {"message": f"Report {report_id} deleted successfully"}
        
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
            detail="Failed to delete report"
        )