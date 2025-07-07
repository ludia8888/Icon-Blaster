"""
End-to-End tests for critical API flows.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock
from pytest import MonkeyPatch
from starlette.testclient import TestClient
from pytest_mock import MockerFixture

import punq
from fastapi import FastAPI

from bootstrap.app import create_app
from bootstrap.dependencies import get_db_client # Using the dependency provider
from database.clients.unified_database_client import UnifiedDatabaseClient
from database.clients.postgres_client import PostgresClient
from database.clients.sqlite_client import SQLiteClient
from database.clients.terminusdb_client import TerminusDBClient

# --- Test Setup ---

@pytest.fixture(autouse=True)
def patch_imports(monkeypatch: MonkeyPatch):
    """
    Patch modules to fix various import errors in the application code.
    This is a temporary measure to allow E2E tests to run without a full refactor.
    """
    # Most patches are no longer needed as the application loads successfully
    pass

@pytest.fixture
def mock_udc() -> MagicMock:
    """Create a mock UnifiedDatabaseClient."""
    # Mock individual clients
    mock_postgres_client = MagicMock(spec=PostgresClient)
    mock_sqlite_client = MagicMock(spec=SQLiteClient)
    mock_terminus_client = AsyncMock(spec=TerminusDBClient)

    # Mock the UnifiedDatabaseClient
    udc = MagicMock(spec=UnifiedDatabaseClient)
    
    # Set up the internal clients
    udc.postgres_client = mock_postgres_client
    udc.sqlite_client = mock_sqlite_client
    # udc.terminus_client = mock_terminus_client  # Not used in current implementation
    
    # Mock the get_client method to return the terminus client
    udc.get_client = MagicMock(return_value=mock_terminus_client)
    
    # Mock the CRUD methods
    udc.create = AsyncMock(return_value={"id": "test-id"})
    udc.read = AsyncMock(return_value=[])
    udc.update = AsyncMock(return_value=True)
    udc.delete = AsyncMock(return_value=True)
    
    return udc

@pytest.fixture
def test_app(mock_udc: MagicMock, monkeypatch: MonkeyPatch) -> TestClient:
    """Create a TestClient with the UDC dependency overridden."""
    # Mock the health checker to return healthy status
    from core.health import HealthStatus
    mock_health_checker = MagicMock()
    mock_health_checker.get_health = AsyncMock(return_value={
        "status": HealthStatus.HEALTHY.value,
        "timestamp": "2025-01-07T00:00:00",
        "checks": [],
        "version": "2.0.0"
    })
    
    monkeypatch.setattr("core.health.health_checker._health_checker", mock_health_checker)
    
    # Mock the auth middleware to bypass authentication
    from core.auth import UserContext
    mock_user = UserContext(
        user_id="test-user",
        username="test-user",
        email="test@example.com",
        roles=["admin"],
        permissions=["ontologies:read", "ontologies:write"],
        metadata={}
    )
    
    async def mock_validate_token(self, token):
        return {
            "user_id": "test-user",
            "username": "test-user",
            "email": "test@example.com",
            "roles": ["admin"],
            "permissions": ["ontologies:read", "ontologies:write"],
            "metadata": {}
        }
    
    monkeypatch.setattr("middleware.auth_middleware.AuthMiddleware._validate_token", mock_validate_token)
    
    app = create_app()
    app.dependency_overrides[get_db_client] = lambda: mock_udc
    return TestClient(app)

# --- E2E Tests ---

def test_health_check(test_app: TestClient):
    """
    Test a simple, unauthenticated endpoint to ensure the app is running.
    """
    response = test_app.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_create_and_get_schema_object_flow(
    test_app: TestClient, 
    mock_udc: MagicMock,
    mocker: MockerFixture
):
    """
    Test E2E flow: creating a new schema object type and then retrieving it.
    """
    # 1. Mock the external user-service call within AuthMiddleware
    mocker.patch(
        "middleware.auth_middleware.AuthMiddleware._validate_token",
        return_value={
            "user_id": "test-user",
            "username": "Test User",
            "email": "test@example.com",
            "roles": ["editor"],
            "permissions": [], # This field is not used for scope checks
            "metadata": {
                "scopes": ["ontologies:write", "ontologies:read"]
            }
        },
    )
    
    # <<< FIX: Mock the correct permission check method >>>
    mocker.patch(
        "core.iam.iam_integration.IAMIntegration.check_scope",
        return_value=True
    )

    # 2. Setup Mock for the database layer
    mock_terminus_client = mock_udc.get_client("terminus")

    create_payload = {
        "name": "TestObjectType",
        "display_name": "Test Object Type",
        "description": "A type for testing purposes."
    }

    mock_terminus_client.create = AsyncMock(return_value="TestObjectType/123")
    mock_terminus_client.read = AsyncMock(return_value=[{
        "@id": "TestObjectType/123",
        "name": "TestObjectType",
        "displayName": "Test Object Type",
        "description": "A type for testing purposes."
    }])

    # 2. Action: Call the create endpoint
    # Schema routes include branch in the path
    response_create = test_app.post(
        "/api/v1/schemas/main/object-types",
        json=create_payload,
        headers={
            "Authorization": "Bearer test-token",
            "X-User-ID": "test-user"
        }
    )

    # 3. Assertion (Create)
    assert response_create.status_code == 201, f"Failed to create. Response: {response_create.text}"
    assert response_create.json()["name"] == "TestObjectType"

    # 4. Action: Call the get endpoint
    response_get = test_app.get(
        "/api/v1/schemas/main/object-types/TestObjectType",
        headers={
            "Authorization": "Bearer test-token",
            "X-User-ID": "test-user"
        }
    )

    # 5. Assertion (Get)
    assert response_get.status_code == 200, f"Failed to get. Response: {response_get.text}"
    assert response_get.json()[0]["name"] == "TestObjectType"
    assert response_get.json()[0]["displayName"] == "Test Object Type"

    # 6. Verify mocks were called
    mock_terminus_client.create.assert_called_once()
    mock_terminus_client.read.assert_called_once() 