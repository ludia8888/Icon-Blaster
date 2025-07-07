import os
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from middleware.auth_middleware import AuthMiddleware
from core.iam.scope_rbac_middleware import ScopeRBACMiddleware
from core.audit.audit_middleware import AuditMiddleware
from core.observability.middleware import RequestTracingMiddleware
from data_kernel.api.router import router
from data_kernel.service.terminus_service import get_service

# Configure logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    # Startup
    logger.info("Starting Data-Kernel Gateway...")
    
    # Initialize TerminusDB service
    service = await get_service()
    logger.info("TerminusDB service initialized")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Data-Kernel Gateway...")
    if service:
        await service.close()
    logger.info("Cleanup completed")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Data-Kernel Gateway",
        description="Centralized gateway for TerminusDB operations",
        version="1.0.0",
        lifespan=lifespan
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add OpenTelemetry instrumentation
    FastAPIInstrumentor.instrument_app(app)
    
    # Add request tracing middleware (should be early in the chain)
    app.add_middleware(RequestTracingMiddleware)
    
    # Add authentication middleware
    app.add_middleware(AuthMiddleware)
    
    # Add RBAC middleware (if IAM is enabled)
    if os.getenv("USE_IAM_VALIDATION", "false").lower() == "true":
        app.add_middleware(ScopeRBACMiddleware)
    
    # Add audit middleware for tracking operations
    app.add_middleware(AuditMiddleware)
    
    # Include the main router
    app.include_router(router, prefix="/api/v1")
    
    # Root endpoint
    @app.get("/")
    async def root():
        return {
            "service": "Data-Kernel Gateway",
            "status": "operational",
            "version": "1.0.0"
        }
    
    # Health check endpoint
    @app.get("/health")
    async def health_check():
        try:
            service = await get_service()
            terminus_health = await service.health_check()
            return {
                "status": "healthy",
                "service": "data-kernel-gateway",
                "dependencies": {
                    "terminus_db": terminus_health
                }
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "service": "data-kernel-gateway",
                "error": str(e)
            }
    
    return app


# Create the application instance
app = create_app()

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("DATA_KERNEL_PORT", "8080"))
    host = os.getenv("DATA_KERNEL_HOST", "0.0.0.0")
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=os.getenv("ENV", "production") == "development",
        log_level=os.getenv("LOG_LEVEL", "info").lower()
    )