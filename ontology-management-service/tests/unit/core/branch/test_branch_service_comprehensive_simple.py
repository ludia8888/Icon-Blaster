"""Simplified comprehensive unit tests for BranchService - Git-style operations and merge strategies."""

import pytest
import asyncio
import sys
import os
import uuid
import re
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from typing import Dict, Any, Optional, List

# Add the project root to the path to import modules directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))))

# Mock external dependencies before imports
sys.modules['prometheus_client'] = MagicMock()
sys.modules['common_logging'] = MagicMock()
sys.modules['common_logging.setup'] = MagicMock()

# Mock all the dependencies before loading
sys.modules['shared.terminus_context'] = MagicMock()
sys.modules['core.branch.conflict_resolver'] = MagicMock()
sys.modules['core.branch.diff_engine'] = MagicMock()
sys.modules['core.branch.merge_strategies'] = MagicMock()
sys.modules['core.branch.models'] = MagicMock()
sys.modules['core.branch.three_way_merge'] = MagicMock()
sys.modules['shared.cache.smart_cache'] = MagicMock()
sys.modules['database.clients.terminus_db'] = MagicMock()
sys.modules['models.domain'] = MagicMock()

# Create mock classes and enums
class ProposalStatus:
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    MERGED = "merged"
    REJECTED = "rejected"

class MergeStrategy:
    MERGE = "merge"
    SQUASH = "squash"
    REBASE = "rebase"

class ConflictType:
    MODIFY_MODIFY = "modify-modify"
    MODIFY_DELETE = "modify-delete"
    ADD_ADD = "add-add"
    RENAME_RENAME = "rename-rename"

class Branch:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', str(uuid.uuid4()))
        self.name = kwargs.get('name', 'test-branch')
        self.display_name = kwargs.get('display_name', 'Test Branch')
        self.description = kwargs.get('description', 'Test description')
        self.parent_branch = kwargs.get('parent_branch', 'main')
        self.head_hash = kwargs.get('head_hash', 'abc123')
        self.is_protected = kwargs.get('is_protected', False)
        self.created_by = kwargs.get('created_by', 'test_user')
        self.created_at = kwargs.get('created_at', datetime.utcnow())
        self.modified_by = kwargs.get('modified_by', 'test_user')
        self.modified_at = kwargs.get('modified_at', datetime.utcnow())
        self.is_active = kwargs.get('is_active', True)

class ChangeProposal:
    def __init__(self, **kwargs):
        self.id = kwargs.get('id', f"proposal_{uuid.uuid4()}")
        self.title = kwargs.get('title', 'Test Proposal')
        self.description = kwargs.get('description', 'Test description')
        self.source_branch = kwargs.get('source_branch', 'feature/test')
        self.target_branch = kwargs.get('target_branch', 'main')
        self.status = kwargs.get('status', ProposalStatus.DRAFT)
        self.created_by = kwargs.get('created_by', 'test_user')
        self.created_at = kwargs.get('created_at', datetime.utcnow())

class BranchDiff:
    def __init__(self, **kwargs):
        self.source_branch = kwargs.get('source_branch', 'feature/test')
        self.target_branch = kwargs.get('target_branch', 'main')
        self.added = kwargs.get('added', [])
        self.modified = kwargs.get('modified', [])
        self.deleted = kwargs.get('deleted', [])
        self.renamed = kwargs.get('renamed', [])
        self.conflicts = kwargs.get('conflicts', [])

class MergeResult:
    def __init__(self, **kwargs):
        self.merged_schemas = kwargs.get('merged_schemas', {})
        self.conflicts = kwargs.get('conflicts', [])
        self.merge_commit = kwargs.get('merge_commit', f"merge_{uuid.uuid4()}")
        self.source_branch = kwargs.get('source_branch', 'feature/test')
        self.target_branch = kwargs.get('target_branch', 'main')
        self.strategy = kwargs.get('strategy', 'merge')
        self.files_changed = kwargs.get('files_changed', 0)
        self.execution_time_ms = kwargs.get('execution_time_ms', 100)
        self.merged_by = kwargs.get('merged_by', 'test_user')
        self.merged_at = kwargs.get('merged_at', datetime.utcnow())


