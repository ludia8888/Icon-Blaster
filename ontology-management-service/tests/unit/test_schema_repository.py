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

@pytest.mark.asyncio
async def test_create_new_object_type_calls_db_create(mock_db_client: MagicMock):
    """
    Test that create_new_object_type correctly calls the database's create method.
    """
    # 1. Setup
    repo = SchemaRepository(db_client=mock_db_client, db_name="test_db")
    author = "test_author"
    object_data = MagicMock()
    object_data.name = "TestObject"
    object_data.display_name = "Test Object"
    object_data.description = "A test object"

    mock_db_client.create.return_value = True # Assume creation is successful

    # 2. Action
    result = await repo.create_new_object_type(branch="main", data=object_data, author=author)

    # 3. Assertion
    expected_doc = {
        "@type": "ObjectType",
        "@id": f"ObjectType/{object_data.name}",
        "name": object_data.name,
        "displayName": object_data.display_name,
        "description": object_data.description
    }
    mock_db_client.create.assert_called_once_with(
        collection="ObjectType",
        document=expected_doc
    )
    assert result is True

@pytest.mark.asyncio
async def test_get_object_type_by_name_calls_db_read(mock_db_client: MagicMock):
    """
    Test that get_object_type_by_name calls the db's read method with a specific query.
    """
    # 1. Setup
    repo = SchemaRepository(db_client=mock_db_client, db_name="test_db")
    object_name = "TestObject"
    branch_name = "main"
    
    expected_document = [{"@id": f"ObjectType/{object_name}", "name": object_name}]
    mock_db_client.read.return_value = expected_document

    # 2. Action
    result = await repo.get_object_type_by_name(name=object_name, branch=branch_name)

    # 3. Assertion
    mock_db_client.read.assert_called_once_with(
        collection="ObjectType",
        query={"name": object_name, "branch": branch_name}
    )
    assert result == expected_document[0] 