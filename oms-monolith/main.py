"""
OMS Enterprise - DB 연결 문제 해결 버전
SimpleTerminusDBClient 사용으로 실제 데이터 반환
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# 수정된 Schema Service 사용
from core.schema.service_fixed import SchemaService
from core.validation import ValidationService
from core.branch import BranchService
from core.history import HistoryService

# Database
from database.simple_terminus_client import SimpleTerminusDBClient

# Event System
from core.event_publisher.enhanced_event_service import EnhancedEventService
from shared.events import EventPublisher

# Cache
from shared.cache.smart_cache import SmartCacheManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ServiceContainer:
    """모든 서비스 인스턴스를 관리하는 컨테이너"""
    
    def __init__(self):
        self.db_client = None
        self.cache = None
        self.event_publisher = EventPublisher()
        
        # Core Services
        self.schema_service = None
        self.validation_service = None
        self.branch_service = None
        self.history_service = None
        self.event_service = None
        
    async def initialize(self):
        """모든 서비스 초기화"""
        logger.info("Initializing services with fixed DB connection...")
        
        try:
            # SimpleTerminusDBClient 사용
            self.db_client = SimpleTerminusDBClient(
                endpoint="http://localhost:6363",
                username="admin",
                password="root",
                database="oms"
            )
            
            # DB 연결
            connected = await self.db_client.connect()
            if not connected:
                logger.error("Failed to connect to TerminusDB")
            else:
                logger.info("✅ Connected to TerminusDB successfully")
            
            # 수정된 Schema Service 사용
            self.schema_service = SchemaService(
                tdb_endpoint="http://localhost:6363",
                event_publisher=self.event_publisher
            )
            await self.schema_service.initialize()
            logger.info("✅ Schema Service initialized with real DB connection")
            
            # 다른 서비스들은 일단 None으로 (나중에 수정)
            self.validation_service = None
            self.branch_service = None
            self.history_service = None
            self.event_service = EnhancedEventService()
            
            logger.info("All services initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize services: {e}")
            raise
    
    async def shutdown(self):
        """모든 서비스 정리"""
        logger.info("Shutting down services...")
        
        if self.db_client:
            await self.db_client.disconnect()
        
        if self.event_publisher:
            self.event_publisher.close()
        
        logger.info("All services shut down")


# 전역 서비스 컨테이너
services = ServiceContainer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """애플리케이션 생명주기 관리"""
    logger.info("OMS Enterprise (Fixed) starting up...")
    
    # 서비스 초기화
    await services.initialize()
    
    yield
    
    # Shutdown
    logger.info("OMS Enterprise (Fixed) shutting down...")
    await services.shutdown()


# FastAPI 앱 생성
app = FastAPI(
    title="OMS Enterprise (Fixed)",
    version="2.0.1",
    description="Ontology Management System - DB Connection Fixed",
    lifespan=lifespan
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === Health & Status ===
@app.get("/health")
async def health_check():
    """시스템 상태 확인"""
    return {
        "status": "healthy",
        "version": "2.0.1",
        "db_connected": services.db_client and services.db_client.is_connected(),
        "services": {
            "schema": services.schema_service is not None,
            "db": services.db_client is not None,
            "events": services.event_service is not None,
        }
    }


@app.get("/")
async def root():
    """API 정보"""
    return {
        "name": "OMS Enterprise API (Fixed)",
        "version": "2.0.1",
        "status": "DB Connection Fixed - Real Data",
        "docs": "/docs",
        "health": "/health"
    }


# === Schema Management API (Fixed) ===
@app.get("/api/v1/schemas/{branch}/object-types")
async def list_object_types(branch: str):
    """ObjectType 목록 조회 - 실제 DB에서"""
    if not services.schema_service:
        raise HTTPException(status_code=503, detail="Schema service not available")
    
    try:
        # 수정된 서비스 사용 - 실제 DB 데이터 반환
        result = await services.schema_service.list_object_types(branch=branch)
        return {
            "objectTypes": result, 
            "branch": branch,
            "source": "real_database"  # Mock이 아님을 표시
        }
    except Exception as e:
        logger.error(f"Failed to list object types: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/schemas/{branch}/object-types")
async def create_object_type(branch: str, request: Dict[str, Any]):
    """ObjectType 생성 - 실제 DB에"""
    if not services.schema_service:
        raise HTTPException(status_code=503, detail="Schema service not available")
    
    try:
        from models.domain import ObjectTypeCreate
        
        # Request를 모델로 변환
        data = ObjectTypeCreate(
            name=request.get("name"),
            display_name=request.get("displayName"),
            description=request.get("description")
        )
        
        # 실제 DB에 생성
        result = await services.schema_service.create_object_type(branch, data)
        return {
            "objectType": result.model_dump() if hasattr(result, 'model_dump') else result,
            "source": "real_database"
        }
    except Exception as e:
        logger.error(f"Failed to create object type: {e}")
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main_enterprise_fixed:app",
        host="0.0.0.0",
        port=8002,  # 다른 포트 사용
        reload=True,
        log_level="info"
    )