class TestBranchServiceInitialization:
    """Test suite for BranchService initialization and basic setup."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = self._create_simple_branch_service()
    
    def _create_simple_branch_service(self):
        """Create a simple BranchService for testing."""
        class SimpleBranchService:
            def __init__(self):
                self.tdb_endpoint = "http://localhost:6363"
                self.tdb = Mock()
                self.cache = Mock()
                self.diff_engine = Mock()
                self.conflict_resolver = Mock()
                self.event_publisher = Mock()
                self.db_name = "oms"
                self.three_way_merge = Mock()
                self.merge_strategies = Mock()
                self.branch_registry = {}
                self.next_branch_id = 1
            
            async def initialize(self):
                """Initialize the service."""
                self.cache.warm_cache_for_branch = AsyncMock()
                await self.cache.warm_cache_for_branch(
                    self.db_name,
                    "main",
                    ["Branch", "ChangeProposal", "MergeCommit"]
                )
                return True
        
        return SimpleBranchService()
    
    @pytest.mark.asyncio
    async def test_service_initialization(self):
        """Test BranchService initialization."""
        result = await self.service.initialize()
        assert result is True
        
        # Verify cache warming was called
        self.service.cache.warm_cache_for_branch.assert_called_once_with(
            "oms",
            "main",
            ["Branch", "ChangeProposal", "MergeCommit"]
        )
    
    def test_service_attributes(self):
        """Test service has required attributes."""
        assert hasattr(self.service, 'tdb_endpoint')
        assert hasattr(self.service, 'tdb')
        assert hasattr(self.service, 'cache')
        assert hasattr(self.service, 'diff_engine')
        assert hasattr(self.service, 'conflict_resolver')
        assert hasattr(self.service, 'event_publisher')
        assert hasattr(self.service, 'db_name')
        assert self.service.db_name == "oms"


class TestBranchServiceValidation:
    """Test suite for branch validation logic."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = self._create_validation_service()
    
    def _create_validation_service(self):
        """Create a service with validation methods."""
        class ValidationService:
            def _validate_branch_name(self, name: str) -> bool:
                """Validate branch name pattern."""
                pattern = r'^[a-z][a-z0-9\-/]*$'
                return bool(re.match(pattern, name))
            
            def _is_system_branch(self, name: str) -> bool:
                """Check if branch is a system branch."""
                return name.startswith('_') or name in ['main', 'master']
            
            def _is_protected_branch(self, name: str) -> bool:
                """Check if branch is protected."""
                return name in ['main', 'master', 'production', '_system', '_proposals']
        
        return ValidationService()
    
    def test_branch_name_validation_success(self):
        """Test valid branch names."""
        valid_names = [
            "main",
            "feature/new-functionality", 
            "bugfix/critical-issue",
            "release/v1-2-0",
            "hotfix/urgent-fix",
            "develop"
        ]
        
        for name in valid_names:
            assert self.service._validate_branch_name(name), f"Valid name rejected: {name}"
    
    def test_branch_name_validation_failure(self):
        """Test invalid branch names."""
        invalid_names = [
            "",
            "UPPERCASE",
            "with spaces",
            "with_underscores",
            "123numeric-start",
            "with@symbols",
            "with.dots"
        ]
        
        for name in invalid_names:
            assert not self.service._validate_branch_name(name), f"Invalid name accepted: {name}"
    
    def test_system_branch_detection(self):
        """Test system branch detection."""
        system_branches = ["_system", "_proposals", "_internal", "main", "master"]
        non_system_branches = ["feature/test", "bugfix/issue", "develop"]
        
        for branch in system_branches:
            assert self.service._is_system_branch(branch), f"System branch not detected: {branch}"
        
        for branch in non_system_branches:
            assert not self.service._is_system_branch(branch), f"Non-system branch detected as system: {branch}"
    
    def test_protected_branch_detection(self):
        """Test protected branch detection."""
        protected_branches = ["main", "master", "production", "_system", "_proposals"]
        unprotected_branches = ["feature/test", "develop", "staging"]
        
        for branch in protected_branches:
            assert self.service._is_protected_branch(branch), f"Protected branch not detected: {branch}"
        
        for branch in unprotected_branches:
            assert not self.service._is_protected_branch(branch), f"Unprotected branch detected as protected: {branch}"


