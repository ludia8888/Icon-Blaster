"""
헬스체크 및 기본 라우터
시스템 상태 확인을 위한 엔드포인트
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any
import logging

from container import get_database_service
from services.core.interfaces import IDatabaseService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


@router.get("/")
async def root():
    """
    루트 엔드포인트
    
    서비스 기본 정보를 반환합니다.
    """
    return {
        "service": "Ontology BFF Service",
        "version": "2.0.0",
        "description": "도메인 독립적인 온톨로지 관리 서비스"
    }


@router.get("/health")
async def health_check(database_service: IDatabaseService = Depends(get_database_service)):
    """
    헬스체크 엔드포인트
    
    서비스와 데이터베이스 연결 상태를 확인합니다.
    """
    try:
        # TerminusDB 연결 확인
        databases = database_service.list_databases()
        
        return {
            "status": "healthy",
            "database": {
                "connected": True,
                "databases_count": len(databases)
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        
        # 서비스는 동작하지만 DB 연결에 문제가 있는 경우
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unhealthy",
                "database": {
                    "connected": False,
                    "error": str(e)
                }
            }
        )