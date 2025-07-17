"""
헬스체크 및 기본 라우터
시스템 상태 확인을 위한 엔드포인트
"""

from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any
import logging

from dependencies import get_oms_client

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
async def health_check():
    """
    헬스체크 엔드포인트
    
    서비스와 데이터베이스 연결 상태를 확인합니다.
    """
    try:
        # OMS 연결 확인
        oms_client = get_oms_client()
        
        return {
            "status": "healthy",
            "service": "BFF",
            "oms_connected": True,
            "version": "2.0.0"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        
        # 서비스는 동작하지만 OMS 연결에 문제가 있는 경우
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unhealthy",
                "service": "BFF",
                "oms_connected": False,
                "error": str(e)
            }
        )