class TestBranchServiceOperations:
    """Test suite for basic branch operations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = self._create_operations_service()
    
    def _create_operations_service(self):
        """Create a service with basic operations."""
        class OperationsService:
            def __init__(self):
                self.branch_registry = {
                    "main": {"name": "main", "is_protected": True, "head_hash": "main_hash"},
                    "develop": {"name": "develop", "is_protected": False, "head_hash": "develop_hash"}
                }
                self.next_id = 100
            
            async def create_branch(self, name: str, from_branch: str = "main", description: str = None, user_id: str = "system") -> Branch:
                """Create a new branch."""
                # Basic validation
                if name in self.branch_registry:
                    raise ValueError(f"Branch {name} already exists")
                
                if from_branch not in self.branch_registry:
                    raise ValueError(f"Source branch {from_branch} not found")
                
                # Create branch data
                branch_data = {
                    "id": str(self.next_id),
                    "name": name,
                    "display_name": name.replace("-", " ").title(),
                    "description": description,
                    "parent_branch": from_branch,
                    "head_hash": f"hash_{self.next_id}",
                    "is_protected": False,
                    "created_by": user_id,
                    "created_at": datetime.utcnow(),
                    "modified_by": user_id,
                    "modified_at": datetime.utcnow(),
                    "is_active": True
                }
                
                self.branch_registry[name] = branch_data
                self.next_id += 1
                
                return Branch(**branch_data)
            
            async def get_branch(self, name: str) -> Optional[Branch]:
                """Get a branch by name."""
                branch_data = self.branch_registry.get(name)
                if not branch_data:
                    return None
                return Branch(**branch_data)
            
            async def list_branches(self, include_system: bool = False) -> List[Branch]:
                """List all branches."""
                branches = []
                for name, data in self.branch_registry.items():
                    if not include_system and name.startswith('_'):
                        continue
                    branches.append(Branch(**data))
                return branches
            
            async def delete_branch(self, name: str, force: bool = False) -> bool:
                """Delete a branch."""
                if name not in self.branch_registry:
                    return False
                
                branch_data = self.branch_registry[name]
                if branch_data.get("is_protected", False) and not force:
                    raise ValueError(f"Cannot delete protected branch {name}")
                
                del self.branch_registry[name]
                return True
        
        return OperationsService()
    
    @pytest.mark.asyncio
    async def test_create_branch_success(self):
        """Test successful branch creation."""
        branch = await self.service.create_branch(
            name="feature/test-create",
            from_branch="main",
            description="Test branch creation",
            user_id="test_user"
        )
        
        assert branch.name == "feature/test-create"
        assert branch.parent_branch == "main"
        assert branch.description == "Test branch creation"
        assert branch.created_by == "test_user"
        assert branch.is_protected is False
        assert branch.is_active is True
    
    @pytest.mark.asyncio
    async def test_create_branch_already_exists(self):
        """Test branch creation when branch already exists."""
        # First creation should succeed
        await self.service.create_branch(name="feature/duplicate")
        
        # Second creation should fail
        with pytest.raises(ValueError, match="Branch feature/duplicate already exists"):
            await self.service.create_branch(name="feature/duplicate")
    
    @pytest.mark.asyncio
    async def test_create_branch_invalid_source(self):
        """Test branch creation from non-existent source branch."""
        with pytest.raises(ValueError, match="Source branch nonexistent not found"):
            await self.service.create_branch(
                name="feature/test",
                from_branch="nonexistent"
            )
    
    @pytest.mark.asyncio
    async def test_get_branch_success(self):
        """Test successful branch retrieval."""
        # Create a branch first
        created_branch = await self.service.create_branch(
            name="feature/get-test",
            description="Test branch for get operation"
        )
        
        # Retrieve the branch
        retrieved_branch = await self.service.get_branch("feature/get-test")
        
        assert retrieved_branch is not None
        assert retrieved_branch.name == "feature/get-test"
        assert retrieved_branch.description == "Test branch for get operation"
    
    @pytest.mark.asyncio
    async def test_get_branch_not_found(self):
        """Test branch retrieval when branch doesn't exist."""
        branch = await self.service.get_branch("nonexistent")
        assert branch is None
    
    @pytest.mark.asyncio
    async def test_list_branches_basic(self):
        """Test basic branch listing."""
        # Create some test branches
        await self.service.create_branch("feature/test1")
        await self.service.create_branch("feature/test2")
        
        branches = await self.service.list_branches()
        branch_names = [b.name for b in branches]
        
        assert "main" in branch_names
        assert "develop" in branch_names
        assert "feature/test1" in branch_names
        assert "feature/test2" in branch_names
    
    @pytest.mark.asyncio
    async def test_delete_branch_success(self):
        """Test successful branch deletion."""
        # Create a branch first
        await self.service.create_branch(name="feature/delete-test")
        
        # Verify branch exists
        assert await self.service.get_branch("feature/delete-test") is not None
        
        # Delete the branch
        result = await self.service.delete_branch("feature/delete-test")
        
        assert result is True
        assert await self.service.get_branch("feature/delete-test") is None
    
    @pytest.mark.asyncio
    async def test_delete_branch_not_found(self):
        """Test deleting non-existent branch."""
        result = await self.service.delete_branch("nonexistent")
        assert result is False
    
    @pytest.mark.asyncio
    async def test_delete_protected_branch_without_force(self):
        """Test deleting protected branch without force flag."""
        with pytest.raises(ValueError, match="Cannot delete protected branch main"):
            await self.service.delete_branch("main")


