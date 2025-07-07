"""
Modular GraphQL Service with Feature Flags
Production-ready with optional enterprise features
"""
import os
import logging
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any, List
from datetime import datetime

from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
import redis.asyncio as redis
from strawberry.fastapi import GraphQLRouter
from strawberry.extensions import SchemaExtension

from core.config.environment import get_environment
from api.graphql.auth import get_current_user_optional, GraphQLWebSocketAuth, AuthenticationManager
from core.auth_utils import UserContext

# 로깅 설정
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)
logger.info(f"GraphQL Modular Main starting with log level: {log_level}")

# Import components
from .realtime_publisher import realtime_publisher
from .working_schema import schema
from .websocket_manager import websocket_manager
from .config import graphql_config

# Import optional middleware
from .middleware.security import create_security_extension
from .middleware.cache import create_cache_extension

from common_logging.setup import get_logger

logger = get_logger(__name__)

# Global instances
auth_manager: Optional[AuthenticationManager] = None
graphql_ws_auth: Optional[GraphQLWebSocketAuth] = None
redis_client: Optional[redis.Redis] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modular service lifespan with optional features"""
    global auth_manager, graphql_ws_auth, redis_client
    
    logger.info(f"GraphQL Service starting (env: {os.getenv('APP_ENV', 'development')})")
    logger.info(f"Feature flags - Security: {graphql_config.enable_security}, "
                f"Cache: {graphql_config.enable_cache}, "
                f"Tracing: {graphql_config.enable_tracing}")
    
    try:
        # Core components (always required)
        
        # 1. Redis connection
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        logger.debug(f"Connecting to Redis at: {redis_url}")
        redis_client = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        await redis_client.ping()
        logger.info("Redis connection established")
        
        # 2. Authentication Manager
        logger.debug("Initializing Authentication Manager...")
        auth_manager = AuthenticationManager()
        await auth_manager.init_redis()
        logger.info("Authentication manager initialized")
        
        # 3. GraphQL WebSocket auth
        logger.debug("Initializing GraphQL WebSocket auth...")
        graphql_ws_auth = GraphQLWebSocketAuth(auth_manager)
        logger.info("GraphQL WebSocket authentication initialized")
        
        # 4. NATS for real-time events
        logger.debug("Connecting to NATS/realtime publisher...")
        await realtime_publisher.connect()
        logger.info("Connected to NATS for real-time events")
        
        # Optional components based on feature flags
        
        # 5. Tracing (if enabled)
        if graphql_config.enable_tracing:
            try:
                from infra.tracing.otel_init import get_otel_manager
                otel_manager = get_otel_manager()
                otel_manager.initialize(service_name="graphql-service")
                logger.info("OpenTelemetry tracing initialized")
            except Exception as e:
                logger.warning(f"Tracing initialization failed: {e}")
                
    except Exception as e:
        logger.error(f"Failed to initialize components: {e}", exc_info=True)
        import traceback
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
        # Continue without some features rather than failing completely
    
    yield
    
    # Graceful shutdown
    try:
        if redis_client:
            await redis_client.close()
        await realtime_publisher.disconnect()
        logger.info("GraphQL Service shutdown complete")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


async def get_graphql_context(request: Request) -> Dict[str, Any]:
    """GraphQL context with modular features"""
    user = await get_current_user_optional(request)
    
    context = {
        "request": request,
        "user": user,
        "redis": redis_client,
        "websocket_manager": websocket_manager,
        "realtime_publisher": realtime_publisher,
        "auth_manager": auth_manager,
        "config": graphql_config,
    }
    
    # Add performance metrics collection if tracing enabled
    if graphql_config.enable_tracing:
        context["request_start_time"] = datetime.utcnow()
    
    return context


def get_extensions() -> List[SchemaExtension]:
    """Get list of enabled extensions based on feature flags"""
    extensions = []
    
    # Security extension
    if graphql_config.enable_security:
        security_ext = create_security_extension(graphql_config)
        if security_ext:
            extensions.append(security_ext)
            logger.info("Security extension enabled")
    
    # Cache extension
    if graphql_config.enable_cache and redis_client:
        cache_ext = create_cache_extension(redis_client, graphql_config)
        if cache_ext:
            extensions.append(cache_ext)
            logger.info("Cache extension enabled")
    
    return extensions


# Create FastAPI app
app = FastAPI(
    title="OMS GraphQL Service",
    description="Modular GraphQL API with Enterprise Features",
    version="3.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create GraphQL router with optional extensions
graphql_app = GraphQLRouter(
    schema,
    context_getter=get_graphql_context,
    graphql_ide="graphiql" if graphql_config.enable_introspection else None
)

app.include_router(graphql_app, prefix="/graphql")


@app.get("/health")
async def health_check():
    """Comprehensive health check with feature status"""
    health_status = {
        "status": "healthy",
        "service": "graphql-service",
        "version": "3.0.0",
        "environment": os.getenv("APP_ENV", "development"),
        "timestamp": datetime.utcnow().isoformat(),
        "features": {
            "security": graphql_config.enable_security,
            "cache": graphql_config.enable_cache,
            "tracing": graphql_config.enable_tracing,
            "introspection": graphql_config.enable_introspection
        },
        "components": {},
        "checks_passed": 0,
        "checks_failed": 0
    }
    
    # Check Redis
    if redis_client:
        try:
            start = datetime.utcnow()
            await redis_client.ping()
            latency_ms = (datetime.utcnow() - start).total_seconds() * 1000
            
            health_status["components"]["redis"] = {
                "status": "healthy",
                "latency_ms": round(latency_ms, 2),
                "message": "Redis connection active"
            }
            
            # Check cache hit rate if enabled
            if graphql_config.enable_cache:
                try:
                    # Get cache stats from Redis
                    cache_hits = await redis_client.get("gql:stats:hits") or 0
                    cache_misses = await redis_client.get("gql:stats:misses") or 0
                    total = int(cache_hits) + int(cache_misses)
                    hit_rate = (int(cache_hits) / total * 100) if total > 0 else 0
                    
                    health_status["components"]["redis"]["cache_stats"] = {
                        "hits": int(cache_hits),
                        "misses": int(cache_misses),
                        "hit_rate": round(hit_rate, 2)
                    }
                except:
                    pass
                    
            health_status["checks_passed"] += 1
        except Exception as e:
            health_status["components"]["redis"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_status["status"] = "degraded"
            health_status["checks_failed"] += 1
    
    # Check Authentication
    if auth_manager:
        health_status["components"]["auth"] = {
            "status": "healthy",
            "message": "Authentication service ready"
        }
        health_status["checks_passed"] += 1
    
    # Check NATS
    if realtime_publisher:
        health_status["components"]["nats"] = {
            "status": "healthy" if realtime_publisher._connected else "disconnected",
            "message": "Real-time event publisher"
        }
        health_status["checks_passed"] += 1
    
    # Add configuration warnings for production
    if os.getenv("APP_ENV") == "production":
        warnings = []
        if graphql_config.enable_introspection:
            warnings.append("GraphQL introspection is enabled in production")
        if not graphql_config.enable_security:
            warnings.append("Security features are disabled in production")
        if not graphql_config.enable_cache:
            warnings.append("Caching is disabled in production")
            
        if warnings:
            health_status["warnings"] = warnings
    
    return health_status


@app.get("/metrics")
async def metrics():
    """Prometheus-compatible metrics endpoint"""
    if not graphql_config.enable_tracing:
        return {"error": "Metrics disabled. Set ENABLE_GQL_TRACING=true"}
    
    # Basic metrics in Prometheus format
    metrics_text = """
