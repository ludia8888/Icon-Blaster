"""
데이터베이스 관리 라우터
데이터베이스 생성, 삭제, 목록 조회 등을 담당
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, List, Any
import logging
import sys
import os

# Add shared security module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from security.input_sanitizer import (
    validate_db_name, 
    sanitize_input,
    SecurityViolationError
)

from services.async_terminus import AsyncTerminusService
from dependencies import get_terminus_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/database",
    tags=["Database Management"]
)


@router.get("/list")
async def list_databases(
    terminus_service: AsyncTerminusService = Depends(get_terminus_service)
):
    """
    데이터베이스 목록 조회
    
    모든 데이터베이스의 이름 목록을 반환합니다.
    """
    try:
        databases = await terminus_service.list_databases()
        return {
            "status": "success",
            "data": {"databases": databases}
        }
    except Exception as e:
        logger.error(f"Failed to list databases: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"데이터베이스 목록 조회 실패: {str(e)}"
        )


@router.post("/create")
async def create_database(
    request: dict,
    terminus_service: AsyncTerminusService = Depends(get_terminus_service)
):
    """
    새 데이터베이스 생성
    
    지정된 이름으로 새 데이터베이스를 생성합니다.
    """
    try:
        # 입력 데이터 보안 검증 및 정화
        sanitized_request = sanitize_input(request)
        
        # 요청 데이터 검증
        db_name = sanitized_request.get("name")
        if not db_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="데이터베이스 이름이 필요합니다"
            )
        
        # 데이터베이스 이름 보안 검증
        db_name = validate_db_name(db_name)
        
        # 설명 정화
        description = sanitized_request.get("description")
        if description and len(description) > 500:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="설명이 너무 깁니다 (500자 이하)"
            )
        
        # 데이터베이스 생성
        result = await terminus_service.create_database(db_name, description=description)
        
        return {
            "status": "success",
            "message": f"데이터베이스 '{db_name}'이(가) 생성되었습니다",
            "data": result
        }
    except SecurityViolationError as e:
        logger.warning(f"Security violation in create_database: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="입력 데이터에 보안 위반이 감지되었습니다"
        )
    except HTTPException:
        raise
    except Exception as e:
        # 변수를 안전하게 처리
        db_name_for_error = "unknown"
        try:
            db_name_for_error = validate_db_name(request.get("name", "unknown"))
        except (ValueError, KeyError):
            # 검증 실패시 기본값 사용
            pass
        except Exception as validation_error:
            logger.debug(f"Error validating db_name for error message: {validation_error}")
        
        logger.error(f"Failed to create database '{db_name_for_error}': {e}")
        
        # Import the exception class for proper type checking
        from services.async_terminus import AsyncDuplicateOntologyError
        
        if isinstance(e, AsyncDuplicateOntologyError) or "already exists" in str(e).lower() or "이미 존재합니다" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="데이터베이스가 이미 존재합니다"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"데이터베이스 생성 실패: {str(e)}"
        )


@router.delete("/{db_name}")
async def delete_database(
    db_name: str,
    terminus_service: AsyncTerminusService = Depends(get_terminus_service)
):
    """
    데이터베이스 삭제
    
    지정된 데이터베이스를 삭제합니다.
    주의: 이 작업은 되돌릴 수 없습니다!
    """
    try:
        # 입력 데이터 보안 검증
        db_name = validate_db_name(db_name)
        
        # 시스템 데이터베이스 보호
        protected_dbs = ['_system', '_meta']
        if db_name in protected_dbs:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"시스템 데이터베이스 '{db_name}'은(는) 삭제할 수 없습니다"
            )
        
        # 데이터베이스 존재 확인
        if not await terminus_service.database_exists(db_name):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"데이터베이스 '{db_name}'을(를) 찾을 수 없습니다"
            )
        
        # 데이터베이스 삭제 실행
        await terminus_service.delete_database(db_name)
        
        return {
            "status": "success",
            "message": f"데이터베이스 '{db_name}'이(가) 삭제되었습니다",
            "database": db_name
        }
    except SecurityViolationError as e:
        logger.warning(f"Security violation in delete_database: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="입력 데이터에 보안 위반이 감지되었습니다"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete database '{db_name}': {e}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"데이터베이스 삭제 실패: {str(e)}"
        )


@router.get("/exists/{db_name}")
async def database_exists(
    db_name: str,
    terminus_service: AsyncTerminusService = Depends(get_terminus_service)
):
    """
    데이터베이스 존재 여부 확인
    
    지정된 데이터베이스가 존재하는지 확인합니다.
    존재하지 않으면 404를 반환합니다.
    """
    try:
        # 입력 데이터 보안 검증
        db_name = validate_db_name(db_name)
        
        exists = await terminus_service.database_exists(db_name)
        if not exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"데이터베이스 '{db_name}'을(를) 찾을 수 없습니다"
            )
        
        return {
            "status": "success",
            "data": {"exists": True}
        }
    except SecurityViolationError as e:
        logger.warning(f"Security violation in database_exists: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="입력 데이터에 보안 위반이 감지되었습니다"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to check database existence for '{db_name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"데이터베이스 존재 확인 실패: {str(e)}"
        )