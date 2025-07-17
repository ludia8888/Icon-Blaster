"""
브랜치 관리 라우터
브랜치 생성, 삭제, 체크아웃 등을 담당
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
    prefix="/branch/{db_name}",
    tags=["Branch Management"]
)


class BranchCreateRequest(BaseModel):
    """브랜치 생성 요청"""
    branch_name: str
    from_branch: Optional[str] = None
    
    class Config:
        schema_extra = {
            "example": {
                "branch_name": "feature/new-ontology",
                "from_branch": "main"
            }
        }


class CheckoutRequest(BaseModel):
    """체크아웃 요청"""
    target: str
    target_type: str = "branch"  # "branch" 또는 "commit"
    
    class Config:
        schema_extra = {
            "example": {
                "target": "develop",
                "target_type": "branch"
            }
        }


@router.get("/list")
async def list_branches(
    db_name: str,
    terminus: AsyncTerminusService = Depends(get_terminus_service)
):
    """
    브랜치 목록 조회
    
    데이터베이스의 모든 브랜치 목록을 조회합니다.
    """
    try:
        # 입력 데이터 보안 검증
        db_name = validate_db_name(db_name)
        
        branches = await terminus.list_branches(db_name)
        current_branch = await terminus.get_current_branch(db_name)
        
        # 브랜치 정보 구성
        branch_info = []
        for branch in branches:
            info = {
                "name": branch,
                "current": branch == current_branch
            }
            
            # 추가 정보 (커밋 수 등) 조회 가능
            branch_info.append(info)
        
        return {
            "branches": branch_info,
            "current": current_branch,
            "total": len(branch_info)
        }
        
    except SecurityViolationError as e:
        logger.warning(f"Security violation in list_branches: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="입력 데이터에 보안 위반이 감지되었습니다"
        )
    except Exception as e:
        logger.error(f"Failed to list branches: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"브랜치 목록 조회 실패: {str(e)}"
        )


@router.post("/create")
async def create_branch(
    db_name: str,
    request: BranchCreateRequest,
    terminus: AsyncTerminusService = Depends(get_terminus_service)
):
    """
    새 브랜치 생성
    
    현재 브랜치 또는 지정된 브랜치에서 새 브랜치를 생성합니다.
    """
    try:
        # 입력 데이터 보안 검증
        db_name = validate_db_name(db_name)
        
        # 요청 데이터 정화
        sanitized_data = sanitize_input(request.dict())
        
        # 브랜치 이름 유효성 검증
        branch_name = sanitized_data.get("branch_name")
        if not branch_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="브랜치 이름은 필수입니다"
            )
        
        # 브랜치 이름 보안 검증
        branch_name = validate_branch_name(branch_name)
        
        # from_branch 검증
        from_branch = sanitized_data.get("from_branch")
        if from_branch:
            from_branch = validate_branch_name(from_branch)
        
        # 브랜치 생성
        await terminus.create_branch(
            db_name, 
            branch_name,
            from_branch=from_branch
        )
        
        return {
            "message": f"브랜치 '{branch_name}'이(가) 생성되었습니다",
            "branch": branch_name,
            "from_branch": from_branch or await terminus.get_current_branch(db_name)
        }
        
    except SecurityViolationError as e:
        logger.warning(f"Security violation in create_branch: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="입력 데이터에 보안 위반이 감지되었습니다"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create branch: {e}")
        
        if "already exists" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"브랜치가 이미 존재합니다"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"브랜치 생성 실패: {str(e)}"
        )


@router.delete("/branch/{branch_name}")
async def delete_branch(
    db_name: str,
    branch_name: str,
    force: bool = Query(False, description="강제 삭제 여부"),
    terminus: AsyncTerminusService = Depends(get_terminus_service)
):
    """
    브랜치 삭제
    
    지정된 브랜치를 삭제합니다.
    """
    try:
        # 입력 데이터 보안 검증
        db_name = validate_db_name(db_name)
        branch_name = validate_branch_name(branch_name)
        
        # 보호된 브랜치 확인
        protected_branches = ['main', 'master', 'production']
        if branch_name in protected_branches and not force:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"보호된 브랜치 '{branch_name}'은(는) 삭제할 수 없습니다. 강제 삭제를 원하면 force=true를 사용하세요"
            )
        
        # 현재 브랜치 확인
        current_branch = await terminus.get_current_branch(db_name)
        if branch_name == current_branch:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="현재 체크아웃된 브랜치는 삭제할 수 없습니다"
            )
        
        # 브랜치 삭제
        await terminus.delete_branch(db_name, branch_name)
        
        return {
            "message": f"브랜치 '{branch_name}'이(가) 삭제되었습니다",
            "branch": branch_name
        }
        
    except SecurityViolationError as e:
        logger.warning(f"Security violation in delete_branch: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="입력 데이터에 보안 위반이 감지되었습니다"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete branch: {e}")
        
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"브랜치 '{branch_name}'을(를) 찾을 수 없습니다"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"브랜치 삭제 실패: {str(e)}"
        )


@router.post("/checkout")
async def checkout(
    db_name: str,
    request: CheckoutRequest,
    terminus: AsyncTerminusService = Depends(get_terminus_service)
):
    """
    브랜치 또는 커밋 체크아웃
    
    지정된 브랜치나 커밋으로 체크아웃합니다.
    """
    try:
        # 입력 데이터 보안 검증
        db_name = validate_db_name(db_name)
        
        # 요청 데이터 정화
        sanitized_data = sanitize_input(request.dict())
        
        target = sanitized_data["target"]
        target_type = sanitized_data.get("target_type", "branch")
        
        # 타겟 타입 검증
        allowed_types = ["branch", "commit"]
        if target_type not in allowed_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"잘못된 타겟 타입입니다. 허용된 값: {allowed_types}"
            )
        
        # 브랜치인 경우 이름 검증
        if target_type == "branch":
            target = validate_branch_name(target)
        else:
            # 커밋 ID인 경우 기본 정화
            target = sanitize_input(target)
            if len(target) > 100:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="커밋 ID가 너무 깁니다"
                )
        
        # 체크아웃 실행
        await terminus.checkout(db_name, target, target_type)
        
        # 현재 브랜치 확인
        current_branch = await terminus.get_current_branch(db_name)
        
        return {
            "message": f"{target_type} '{target}'(으)로 체크아웃했습니다",
            "target": target,
            "target_type": target_type,
            "current_branch": current_branch
        }
        
    except SecurityViolationError as e:
        logger.warning(f"Security violation in checkout: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="입력 데이터에 보안 위반이 감지되었습니다"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to checkout: {e}")
        
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="브랜치 또는 커밋을 찾을 수 없습니다"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"체크아웃 실패: {str(e)}"
        )


@router.get("/branch/{branch_name}/info")
async def get_branch_info(
    db_name: str,
    branch_name: str,
    terminus: AsyncTerminusService = Depends(get_terminus_service)
):
    """
    브랜치 정보 조회
    
    특정 브랜치의 상세 정보를 조회합니다.
    """
    try:
        # 입력 데이터 보안 검증
        db_name = validate_db_name(db_name)
        branch_name = validate_branch_name(branch_name)
        
        # 브랜치 존재 확인
        branches = await terminus.list_branches(db_name)
        if branch_name not in branches:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"브랜치 '{branch_name}'을(를) 찾을 수 없습니다"
            )
        
        # 현재 브랜치 확인
        current_branch = await terminus.get_current_branch(db_name)
        
        # 브랜치 정보 구성
        info = {
            "name": branch_name,
            "current": branch_name == current_branch,
            "protected": branch_name in ['main', 'master', 'production']
        }
        
        # 추가 정보 조회 가능 (커밋 히스토리, 통계 등)
        
        return info
        
    except SecurityViolationError as e:
        logger.warning(f"Security violation in get_branch_info: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="입력 데이터에 보안 위반이 감지되었습니다"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get branch info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"브랜치 정보 조회 실패: {str(e)}"
        )