"""conftest.py
Test configuration for ontology-management-service.
Sets up Python path, test fixtures, and mock dependencies.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import AsyncGenerator, Generator
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from httpx import AsyncClient

# --------------------------------------------------------------------------------------------------
# Path Configuration
# --------------------------------------------------------------------------------------------------
SERVICE_ROOT: Path = Path(__file__).resolve().parent.parent
service_root_str = str(SERVICE_ROOT)

# Add service root to Python path
if service_root_str not in sys.path:
    sys.path.insert(0, service_root_str)

# Add common packages if available
COMMON_PACKAGES_PATH = SERVICE_ROOT.parent.parent / "packages" / "backend"
if COMMON_PACKAGES_PATH.exists():
    common_packages_str = str(COMMON_PACKAGES_PATH)
    if common_packages_str not in sys.path:
        sys.path.insert(0, common_packages_str)

# --------------------------------------------------------------------------------------------------
# Environment Configuration
# --------------------------------------------------------------------------------------------------
os.environ.update({
    "ENVIRONMENT": "test",
    "DEBUG": "true",
    "DATABASE_URL": "sqlite:///./test.db",
    "REDIS_URL": "redis://localhost:6379/1",
    "JWT_SECRET": "test-secret-key-for-testing-purposes-only",
    "JWT_ALGORITHM": "HS256",
    "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
    "IAM_SERVICE_URL": "http://localhost:8000",
    "IAM_VERIFY_SSL": "false",
    "JWT_LOCAL_VALIDATION": "true",
    "IAM_PERMISSION_CACHE_TTL": "300",
})

# --------------------------------------------------------------------------------------------------
# Test Fixtures
# --------------------------------------------------------------------------------------------------
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def app():
    """Create FastAPI app instance for testing."""
    from bootstrap.app import create_app
    return create_app()


@pytest.fixture
def client(app) -> Generator[TestClient, None, None]:
    """Create test client with mocked dependencies."""
    # Mock Redis
    mock_redis = MagicMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock(return_value=True)
    mock_redis.exists = AsyncMock(return_value=False)
    
    # Mock dependencies
    from bootstrap.dependencies import get_redis_client, get_database
    from database.clients.unified_database_client import UnifiedDatabaseClient
    
    # Create mock database client
    mock_db = AsyncMock(spec=UnifiedDatabaseClient)
    mock_db.query_one = AsyncMock(return_value=None)
    mock_db.query_all = AsyncMock(return_value=[])
    mock_db.execute = AsyncMock(return_value=None)
    
    # Override dependencies
    app.dependency_overrides[get_redis_client] = lambda: mock_redis
    app.dependency_overrides[get_database] = lambda: mock_db
    
    with TestClient(app) as test_client:
        yield test_client
    
    # Clear overrides
    app.dependency_overrides.clear()


@pytest.fixture
async def async_client(app) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client for async tests."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_user_context():
    """Create mock user context for authentication."""
    from core.auth_utils import UserContext
    return UserContext(
        user_id="test-user-123",
        username="testuser",
        email="test@example.com",
        roles=["user", "admin"],
        tenant_id="test-tenant",
        metadata={
            "scopes": ["api:ontologies:read", "api:ontologies:write"],
            "auth_time": 1234567890,
        }
    )


@pytest.fixture
def auth_headers(mock_user_context):
    """Create authentication headers with valid JWT token."""
    import jwt
    from datetime import datetime, timedelta
    
    # Create JWT token
    payload = {
        "sub": mock_user_context.user_id,
        "username": mock_user_context.username,
        "email": mock_user_context.email,
        "roles": mock_user_context.roles,
        "tenant_id": mock_user_context.tenant_id,
        "scope": " ".join(mock_user_context.metadata.get("scopes", [])),
        "exp": datetime.utcnow() + timedelta(minutes=30),
        "iat": datetime.utcnow(),
        "iss": "iam.company",
        "aud": "oms",
    }
    
    token = jwt.encode(
        payload,
        os.environ["JWT_SECRET"],
        algorithm=os.environ["JWT_ALGORITHM"]
    )
    
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_schema_data():
    """Sample schema data for testing."""
    return {
        "name": "TestObject",
        "type": "object",
        "description": "Test object type",
        "properties": {
            "id": {"type": "string", "required": True},
            "name": {"type": "string", "required": True},
            "created_at": {"type": "datetime", "required": False},
        },
        "branch": "main",
    } 