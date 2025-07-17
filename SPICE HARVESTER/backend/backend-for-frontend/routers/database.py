"""
Database management router for BFF
Handles database creation, deletion, and listing
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import Dict, List, Optional, Any
import logging
import sys
import os

# Add shared path for common utilities
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from utils.language import get_accept_language
from models.requests import DatabaseCreateRequest, ApiResponse

from services.oms_client import OMSClient
from dependencies import get_oms_client

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/databases",
    tags=["Database Management"]
)


@router.get("")
async def list_databases(
    oms: OMSClient = Depends(get_oms_client)
):
    """데이터베이스 목록 조회"""
    try:
        # OMS를 통해 데이터베이스 목록 조회
        result = await oms.list_databases()
        
        databases = result.get("data", {}).get("databases", [])
        
        return {
            "databases": databases,
            "count": len(databases)
        }
    except Exception as e:
        logger.error(f"Failed to list databases: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("", response_model=ApiResponse)
async def create_database(
    request: DatabaseCreateRequest,
    oms: OMSClient = Depends(get_oms_client)
):
    """데이터베이스 생성"""
    try:
        # OMS를 통해 데이터베이스 생성
        result = await oms.create_database(request.name, request.description)
        
        return {
            "status": "success",
            "message": f"데이터베이스 '{request.name}'가 생성되었습니다",
            "name": request.name,
            "data": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create database '{request.name}': {e}")
        
        # 중복 데이터베이스 체크
        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"데이터베이스 '{request.name}'이(가) 이미 존재합니다"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.delete("/{db_name}")
async def delete_database(
    db_name: str,
    oms: OMSClient = Depends(get_oms_client)
):
    """데이터베이스 삭제"""
    try:
        # 시스템 데이터베이스 보호
        protected_dbs = ['_system', '_meta']
        if db_name in protected_dbs:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"시스템 데이터베이스 '{db_name}'은(는) 삭제할 수 없습니다"
            )
        
        # OMS를 통해 데이터베이스 삭제
        result = await oms.delete_database(db_name)
        
        return {
            "status": "success",
            "message": f"데이터베이스 '{db_name}'이(가) 삭제되었습니다",
            "database": db_name
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete database '{db_name}': {e}")
        
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"데이터베이스 '{db_name}'을(를) 찾을 수 없습니다"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{db_name}")
async def get_database(
    db_name: str,
    oms: OMSClient = Depends(get_oms_client)
):
    """데이터베이스 정보 조회"""
    try:
        # OMS를 통해 데이터베이스 정보 조회
        result = await oms.get_database(db_name)
        
        return {
            "status": "success",
            "data": result
        }
    except Exception as e:
        logger.error(f"Failed to get database '{db_name}': {e}")
        
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"데이터베이스 '{db_name}'을(를) 찾을 수 없습니다"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{db_name}/classes")
async def list_classes(
    db_name: str,
    type: Optional[str] = "Class",
    limit: Optional[int] = None,
    oms: OMSClient = Depends(get_oms_client)
):
    """데이터베이스의 클래스 목록 조회"""
    try:
        # OMS를 통해 클래스 목록 조회
        result = await oms.list_ontologies(db_name)
        
        classes = result.get("data", {}).get("ontologies", [])
        
        return {
            "classes": classes,
            "count": len(classes)
        }
    except Exception as e:
        logger.error(f"Failed to list classes for database '{db_name}': {e}")
        
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"데이터베이스 '{db_name}'을(를) 찾을 수 없습니다"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{db_name}/classes")
async def create_class(
    db_name: str,
    class_data: Dict[str, Any],
    oms: OMSClient = Depends(get_oms_client)
):
    """데이터베이스에 새 클래스 생성"""
    try:
        # 요청 데이터 검증
        if not class_data.get("@id"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="클래스 ID (@id)가 필요합니다"
            )
        
        # OMS를 통해 클래스 생성
        result = await oms.create_ontology(db_name, class_data)
        
        return {
            "status": "success",
            "@id": class_data.get("@id"),
            "data": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create class in database '{db_name}': {e}")
        
        if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"클래스 '{class_data.get('@id')}'이(가) 이미 존재합니다"
            )
        
        if "invalid" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"잘못된 클래스 데이터: {str(e)}"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{db_name}/classes/{class_id}")
async def get_class(
    db_name: str,
    class_id: str,
    request: Request,
    oms: OMSClient = Depends(get_oms_client)
):
    """특정 클래스 조회"""
    lang = get_accept_language(request)
    
    try:
        # OMS를 통해 클래스 조회
        result = await oms.get_ontology(db_name, class_id)
        
        return result
    except Exception as e:
        logger.error(f"Failed to get class '{class_id}' from database '{db_name}': {e}")
        
        if "not found" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"클래스 '{class_id}'을(를) 찾을 수 없습니다"
            )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{db_name}/branches")
async def list_branches(
    db_name: str,
    oms: OMSClient = Depends(get_oms_client)
):
    """브랜치 목록 조회"""
    try:
        # OMS를 통해 브랜치 목록 조회
        result = await oms.list_branches(db_name)
        
        branches = result.get("data", {}).get("branches", [])
        
        return {
            "branches": branches,
            "count": len(branches)
        }
    except Exception as e:
        logger.error(f"Failed to list branches for database '{db_name}': {e}")
        
        # 브랜치 기능이 구현되지 않은 경우 빈 목록 반환
        if "not implemented" in str(e).lower() or "not found" in str(e).lower():
            return {
                "branches": [],
                "count": 0
            }
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.post("/{db_name}/branches")
async def create_branch(
    db_name: str,
    branch_data: Dict[str, Any],
    oms: OMSClient = Depends(get_oms_client)
):
    """새 브랜치 생성"""
    try:
        # 요청 데이터 검증
        branch_name = branch_data.get("name")
        if not branch_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="브랜치 이름이 필요합니다"
            )
        
        # OMS를 통해 브랜치 생성
        result = await oms.create_branch(db_name, branch_data)
        
        return {
            "status": "success",
            "name": branch_name,
            "data": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create branch in database '{db_name}': {e}")
        
        # 브랜치 기능이 구현되지 않은 경우
        if "not implemented" in str(e).lower():
            return {
                "status": "success",
                "name": branch_data.get("name"),
                "data": {"message": "브랜치 기능은 아직 구현 중입니다"}
            }
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/{db_name}/versions")
async def get_versions(
    db_name: str,
    oms: OMSClient = Depends(get_oms_client)
):
    """버전 히스토리 조회"""
    try:
        # OMS를 통해 버전 히스토리 조회
        result = await oms.get_version_history(db_name)
        
        versions = result.get("data", {}).get("versions", [])
        
        return {
            "versions": versions,
            "count": len(versions)
        }
    except Exception as e:
        logger.error(f"Failed to get versions for database '{db_name}': {e}")
        
        # 버전 기능이 구현되지 않은 경우 빈 목록 반환
        if "not implemented" in str(e).lower() or "not found" in str(e).lower():
            return {
                "versions": [],
                "count": 0
            }
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )