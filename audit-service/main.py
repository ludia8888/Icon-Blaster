"""
Audit Service FastAPI Application
OMS에서 분리된 독립적인 감사 로그 서비스
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import history_router, audit_router, reports_router, health_router
from core.subscribers.oms_subscriber import start_oms_subscriber, stop_oms_subscriber
from utils.logger import get_logger

# 로거 설정
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 라이프사이클 관리"""
    # 시작 시
    logger.info("Starting Audit Service...")
    
    # OMS 이벤트 구독자 시작
    await start_oms_subscriber()
    
    # SIEM 연동 초기화
    # await initialize_siem_integration()
    
    logger.info("Audit Service started successfully")
    
    yield
    
    # 종료 시
    logger.info("Shutting down Audit Service...")
    
    # OMS 이벤트 구독자 중지
    await stop_oms_subscriber()
    
    logger.info("Audit Service shut down completed")


# FastAPI 앱 생성
app = FastAPI(
    title="Audit Service",
    description="OMS에서 분리된 독립적인 감사 로그 서비스",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS 미들웨어
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 제한 필요
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 전역 예외 처리기
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """전역 예외 처리"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred",
            "request_id": getattr(request.state, "request_id", None)
        }
    )


# 미들웨어: 요청 로깅
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """요청 로깅 미들웨어"""
    import uuid
    import time
    
    # 요청 ID 생성
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    # 요청 시작 시간
    start_time = time.time()
    
    # 요청 로깅
    logger.info(
        f"Request started",
        extra={
            "request_id": request_id,
            "method": request.method,
            "url": str(request.url),
            "client_ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent")
        }
    )
    
    # 요청 처리
    response = await call_next(request)
    
    # 응답 시간 계산
    process_time = time.time() - start_time
    
    # 응답 로깅
    logger.info(
        f"Request completed",
        extra={
            "request_id": request_id,
            "status_code": response.status_code,
            "process_time_ms": round(process_time * 1000, 2)
        }
    )
    
    # 응답 헤더에 요청 ID 추가
    response.headers["X-Request-ID"] = request_id
    
    return response


# 라우터 등록
app.include_router(health_router)
app.include_router(history_router)
app.include_router(audit_router)
app.include_router(reports_router)


# 루트 엔드포인트
@app.get("/")
async def root():
    """루트 엔드포인트"""
    return {
        "service": "Audit Service",
        "description": "OMS에서 분리된 독립적인 감사 로그 서비스",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/api/v1/health"
    }


# 서비스 정보 엔드포인트
@app.get("/info")
async def service_info():
    """서비스 정보"""
    return {
        "service": "audit-service",
        "version": "1.0.0",
        "description": "OMS에서 분리된 독립적인 감사 로그 서비스",
        "features": [
            "감사 로그 수집/저장",
            "감사 로그 조회/검색",
            "히스토리 조회/관리",
            "SIEM 통합",
            "규제 준수 리포트",
            "데이터 내보내기"
        ],
        "endpoints": {
            "health": "/api/v1/health",
            "history": "/api/v1/history",
            "audit": "/api/v1/audit",
            "reports": "/api/v1/reports"
        },
        "migrated_from": "oms-monolith/core/history",
        "msa_boundaries": {
            "responsibilities": [
                "감사 로그 수집/저장/조회",
                "SIEM 통합",
                "규제 준수 리포트",
                "히스토리 조회/관리"
            ],
            "not_responsible": [
                "스키마 변경 이벤트 발행 (OMS 담당)",
                "스키마 복원 (OMS 담당)",
                "스키마 메타데이터 관리 (OMS 담당)"
            ]
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    # 개발 서버 실행
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info"
    )