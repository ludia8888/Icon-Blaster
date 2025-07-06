"""Unit tests for BranchService - Core business logic for Git-style branching."""

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

# Load branch models
branch_models_spec = importlib.util.spec_from_file_location(
    "branch_models",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))), "core", "branch", "models.py")
)
branch_models_module = importlib.util.module_from_spec(branch_models_spec)
sys.modules['branch_models'] = branch_models_module

# Load domain models
domain_models_spec = importlib.util.spec_from_file_location(
    "domain_models",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))), "models", "domain.py")
)
domain_models_module = importlib.util.module_from_spec(domain_models_spec)
sys.modules['domain_models'] = domain_models_module

try:
    branch_service_spec.loader.exec_module(branch_service_module)
    branch_models_spec.loader.exec_module(branch_models_module)
    domain_models_spec.loader.exec_module(domain_models_module)
except Exception as e:
    print(f"Warning: Could not load some modules: {e}")

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


class TestBranchServiceInitialization:
    """Test suite for BranchService initialization and basic setup."""
    
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
    
    @pytest.mark.asyncio
    async def test_initialize_success(self):
        """Test successful service initialization."""
        self.mock_tdb.create_database = AsyncMock()
        self.mock_cache.warm_cache_for_branch = AsyncMock()
        
        # Since we are now using JsonMerger from middleware,
        # we might need to mock that instead if we want to isolate the service.
        # For now, we assume the new merger is tested independently.
        # with patch('middleware.three_way_merge.JsonMerger') as mock_merger:
        #     instance = mock_merger.return_value
        #     instance.merge.return_value = ... 
        
        await self.service.initialize()
        
        self.mock_tdb.create_database.assert_called_once_with(self.service.db_name)
        self.mock_cache.warm_cache_for_branch.assert_called_once_with(
            self.service.db_name,
            "main",
            ["Branch", "ChangeProposal", "MergeCommit"]
        )
        assert self.service.three_way_merge == mock_three_way_instance
    
    @pytest.mark.asyncio
    async def test_initialize_database_creation_failure(self):
        """Test initialization when database creation fails."""
        self.mock_tdb.create_database = AsyncMock(side_effect=Exception("DB creation failed"))
        self.mock_cache.warm_cache_for_branch = AsyncMock()
        
        with patch('core.branch.service.ThreeWayMergeAlgorithm') as mock_three_way:
            mock_three_way_instance = Mock()
            mock_three_way.return_value = mock_three_way_instance
            
            await self.service.initialize()
            
            # Should continue initialization despite DB creation failure
            self.mock_tdb.create_database.assert_called_once()
            # Cache warming should not be called due to exception
            self.mock_cache.warm_cache_for_branch.assert_not_called()
            assert self.service.three_way_merge == mock_three_way_instance
    
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
    async def test_branch_exists_cached(self):
        """Test branch existence check with cached result."""
        branch_name = "feature/test"
        self.service.cache.get_with_optimization = AsyncMock(return_value=True)
        
        result = await self.service._branch_exists(branch_name)
        
        assert result is True
        # Verify that cache was called (specific arguments may vary due to lambda)
        self.service.cache.get_with_optimization.assert_called_once()
        call_args = self.service.cache.get_with_optimization.call_args
        assert call_args.kwargs['key'] == f"branch_exists:{branch_name}"
        assert call_args.kwargs['db'] == self.service.db_name
        assert call_args.kwargs['branch'] == "_system"
        assert call_args.kwargs['doc_type'] == "Branch"
    
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