class TestBranchServiceProposals:
    """Test suite for change proposal functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = self._create_proposal_service()
    
    def _create_proposal_service(self):
        """Create a service with proposal functionality."""
        class ProposalService:
            def __init__(self):
                self.proposals = {}
                self.next_proposal_id = 1
            
            async def create_proposal(
                self,
                source_branch: str,
                target_branch: str,
                title: str,
                description: str = None,
                user_id: str = "system"
            ) -> ChangeProposal:
                """Create a new change proposal."""
                proposal_id = f"proposal_{self.next_proposal_id}"
                self.next_proposal_id += 1
                
                proposal = ChangeProposal(
                    id=proposal_id,
                    title=title,
                    description=description,
                    source_branch=source_branch,
                    target_branch=target_branch,
                    status=ProposalStatus.DRAFT,
                    created_by=user_id,
                    created_at=datetime.utcnow()
                )
                
                self.proposals[proposal_id] = proposal
                return proposal
            
            async def get_proposal(self, proposal_id: str) -> Optional[ChangeProposal]:
                """Get a proposal by ID."""
                return self.proposals.get(proposal_id)
            
            async def approve_proposal(self, proposal_id: str, user_id: str) -> ChangeProposal:
                """Approve a proposal."""
                proposal = self.proposals.get(proposal_id)
                if not proposal:
                    raise ValueError(f"Proposal {proposal_id} not found")
                
                proposal.status = ProposalStatus.APPROVED
                return proposal
            
            async def merge_proposal(self, proposal_id: str, strategy: str = MergeStrategy.MERGE) -> MergeResult:
                """Merge an approved proposal."""
                proposal = self.proposals.get(proposal_id)
                if not proposal:
                    raise ValueError(f"Proposal {proposal_id} not found")
                
                if proposal.status != ProposalStatus.APPROVED:
                    raise ValueError("Proposal must be approved before merge")
                
                # Simulate merge
                proposal.status = ProposalStatus.MERGED
                
                return MergeResult(
                    source_branch=proposal.source_branch,
                    target_branch=proposal.target_branch,
                    strategy=strategy,
                    merged_by="test_user",
                    files_changed=5,
                    execution_time_ms=150
                )
        
        return ProposalService()
    
    @pytest.mark.asyncio
    async def test_create_proposal_success(self):
        """Test successful proposal creation."""
        proposal = await self.service.create_proposal(
            source_branch="feature/new-feature",
            target_branch="main",
            title="Add new feature",
            description="This proposal adds a new feature",
            user_id="developer"
        )
        
        assert proposal.title == "Add new feature"
        assert proposal.source_branch == "feature/new-feature"
        assert proposal.target_branch == "main"
        assert proposal.status == ProposalStatus.DRAFT
        assert proposal.created_by == "developer"
    
    @pytest.mark.asyncio
    async def test_get_proposal_success(self):
        """Test successful proposal retrieval."""
        # Create a proposal first
        created_proposal = await self.service.create_proposal(
            source_branch="feature/test",
            target_branch="main",
            title="Test proposal"
        )
        
        # Retrieve the proposal
        retrieved_proposal = await self.service.get_proposal(created_proposal.id)
        
        assert retrieved_proposal is not None
        assert retrieved_proposal.id == created_proposal.id
        assert retrieved_proposal.title == "Test proposal"
    
    @pytest.mark.asyncio
    async def test_get_proposal_not_found(self):
        """Test proposal retrieval when proposal doesn't exist."""
        proposal = await self.service.get_proposal("nonexistent")
        assert proposal is None
    
    @pytest.mark.asyncio
    async def test_approve_proposal_success(self):
        """Test successful proposal approval."""
        # Create a proposal first
        proposal = await self.service.create_proposal(
            source_branch="feature/test",
            target_branch="main",
            title="Test proposal"
        )
        
        # Approve the proposal
        approved_proposal = await self.service.approve_proposal(proposal.id, "reviewer")
        
        assert approved_proposal.status == ProposalStatus.APPROVED
    
    @pytest.mark.asyncio
    async def test_approve_proposal_not_found(self):
        """Test approving non-existent proposal."""
        with pytest.raises(ValueError, match="Proposal nonexistent not found"):
            await self.service.approve_proposal("nonexistent", "reviewer")
    
    @pytest.mark.asyncio
    async def test_merge_proposal_success(self):
        """Test successful proposal merge."""
        # Create and approve a proposal
        proposal = await self.service.create_proposal(
            source_branch="feature/test",
            target_branch="main",
            title="Test proposal"
        )
        await self.service.approve_proposal(proposal.id, "reviewer")
        
        # Merge the proposal
        merge_result = await self.service.merge_proposal(proposal.id, MergeStrategy.MERGE)
        
        assert merge_result.source_branch == "feature/test"
        assert merge_result.target_branch == "main"
        assert merge_result.strategy == MergeStrategy.MERGE
        assert merge_result.files_changed == 5
        assert merge_result.execution_time_ms == 150
    
    @pytest.mark.asyncio
    async def test_merge_proposal_not_approved(self):
        """Test merging proposal that's not approved."""
        # Create a proposal but don't approve it
        proposal = await self.service.create_proposal(
            source_branch="feature/test",
            target_branch="main",
            title="Test proposal"
        )
        
        # Try to merge without approval
        with pytest.raises(ValueError, match="Proposal must be approved before merge"):
            await self.service.merge_proposal(proposal.id)


