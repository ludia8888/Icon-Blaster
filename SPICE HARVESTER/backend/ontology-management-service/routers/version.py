"""
버전 관리 라우터
커밋, 히스토리, 머지, 롤백 등을 담당
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
import logging

from services.async_terminus import AsyncTerminusService
from dependencies import get_terminus_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/database/{db_name}",
    tags=["Version Control"]
)


class CommitRequest(BaseModel):
    """커밋 요청"""
    message: str
    author: Optional[str] = "admin"
    
    class Config:
        schema_extra = {
            "example": {
                "message": "Add new product ontology",
                "author": "admin"
            }
        }


class MergeRequest(BaseModel):
    """머지 요청"""
    source_branch: str
    target_branch: Optional[str] = None  # None이면 현재 브랜치
    strategy: str = "auto"  # "auto", "ours", "theirs"
    
    class Config:
        schema_extra = {
            "example": {
                "source_branch": "feature/new-ontology",
                "target_branch": "main",
                "strategy": "auto"
            }
        }


class RollbackRequest(BaseModel):
    """롤백 요청"""
    target: str  # 커밋 ID 또는 상대 참조 (예: HEAD~1)
    
    class Config:
        schema_extra = {
            "example": {
                "target": "HEAD~1"
            }
        }


@router.post("/commit")
async def create_commit(
    db_name: str,
    request: CommitRequest,
    terminus: AsyncTerminusService = Depends(get_terminus_service)
):
    """
    변경사항 커밋
    
    현재 브랜치의 변경사항을 커밋합니다.
    """
    try:
        # 커밋 메시지 검증
        if not request.message:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="커밋 메시지는 필수입니다"
            )
        
        # 커밋 생성
        commit_id = terminus.commit(
            db_name,
            message=request.message,
            author=request.author
        )
        
        return {
            "message": "커밋이 생성되었습니다",
            "commit_id": commit_id,
            "author": request.author,
            "commit_message": request.message
        }
        
    except Exception as e:
        logger.error(f"Failed to create commit: {e}")
        
        if "no changes" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="커밋할 변경사항이 없습니다"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"커밋 생성 실패: {str(e)}"
        )


@router.get("/history")
async def get_commit_history(
    db_name: str,
    branch: Optional[str] = Query(None, description="브랜치 이름"),
    limit: int = Query(10, description="조회할 커밋 수"),
    offset: int = Query(0, description="오프셋"),
    terminus: AsyncTerminusService = Depends(get_terminus_service)
):
    """
    커밋 히스토리 조회
    
    브랜치의 커밋 히스토리를 조회합니다.
    """
    try:
        # 브랜치가 지정되지 않으면 현재 브랜치 사용
        if not branch:
            branch = terminus.get_current_branch(db_name)
        
        # 히스토리 조회
        history = terminus.get_commit_history(
            db_name,
            branch=branch,
            limit=limit,
            offset=offset
        )
        
        return {
            "branch": branch,
            "commits": history,
            "total": len(history),
            "limit": limit,
            "offset": offset
        }
        
    except Exception as e:
        logger.error(f"Failed to get commit history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"커밋 히스토리 조회 실패: {str(e)}"
        )


@router.get("/diff")
async def get_diff(
    db_name: str,
    from_ref: str = Query(..., description="시작 참조 (브랜치 또는 커밋)"),
    to_ref: str = Query("HEAD", description="끝 참조 (브랜치 또는 커밋)"),
    terminus: AsyncTerminusService = Depends(get_terminus_service)
):
    """
    차이점 조회
    
    두 참조 간의 차이점을 조회합니다.
    """
    try:
        # 차이점 조회
        diff = terminus.diff(db_name, from_ref, to_ref)
        
        return {
            "from": from_ref,
            "to": to_ref,
            "changes": diff,
            "summary": {
                "added": len([c for c in diff if c.get("type") == "added"]),
                "modified": len([c for c in diff if c.get("type") == "modified"]),
                "deleted": len([c for c in diff if c.get("type") == "deleted"])
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get diff: {e}")
        
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="참조를 찾을 수 없습니다"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"차이점 조회 실패: {str(e)}"
        )


@router.post("/merge")
async def merge_branches(
    db_name: str,
    request: MergeRequest,
    terminus: AsyncTerminusService = Depends(get_terminus_service)
):
    """
    브랜치 머지
    
    소스 브랜치를 대상 브랜치로 머지합니다.
    """
    try:
        # 대상 브랜치가 지정되지 않으면 현재 브랜치 사용
        target_branch = request.target_branch
        if not target_branch:
            target_branch = terminus.get_current_branch(db_name)
        
        # 같은 브랜치 머지 방지
        if request.source_branch == target_branch:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="소스와 대상 브랜치가 동일합니다"
            )
        
        # 머지 실행
        result = terminus.merge(
            db_name,
            source_branch=request.source_branch,
            target_branch=target_branch,
            strategy=request.strategy
        )
        
        return {
            "message": f"브랜치 '{request.source_branch}'을(를) '{target_branch}'(으)로 머지했습니다",
            "source_branch": request.source_branch,
            "target_branch": target_branch,
            "strategy": request.strategy,
            "conflicts": result.get("conflicts", []),
            "merged": result.get("merged", True)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to merge branches: {e}")
        
        if "conflict" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="머지 충돌이 발생했습니다. 수동으로 해결해야 합니다"
            )
        
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="브랜치를 찾을 수 없습니다"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"브랜치 머지 실패: {str(e)}"
        )


@router.post("/rollback")
async def rollback(
    db_name: str,
    request: RollbackRequest,
    terminus: AsyncTerminusService = Depends(get_terminus_service)
):
    """
    변경사항 롤백
    
    지정된 커밋으로 롤백합니다.
    """
    try:
        # 롤백 실행
        terminus.rollback(db_name, request.target)
        
        return {
            "message": f"'{request.target}'(으)로 롤백했습니다",
            "target": request.target,
            "current_branch": terminus.get_current_branch(db_name)
        }
        
    except Exception as e:
        logger.error(f"Failed to rollback: {e}")
        
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"대상 '{request.target}'을(를) 찾을 수 없습니다"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"롤백 실패: {str(e)}"
        )


@router.post("/rebase")
async def rebase_branch(
    db_name: str,
    onto: str = Query(..., description="리베이스 대상 브랜치"),
    branch: Optional[str] = Query(None, description="리베이스할 브랜치 (기본: 현재 브랜치)"),
    terminus: AsyncTerminusService = Depends(get_terminus_service)
):
    """
    브랜치 리베이스
    
    브랜치를 다른 브랜치 위로 리베이스합니다.
    """
    try:
        # 브랜치가 지정되지 않으면 현재 브랜치 사용
        if not branch:
            branch = terminus.get_current_branch(db_name)
        
        # 같은 브랜치 리베이스 방지
        if branch == onto:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="리베이스 대상과 브랜치가 동일합니다"
            )
        
        # 리베이스 실행
        result = terminus.rebase(db_name, onto=onto, branch=branch)
        
        return {
            "message": f"브랜치 '{branch}'을(를) '{onto}' 위로 리베이스했습니다",
            "branch": branch,
            "onto": onto,
            "success": True
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to rebase: {e}")
        
        if "conflict" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="리베이스 충돌이 발생했습니다"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"리베이스 실패: {str(e)}"
        )