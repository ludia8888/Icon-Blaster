"""Basic unit tests for BranchService - Core business logic for Git-style branching."""

import pytest
import asyncio
import sys
import os
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from typing import Dict, Any, Optional

# Add the project root to the path to import modules directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))))

# Mock external dependencies before imports
sys.modules['prometheus_client'] = MagicMock()
sys.modules['common_logging'] = MagicMock()
sys.modules['common_logging.setup'] = MagicMock()

# Import modules directly using importlib to avoid dependency issues
import importlib.util

# Load BranchService
branch_service_spec = importlib.util.spec_from_file_location(
    "branch_service",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))), "core", "branch", "service.py")
)
branch_service_module = importlib.util.module_from_spec(branch_service_spec)
sys.modules['branch_service'] = branch_service_module

# Mock all the dependencies before loading
sys.modules['core.branch.diff_engine'] = MagicMock()
sys.modules['core.branch.conflict_resolver'] = MagicMock()
sys.modules['core.branch.merge_strategies'] = MagicMock()
sys.modules['core.branch.three_way_merge'] = MagicMock()
sys.modules['shared.cache.smart_cache'] = MagicMock()
sys.modules['database.clients.terminus_db'] = MagicMock()
sys.modules['shared.terminus_context'] = MagicMock()

try:
    branch_service_spec.loader.exec_module(branch_service_module)
except Exception as e:
    print(f"Warning: Could not load BranchService module: {e}")

# Import what we need
BranchService = getattr(branch_service_module, 'BranchService', None)

# Create mock classes if imports fail
if BranchService is None:
    class BranchService:
        def __init__(self, *args, **kwargs):
            pass

# Mock enum classes
class ProposalStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class MergeStrategy:
    THREE_WAY = "three_way"
    FAST_FORWARD = "fast_forward"

# Mock data classes
class ChangeProposal:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

