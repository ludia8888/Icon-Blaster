"""
User Service - Identity Provider
Main application entry point
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from core.config import settings
from core.database import engine, Base
from api import auth, users, admin
from core.logging import setup_logging

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("Starting User Service...")
    
    # Create database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield
    
    # Cleanup
    logger.info("Shutting down User Service...")
    await engine.dispose()


# Create FastAPI app
app = FastAPI(
    title="User Service (IdP)",
    version="1.0.0",
    description="""
    Enterprise Identity Provider Service
    
    Features:
    - JWT-based authentication
    - User management
    - Multi-factor authentication (MFA)
    - Role-based access control (RBAC)
    - Session management
    - Audit logging
    """,
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Prometheus metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/users", tags=["Users"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])

# Health check endpoints
@app.get("/health")
async def health_check():
    """Basic health check"""
    return {"status": "healthy", "service": "user-service"}


@app.get("/ready")
async def readiness_check():
    """Readiness check - verify DB and Redis connections"""
    checks = {
        "database": False,
        "redis": False
    }
    
    # Check database
    try:
        async with engine.connect() as conn:
            await conn.execute("SELECT 1")
        checks["database"] = True
    except Exception as e:
        logger.error(f"Database check failed: {e}")
    
    # Check Redis
    try:
        from core.redis import redis_client
        await redis_client.ping()
        checks["redis"] = True
    except Exception as e:
        logger.error(f"Redis check failed: {e}")
    
    all_healthy = all(checks.values())
    return {
        "status": "ready" if all_healthy else "not ready",
        "checks": checks
    }


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "User Service (IdP)",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.PORT,
        reload=settings.DEBUG
    )