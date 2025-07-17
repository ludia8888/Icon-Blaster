"""
버전 관리 라우터
커밋, 히스토리, 머지, 롤백 등을 담당
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Dict, List, Optional, Any
from pydantic import BaseModel
import logging
import sys
import os

# Add shared security module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from security.input_sanitizer import (
    validate_db_name, 
    validate_branch_name, 
    sanitize_input,
    SecurityViolationError
)

from services.async_terminus import AsyncTerminusService
from dependencies import get_terminus_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/version/{db_name}",
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
        # 입력 데이터 보안 검증
        db_name = validate_db_name(db_name)
        
        # 요청 데이터 정화
        sanitized_data = sanitize_input(request.dict())
        
        # 커밋 메시지 검증
        if not sanitized_data.get("message"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="커밋 메시지는 필수입니다"
            )
        
        # 커밋 생성
        commit_id = await terminus.commit(
            db_name,
            message=sanitized_data["message"],
            author=sanitized_data.get("author", "admin")
        )
        
        return {
            "message": "커밋이 생성되었습니다",
            "commit_id": commit_id,
            "author": request.author,
            "commit_message": request.message
        }
        
    except SecurityViolationError as e:
        logger.warning(f"Security violation in create_commit: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="입력 데이터에 보안 위반이 감지되었습니다"
        )
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
        # 입력 데이터 보안 검증
        db_name = validate_db_name(db_name)
        
        # 브랜치 이름 검증 (지정된 경우)
        if branch:
            branch = validate_branch_name(branch)
        
        # 페이징 파라미터 검증
        if limit < 1 or limit > 1000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="limit은 1-1000 범위여야 합니다"
            )
        if offset < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="offset은 0 이상이어야 합니다"
            )
        
        # 브랜치가 지정되지 않으면 현재 브랜치 사용
        if not branch:
            branch = await terminus.get_current_branch(db_name)
        
        # 히스토리 조회
        history = await terminus.get_commit_history(
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
        
    except SecurityViolationError as e:
        logger.warning(f"Security violation in get_commit_history: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="입력 데이터에 보안 위반이 감지되었습니다"
        )
    except HTTPException:
        raise
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
        # 입력 데이터 보안 검증
        db_name = validate_db_name(db_name)
        from_ref = sanitize_input(from_ref)
        to_ref = sanitize_input(to_ref)
        
        # 참조 길이 검증
        if len(from_ref) > 100 or len(to_ref) > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="참조 이름이 너무 깁니다"
            )
        
        # 차이점 조회
        diff = await terminus.diff(db_name, from_ref, to_ref)
        
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
        
    except SecurityViolationError as e:
        logger.warning(f"Security violation in get_diff: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="입력 데이터에 보안 위반이 감지되었습니다"
        )
    except HTTPException:
        raise
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
        # 입력 데이터 보안 검증
        db_name = validate_db_name(db_name)
        
        # 요청 데이터 정화
        sanitized_data = sanitize_input(request.dict())
        
        # 브랜치 이름 검증
        source_branch = validate_branch_name(sanitized_data["source_branch"])
        target_branch = sanitized_data.get("target_branch")
        if target_branch:
            target_branch = validate_branch_name(target_branch)
        
        # 대상 브랜치가 지정되지 않으면 현재 브랜치 사용
        if not target_branch:
            target_branch = await terminus.get_current_branch(db_name)
        
        # 같은 브랜치 머지 방지
        if source_branch == target_branch:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="소스와 대상 브랜치가 동일합니다"
            )
        
        # 머지 전략 검증
        allowed_strategies = ["auto", "ours", "theirs"]
        strategy = sanitized_data.get("strategy", "auto")
        if strategy not in allowed_strategies:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"잘못된 머지 전략입니다. 허용된 값: {allowed_strategies}"
            )
        
        # 머지 실행
        result = await terminus.merge(
            db_name,
            source_branch=source_branch,
            target_branch=target_branch,
            strategy=strategy
        )
        
        return {
            "message": f"브랜치 '{source_branch}'을(를) '{target_branch}'(으)로 머지했습니다",
            "source_branch": source_branch,
            "target_branch": target_branch,
            "strategy": strategy,
            "conflicts": result.get("conflicts", []),
            "merged": result.get("merged", True)
        }
        
    except SecurityViolationError as e:
        logger.warning(f"Security violation in merge_branches: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="입력 데이터에 보안 위반이 감지되었습니다"
        )
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
        # 입력 데이터 보안 검증
        db_name = validate_db_name(db_name)
        
        # 요청 데이터 정화
        sanitized_data = sanitize_input(request.dict())
        target = sanitized_data["target"]
        
        # 타겟 검증
        if len(target) > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="롤백 타겟이 너무 깁니다"
            )
        
        # 롤백 실행
        await terminus.rollback(db_name, target)
        
        return {
            "message": f"'{target}'(으)로 롤백했습니다",
            "target": target,
            "current_branch": await terminus.get_current_branch(db_name)
        }
        
    except SecurityViolationError as e:
        logger.warning(f"Security violation in rollback: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="입력 데이터에 보안 위반이 감지되었습니다"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to rollback: {e}")
        
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"대상을 찾을 수 없습니다"
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
        # 입력 데이터 보안 검증
        db_name = validate_db_name(db_name)
        onto = validate_branch_name(onto)
        
        if branch:
            branch = validate_branch_name(branch)
        
        # 브랜치가 지정되지 않으면 현재 브랜치 사용
        if not branch:
            branch = await terminus.get_current_branch(db_name)
            branch = validate_branch_name(branch)
        
        # 같은 브랜치 리베이스 방지
        if branch == onto:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="리베이스 대상과 브랜치가 동일합니다"
            )
        
        # 리베이스 실행
        result = await terminus.rebase(db_name, onto=onto, branch=branch)
        
        return {
            "message": f"브랜치 '{branch}'을(를) '{onto}' 위로 리베이스했습니다",
            "branch": branch,
            "onto": onto,
            "success": True
        }
        
    except SecurityViolationError as e:
        logger.warning(f"Security violation in rebase_branch: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="입력 데이터에 보안 위반이 감지되었습니다"
        )
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