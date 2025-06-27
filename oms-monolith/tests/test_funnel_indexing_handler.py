"""
Tests for Funnel Service Indexing Event Handler
Validates indexing.completed event processing and branch state management
"""
import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from core.event_consumer.funnel_indexing_handler import FunnelIndexingEventHandler
from models.branch_state import BranchState, BranchStateInfo
from models.audit_events import AuditAction


class TestFunnelIndexingEventHandler:
    """Test the Funnel Service indexing event handler"""
    
    @pytest.fixture
    def mock_lock_manager(self):
        """Create a mock lock manager"""
        mock = AsyncMock()
        mock.get_branch_state = AsyncMock()
        mock.complete_indexing = AsyncMock()
        mock.set_branch_state = AsyncMock()
        return mock
    
    @pytest.fixture
    def handler(self, mock_lock_manager):
        """Create handler with mock lock manager"""
        with patch('core.event_consumer.funnel_indexing_handler.get_lock_manager', 
                  return_value=mock_lock_manager):
            return FunnelIndexingEventHandler()
    
    @pytest.fixture
    def successful_indexing_event(self):
        """Sample successful indexing event"""
        return {
            "id": "indexing-event-123",
            "source": "funnel-service",
            "type": "com.oms.indexing.completed",
            "timestamp": "2025-06-26T10:30:00Z",
            "data": {
                "branch_name": "feature/user-schema",
                "indexing_id": "idx-123",
                "started_at": "2025-06-26T10:00:00Z",
                "completed_at": "2025-06-26T10:30:00Z",
                "status": "success",
                "records_indexed": 1250,
                "errors": [],
                "validation_results": {
                    "passed": True,
                    "errors": []
                }
            }
        }
    
    @pytest.fixture
    def failed_indexing_event(self):
        """Sample failed indexing event"""
        return {
            "id": "indexing-event-456",
            "source": "funnel-service",
            "type": "com.oms.indexing.completed",
            "timestamp": "2025-06-26T10:30:00Z",
            "data": {
                "branch_name": "feature/problematic-schema",
                "indexing_id": "idx-456",
                "started_at": "2025-06-26T10:00:00Z",
                "completed_at": "2025-06-26T10:30:00Z",
                "status": "failed",
                "error_message": "Schema validation failed",
                "records_indexed": 0,
                "errors": ["Invalid field type in User object"]
            }
        }
    
    @pytest.mark.asyncio
    async def test_successful_indexing_handling(
        self, 
        handler, 
        mock_lock_manager, 
        successful_indexing_event
    ):
        """Test handling of successful indexing event"""
        # Setup mock branch state
        branch_state = BranchStateInfo(
            branch_name="feature/user-schema",
            current_state=BranchState.LOCKED_FOR_WRITE,
            state_changed_by="funnel-service",
            state_change_reason="Indexing in progress"
        )
        mock_lock_manager.get_branch_state.return_value = branch_state
        mock_lock_manager.complete_indexing.return_value = True
        
        # Process event
        result = await handler.handle_indexing_completed(successful_indexing_event)
        
        # Verify success
        assert result is True
        
        # Verify lock manager calls
        mock_lock_manager.get_branch_state.assert_called_with("feature/user-schema")
        mock_lock_manager.complete_indexing.assert_called_with(
            branch_name="feature/user-schema",
            completed_by="funnel-service"
        )
    
    @pytest.mark.asyncio
    async def test_failed_indexing_handling(
        self, 
        handler, 
        mock_lock_manager, 
        failed_indexing_event
    ):
        """Test handling of failed indexing event"""
        # Setup mock branch state
        branch_state = BranchStateInfo(
            branch_name="feature/problematic-schema",
            current_state=BranchState.LOCKED_FOR_WRITE,
            state_changed_by="funnel-service",
            state_change_reason="Indexing in progress"
        )
        mock_lock_manager.get_branch_state.return_value = branch_state
        mock_lock_manager.set_branch_state.return_value = True
        
        # Process event
        result = await handler.handle_indexing_completed(failed_indexing_event)
        
        # Verify success (event was processed, even though indexing failed)
        assert result is True
        
        # Verify lock manager calls
        mock_lock_manager.get_branch_state.assert_called_with("feature/problematic-schema")
        mock_lock_manager.set_branch_state.assert_called_with(
            branch_name="feature/problematic-schema",
            new_state=BranchState.ERROR,
            reason="Indexing failed: Schema validation failed"
        )
    
    @pytest.mark.asyncio
    async def test_missing_branch_name(
        self, 
        handler, 
        mock_lock_manager
    ):
        """Test handling of event with missing branch name"""
        invalid_event = {
            "id": "invalid-event-123",
            "source": "funnel-service",
            "data": {
                "indexing_id": "idx-123",
                "status": "success"
                # Missing branch_name
            }
        }
        
        # Process event
        result = await handler.handle_indexing_completed(invalid_event)
        
        # Verify failure
        assert result is False
        
        # Verify no lock manager calls
        mock_lock_manager.get_branch_state.assert_not_called()
        mock_lock_manager.complete_indexing.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_auto_merge_conditions_check(
        self, 
        handler, 
        mock_lock_manager, 
        successful_indexing_event
    ):
        """Test auto-merge conditions checking"""
        # Setup mock branch state (successful indexing puts branch in READY state)
        ready_branch_state = BranchStateInfo(
            branch_name="feature/user-schema",
            current_state=BranchState.READY,
            state_changed_by="funnel-service",
            state_change_reason="Indexing completed"
        )
        
        # First call returns LOCKED_FOR_WRITE, second call returns READY
        mock_lock_manager.get_branch_state.side_effect = [
            BranchStateInfo(
                branch_name="feature/user-schema",
                current_state=BranchState.LOCKED_FOR_WRITE,
                state_changed_by="funnel-service",
                state_change_reason="Indexing in progress"
            ),
            ready_branch_state
        ]
        mock_lock_manager.complete_indexing.return_value = True
        
        # Mock auto-merge check methods
        with patch.object(handler, '_check_merge_conflicts', return_value=False), \
             patch.object(handler, '_trigger_auto_merge') as mock_auto_merge:
            
            # Process event
            result = await handler.handle_indexing_completed(successful_indexing_event)
            
            # Verify success
            assert result is True
            
            # Verify auto-merge was triggered
            mock_auto_merge.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_auto_merge_blocked_by_validation(
        self, 
        handler, 
        mock_lock_manager
    ):
        """Test auto-merge blocked by validation failure"""
        # Event with failed validation
        event_with_failed_validation = {
            "id": "indexing-event-123",
            "source": "funnel-service",
            "data": {
                "branch_name": "feature/user-schema",
                "status": "success",
                "validation_results": {
                    "passed": False,
                    "errors": ["Validation error"]
                }
            }
        }
        
        # Setup mocks
        mock_lock_manager.get_branch_state.side_effect = [
            BranchStateInfo(
                branch_name="feature/user-schema",
                current_state=BranchState.LOCKED_FOR_WRITE,
                state_changed_by="funnel-service",
                state_change_reason="Indexing in progress"
            ),
            BranchStateInfo(
                branch_name="feature/user-schema",
                current_state=BranchState.READY,
                state_changed_by="funnel-service",
                state_change_reason="Indexing completed"
            )
        ]
        mock_lock_manager.complete_indexing.return_value = True
        
        # Mock auto-merge methods
        with patch.object(handler, '_trigger_auto_merge') as mock_auto_merge:
            
            # Process event
            result = await handler.handle_indexing_completed(event_with_failed_validation)
            
            # Verify success but no auto-merge
            assert result is True
            mock_auto_merge.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_duration_calculation(self, handler):
        """Test indexing duration calculation"""
        duration = handler._calculate_duration(
            "2025-06-26T10:00:00Z",
            "2025-06-26T10:30:00Z"
        )
        
        assert duration == 1800.0  # 30 minutes in seconds
    
    @pytest.mark.asyncio
    async def test_duration_calculation_invalid_dates(self, handler):
        """Test duration calculation with invalid dates"""
        duration = handler._calculate_duration(
            "invalid-date",
            "2025-06-26T10:30:00Z"
        )
        
        assert duration is None
    
    @pytest.mark.asyncio
    async def test_branch_in_unexpected_state(
        self, 
        handler, 
        mock_lock_manager, 
        successful_indexing_event
    ):
        """Test handling when branch is not in LOCKED_FOR_WRITE state"""
        # Branch in unexpected state
        branch_state = BranchStateInfo(
            branch_name="feature/user-schema",
            current_state=BranchState.ACTIVE,  # Unexpected state
            state_changed_by="user",
            state_change_reason="Manual unlock"
        )
        mock_lock_manager.get_branch_state.return_value = branch_state
        mock_lock_manager.complete_indexing.return_value = True
        
        # Process event
        result = await handler.handle_indexing_completed(successful_indexing_event)
        
        # Should still process successfully but log warning
        assert result is True
        
        # Complete indexing should still be called
        mock_lock_manager.complete_indexing.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
