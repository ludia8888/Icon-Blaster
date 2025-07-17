"""
OMS (Ontology Management Service) 메인 애플리케이션
내부 ID 기반 핵심 온톨로지 관리 서비스
"""

from fastapi import FastAPI, HTTPException, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import json
from typing import Dict, List, Optional, Any
import logging
from contextlib import asynccontextmanager
import sys
import os

# shared 모델 import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from models.common import BaseResponse

# OMS 서비스 import
from services.async_terminus import AsyncTerminusService

# shared imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'shared'))
from utils.jsonld import JSONToJSONLDConverter
from models.config import ConnectionConfig

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 전역 서비스 인스턴스
terminus_service: Optional[AsyncTerminusService] = None
jsonld_converter: Optional[JSONToJSONLDConverter] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 생명주기 관리"""
    # 시작 시
    global terminus_service, jsonld_converter
    
    logger.info("OMS 서비스 초기화 중...")
    
    # 서비스 초기화
    connection_info = ConnectionConfig(
        server_url="http://localhost:6363",
        user="admin",
        account="admin",
        key="admin123"
    )
    
    terminus_service = AsyncTerminusService(connection_info)
    jsonld_converter = JSONToJSONLDConverter()
    
    # 의존성 설정
    from dependencies import set_services
    set_services(terminus_service, jsonld_converter)
    
    try:
        # TerminusDB 연결 테스트
        await terminus_service.connect()
        logger.info("TerminusDB 연결 성공")
    except Exception as e:
        logger.error(f"TerminusDB 연결 실패: {e}")
        # 연결 실패해도 서비스는 시작 (나중에 재연결 시도)
    
    yield
    
    # 종료 시
    logger.info("OMS 서비스 종료 중...")
    if terminus_service:
        await terminus_service.disconnect()

# FastAPI 앱 생성
app = FastAPI(
    title="Ontology Management Service (OMS)",
    description="내부 ID 기반 핵심 온톨로지 관리 서비스",
    version="1.0.0",
    lifespan=lifespan
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인만 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 에러 핸들러

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """FastAPI validation error를 400으로 변환"""
    logger.warning(f"Validation error: {exc}")
    
    # JSON parsing 오류인지 확인
    body_errors = [error for error in exc.errors() if error.get('type') == 'json_invalid']
    if body_errors:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "status": "error", 
                "message": "잘못된 JSON 형식입니다",
                "detail": "Invalid JSON format"
            }
        )
    
    # 기타 validation 오류는 400으로 변환
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "status": "error",
            "message": "입력 데이터 검증 실패",
            "detail": str(exc)
        }
    )

@app.exception_handler(json.JSONDecodeError)
async def json_decode_error_handler(request: Request, exc: json.JSONDecodeError):
    """JSON decode 오류를 400으로 처리"""
    logger.warning(f"JSON decode error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "status": "error",
            "message": "잘못된 JSON 형식입니다",
            "detail": f"JSON parsing failed: {str(exc)}"
        }
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"예상치 못한 오류 발생: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"status": "error", "message": "내부 서버 오류가 발생했습니다"}
    )

# API 엔드포인트
@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "message": "Ontology Management Service (OMS)",
        "version": "1.0.0",
        "description": "내부 ID 기반 핵심 온톨로지 관리 서비스",
        "features": [
            "내부 ID 기반 온톨로지 CRUD",
            "TerminusDB 직접 연동",
            "JSON-LD 변환",
            "버전 관리",
            "브랜치 관리"
        ]
    }

@app.get("/health")
async def health_check():
    """헬스 체크"""
    try:
        is_connected = await terminus_service.check_connection()
        
        return {
            "status": "healthy" if is_connected else "unhealthy",
            "service": "OMS",
            "terminus_connected": is_connected,
            "version": "1.0.0"
        }
    except Exception as e:
        logger.error(f"헬스 체크 실패: {e}")
        return {
            "status": "unhealthy",
            "service": "OMS",
            "terminus_connected": False,
            "error": str(e)
        }

# 라우터 등록
from routers import database, ontology, branch, version

app.include_router(database.router, prefix="/api/v1", tags=["database"])
app.include_router(ontology.router, prefix="/api/v1", tags=["ontology"])
app.include_router(branch.router, prefix="/api/v1", tags=["branch"])
app.include_router(version.router, prefix="/api/v1", tags=["version"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,  # BFF와 다른 포트
        reload=True,
        log_level="info"
    )