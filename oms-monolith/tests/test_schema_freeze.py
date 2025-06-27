"""
Tests for Schema Freeze mechanism
Validates branch locking and data integrity features
"""
import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

from core.branch.lock_manager import BranchLockManager, LockConflictError
from models.branch_state import (
    BranchState, BranchLock, BranchStateInfo,
    LockType, LockScope
)
from middleware.schema_freeze_middleware import (
    SchemaFreezeMiddleware, check_branch_write_permission,
    require_write_permission, SchemaFreezeError
)


class TestBranchLockManager:
    """Test the branch lock manager"""
    
    @pytest.fixture
    def lock_manager(self):
        """Create a lock manager for testing"""
        return BranchLockManager()
    
    @pytest.mark.asyncio
    async def test_initial_branch_state(self, lock_manager):
        """Test that new branches start in ACTIVE state"""
        branch_state = await lock_manager.get_branch_state("test-branch")
        
        assert branch_state.branch_name == "test-branch"
        assert branch_state.current_state == BranchState.ACTIVE
        assert len(branch_state.active_locks) == 0
        assert not branch_state.is_write_locked
    
    @pytest.mark.asyncio
    async def test_acquire_indexing_lock(self, lock_manager):
        """Test acquiring an indexing lock"""
        lock_id = await lock_manager.lock_for_indexing(
            branch_name="test-branch",
            locked_by="funnel-service",
            reason="Test indexing"
        )
        
        assert lock_id is not None
        
        # Check branch state
        branch_state = await lock_manager.get_branch_state("test-branch")
        assert branch_state.current_state == BranchState.LOCKED_FOR_WRITE
        assert branch_state.is_write_locked
        assert len(branch_state.active_locks) == 1
        assert branch_state.indexing_started_at is not None
    
    @pytest.mark.asyncio
    async def test_write_permission_blocked_when_locked(self, lock_manager):
        """Test that write operations are blocked when branch is locked"""
        # Lock the branch
        await lock_manager.lock_for_indexing("test-branch")
        
        # Check write permission
        can_write, reason = await lock_manager.check_write_permission(
            "test-branch", "write"
        )
        
        assert not can_write
        assert "locked for write operations" in reason.lower()
    
    @pytest.mark.asyncio
    async def test_read_permission_allowed_when_locked(self, lock_manager):
        """Test that read operations are still allowed when branch is locked"""
        # Lock the branch
        await lock_manager.lock_for_indexing("test-branch")
        
        # Check read permission
        can_read, reason = await lock_manager.check_write_permission(
            "test-branch", "read"
        )
        
        assert can_read
        assert "always allowed" in reason.lower()
    
    @pytest.mark.asyncio
    async def test_complete_indexing(self, lock_manager):
        """Test completing indexing operation"""
        # Start indexing
        lock_id = await lock_manager.lock_for_indexing("test-branch")
        
        # Complete indexing
        success = await lock_manager.complete_indexing("test-branch")
        assert success
        
        # Check branch state
        branch_state = await lock_manager.get_branch_state("test-branch")
        assert branch_state.current_state == BranchState.READY
        assert not branch_state.is_write_locked
        assert branch_state.indexing_completed_at is not None
    
    @pytest.mark.asyncio
    async def test_lock_conflicts(self, lock_manager):
        """Test that conflicting locks are rejected"""
        # Acquire first lock
        lock_id1 = await lock_manager.acquire_lock(
            branch_name="test-branch",
            lock_type=LockType.INDEXING,
            locked_by="service1",
            lock_scope=LockScope.BRANCH,
            reason="First lock"
        )
        
        # Try to acquire conflicting lock
        with pytest.raises(LockConflictError):
            await lock_manager.acquire_lock(
                branch_name="test-branch",
                lock_type=LockType.MAINTENANCE,
                locked_by="service2",
                lock_scope=LockScope.BRANCH,
                reason="Conflicting lock"
            )
    
    @pytest.mark.asyncio
    async def test_resource_specific_locks(self, lock_manager):
        """Test resource-specific locks don't conflict with other resources"""
        # Lock specific resource type
        lock_id1 = await lock_manager.acquire_lock(
            branch_name="test-branch",
            lock_type=LockType.MAINTENANCE,
            locked_by="service1",
            lock_scope=LockScope.RESOURCE_TYPE,
            resource_type="object_type",
            reason="ObjectType maintenance"
        )
        
        # Should be able to lock different resource type
        lock_id2 = await lock_manager.acquire_lock(
            branch_name="test-branch",
            lock_type=LockType.MAINTENANCE,
            locked_by="service2",
            lock_scope=LockScope.RESOURCE_TYPE,
            resource_type="link_type",
            reason="LinkType maintenance"
        )
        
        assert lock_id1 != lock_id2
        
        # But should conflict with same resource type
        with pytest.raises(LockConflictError):
            await lock_manager.acquire_lock(
                branch_name="test-branch",
                lock_type=LockType.BACKUP,
                locked_by="service3",
                lock_scope=LockScope.RESOURCE_TYPE,
                resource_type="object_type",
                reason="Conflicting ObjectType lock"
            )
    
    @pytest.mark.asyncio
    async def test_force_unlock(self, lock_manager):
        """Test administrative force unlock"""
        # Create multiple locks
        lock_id1 = await lock_manager.lock_for_indexing("test-branch")
        lock_id2 = await lock_manager.acquire_lock(
            branch_name="test-branch",
            lock_type=LockType.MANUAL,
            locked_by="user1",
            lock_scope=LockScope.RESOURCE_TYPE,
            resource_type="object_type",
            reason="Manual lock"
        )
        
        # Force unlock
        count = await lock_manager.force_unlock(
            branch_name="test-branch",
            admin_user="admin",
            reason="Emergency unlock"
        )
        
        assert count == 2  # Two locks were released
        
        # Check branch state
        branch_state = await lock_manager.get_branch_state("test-branch")
        assert branch_state.current_state == BranchState.ACTIVE
        assert not branch_state.is_write_locked


