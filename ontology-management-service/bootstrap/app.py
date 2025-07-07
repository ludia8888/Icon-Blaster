"""Application factory with dependency injection"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
# import punq  # Replaced with dependency-injector
from typing import Optional

from bootstrap.dependencies import init_container
from bootstrap.config import get_config, AppConfig
from common_logging.setup import get_logger
# from infra.tracing.otel_init import get_otel_manager # Temporarily disabled
# --- Middleware Imports ---
from middleware.auth_middleware import AuthMiddleware
from middleware.terminus_context_middleware import TerminusContextMiddleware
from core.auth_utils.database_context import DatabaseContextMiddleware as CoreDatabaseContextMiddleware
from middleware.error_handler import ErrorHandlerMiddleware
from middleware.etag_middleware import ETagMiddleware
from core.iam.scope_rbac_middleware import ScopeRBACMiddleware
# Optional middlewares – create no-op fallbacks when the real implementation is missing

try:
    from middleware.request_id import RequestIdMiddleware  # type: ignore
except ImportError:  # pragma: no cover
    class RequestIdMiddleware:  # pylint: disable=too-few-public-methods
        """Fallback RequestIdMiddleware (noop)."""

        def __init__(self, app, **kwargs):
            self.app = app

        async def __call__(self, scope, receive, send):  # noqa: D401
            await self.app(scope, receive, send)


try:
    from middleware.scope_rbac import ScopeRBACMiddleware  # type: ignore
except ImportError:  # pragma: no cover
    class ScopeRBACMiddleware:  # pylint: disable=too-few-public-methods
        """Fallback RBAC middleware (noop)."""

        def __init__(self, app, **kwargs):
            self.app = app

        async def __call__(self, scope, receive, send):
            await self.app(scope, receive, send)


try:
    from middleware.audit_log import AuditLogMiddleware  # type: ignore
except ImportError:  # pragma: no cover
    class AuditLogMiddleware:
        """Fallback audit log middleware (noop)."""

        def __init__(self, app, **kwargs):
            self.app = app

        async def __call__(self, scope, receive, send):
            await self.app(scope, receive, send)


try:
    from middleware.circuit_breaker import CircuitBreakerMiddleware  # type: ignore
except ImportError:  # pragma: no cover
    class CircuitBreakerMiddleware:
        """Fallback circuit breaker middleware (noop)."""

        def __init__(self, app, **kwargs):
            self.app = app

        async def __call__(self, scope, receive, send):
            await self.app(scope, receive, send)

# --- API Router Imports ---
from api.v1 import (
    system_routes, health_routes, schema_routes, audit_routes,
    auth_proxy_routes, batch_routes, branch_lock_routes, branch_routes,
    document_routes, graph_health_routes, idempotent_routes,
    issue_tracking_routes, job_progress_routes, shadow_index_routes,
    time_travel_routes, version_routes
)
from api.graphql.modular_main import graphql_app as modular_graphql_app
from api.graphql.main import app as websocket_app

logger = get_logger(__name__)

def create_app(container=None) -> FastAPI:
    """Application factory, creating a new FastAPI application."""
    
    config = get_config()

    if container is None:
        container = init_container(config)

    api_prefix = "/api/v1"

    # Create the FastAPI application
    app = FastAPI(
        title="Ontology Management Service",
        version="2.0.0", # Or derive from config if available
        debug=config.service.debug,
        openapi_url=f"{api_prefix}/openapi.json",
        docs_url=f"{api_prefix}/docs",
        redoc_url=f"{api_prefix}/redoc"
    )

    # Store the DI container in the app state
    app.state.container = container
    
    # Add redis client and circuit breaker to app state for middleware access
    try:
        app.state.redis_client = container.redis_provider()
        app.state.circuit_breaker_group = container.circuit_breaker_provider()
        logger.info("Successfully loaded Redis and Circuit Breaker from container.")
    except Exception as e:
        logger.critical(f"Could not resolve redis or circuit breaker from container: {e}", exc_info=True)
        # In a real scenario, we might want to prevent the app from starting.
        app.state.redis_client = None
        app.state.circuit_breaker_group = None

    # No longer need startup/shutdown events for providers managed by punq
    # as singletons. Their lifecycle is tied to the container.

    # Add middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add routers
    app.include_router(health_routes.router, prefix=api_prefix, tags=["Health"])
    app.include_router(system_routes.router, prefix=api_prefix, tags=["System"])
    app.include_router(schema_routes.router, prefix=api_prefix, tags=["Schema"])
    
    v1_routers = [
        audit_routes, batch_routes, branch_lock_routes, branch_routes,
        document_routes, graph_health_routes, idempotent_routes,
        issue_tracking_routes, job_progress_routes, shadow_index_routes, 
        time_travel_routes, version_routes
    ]
    for router_module in v1_routers:
        app.include_router(router_module.router, prefix=api_prefix)

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
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 3. ETag
    app.add_middleware(ETagMiddleware)
    
    # 4. Authentication
    app.add_middleware(AuthMiddleware)

    # 5. TerminusDB Context
    app.add_middleware(TerminusContextMiddleware)

    # 6. Database Context
    app.add_middleware(CoreDatabaseContextMiddleware)

    # 7. Scope-based RBAC
    app.add_middleware(ScopeRBACMiddleware)
    logger.info("ScopeRBACMiddleware registered - security layer active")

    # Optional: Instrumenting for OpenTelemetry
    # try:
    #     # Only enable in production or based on a specific setting
    #     if config.service.environment == "production":
    #         from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    #         FastAPIInstrumentor.instrument_app(app)
    #         logger.info("FastAPI application instrumented for OpenTelemetry.")
    # except ImportError:
    #     logger.warning("OpenTelemetry libraries not found. Skipping instrumentation.")
    # except Exception as e:
    #     logger.warning(f"FastAPI instrumentation skipped: {e}")

    return app