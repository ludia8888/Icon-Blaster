"""
Foundry-style Branch Service with optimistic concurrency
"""
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from core.concurrency.optimistic_lock import FoundryStyleLockManager
from models.exceptions import ConflictError, ConcurrencyError
from models.branch_state import BranchState, BranchStateInfo
from common_logging.setup import get_logger

logger = get_logger(__name__)


class FoundryBranchService:
    """
    Branch service with Foundry-style concurrency control
    - Optimistic locking for most operations
    - Advisory locks only for branch lifecycle
    """
    
    def __init__(self, db_session: AsyncSession):
        self.session = db_session
        self.lock_manager = FoundryStyleLockManager(db_session)
    
    async def create_branch(
        self,
        branch_name: str,
        parent_branch: str,
        parent_commit: str,
        user_id: str,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create new branch with conflict detection
        """
        async with self.lock_manager.branch_operation_lock(branch_name):
            # Check if branch already exists
            existing = await self._get_branch_info(branch_name)
            if existing:
                raise ConflictError(
                    resource_type="branch",
                    resource_id=branch_name,
                    message=f"Branch {branch_name} already exists"
                )
            
            # Validate parent branch commit
            is_valid, current_commit = await self.lock_manager.occ.validate_parent_commit(
                resource_type="branch",
                resource_id=parent_branch,
                parent_commit=parent_commit
            )
            
            if not is_valid:
                raise ConflictError(
                    resource_type="branch",
                    resource_id=parent_branch,
                    expected_commit=parent_commit,
                    actual_commit=current_commit,
                    message="Parent branch has been updated - please rebase"
                )
            
            # Create branch
            async def _create():
                branch_info = BranchStateInfo(
                    branch_name=branch_name,
                    current_state=BranchState.ACTIVE,
                    state_changed_by=user_id,
                    state_change_reason=f"Created from {parent_branch}",
                    metadata={
                        "parent_branch": parent_branch,
                        "parent_commit": parent_commit,
                        "description": description
                    }
                )
                
                # Store in database
                await self._store_branch_info(branch_info)
                return branch_info.model_dump()
            
            result = await self.lock_manager.occ.atomic_update_with_conflict_detection(
                resource_type="branch",
                resource_id=branch_name,
                parent_commit="",  # New branch has no parent commit
                update_fn=_create,
                user_id=user_id
            )
            
            logger.info(
                f"Created branch {branch_name} from {parent_branch}@{parent_commit} "
                f"with commit {result['new_commit_hash']}"
            )
            
            return result
    
    async def update_branch_state(
        self,
        branch_name: str,
        new_state: BranchState,
        parent_commit: str,
        user_id: str,
        reason: str
    ) -> Dict[str, Any]:
        """
        Update branch state with optimistic concurrency
        """
        # Most state changes don't need locks
        async def _update():
            branch_info = await self._get_branch_info(branch_name)
            if not branch_info:
                raise ValueError(f"Branch {branch_name} not found")
            
            # Validate state transition
            if not self._is_valid_transition(branch_info.current_state, new_state):
                raise ValueError(
                    f"Invalid state transition: {branch_info.current_state} -> {new_state}"
                )
            
            # Update state
            branch_info.previous_state = branch_info.current_state
            branch_info.current_state = new_state
            branch_info.state_changed_at = datetime.now(timezone.utc)
            branch_info.state_changed_by = user_id
            branch_info.state_change_reason = reason
            
            # Special handling for READY state
            if new_state == BranchState.READY:
                branch_info.indexing_completed_at = datetime.now(timezone.utc)
            
            await self._store_branch_info(branch_info)
            return branch_info.model_dump()
        
        # Use optimistic concurrency with retry
        return await self.lock_manager.update_with_retry(
            resource_type="branch_state",
            resource_id=branch_name,
            parent_commit=parent_commit,
            update_fn=_update,
            user_id=user_id
        )
    
    async def merge_branch(
        self,
        source_branch: str,
        target_branch: str,
        parent_commit: str,
        user_id: str,
        merge_strategy: str = "three-way"
    ) -> Dict[str, Any]:
        """
        Merge branches with conflict detection
        """
        # Merge needs locks on both branches
        async with self.lock_manager.branch_operation_lock(source_branch):
            async with self.lock_manager.branch_operation_lock(target_branch):
                
                # Validate source branch state
                source_info = await self._get_branch_info(source_branch)
                if not source_info:
                    raise ValueError(f"Source branch {source_branch} not found")
                
                if source_info.current_state != BranchState.READY:
                    raise ValueError(
                        f"Source branch must be in READY state, got {source_info.current_state}"
                    )
                
                # Validate target branch commit
                is_valid, current_commit = await self.lock_manager.occ.validate_parent_commit(
                    resource_type="branch",
                    resource_id=target_branch,
                    parent_commit=parent_commit
                )
                
                if not is_valid:
                    # This is the key Foundry pattern - don't block, inform
                    raise ConflictError(
                        resource_type="branch",
                        resource_id=target_branch,
                        expected_commit=parent_commit,
                        actual_commit=current_commit,
                        message=(
                            f"Target branch {target_branch} has been updated. "
                            "Please rebase your changes and retry the merge."
                        ),
                        merge_hints={
                            "source_branch": source_branch,
                            "target_branch": target_branch,
                            "target_head": current_commit,
                            "strategy": merge_strategy
                        }
                    )
                
                # Perform merge
                async def _merge():
                    # Actual merge logic would go here
                    # For now, simulate successful merge
                    merge_result = {
                        "merged_at": datetime.now(timezone.utc),
                        "source_branch": source_branch,
                        "target_branch": target_branch,
                        "merge_commit": self._generate_merge_commit_id(),
                        "conflicts_resolved": 0,
                        "files_changed": 42  # Mock
                    }
                    
                    # Mark source branch as merged
                    source_info.current_state = BranchState.MERGED
                    source_info.state_changed_by = user_id
                    source_info.state_change_reason = f"Merged into {target_branch}"
                    await self._store_branch_info(source_info)
                    
                    return merge_result
                
                result = await self.lock_manager.occ.atomic_update_with_conflict_detection(
                    resource_type="branch",
                    resource_id=target_branch,
                    parent_commit=parent_commit,
                    update_fn=_merge,
                    user_id=user_id
                )
                
                logger.info(
                    f"Successfully merged {source_branch} -> {target_branch} "
                    f"with commit {result['new_commit_hash']}"
                )
                
                return result
    
    async def delete_branch(
        self,
        branch_name: str,
        user_id: str,
        force: bool = False
    ) -> Dict[str, Any]:
        """
        Delete branch with proper locking
        """
        async with self.lock_manager.branch_operation_lock(branch_name):
            branch_info = await self._get_branch_info(branch_name)
            if not branch_info:
                raise ValueError(f"Branch {branch_name} not found")
            
            # Check if safe to delete
            if not force and branch_info.current_state == BranchState.ACTIVE:
                raise ValueError(
                    "Cannot delete active branch without force flag. "
                    "Merge or archive the branch first."
                )
            
            # Perform deletion
            async def _delete():
                # Archive instead of hard delete
                branch_info.current_state = BranchState.ARCHIVED
                branch_info.state_changed_by = user_id
                branch_info.state_change_reason = "Branch deleted"
                branch_info.metadata["deleted_at"] = datetime.now(timezone.utc).isoformat()
                
                await self._store_branch_info(branch_info)
                return {"deleted": branch_name, "archived": True}
            
            result = await self.lock_manager.occ.atomic_update_with_conflict_detection(
                resource_type="branch",
                resource_id=branch_name,
                parent_commit=branch_info.metadata.get("commit_hash", ""),
                update_fn=_delete,
                user_id=user_id
            )
            
            logger.info(f"Deleted branch {branch_name}")
            return result
    
    def _is_valid_transition(self, from_state: BranchState, to_state: BranchState) -> bool:
        """Validate state transitions"""
        valid_transitions = {
            BranchState.ACTIVE: [BranchState.LOCKED_FOR_WRITE, BranchState.READY, BranchState.ARCHIVED],
            BranchState.LOCKED_FOR_WRITE: [BranchState.ACTIVE, BranchState.READY, BranchState.FAILED],
            BranchState.READY: [BranchState.MERGED, BranchState.ACTIVE, BranchState.ARCHIVED],
            BranchState.MERGED: [BranchState.ARCHIVED],
            BranchState.FAILED: [BranchState.ACTIVE, BranchState.ARCHIVED],
            BranchState.ARCHIVED: []  # Terminal state
        }
        
        return to_state in valid_transitions.get(from_state, [])
    
    def _generate_merge_commit_id(self) -> str:
        """Generate unique merge commit ID"""
        import uuid
        return f"merge_{uuid.uuid4().hex[:12]}"
    
    async def _get_branch_info(self, branch_name: str) -> Optional[BranchStateInfo]:
        """Get branch info from database"""
        # This would query the actual database
        # For now, return mock
        return None
    
    async def _store_branch_info(self, branch_info: BranchStateInfo):
        """Store branch info in database"""
        # This would store in actual database
        pass


class ConflictResolutionHelper:
    """
    Helper for Foundry-style conflict resolution
    """
    
    @staticmethod
    def generate_merge_proposal(conflict_error: ConflictError) -> Dict[str, Any]:
        """
        Generate merge proposal from conflict error
        """
        hints = conflict_error.merge_hints or {}
        
        return {
            "conflict_type": "concurrent_update",
            "resolution_strategy": "rebase_and_merge",
            "steps": [
                {
                    "action": "fetch_latest",
                    "target": conflict_error.resource_id,
                    "commit": conflict_error.actual_commit
                },
                {
                    "action": "rebase_changes",
                    "base": conflict_error.actual_commit,
                    "onto": hints.get("target_head", conflict_error.actual_commit)
                },
                {
                    "action": "retry_operation",
                    "with_commit": conflict_error.actual_commit
                }
            ],
            "auto_resolvable": True,
            "estimated_time_seconds": 5
        }
    
    @staticmethod
    def can_auto_merge(
        source_changes: Dict[str, Any],
        target_changes: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Check if changes can be automatically merged
        
        Returns:
            (can_merge, conflict_paths)
        """
        conflicts = []
        
        # Check for overlapping changes
        for path in source_changes:
            if path in target_changes:
                # Both modified same path
                if source_changes[path] != target_changes[path]:
                    conflicts.append(path)
        
        return len(conflicts) == 0, conflicts