class Branch:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class TestBranchServiceBasics:
    """Test suite for BranchService basic functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.tdb_endpoint = "http://test-terminus.local"
        self.mock_diff_engine = Mock()
        self.mock_conflict_resolver = Mock()
        self.mock_event_publisher = Mock()
        
        with patch('core.branch.service.TerminusDBClient') as mock_tdb_client, \
             patch('core.branch.service.SmartCacheManager') as mock_cache, \
             patch('core.branch.service.MergeStrategyImplementor') as mock_merge_strategies:
            
            self.mock_tdb = Mock()
            mock_tdb_client.return_value = self.mock_tdb
            
            self.mock_cache = Mock()
            mock_cache.return_value = self.mock_cache
            
            self.mock_merge_strategies = Mock()
            mock_merge_strategies.return_value = self.mock_merge_strategies
            
            self.service = BranchService(
                tdb_endpoint=self.tdb_endpoint,
                diff_engine=self.mock_diff_engine,
                conflict_resolver=self.mock_conflict_resolver,
                event_publisher=self.mock_event_publisher
            )
    
    def test_branch_service_initialization(self):
        """Test BranchService initialization with dependencies."""
        assert self.service.tdb_endpoint == self.tdb_endpoint
        assert self.service.diff_engine == self.mock_diff_engine
        assert self.service.conflict_resolver == self.mock_conflict_resolver
        assert self.service.event_publisher == self.mock_event_publisher
        assert self.service.db_name == os.getenv("TERMINUSDB_DB", "oms")
        assert self.service.three_way_merge is None  # Not initialized yet
    
    def test_generate_id(self):
        """Test ID generation."""
        id1 = self.service._generate_id()
        id2 = self.service._generate_id()
        
        assert isinstance(id1, str)
        assert isinstance(id2, str)
        assert id1 != id2  # Should generate unique IDs
        assert len(id1) == 36  # UUID4 format
    
    def test_generate_proposal_id(self):
        """Test proposal ID generation."""
        proposal_id = self.service._generate_proposal_id()
        
        assert isinstance(proposal_id, str)
        assert proposal_id.startswith("proposal_")
        assert len(proposal_id) > 9  # "proposal_" + UUID


class TestBranchServiceValidation:
    """Test suite for BranchService validation methods."""
    
    def setup_method(self):
        """Set up test fixtures."""
        with patch('core.branch.service.TerminusDBClient'), \
             patch('core.branch.service.SmartCacheManager'), \
             patch('core.branch.service.MergeStrategyImplementor'):
            
            self.service = BranchService(
                tdb_endpoint="http://test.local",
                diff_engine=Mock(),
                conflict_resolver=Mock()
            )
    
    def test_validate_branch_name_valid_names(self):
        """Test branch name validation with valid names."""
        valid_names = [
            "main",
            "feature",
            "feature/user-auth",
            "bugfix/fix-123",
            "release/v1-0-0",
            "hotfix/security-patch",
            "dev/john-doe",
            "test123",
            "a",
            "a123",
            "feature-branch"
        ]
        
        for name in valid_names:
            assert self.service._validate_branch_name(name) is True, f"'{name}' should be valid"
    
    def test_validate_branch_name_invalid_names(self):
        """Test branch name validation with invalid names."""
        invalid_names = [
            "",              # Empty
            "Feature",       # Uppercase
            "123feature",    # Starts with number
            "-feature",      # Starts with hyphen
            "/feature",      # Starts with slash
            "feature..dev",  # Double dots
            "feature branch", # Spaces
            "feature@dev",   # Special characters
            "feature.dev",   # Dots
            "feature_dev",   # Underscores
        ]
        
        for name in invalid_names:
            assert self.service._validate_branch_name(name) is False, f"'{name}' should be invalid"
    
    @pytest.mark.asyncio
    async def test_check_branch_exists_from_db_success(self):
        """Test direct DB branch existence check - success case."""
        branch_name = "test-branch"
        mock_branch_info = {"name": branch_name, "head": "commit123"}
        
        self.service.tdb.get_branch_info = AsyncMock(return_value=mock_branch_info)
        
        result = await self.service._check_branch_exists_from_db(branch_name)
        
        assert result is True
        self.service.tdb.get_branch_info.assert_called_once_with(self.service.db_name, branch_name)
    
    @pytest.mark.asyncio
    async def test_check_branch_exists_from_db_not_found(self):
        """Test direct DB branch existence check - branch not found."""
        branch_name = "nonexistent-branch"
        
        self.service.tdb.get_branch_info = AsyncMock(return_value=None)
        
        result = await self.service._check_branch_exists_from_db(branch_name)
        
        assert result is False
        self.service.tdb.get_branch_info.assert_called_once_with(self.service.db_name, branch_name)
    
    @pytest.mark.asyncio
    async def test_check_branch_exists_from_db_exception(self):
        """Test direct DB branch existence check - exception handling."""
        branch_name = "error-branch"
        
        self.service.tdb.get_branch_info = AsyncMock(side_effect=Exception("DB connection error"))
        
        result = await self.service._check_branch_exists_from_db(branch_name)
        
        assert result is False
        self.service.tdb.get_branch_info.assert_called_once_with(self.service.db_name, branch_name)
    
    @pytest.mark.asyncio
    async def test_is_protected_branch_system_branches(self):
        """Test protected branch detection for system branches."""
        # Based on actual implementation at end of file: ["main", "master", "production"]
        system_branches = ["main", "master", "production"]
        
        for branch in system_branches:
            result = await self.service._is_protected_branch(branch)
            assert result is True, f"'{branch}' should be protected"
    
    @pytest.mark.asyncio
    async def test_is_protected_branch_not_protected(self):
        """Test protected branch detection for regular branches."""
        # Simple implementation just checks hardcoded list
        non_protected_branches = ["feature/test", "bugfix/issue-123", "dev/user"]
        
        for branch in non_protected_branches:
            result = await self.service._is_protected_branch(branch)
            assert result is False, f"'{branch}' should not be protected"


class TestBranchServiceDirectDB:
    """Test suite for BranchService direct database operations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        with patch('core.branch.service.TerminusDBClient'), \
             patch('core.branch.service.SmartCacheManager'), \
             patch('core.branch.service.MergeStrategyImplementor'):
            
            self.service = BranchService(
                tdb_endpoint="http://test.local",
                diff_engine=Mock(),
                conflict_resolver=Mock()
            )
    
    @pytest.mark.asyncio
    async def test_get_branch_info_from_db_success(self):
        """Test direct DB branch info retrieval - success case."""
        branch_name = "test-branch"
        expected_info = {
            "name": branch_name,
            "head": "commit456",
            "parent": "main"
        }
        
        self.service.tdb.get_branch_info = AsyncMock(return_value=expected_info)
        
        result = await self.service._get_branch_info_from_db(branch_name)
        
        assert result == expected_info
        self.service.tdb.get_branch_info.assert_called_once_with(self.service.db_name, branch_name)
    
    @pytest.mark.asyncio
    async def test_get_branch_info_from_db_not_found(self):
        """Test direct DB branch info retrieval - branch not found."""
        branch_name = "nonexistent"
        
        self.service.tdb.get_branch_info = AsyncMock(return_value=None)
        
        result = await self.service._get_branch_info_from_db(branch_name)
        
        assert result is None
        self.service.tdb.get_branch_info.assert_called_once_with(self.service.db_name, branch_name)
    
    @pytest.mark.asyncio
    async def test_get_branch_info_from_db_exception(self):
        """Test direct DB branch info retrieval - exception handling."""
        branch_name = "error-branch"
        
        self.service.tdb.get_branch_info = AsyncMock(side_effect=Exception("Network error"))
        
        result = await self.service._get_branch_info_from_db(branch_name)
        
        assert result is None
        self.service.tdb.get_branch_info.assert_called_once_with(self.service.db_name, branch_name)


