"""
Integration Test for UnifiedDatabaseClient Routing Logic
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from database.clients.postgres_client import PostgresClient
from database.clients.sqlite_client import SQLiteClient
from database.clients.unified_database_client import UnifiedDatabaseClient, DatabaseBackend


@pytest.fixture
def mock_postgres_client() -> MagicMock:
    """Provides a mock PostgresClient."""
    mock = MagicMock(spec=PostgresClient)
    mock.create = AsyncMock(return_value=1)
    mock.read = AsyncMock(return_value=[{"id": 1, "data": "pg_data"}])
    mock.is_connected = True
    return mock

@pytest.fixture
def mock_sqlite_client() -> MagicMock:
    """Provides a mock SQLiteClient."""
    mock = MagicMock(spec=SQLiteClient)
    mock.create = AsyncMock(return_value=123)
    mock.read = AsyncMock(return_value=[{"id": 1, "data": "sqlite_data"}])
    mock.is_connected = True
    return mock

@pytest.mark.asyncio
class TestDatabaseRouting:
    
    async def test_routing_to_postgres(self, mock_postgres_client, mock_sqlite_client):
        """
        Verify that a write operation for a 'user' collection is routed to PostgresClient.
        """
        # 1. Arrange
        unified_client = UnifiedDatabaseClient(
            postgres_client=mock_postgres_client, 
            sqlite_client=mock_sqlite_client
        )
        user_data = {"name": "test_user"}
        
        # 2. Act
        await unified_client.create(collection="user_profiles", document=user_data)
        
        # 3. Assert
        mock_postgres_client.create.assert_awaited_once_with("user_profiles", user_data)
        mock_sqlite_client.create.assert_not_awaited()

    async def test_routing_to_postgres_for_read(self, mock_postgres_client, mock_sqlite_client):
        """
        Verify that a read operation for a 'session' collection is routed to PostgresClient.
        """
        # 1. Arrange
        unified_client = UnifiedDatabaseClient(
            postgres_client=mock_postgres_client,
            sqlite_client=mock_sqlite_client
        )
        query = {"user_id": 42}
        
        # 2. Act
        result = await unified_client.read(collection="session_data", query=query)
        
        # 3. Assert
        mock_postgres_client.read.assert_awaited_once_with("session_data", query, None, None)
        mock_sqlite_client.read.assert_not_awaited()
        assert result[0]["data"] == "pg_data"

    async def test_fallback_to_sqlite(self, mock_sqlite_client):
        """
        Verify that if PostgresClient is not available, the operation falls back to SQLiteClient.
        """
        # 1. Arrange
        unified_client = UnifiedDatabaseClient(
            postgres_client=None,
            sqlite_client=mock_sqlite_client
        )
        user_data = {"name": "fallback_user"}
        
        # 2. Act
        await unified_client.create(collection="user_logins", document=user_data)
        
        # 3. Assert
        mock_sqlite_client.create.assert_awaited_once_with("user_logins", user_data)

    async def test_routing_to_terminusdb_raises_not_implemented(self, mock_postgres_client, mock_sqlite_client):
        """
        Verify that an operation for a 'schema' collection raises NotImplementedError.
        """
        # 1. Arrange
        unified_client = UnifiedDatabaseClient(
            postgres_client=mock_postgres_client,
            sqlite_client=mock_sqlite_client
        )
        schema_data = {"@type": "Class", "name": "MyClass"}

        # 2. Act & Assert
        with pytest.raises(NotImplementedError):
            await unified_client.create(collection="schema_definitions", document=schema_data) 