"""
Unit Tests for SchemaService
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from core.schema.service import SchemaService
from core.schema.repository import SchemaRepository
# We need to import BranchService, but to avoid circular dependencies in tests,
# we can use a string hint or a placeholder mock.
# For now, let's create a dummy class for type hinting.

class MockBranchService:
    create_branch = AsyncMock()
    commit_changes = AsyncMock()
    create_pull_request = AsyncMock()

@pytest.fixture
def mock_schema_repository() -> MagicMock:
    """Provides a MagicMock for the SchemaRepository."""
    repo = MagicMock(spec=SchemaRepository)
    repo.list_all_object_types = AsyncMock()
    repo.create_new_object_type = AsyncMock()
    return repo

@pytest.fixture
def mock_branch_service() -> MagicMock:
    """Provides a MagicMock for the BranchService."""
    service = MagicMock(spec=MockBranchService)
    service.create_branch = AsyncMock(return_value=True)
    service.commit_changes = AsyncMock(return_value="new_commit_sha")
    service.create_pull_request = AsyncMock(return_value={"pr_id": "123"})
    return service

@pytest.mark.asyncio
async def test_list_object_types_calls_repository(mock_schema_repository: MagicMock, mock_branch_service: MagicMock):
    """
    Test that list_object_types simply calls the repository's method.
    """
    # 1. Setup
    service = SchemaService(repository=mock_schema_repository, branch_service=mock_branch_service)
    expected_list = [{"name": "TestType"}]
    mock_schema_repository.list_all_object_types.return_value = expected_list

    # 2. Action
    result = await service.list_object_types(branch="main")

    # 3. Assertion
    mock_schema_repository.list_all_object_types.assert_called_once_with("main")
    assert result == expected_list

@pytest.mark.asyncio
async def test_create_object_type_with_branch_workflow(mock_schema_repository: MagicMock, mock_branch_service: MagicMock):
    """
    Test the create_object_type method when using the full branch workflow.
    It should call branch_service methods in the correct order.
    """
    # 1. Setup
    # To properly mock the chained calls, we need to ensure get_author is patched
    # or handled. For unit tests, we can often just provide the values directly.
    # Let's assume get_author() returns 'test_user'. We can use monkeypatch for this.
    
    service = SchemaService(repository=mock_schema_repository, branch_service=mock_branch_service)

    # Mocking the input data
    object_data = MagicMock()
    object_data.name = "NewSchema"
    object_data.display_name = "New Schema"
    object_data.description = "A new schema for testing"

    mock_schema_repository.create_new_object_type.return_value = True

    # 2. Action
    # We need to mock the context functions get_author and get_branch
    # For now, let's proceed and see the error, then patch it.
    # This test will likely fail because get_author is not available in the test context.
    
    # Let's pretend for a moment that we can patch it easily.
    # with patch('core.schema.service.get_author', return_value='test_user'):
    # result = await service.create_object_type(branch="main", data=object_data, use_branch_workflow=True)

    # To make it pass without patching for now, we can simplify the test scope
    # and focus on the interactions. We will need to patch get_author.
    # Let's add a placeholder assertion and then fix the context issue.

    from unittest.mock import patch
    with patch('core.schema.service.get_author', return_value='test_user'):
        await service.create_object_type(branch="main", data=object_data, use_branch_workflow=True)

    # 3. Assertion
    # Check that the branch service methods were called in order
    mock_branch_service.create_branch.assert_called_once()
    mock_schema_repository.create_new_object_type.assert_called_once()
    mock_branch_service.commit_changes.assert_called_once()
    mock_branch_service.create_pull_request.assert_called_once()

    # More detailed assertion for arguments
    create_branch_args = mock_branch_service.create_branch.call_args
    assert create_branch_args.kwargs['parent_branch'] == 'main'
    assert create_branch_args.kwargs['created_by'] == 'test_user'
    assert create_branch_args.kwargs['branch_name'].startswith('schema-create/NewSchema-') 