class TestBranchServiceEventPublishing:
    """Test suite for BranchService event publishing functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_event_publisher = AsyncMock()
        
        with patch('core.branch.service.TerminusDBClient'), \
             patch('core.branch.service.SmartCacheManager'), \
             patch('core.branch.service.MergeStrategyImplementor'):
            
            self.service = BranchService(
                tdb_endpoint="http://test.local",
                diff_engine=Mock(),
                conflict_resolver=Mock(),
                event_publisher=self.mock_event_publisher
            )
    
    @pytest.mark.asyncio
    async def test_publish_event_with_publisher(self):
        """Test event publishing when event publisher is available."""
        event_type = "branch.created"
        event_data = {
            "branch_name": "feature/test",
            "created_by": "user1",
            "timestamp": datetime.now().isoformat()
        }
        
        self.mock_event_publisher.publish = AsyncMock()
        
        await self.service._publish_event(event_type, event_data)
        
        self.mock_event_publisher.publish.assert_called_once_with(event_type, event_data)
    
    @pytest.mark.asyncio
    async def test_publish_event_no_publisher(self):
        """Test event publishing when no event publisher is configured."""
        event_type = "branch.deleted"
        event_data = {"branch_name": "feature/test"}
        
        # Create service without event publisher
        with patch('core.branch.service.TerminusDBClient'), \
             patch('core.branch.service.SmartCacheManager'), \
             patch('core.branch.service.MergeStrategyImplementor'):
            
            service_no_publisher = BranchService(
                tdb_endpoint="http://test.local",
                diff_engine=Mock(),
                conflict_resolver=Mock(),
                event_publisher=None
            )
        
        # Should not raise exception
        await service_no_publisher._publish_event(event_type, event_data)
        
        # No assertions needed - just ensuring no exception is raised
    
    @pytest.mark.asyncio
    async def test_publish_event_publisher_exception(self):
        """Test event publishing when publisher raises exception."""
        event_type = "branch.merged"
        event_data = {"branch_name": "feature/test"}
        
        self.mock_event_publisher.publish = AsyncMock(side_effect=Exception("Event publishing failed"))
        
        # Should not raise exception (event publishing failures should be non-blocking)
        await self.service._publish_event(event_type, event_data)
        
        self.mock_event_publisher.publish.assert_called_once_with(event_type, event_data)


# Test data factories for complex objects
class BranchTestDataFactory:
    """Factory for creating test data objects."""
    
    @staticmethod
    def create_branch_info(
        name: str = "test-branch",
        head: str = "commit123",
        parent: Optional[str] = "main",
        created_by: str = "user1"
    ) -> Dict[str, Any]:
        """Create branch info dictionary."""
        return {
            "name": name,
            "head": head,
            "parent": parent,
            "created_by": created_by,
            "created_at": datetime.now().isoformat(),
            "protected": False
        }
    
    @staticmethod
    def create_change_proposal(
        proposal_id: str = "proposal_123",
        source_branch: str = "feature/test",
        target_branch: str = "main",
        status: str = "pending"
    ) -> ChangeProposal:
        """Create ChangeProposal object."""
        return ChangeProposal(
            id=proposal_id,
            source_branch=source_branch,
            target_branch=target_branch,
            title=f"Merge {source_branch} into {target_branch}",
            description="Test proposal",
            author="user1",
            status=status,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )