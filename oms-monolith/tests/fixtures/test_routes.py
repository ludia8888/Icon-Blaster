"""
Test-Only Routes
These routes are only registered in non-production environments
"""
import os
from fastapi import FastAPI, APIRouter
from core.config.environment import get_environment
from utils.logger import get_logger

logger = get_logger(__name__)


def register_test_routes(app: FastAPI) -> None:
    """
    Register test-only routes if not in production
    
    Args:
        app: FastAPI application instance
    """
    env_config = get_environment()
    
    if not env_config.allows_test_routes:
        logger.info(f"Skipping test route registration in {env_config.current} environment")
        return
    
    logger.warning(
        f"Registering test routes in {env_config.current} environment. "
        "These routes use mock authentication and should NOT be used in production!"
    )
    
    # Import test routes that use mock auth
    # These imports are done inside the function to avoid loading them in production
    try:
        from api.v1.schema_generation.endpoints import router as schema_gen_router
        from api.v1.struct_types.endpoints import router as struct_types_router
        from api.v1.semantic_types.endpoints import router as semantic_types_router
        
        # Create a test router group
        test_router = APIRouter(prefix="/test", tags=["Test Routes"])
        
        # Include the routers under /test prefix
        test_router.include_router(
            schema_gen_router,
            prefix="/schema-generation",
            tags=["Test: Schema Generation"]
        )
        test_router.include_router(
            struct_types_router,
            prefix="/struct-types",
            tags=["Test: Struct Types"]
        )
        test_router.include_router(
            semantic_types_router,
            prefix="/semantic-types",
            tags=["Test: Semantic Types"]
        )
        
        # Register the test router group
        app.include_router(test_router)
        
        logger.info(
            "Test routes registered successfully. "
            f"Available at: /test/schema-generation, /test/struct-types, /test/semantic-types"
        )
        
    except ImportError as e:
        logger.error(f"Failed to import test routes: {e}")
        raise


def create_test_app() -> FastAPI:
    """
    Create a FastAPI app instance for testing with mock authentication
    
    This function creates an app with test routes and mock dependencies.
    Should only be used in test environments.
    """
    if os.getenv("ENV", "development") == "production":
        raise RuntimeError("create_test_app() cannot be used in production!")
    
    from main import app  # Import the main app
    from middleware.auth_middleware import get_current_user
    from tests.fixtures.auth.mock_auth import get_test_user_dependency
    
    # Override authentication dependency with mock
    app.dependency_overrides[get_current_user] = get_test_user_dependency("developer")
    
    # Register test routes
    register_test_routes(app)
    
    return app