# HELP graphql_requests_total Total GraphQL requests
# TYPE graphql_requests_total counter
graphql_requests_total 0

# HELP graphql_errors_total Total GraphQL errors  
# TYPE graphql_errors_total counter
graphql_errors_total 0

# HELP graphql_request_duration_seconds GraphQL request duration
# TYPE graphql_request_duration_seconds histogram
graphql_request_duration_seconds_bucket{le="0.1"} 0
graphql_request_duration_seconds_bucket{le="0.5"} 0
graphql_request_duration_seconds_bucket{le="1.0"} 0
graphql_request_duration_seconds_bucket{le="+Inf"} 0
"""
    
    return Response(content=metrics_text, media_type="text/plain")


@app.get("/")
async def root():
    """Root endpoint with feature information"""
    return {
        "name": "OMS Modular GraphQL Service",
        "version": "3.0.0",
        "environment": os.getenv("APP_ENV", "development"),
        "graphql": "/graphql",
        "health": "/health",
        "metrics": "/metrics" if graphql_config.enable_tracing else None,
        "features": {
            "security": "enabled" if graphql_config.enable_security else "disabled",
            "cache": "enabled" if graphql_config.enable_cache else "disabled",
            "tracing": "enabled" if graphql_config.enable_tracing else "disabled",
            "introspection": "enabled" if graphql_config.enable_introspection else "disabled"
        }
    }


# Export for use in main app
modular_graphql_app = graphql_app