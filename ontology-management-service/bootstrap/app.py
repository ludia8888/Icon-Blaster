"""Application factory with dependency injection"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from bootstrap.dependencies import (
    cleanup_providers, get_redis_provider, get_circuit_breaker_provider
)
from bootstrap.config import get_config
from common_logging.setup import get_logger
from infra.tracing.otel_init import get_otel_manager
from core.config import settings

# --- Middleware Imports ---
from middleware.transaction_middleware import TransactionMiddleware
from middleware.feature_flag_middleware import FeatureFlagMiddleware
from middleware.rate_limiting_middleware import RateLimitingMiddleware
from middleware.auth_middleware import AuthMiddleware
from middleware.terminus_context_middleware import TerminusContextMiddleware
from core.auth_utils.database_context import DatabaseContextMiddleware as CoreDatabaseContextMiddleware
from middleware.error_handler import ErrorHandlerMiddleware
from middleware.etag_middleware import ETagMiddleware
from core.iam.scope_rbac_middleware import ScopeRBACMiddleware

# --- API Router Imports ---
from api.v1 import (
    system_routes, health_routes, schema_routes, audit_routes,
    auth_proxy_routes, batch_routes, branch_lock_routes, branch_routes,
    document_routes, graph_health_routes, idempotent_routes,
    issue_tracking_routes, job_progress_routes, shadow_index_routes,
    time_travel_routes, version_routes
)
from api.v1.schema_generation import endpoints as schema_gen_routes
from api.graphql.modular_main import graphql_app as modular_graphql_app
from api.graphql.main import app as websocket_app

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    config = get_config()
    logger.info(f"Starting application in {config.service.environment} environment")
    
    otel_manager = get_otel_manager()
    
    redis_provider = get_redis_provider()
    app.state.redis_provider = redis_provider
    app.state.redis_client = await redis_provider.provide()
    
    # Initialize Circuit Breaker Provider and store the group in app state
    circuit_breaker_provider = get_circuit_breaker_provider(redis_provider)
    app.state.circuit_breaker_group = await circuit_breaker_provider.provide()
    
    yield
    
    logger.info("Shutting down application...")
    await cleanup_providers()
    await redis_provider.shutdown()
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
    
    otel_manager = get_otel_manager()
    otel_manager.initialize(service_name="oms-monolith")
    logger.info("OpenTelemetry 초기화 완료(Instrumentation은 후행) ")
    
    # Register Routers
    app.include_router(system_routes.router)
    app.include_router(health_routes.router)
    app.include_router(schema_routes.router)
    
    v1_routers = [
        audit_routes, batch_routes, branch_lock_routes, branch_routes,
        document_routes, graph_health_routes, idempotent_routes,
        issue_tracking_routes, job_progress_routes, shadow_index_routes, 
        time_travel_routes, version_routes, schema_gen_routes
    ]
    for router_module in v1_routers:
        app.include_router(router_module.router, prefix="/api/v1")

    app.include_router(auth_proxy_routes.router)
    
    app.mount("/graphql", modular_graphql_app, name="graphql")
    app.mount("/graphql-ws", websocket_app, name="graphql_ws")
    
    if config.service.environment != "production":
        from api.test_endpoints import router as test_router
        app.include_router(test_router)
    
    # MIDDLEWARE CHAIN CONFIGURATION (Correct Order)
    
    # 1. Error Handler (Top-level)
    app.add_middleware(ErrorHandlerMiddleware)

    # 2. CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 3. ETag
    app.add_middleware(ETagMiddleware)

    # 4. Transaction
    app.add_middleware(TransactionMiddleware)

    # 5. Feature Flag
    app.add_middleware(FeatureFlagMiddleware)

    # 6. Rate Limiting
    app.add_middleware(RateLimitingMiddleware)
    
    # 7. Authentication
    app.add_middleware(AuthMiddleware)

    # 8. TerminusDB Context
    app.add_middleware(TerminusContextMiddleware)

    # 9. Database Context
    app.add_middleware(CoreDatabaseContextMiddleware)

    # 10. Scope-based RBAC
    app.add_middleware(ScopeRBACMiddleware)
    logger.info("ScopeRBACMiddleware registered - security layer active")

    # Final Step: OpenTelemetry Instrumentation
    try:
        otel_manager.instrument_fastapi(app)
        logger.info("OpenTelemetry FastAPI instrumentation completed")
    except RuntimeError as e:
        logger.warning(f"FastAPI instrumentation skipped: {e}")

    return app