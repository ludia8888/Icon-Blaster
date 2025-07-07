"""
Unit Tests for SchemaRepository
"""
import pytest
from unittest.mock import MagicMock, AsyncMock

from core.schema.repository import SchemaRepository
from database.clients.unified_database_client import UnifiedDatabaseClient

@pytest.fixture
def mock_db_client() -> MagicMock:
    """Provides a MagicMock for the UnifiedDatabaseClient."""
    client = MagicMock(spec=UnifiedDatabaseClient)
    client.read = AsyncMock()
    client.create = AsyncMock()
    client.update = AsyncMock()
    client.delete = AsyncMock()
    return client

@pytest.mark.asyncio
async def test_list_all_object_types_calls_db_read(mock_db_client: MagicMock):
    """
    Test that list_all_object_types correctly calls the database's read method.
    """
    # 1. Setup
    repo = SchemaRepository(db_client=mock_db_client, db_name="test_db")
    branch_name = "main"
    
    # Mock the return value of the read method
    expected_documents = [{"@id": "ObjectType/Person", "name": "Person"}]
    mock_db_client.read.return_value = expected_documents

    # 2. Action
    # Before we call the method, we need to un-comment the actual logic in the repository
    # For now, this test will fail until we fix the repository method.
    # Let's assume for the test that the code is already fixed.
    
    result = await repo.list_all_object_types(branch=branch_name)

    # 3. Assertion
    # Verify that the read method was called once with the correct parameters
    mock_db_client.read.assert_called_once_with(
        collection="ObjectType", 
        query={"branch": branch_name}
    )
    
    # Verify that the result is what the database returned
    assert result == expected_documents 