class TestBranchServiceBranchInfo:
    """Test suite for BranchService branch information methods."""
    
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
    async def test_get_branch_info_cached(self):
        """Test branch info retrieval with caching."""
        branch_name = "feature/test"
        expected_info = {
            "name": branch_name,
            "head": "commit123",
            "created_at": "2024-01-01T00:00:00Z",
            "created_by": "user1"
        }
        
        self.service.cache.get_with_optimization = AsyncMock(return_value=expected_info)
        
        result = await self.service._get_branch_info(branch_name)
        
        assert result == expected_info
        self.service.cache.get_with_optimization.assert_called_once_with(
            key=f"branch_info:{branch_name}",
            db=self.service.db_name,
            branch="_system",
            query_factory=self.service._get_branch_info_from_db,
            doc_type="Branch"
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
    
    @pytest.mark.asyncio
    async def test_get_branch_head_success(self):
        """Test branch HEAD retrieval - success case."""
        branch_name = "feature/test"
        branch_info = {"head": "commit789", "name": branch_name}
        
        with patch.object(self.service, '_get_branch_info', new_callable=AsyncMock) as mock_get_info:
            mock_get_info.return_value = branch_info
            
            result = await self.service._get_branch_head(branch_name)
            
            assert result == "commit789"
            mock_get_info.assert_called_once_with(branch_name)
    
    @pytest.mark.asyncio
    async def test_get_branch_head_no_info(self):
        """Test branch HEAD retrieval - no branch info."""
        branch_name = "nonexistent"
        
        with patch.object(self.service, '_get_branch_info', new_callable=AsyncMock) as mock_get_info:
            mock_get_info.return_value = None
            
            result = await self.service._get_branch_head(branch_name)
            
            assert result is None
            mock_get_info.assert_called_once_with(branch_name)
    
    @pytest.mark.asyncio
    async def test_get_branch_head_no_head_field(self):
        """Test branch HEAD retrieval - branch info without head field."""
        branch_name = "feature/incomplete"
        branch_info = {"name": branch_name}  # Missing head field
        
        with patch.object(self.service, '_get_branch_info', new_callable=AsyncMock) as mock_get_info:
            mock_get_info.return_value = branch_info
            
            result = await self.service._get_branch_head(branch_name)
            
            assert result is None
            mock_get_info.assert_called_once_with(branch_name)


class TestBranchServiceEventPublishing:
    """Test suite for BranchService event publishing functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_event_publisher = Mock()
        
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


class TestBranchServiceCoreOperations:
    """Test suite for BranchService core operations (create, delete, merge)."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_event_publisher = Mock()
        
        with patch('core.branch.service.TerminusDBClient') as mock_tdb_client, \
             patch('core.branch.service.SmartCacheManager') as mock_cache, \
             patch('core.branch.service.MergeStrategyImplementor') as mock_merge_strategies:
            
            self.mock_tdb = Mock()
            mock_tdb_client.return_value = self.mock_tdb
            
            self.service = BranchService(
                tdb_endpoint="http://test.local",
                diff_engine=Mock(),
                conflict_resolver=Mock(),
                event_publisher=self.mock_event_publisher
            )
    
    @pytest.mark.asyncio
    async def test_create_branch_success(self):
        """Test successful branch creation."""
        branch_name = "feature/new-feature"
        from_branch = "main"
        description = "New feature branch"
        user_id = "user123"
        
        # Mock validation methods
        with patch.object(self.service, '_validate_branch_name', return_value=True), \
             patch.object(self.service, '_branch_exists', new_callable=AsyncMock, return_value=False), \
             patch.object(self.service, '_get_branch_info', new_callable=AsyncMock) as mock_get_info, \
             patch.object(self.service, '_publish_event', new_callable=AsyncMock) as mock_publish, \
             patch('core.branch.service.TerminusDBClient') as mock_tdb_context:
            
            # Setup source branch info
            source_info = {"head": "commit456", "name": from_branch}
            mock_get_info.return_value = source_info
            
            # Setup context manager for TerminusDB client
            mock_context_tdb = AsyncMock()
            mock_context_tdb.create_branch = AsyncMock()
            mock_context_tdb.insert_document = AsyncMock()
            mock_tdb_context.return_value.__aenter__ = AsyncMock(return_value=mock_context_tdb)
            mock_tdb_context.return_value.__aexit__ = AsyncMock(return_value=None)
            
            result = await self.service.create_branch(
                name=branch_name,
                from_branch=from_branch,
                description=description,
                user_id=user_id
            )
            
            # Verify branch creation call
            mock_context_tdb.create_branch.assert_called_once_with(
                db=self.service.db_name,
                branch_name=branch_name,
                from_branch=from_branch
            )
            
            # Verify metadata insertion
            mock_context_tdb.insert_document.assert_called_once()
            
            # Verify event publication
            mock_publish.assert_called_once()
            
            # Verify return type
            assert isinstance(result, Branch)
            assert result.name == branch_name
    
    @pytest.mark.asyncio
    async def test_create_branch_invalid_name(self):
        """Test branch creation with invalid name."""
        invalid_name = "Invalid Branch Name"
        
        with patch.object(self.service, '_validate_branch_name', return_value=False):
            with pytest.raises(ValueError, match="Invalid branch name"):
                await self.service.create_branch(name=invalid_name)
    
    @pytest.mark.asyncio
    async def test_create_branch_already_exists(self):
        """Test branch creation when branch already exists."""
        branch_name = "existing-branch"
        
        with patch.object(self.service, '_validate_branch_name', return_value=True), \
             patch.object(self.service, '_branch_exists', new_callable=AsyncMock, return_value=True):
            
            with pytest.raises(ValueError, match=f"Branch {branch_name} already exists"):
                await self.service.create_branch(name=branch_name)
    
    @pytest.mark.asyncio
    async def test_create_branch_source_not_found(self):
        """Test branch creation when source branch doesn't exist."""
        branch_name = "feature/test"
        from_branch = "nonexistent"
        
        with patch.object(self.service, '_validate_branch_name', return_value=True), \
             patch.object(self.service, '_branch_exists', new_callable=AsyncMock, return_value=False), \
             patch.object(self.service, '_get_branch_info', new_callable=AsyncMock, return_value=None):
            
            with pytest.raises(ValueError, match=f"Source branch {from_branch} not found"):
                await self.service.create_branch(name=branch_name, from_branch=from_branch)
    
    @pytest.mark.asyncio
    async def test_delete_branch_success(self):
        """Test successful branch deletion."""
        branch_name = "feature/to-delete"
        user_id = "user123"
        
        with patch.object(self.service, '_branch_exists', new_callable=AsyncMock, return_value=True), \
             patch.object(self.service, '_is_protected_branch', new_callable=AsyncMock, return_value=False), \
             patch.object(self.service, '_publish_event', new_callable=AsyncMock) as mock_publish, \
             patch('core.branch.service.TerminusDBClient') as mock_tdb_context:
            
            # Setup context manager for TerminusDB client
            mock_context_tdb = AsyncMock()
            mock_context_tdb.delete_branch = AsyncMock()
            mock_context_tdb.delete_document = AsyncMock()
            mock_tdb_context.return_value.__aenter__ = AsyncMock(return_value=mock_context_tdb)
            mock_tdb_context.return_value.__aexit__ = AsyncMock(return_value=None)
            
            result = await self.service.delete_branch(branch_name, user_id=user_id)
            
            # Verify branch deletion call
            mock_context_tdb.delete_branch.assert_called_once_with(
                db=self.service.db_name,
                branch_name=branch_name
            )
            
            # Verify metadata deletion
            mock_context_tdb.delete_document.assert_called_once()
            
            # Verify event publication
            mock_publish.assert_called_once()
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_delete_branch_not_found(self):
        """Test branch deletion when branch doesn't exist."""
        branch_name = "nonexistent"
        
        with patch.object(self.service, '_branch_exists', new_callable=AsyncMock, return_value=False):
            with pytest.raises(ValueError, match=f"Branch {branch_name} not found"):
                await self.service.delete_branch(branch_name)
    
    @pytest.mark.asyncio
    async def test_delete_branch_protected(self):
        """Test branch deletion when branch is protected."""
        branch_name = "main"
        
        with patch.object(self.service, '_branch_exists', new_callable=AsyncMock, return_value=True), \
             patch.object(self.service, '_is_protected_branch', new_callable=AsyncMock, return_value=True):
            
            with pytest.raises(ValueError, match=f"Cannot delete protected branch: {branch_name}"):
                await self.service.delete_branch(branch_name)


class TestBranchServiceProposalOperations:
    """Test suite for BranchService proposal management operations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        with patch('core.branch.service.TerminusDBClient'), \
             patch('core.branch.service.SmartCacheManager'), \
             patch('core.branch.service.MergeStrategyImplementor'):
            
            self.service = BranchService(
                tdb_endpoint="http://test.local",
                diff_engine=Mock(),
                conflict_resolver=Mock(),
                event_publisher=Mock()
            )
    
    @pytest.mark.asyncio
    async def test_create_proposal_success(self):
        """Test successful proposal creation."""
        source_branch = "feature/test"
        target_branch = "main"
        title = "Test proposal"
        description = "Test description"
        author = "user123"
        
        with patch.object(self.service, '_branch_exists', new_callable=AsyncMock, return_value=True), \
             patch.object(self.service, '_publish_event', new_callable=AsyncMock) as mock_publish, \
             patch('core.branch.service.TerminusDBClient') as mock_tdb_context:
            
            # Setup context manager
            mock_context_tdb = AsyncMock()
            mock_context_tdb.insert_document = AsyncMock()
            mock_tdb_context.return_value.__aenter__ = AsyncMock(return_value=mock_context_tdb)
            mock_tdb_context.return_value.__aexit__ = AsyncMock(return_value=None)
            
            result = await self.service.create_proposal(
                source_branch=source_branch,
                target_branch=target_branch,
                title=title,
                description=description,
                author=author
            )
            
            # Verify document insertion
            mock_context_tdb.insert_document.assert_called_once()
            
            # Verify event publication
            mock_publish.assert_called_once()
            
            # Verify return type
            assert isinstance(result, ChangeProposal)
            assert result.source_branch == source_branch
            assert result.target_branch == target_branch
            assert result.title == title
            assert result.author == author
            assert result.status == ProposalStatus.PENDING
    
    @pytest.mark.asyncio
    async def test_create_proposal_source_branch_not_found(self):
        """Test proposal creation when source branch doesn't exist."""
        source_branch = "nonexistent"
        target_branch = "main"
        
        async def mock_branch_exists(branch_name):
            return branch_name == target_branch
        
        with patch.object(self.service, '_branch_exists', new_callable=AsyncMock, side_effect=mock_branch_exists):
            with pytest.raises(ValueError, match=f"Source branch {source_branch} not found"):
                await self.service.create_proposal(
                    source_branch=source_branch,
                    target_branch=target_branch,
                    title="Test",
                    author="user"
                )
    
    @pytest.mark.asyncio
    async def test_create_proposal_target_branch_not_found(self):
        """Test proposal creation when target branch doesn't exist."""
        source_branch = "feature/test"
        target_branch = "nonexistent"
        
        async def mock_branch_exists(branch_name):
            return branch_name == source_branch
        
        with patch.object(self.service, '_branch_exists', new_callable=AsyncMock, side_effect=mock_branch_exists):
            with pytest.raises(ValueError, match=f"Target branch {target_branch} not found"):
                await self.service.create_proposal(
                    source_branch=source_branch,
                    target_branch=target_branch,
                    title="Test",
                    author="user"
                )
    
    @pytest.mark.asyncio
    async def test_approve_proposal_success(self):
        """Test successful proposal approval."""
        proposal_id = "proposal_123"
        approved_by = "admin"
        
        # Mock proposal data
        mock_proposal = BranchTestDataFactory.create_change_proposal(
            proposal_id=proposal_id,
            status=ProposalStatus.PENDING
        )
        
        with patch.object(self.service, 'get_proposal', new_callable=AsyncMock, return_value=mock_proposal), \
             patch.object(self.service, '_update_proposal_status', new_callable=AsyncMock) as mock_update, \
             patch.object(self.service, '_publish_event', new_callable=AsyncMock) as mock_publish:
            
            result = await self.service.approve_proposal(proposal_id, approved_by)
            
            # Verify status update
            mock_update.assert_called_once_with(proposal_id, ProposalStatus.APPROVED, approved_by)
            
            # Verify event publication
            mock_publish.assert_called_once()
            
            assert result is True
    
    @pytest.mark.asyncio
    async def test_approve_proposal_not_found(self):
        """Test proposal approval when proposal doesn't exist."""
        proposal_id = "nonexistent"
        
        with patch.object(self.service, 'get_proposal', new_callable=AsyncMock, return_value=None):
            with pytest.raises(ValueError, match=f"Proposal {proposal_id} not found"):
                await self.service.approve_proposal(proposal_id, "admin")
    
    @pytest.mark.asyncio
    async def test_approve_proposal_already_processed(self):
        """Test proposal approval when proposal is already processed."""
        proposal_id = "proposal_456"
        
        # Mock approved proposal
        mock_proposal = BranchTestDataFactory.create_change_proposal(
            proposal_id=proposal_id,
            status=ProposalStatus.APPROVED
        )
        
        with patch.object(self.service, 'get_proposal', new_callable=AsyncMock, return_value=mock_proposal):
            with pytest.raises(ValueError, match="Proposal proposal_456 is already"):
                await self.service.approve_proposal(proposal_id, "admin")
    
    @pytest.mark.asyncio
    async def test_reject_proposal_success(self):
        """Test successful proposal rejection."""
        proposal_id = "proposal_789"
        rejected_by = "admin"
        reason = "Does not meet requirements"
        
        # Mock proposal data
        mock_proposal = BranchTestDataFactory.create_change_proposal(
            proposal_id=proposal_id,
            status=ProposalStatus.PENDING
        )
        
        with patch.object(self.service, 'get_proposal', new_callable=AsyncMock, return_value=mock_proposal), \
             patch.object(self.service, '_update_proposal_status', new_callable=AsyncMock) as mock_update, \
             patch.object(self.service, '_publish_event', new_callable=AsyncMock) as mock_publish:
            
            result = await self.service.reject_proposal(proposal_id, rejected_by, reason)
            
            # Verify status update
            mock_update.assert_called_once_with(proposal_id, ProposalStatus.REJECTED, rejected_by)
            
            # Verify event publication
            mock_publish.assert_called_once()
            
            assert result is True


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
        status: ProposalStatus = ProposalStatus.PENDING
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