class TestSchemaFreezeMiddleware:
    """Test the schema freeze middleware"""
    
    @pytest.fixture
    def mock_lock_manager(self):
        """Create a mock lock manager"""
        mock = AsyncMock()
        mock.check_write_permission = AsyncMock()
        return mock
    
    @pytest.fixture
    def middleware(self, mock_lock_manager):
        """Create middleware with mock lock manager"""
        from unittest.mock import patch
        
        with patch('middleware.schema_freeze_middleware.get_lock_manager', 
                  return_value=mock_lock_manager):
            return SchemaFreezeMiddleware(app=None)
    
    def test_extract_branch_from_url(self, middleware):
        """Test branch extraction from URL paths"""
        from fastapi import Request
        
        # Mock request with branch in URL
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/schemas/feature-branch/object-types"
        
        branch = middleware._extract_branch_from_request(request)
        assert branch == "feature-branch"
    
    def test_extract_resource_info(self, middleware):
        """Test resource information extraction"""
        from fastapi import Request
        
        # Mock request for object type
        request = MagicMock(spec=Request)
        request.url.path = "/api/v1/schemas/main/object-types/User"
        
        resource_type, resource_id = middleware._extract_resource_info(request)
        assert resource_type == "object_type"
        assert resource_id == "User"
    
    def test_affects_schema_detection(self, middleware):
        """Test detection of schema-affecting paths"""
        schema_paths = [
            "/api/v1/schemas/main/object-types",
            "/action-types/123",
            "/graphql"
        ]
        
        non_schema_paths = [
            "/health",
            "/metrics",
            "/api/v1/some-other-endpoint"
        ]
        
        for path in schema_paths:
            assert middleware._affects_schema(path)
        
        for path in non_schema_paths:
            assert not middleware._affects_schema(path)


class TestSchemaFreezeUtilities:
    """Test utility functions for schema freeze"""
    
    @pytest.mark.asyncio
    async def test_check_branch_write_permission(self):
        """Test utility function for checking write permission"""
        # This would require setting up the lock manager
        # For now, test the interface
        from unittest.mock import patch, AsyncMock
        
        mock_manager = AsyncMock()
        mock_manager.check_write_permission = AsyncMock(return_value=(True, "Allowed"))
        
        with patch('middleware.schema_freeze_middleware.get_lock_manager', 
                  return_value=mock_manager):
            can_write, reason = await check_branch_write_permission("test-branch")
            
            assert can_write
            assert reason == "Allowed"
            mock_manager.check_write_permission.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_require_write_permission_allowed(self):
        """Test require_write_permission when allowed"""
        from unittest.mock import patch, AsyncMock
        
        mock_manager = AsyncMock()
        mock_manager.check_write_permission = AsyncMock(return_value=(True, "Allowed"))
        
        with patch('middleware.schema_freeze_middleware.get_lock_manager', 
                  return_value=mock_manager):
            # Should not raise exception
            await require_write_permission("test-branch")
    
    @pytest.mark.asyncio
    async def test_require_write_permission_blocked(self):
        """Test require_write_permission when blocked"""
        from unittest.mock import patch, AsyncMock
        
        mock_manager = AsyncMock()
        mock_manager.check_write_permission = AsyncMock(
            return_value=(False, "Branch is locked")
        )
        
        with patch('middleware.schema_freeze_middleware.get_lock_manager', 
                  return_value=mock_manager):
            # Should raise SchemaFreezeError
            with pytest.raises(SchemaFreezeError) as exc_info:
                await require_write_permission("test-branch")
            
            assert exc_info.value.status_code == 423  # HTTP_LOCKED
            assert "locked" in str(exc_info.value.detail)


class TestBranchStateTransitions:
    """Test branch state transitions"""
    
    def test_valid_state_transitions(self):
        """Test that valid state transitions are allowed"""
        from models.branch_state import is_valid_transition
        
        # Valid transitions
        assert is_valid_transition(BranchState.ACTIVE, BranchState.LOCKED_FOR_WRITE)
        assert is_valid_transition(BranchState.LOCKED_FOR_WRITE, BranchState.READY)
        assert is_valid_transition(BranchState.READY, BranchState.ACTIVE)
        assert is_valid_transition(BranchState.ACTIVE, BranchState.ARCHIVED)
    
    def test_invalid_state_transitions(self):
        """Test that invalid state transitions are rejected"""
        from models.branch_state import is_valid_transition
        
        # Invalid transitions
        assert not is_valid_transition(BranchState.ARCHIVED, BranchState.ACTIVE)
        assert not is_valid_transition(BranchState.READY, BranchState.LOCKED_FOR_WRITE)
        assert not is_valid_transition(BranchState.ACTIVE, BranchState.READY)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])