"""Application factory with dependency injection"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from bootstrap.dependencies import cleanup_providers
from bootstrap.config import get_config
from utils.logger import get_logger

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    config = get_config()
    logger.info(f"Starting application in {config.service.environment} environment")
    
    yield
    
    logger.info("Shutting down application...")
    await cleanup_providers()
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
    from api.graphql.enhanced_main import graphql_app as enhanced_graphql_app
    from api.graphql.main import graphql_app
    app.mount("/graphql", enhanced_graphql_app, name="enhanced_graphql")
    app.mount("/graphql-ws", graphql_app, name="graphql_ws")
    
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
    from core.auth.database_context import DatabaseContextMiddleware
    app.add_middleware(DatabaseContextMiddleware)
    
    # 2. RBAC Middleware - Checks permissions (if needed for specific endpoints)
    # from middleware.rbac_middleware import RBACMiddleware
    # app.add_middleware(RBACMiddleware)
    
    # 1. Auth Middleware - Validates identity (executes first)
    from middleware.auth_middleware import AuthMiddleware
    app.add_middleware(AuthMiddleware)
    
    return app