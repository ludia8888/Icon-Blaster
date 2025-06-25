"""
History API Routes (Migrated from OMS)
OMS core/history/routes.py에서 이관된 히스토리 조회 API
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from models.history import (
    HistoryQuery, HistoryListResponse, CommitDetail
)
from core.services.history_service import HistoryService
from utils.auth import get_current_user, require_permissions

router = APIRouter(prefix="/api/v1/history", tags=["history"])


def get_history_service() -> HistoryService:
    """History Service 의존성 주입"""
    # TODO: 실제 구현에서는 DI 컨테이너 사용
    from core.services.history_service import HistoryService
    return HistoryService()


@router.get(
    "/",
    response_model=HistoryListResponse,
    summary="List schema change history",
    description=\"\"\"
    스키마 변경 히스토리 목록을 조회합니다 (OMS에서 이관된 기능).
    
    **권한**: `audit:read` 또는 `history:read`
    
    **필터링 옵션**:
    - 브랜치별 필터링
    - 리소스 타입별 필터링  
    - 작성자별 필터링
    - 날짜 범위별 필터링
    - 작업 타입별 필터링
    
    **페이지네이션**:
    - cursor 기반 페이지네이션 지원
    - limit로 결과 수 제한 (최대 1000)
    
    **정렬**:
    - timestamp, author, resource_id 등으로 정렬 가능
    - asc/desc 정렬 순서 지원
    \"\"\"
)
async def list_history(
    # 필터링 파라미터
    branch: Optional[str] = Query(None, description="브랜치 필터"),
    resource_type: Optional[str] = Query(None, description="리소스 타입 필터"),
    resource_id: Optional[str] = Query(None, description="리소스 ID 필터"),
    author: Optional[str] = Query(None, description="작성자 필터"),
    operation: Optional[str] = Query(None, description="작업 타입 필터"),
    
    # 날짜 범위
    from_date: Optional[str] = Query(None, description="시작 날짜 (ISO 8601)"),
    to_date: Optional[str] = Query(None, description="종료 날짜 (ISO 8601)"),
    
    # 포함 옵션
    include_changes: bool = Query(True, description="상세 변경 내역 포함 여부"),
    include_affected: bool = Query(False, description="영향받은 리소스 포함 여부"),
    include_metadata: bool = Query(False, description="메타데이터 포함 여부"),
    
    # 페이지네이션
    limit: int = Query(50, ge=1, le=1000, description="결과 제한"),
    cursor: Optional[str] = Query(None, description="페이지네이션 커서"),
    
    # 정렬
    sort_by: str = Query("timestamp", description="정렬 기준"),
    sort_order: str = Query("desc", description="정렬 순서 (asc/desc)"),
    
    # 의존성
    current_user: dict = Depends(get_current_user),
    history_service: HistoryService = Depends(get_history_service)
) -> HistoryListResponse:
    \"\"\"스키마 변경 히스토리 목록 조회\"\"\"
    
    # 권한 확인
    require_permissions(current_user, ["audit:read", "history:read"])
    
    try:
        # 쿼리 객체 생성
        query = HistoryQuery(
            branch=branch,
            resource_type=resource_type,
            resource_id=resource_id,
            author=author,
            operation=operation,
            from_date=from_date,
            to_date=to_date,
            include_changes=include_changes,
            include_affected=include_affected,
            include_metadata=include_metadata,
            limit=limit,
            cursor=cursor,
            sort_by=sort_by,
            sort_order=sort_order
        )
        
        # 히스토리 조회
        result = await history_service.list_history(query, current_user)
        
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
            detail="Failed to retrieve history"
        )


@router.get(
    "/{commit_hash}",
    response_model=CommitDetail,
    summary="Get commit details",
    description=\"\"\"
    특정 커밋의 상세 정보를 조회합니다 (OMS에서 이관된 기능).
    
    **권한**: `audit:read` 또는 `history:read`
    
    **포함 정보**:
    - 커밋 기본 정보 (해시, 작성자, 메시지 등)
    - 변경 통계 (추가/수정/삭제 개수)
    - 상세 변경 내역
    - 영향받은 리소스들
    - 스키마 스냅샷 (선택적)
    \"\"\"
)
async def get_commit_detail(
    commit_hash: str,
    branch: str = Query("main", description="브랜치명"),
    include_snapshot: bool = Query(False, description="스키마 스냅샷 포함 여부"),
    include_changes: bool = Query(True, description="상세 변경 내역 포함 여부"),
    include_affected: bool = Query(True, description="영향받은 리소스 포함 여부"),
    current_user: dict = Depends(get_current_user),
    history_service: HistoryService = Depends(get_history_service)
) -> CommitDetail:
    \"\"\"커밋 상세 정보 조회\"\"\"
    
    # 권한 확인
    require_permissions(current_user, ["audit:read", "history:read"])
    
    try:
        # 커밋 상세 조회
        result = await history_service.get_commit_detail(
            commit_hash=commit_hash,
            branch=branch,
            include_snapshot=include_snapshot,
            include_changes=include_changes,
            include_affected=include_affected,
            user_context=current_user
        )
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Commit {commit_hash} not found in branch {branch}"
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
            detail="Failed to retrieve commit details"
        )


@router.get(
    "/{commit_hash}/diff",
    summary="Get commit diff",
    description=\"\"\"
    두 커밋 간의 차이점을 조회합니다.
    
    **권한**: `audit:read` 또는 `history:read`
    \"\"\"
)
async def get_commit_diff(
    commit_hash: str,
    compare_with: Optional[str] = Query(None, description="비교할 커밋 (기본값: 이전 커밋)"),
    branch: str = Query("main", description="브랜치명"),
    format: str = Query("json", description="출력 형식 (json/text/unified)"),
    current_user: dict = Depends(get_current_user),
    history_service: HistoryService = Depends(get_history_service)
):
    \"\"\"커밋 차이점 조회\"\"\"
    
    # 권한 확인
    require_permissions(current_user, ["audit:read", "history:read"])
    
    try:
        diff_result = await history_service.get_commit_diff(
            commit_hash=commit_hash,
            compare_with=compare_with,
            branch=branch,
            format=format,
            user_context=current_user
        )
        
        return diff_result
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate diff"
        )


@router.get(
    "/statistics/summary",
    summary="Get history statistics",
    description=\"\"\"
    히스토리 통계 정보를 조회합니다.
    
    **권한**: `audit:read` 또는 `history:read`
    \"\"\"
)
async def get_history_statistics(
    branch: Optional[str] = Query(None, description="브랜치 필터"),
    from_date: Optional[str] = Query(None, description="시작 날짜"),
    to_date: Optional[str] = Query(None, description="종료 날짜"),
    group_by: str = Query("day", description="그룹화 기준 (hour/day/week/month)"),
    current_user: dict = Depends(get_current_user),
    history_service: HistoryService = Depends(get_history_service)
):
    \"\"\"히스토리 통계 조회\"\"\"
    
    # 권한 확인
    require_permissions(current_user, ["audit:read", "history:read"])
    
    try:
        stats = await history_service.get_statistics(
            branch=branch,
            from_date=from_date,
            to_date=to_date,
            group_by=group_by,
            user_context=current_user
        )
        
        return stats
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve statistics"
        )


@router.get(
    "/export",
    summary="Export history data",
    description=\"\"\"
    히스토리 데이터를 내보냅니다.
    
    **권한**: `audit:export` 또는 `history:export`
    
    **지원 형식**: CSV, JSON, Excel
    \"\"\"
)
async def export_history(
    format: str = Query("csv", description="내보내기 형식 (csv/json/xlsx)"),
    branch: Optional[str] = Query(None, description="브랜치 필터"),
    from_date: Optional[str] = Query(None, description="시작 날짜"),
    to_date: Optional[str] = Query(None, description="종료 날짜"),
    include_changes: bool = Query(False, description="상세 변경 내역 포함"),
    current_user: dict = Depends(get_current_user),
    history_service: HistoryService = Depends(get_history_service)
):
    \"\"\"히스토리 데이터 내보내기\"\"\"
    
    # 권한 확인
    require_permissions(current_user, ["audit:export", "history:export"])
    
    try:
        # 내보내기 파일 생성
        file_stream, filename, media_type = await history_service.export_history(
            format=format,
            branch=branch,
            from_date=from_date,
            to_date=to_date,
            include_changes=include_changes,
            user_context=current_user
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
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export history"
        )