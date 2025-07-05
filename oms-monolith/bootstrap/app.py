"""Application factory with dependency injection"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from bootstrap.dependencies import cleanup_providers
from bootstrap.config import get_config
from utils.logger import get_logger
from infra.tracing.otel_init import get_otel_manager

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    config = get_config()
    logger.info(f"Starting application in {config.service.environment} environment")
    
    # OpenTelemetry initialization is now handled in create_app()
    otel_manager = get_otel_manager()
    
    yield
    
    logger.info("Shutting down application...")
    await cleanup_providers()
    otel_manager.shutdown()
    logger.info("Application shutdown complete")

def create_app() -> FastAPI:
    """Create FastAPI application with proper configuration"""
    config = get_config()
    
    app = FastAPI(
        title="OMS API", 
        version="1.0.0",
        debug=config.service.debug,
        lifespan=lifespan
    )
    
    # ------------------------------
    # Step 1: Initialize Observability (OpenTelemetry)
    # 앱이 라우터 및 미들웨어를 구성하기 전에 OpenTelemetry를 초기화하여
    # FastAPIInstrumentor가 가장 바깥쪽 미들웨어로 삽입되도록 합니다.
    # ------------------------------
    otel_manager = get_otel_manager()
    # 이미 초기화되었다면 내부적으로 경고만 출력하고 무시합니다.
    otel_manager.initialize(service_name="oms-monolith")
    # FastAPIInstrumentor를 아직 호출하지 않고, 모든 사용자 정의 미들웨어를
    # 등록한 뒤에 호출하여 Starlette가 middleware_stack을 최종적으로 빌드하도록 합니다.
    logger.info("OpenTelemetry 초기화 완료(Instrumentation은 후행) ")
    
    # Include system routes
    from api.v1 import system_routes, health_routes, schema_routes
    app.include_router(system_routes.router)
    app.include_router(health_routes.router)
    app.include_router(schema_routes.router)
    
    # Include API v1 routers
    from api.v1.schema_generation import endpoints as schema_gen_routes
    from api.v1 import (
        branch_lock_routes,
        audit_routes,
        issue_tracking_routes,
        version_routes,
        idempotent_routes,
        batch_routes
    )
    
    app.include_router(schema_gen_routes.router, prefix="/api/v1")
    app.include_router(branch_lock_routes.router, prefix="/api/v1")
    app.include_router(audit_routes.router, prefix="/api/v1")
    app.include_router(issue_tracking_routes.router, prefix="/api/v1")
    app.include_router(version_routes.router, prefix="/api/v1")
    app.include_router(idempotent_routes.router, prefix="/api/v1")
    app.include_router(batch_routes.router, prefix="/api/v1")
    
    # Mount GraphQL applications  
    from api.graphql.modular_main import graphql_app as modular_graphql_app
    from api.graphql.main import app as websocket_app
    app.mount("/graphql", modular_graphql_app, name="graphql")
    app.mount("/graphql-ws", websocket_app, name="graphql_ws")
    
    # Register test routes in non-production environments
    if config.service.environment != "production":
        from api.test_endpoints import router as test_router
        app.include_router(test_router)
    
    # Add middleware chain (order is important!)
    # Note: Middleware is added in reverse order (last added is executed first)
    # So we add them in reverse to get the desired execution order
    
    # 4. Audit Middleware - Records all write operations (executes last)
    from core.audit.audit_middleware import AuditMiddleware
    app.add_middleware(AuditMiddleware)
    
    # 3. Database Context Middleware - Propagates UserContext to database operations
    from core.auth_utils.database_context import DatabaseContextMiddleware
    app.add_middleware(DatabaseContextMiddleware)
    
    # 3. TerminusDB Context Middleware - Sets branch/author/trace context
    from middleware.terminus_context_middleware import TerminusContextMiddleware
    app.add_middleware(TerminusContextMiddleware)
    
    # 2. RBAC Middleware - Checks permissions (if needed for specific endpoints)
    # from middleware.rbac_middleware import RBACMiddleware
    # app.add_middleware(RBACMiddleware)
    
    # 1. Auth Middleware - Validates identity (executes first)
    from middleware.auth_middleware import AuthMiddleware
    app.add_middleware(AuthMiddleware)
    
    # ------------------------------
    # Step 2: FastAPI Instrumentation (마지막 단계)
    # 모든 사용자 정의 미들웨어 추가가 끝난 후 호출해야
    # 'Cannot add middleware after an application has started' 오류를 방지할 수 있습니다.
    # ------------------------------
    try:
        otel_manager.instrument_fastapi(app)
        logger.info("OpenTelemetry FastAPI instrumentation completed")
    except RuntimeError as e:
        # 이미 앱이 시작된 이후라면 Instrumentation을 건너뜀
        logger.warning(f"FastAPI instrumentation skipped: {e}")

    return app