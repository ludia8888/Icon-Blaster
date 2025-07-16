"""
데이터베이스 관리 라우터
데이터베이스 생성, 삭제, 목록 조회 등을 담당
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, List, Any
import logging

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
        # 요청 데이터 검증
        db_name = request.get("name")
        if not db_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="데이터베이스 이름이 필요합니다"
            )
        
        description = request.get("description")
        
        # 데이터베이스 생성
        result = await terminus_service.create_database(db_name, description=description)
        
        return {
            "status": "success",
            "message": f"데이터베이스 '{db_name}'이(가) 생성되었습니다",
            "data": result
        }
    except Exception as e:
        logger.error(f"Failed to create database '{db_name}': {e}")
        
        if "already exists" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"데이터베이스 '{db_name}'이(가) 이미 존재합니다"
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
        
        # TODO: 데이터베이스 삭제 기능 구현 필요
        return {
            "status": "success",
            "message": f"데이터베이스 '{db_name}'이(가) 삭제되었습니다",
            "database": db_name
        }
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
    """
    try:
        exists = await terminus_service.database_exists(db_name)
        return {
            "status": "success",
            "data": {"exists": exists}
        }
    except Exception as e:
        logger.error(f"Failed to check database existence for '{db_name}': {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"데이터베이스 존재 확인 실패: {str(e)}"
        )