"""
Find issues in DistributedLockManager implementation
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from core.branch.distributed_lock_manager import DistributedLockManager
from models.branch_state import BranchStateInfo, BranchState

pytestmark = pytest.mark.asyncio


class TestDistributedLockIssues:
    """Find what's wrong with DistributedLockManager"""
    
    async def test_distributed_lock_manager_creation(self):
        """Can we create a DistributedLockManager?"""
        mock_session = AsyncMock(spec=AsyncSession)
        
        # This should work
        manager = DistributedLockManager(mock_session)
        assert manager is not None
        assert manager.db_session == mock_session
    
    async def test_distributed_lock_context_manager(self):
        """Is distributed_lock properly implemented as async context manager?"""
        mock_session = AsyncMock(spec=AsyncSession)
        manager = DistributedLockManager(mock_session)
        
        # Mock execute to return success
        mock_result = MagicMock()
        mock_result.scalar.return_value = True
        mock_session.execute.return_value = mock_result
        
        # This should work
        async with manager.distributed_lock("test-resource"):
            pass
        
        # Check if SQL was executed
        assert mock_session.execute.called
    
    async def test_store_branch_state_issue(self):
        """What's wrong with _store_branch_state?"""
        mock_session = AsyncMock(spec=AsyncSession)
        manager = DistributedLockManager(mock_session)
        
        state = BranchStateInfo(
            branch_name="test",
            current_state=BranchState.ACTIVE,
            state_changed_by="test",
            state_change_reason="test"
        )
        
        # Mock parent's _store_branch_state
        parent_called = False
        
        async def mock_parent_store(self, state_info):
            nonlocal parent_called
            parent_called = True
        
        # Monkey patch the parent method
        import types
        manager._parent_store_branch_state = types.MethodType(mock_parent_store, manager)
        
        # Try to store - what happens?
        try:
            await manager._store_branch_state(state)
            print("_store_branch_state succeeded")
        except Exception as e:
            print(f"_store_branch_state failed: {e}")
            print(f"Error type: {type(e)}")
    
    async def test_json_method_deprecation(self):
        """Is the json() method deprecated?"""
        state = BranchStateInfo(
            branch_name="test",
            current_state=BranchState.ACTIVE,
            state_changed_by="test",
            state_change_reason="test"
        )
        
        # Check if json() exists
        if hasattr(state, 'json'):
            print("state.json() exists but may be deprecated")
            try:
                json_str = state.json()
                print(f"json() returns: {type(json_str)}")
            except Exception as e:
                print(f"json() failed: {e}")
        
        # Check for model_dump_json
        if hasattr(state, 'model_dump_json'):
            print("state.model_dump_json() exists (Pydantic v2)")
            json_str = state.model_dump_json()
            print(f"model_dump_json() returns: {type(json_str)}")
    
    async def test_parse_raw_deprecation(self):
        """Is parse_raw deprecated?"""
        json_data = '{"branch_name": "test", "current_state": "ACTIVE", "state_changed_by": "test", "state_change_reason": "test"}'
        
        # Try parse_raw
        if hasattr(BranchStateInfo, 'parse_raw'):
            print("BranchStateInfo.parse_raw exists but may be deprecated")
            try:
                state = BranchStateInfo.parse_raw(json_data)
                print(f"parse_raw succeeded: {state.branch_name}")
            except Exception as e:
                print(f"parse_raw failed: {e}")
        
        # Try model_validate_json
        if hasattr(BranchStateInfo, 'model_validate_json'):
            print("BranchStateInfo.model_validate_json exists (Pydantic v2)")
            state = BranchStateInfo.model_validate_json(json_data)
            print(f"model_validate_json succeeded: {state.branch_name}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])