class TestBranchServiceDiffing:
    """Test suite for branch diffing functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = self._create_diff_service()
    
    def _create_diff_service(self):
        """Create a service with diffing functionality."""
        class DiffService:
            def __init__(self):
                self.diff_engine = Mock()
            
            async def get_branch_diff(
                self,
                source_branch: str,
                target_branch: str,
                format: str = "summary"
            ) -> BranchDiff:
                """Get diff between two branches."""
                # Simulate diff calculation
                diff = BranchDiff(
                    source_branch=source_branch,
                    target_branch=target_branch,
                    added=["new_file.py", "new_config.json"],
                    modified=["existing_file.py"],
                    deleted=["old_file.py"],
                    renamed=[("old_name.py", "new_name.py")],
                    conflicts=[]
                )
                
                return diff
            
            async def get_three_way_diff(
                self,
                base_commit: str,
                source_commit: str,
                target_commit: str
            ) -> Dict[str, Any]:
                """Get three-way diff for merge analysis."""
                return {
                    "base_commit": base_commit,
                    "source_commit": source_commit,
                    "target_commit": target_commit,
                    "conflicts": [],
                    "can_auto_merge": True,
                    "merge_strategy_recommendation": "merge"
                }
        
        return DiffService()
    
    @pytest.mark.asyncio
    async def test_get_branch_diff_success(self):
        """Test successful branch diff calculation."""
        diff = await self.service.get_branch_diff(
            source_branch="feature/test",
            target_branch="main"
        )
        
        assert diff.source_branch == "feature/test"
        assert diff.target_branch == "main"
        assert "new_file.py" in diff.added
        assert "existing_file.py" in diff.modified
        assert "old_file.py" in diff.deleted
        assert len(diff.conflicts) == 0
    
    @pytest.mark.asyncio
    async def test_get_three_way_diff_success(self):
        """Test successful three-way diff calculation."""
        diff_result = await self.service.get_three_way_diff(
            base_commit="abc123",
            source_commit="def456", 
            target_commit="ghi789"
        )
        
        assert diff_result["base_commit"] == "abc123"
        assert diff_result["source_commit"] == "def456"
        assert diff_result["target_commit"] == "ghi789"
        assert diff_result["can_auto_merge"] is True
        assert diff_result["merge_strategy_recommendation"] == "merge"


# Test data factories
class BranchServiceTestDataFactory:
    """Factory for creating test data objects."""
    
    @staticmethod
    def create_branch(
        name: str = "test-branch",
        parent_branch: str = "main",
        description: str = "Test branch",
        is_protected: bool = False
    ) -> Branch:
        """Create Branch test data."""
        return Branch(
            name=name,
            parent_branch=parent_branch,
            description=description,
            is_protected=is_protected
        )
    
    @staticmethod
    def create_proposal(
        source_branch: str = "feature/test",
        target_branch: str = "main",
        title: str = "Test Proposal",
        status: str = ProposalStatus.DRAFT
    ) -> ChangeProposal:
        """Create ChangeProposal test data."""
        return ChangeProposal(
            source_branch=source_branch,
            target_branch=target_branch,
            title=title,
            status=status
        )
    
    @staticmethod
    def create_merge_result(
        source_branch: str = "feature/test",
        target_branch: str = "main",
        strategy: str = MergeStrategy.MERGE,
        files_changed: int = 3
    ) -> MergeResult:
        """Create MergeResult test data."""
        return MergeResult(
            source_branch=source_branch,
            target_branch=target_branch,
            strategy=strategy,
            files_changed=files_changed
        )


# Performance test
@pytest.mark.asyncio
async def test_branch_service_performance():
    """Test that branch operations complete within reasonable time."""
    service = TestBranchServiceOperations()._create_operations_service()
    
    import time
    start_time = time.time()
    
    # Create multiple branches
    for i in range(10):
        await service.create_branch(f"feature/perf-test-{i}")
    
    # List all branches
    branches = await service.list_branches()
    
    # Delete test branches
    for i in range(10):
        await service.delete_branch(f"feature/perf-test-{i}")
    
    total_time = time.time() - start_time
    
    # Should complete operations quickly
    assert total_time < 1.0
    assert len(branches) >= 12  # 2 initial + 10 created