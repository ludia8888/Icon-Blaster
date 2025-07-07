import sys
import os

# Add project root to the Python path to resolve module imports during tests
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

"""
Configuration for pytest tests.
This file sets up fixtures and application context for integration tests.
"""
import asyncio
from typing import AsyncGenerator, Generator
import pytest
from starlette.testclient import TestClient
from httpx import AsyncClient
from unittest.mock import MagicMock, AsyncMock

from bootstrap.app import create_app
from bootstrap.config import AppConfig, SQLiteConfig, RedisConfig
from bootstrap.dependencies import get_redis_client, get_db_client, get_branch_service
from database.clients.unified_database_client import UnifiedDatabaseClient

@pytest.fixture(scope="session")
def test_config() -> AppConfig:
    """Provides a test-specific AppConfig instance."""
    return AppConfig(
        postgres=None,
        sqlite=SQLiteConfig(db_name=":memory:"),
        redis=RedisConfig(host="localhost", port=6379, db=0),
    )

@pytest.fixture(scope="session")
def test_app(test_config: AppConfig) -> TestClient:
    """
    Creates and configures a FastAPI app instance for testing,
    and yields a TestClient for making requests.
    """
    app = create_app(test_config)

    # --- Dependency Overrides ---
    mock_redis = MagicMock()
    mock_db_client = MagicMock(spec=UnifiedDatabaseClient)
    
    # Mock the return value for the specific terminus client
    mock_terminus_client = MagicMock()
    mock_db_client.get_client.return_value = mock_terminus_client

    # Override the main dependency providers
    app.dependency_overrides[get_redis_client] = lambda: mock_redis
    app.dependency_overrides[get_db_client] = lambda: mock_db_client

    # ---- NEW MOCK STRATEGY FOR BranchService ----
    class DummyBranchService:
        async def create_branch(self, *args, **kwargs):
            print("DUMMY MOCK create_branch called with:", args, kwargs)
            return True

        async def commit_changes(self, *args, **kwargs):
            return "new_commit_sha"

        async def create_pull_request(self, *args, **kwargs):
            return {"pr_id": "123"}

    dummy_branch_service_instance = DummyBranchService()

    async def override_get_branch_service(*args, **kwargs):
        print("DUMMY MOCK get_branch_service called")
        return dummy_branch_service_instance

    app.dependency_overrides[get_branch_service] = override_get_branch_service
    # --- End of Overrides ---

    with TestClient(app) as client:
        yield client
    
    # Clean up overridden dependencies after tests are done
    app.dependency_overrides = {}

@pytest.fixture
def mock_udc(test_app: TestClient) -> MagicMock:
    """
    Provides access to the mocked UnifiedDatabaseClient instance
    used in the test_app fixture.
    """
    return test_app.app.dependency_overrides[get_db_client]()

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
    from bootstrap.dependencies import get_redis_client, get_db_client, get_branch_service
    from database.clients.unified_database_client import UnifiedDatabaseClient
    
    # Create mock database client
    mock_db = AsyncMock(spec=UnifiedDatabaseClient)
    mock_db.query_one = AsyncMock(return_value=None)
    mock_db.query_all = AsyncMock(return_value=[])
    mock_db.execute = AsyncMock(return_value=None)
    
    # Override dependencies
    app.dependency_overrides[get_redis_client] = lambda: mock_redis
    app.dependency_overrides[get_db_client] = lambda: mock_db
    
    # <<< FIX: Override the problematic BranchService dependency >>>
    mock_branch_service_instance = MagicMock()
    # Configure create_branch to accept any keyword arguments
    async def mock_create_branch(*args, **kwargs):
        return True
    mock_branch_service_instance.create_branch.side_effect = mock_create_branch
    mock_branch_service_instance.commit_changes = AsyncMock(return_value="new_commit_sha")
    mock_branch_service_instance.create_pull_request = AsyncMock(return_value={"pr_id": "123", "status": "open"})

    async def override_get_branch_service():
        return mock_branch_service_instance

    app.dependency_overrides[get_branch_service] = override_get_branch_service
    # <<< END FIX >>>

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