"""
Foundry-style Branch Service with optimistic concurrency
"""
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy.sql import text # No longer using SQLAlchemy text

from core.concurrency.optimistic_lock import FoundryStyleLockManager
from models.exceptions import ConflictError, ConcurrencyError
from models.branch_state import BranchState, BranchStateInfo
from common_logging.setup import get_logger
from middleware.three_way_merge import JsonMerger, MergeStrategy as JsonMergeStrategy
from core.time_travel.service import TimeTravelQueryService
from core.versioning.version_service import VersionTrackingService
from core.time_travel.models import TemporalResourceQuery, TemporalQuery, TemporalReference, TemporalOperator

logger = get_logger(__name__)


class FoundryBranchService:
    """
    Branch service with Foundry-style concurrency control
    - Optimistic locking for most operations
    - Advisory locks only for branch lifecycle
    """
    
    def __init__(
        self,
        db_session: Any, # Changed from AsyncSession to Any to support PostgresClientSecure
        time_travel_service: TimeTravelQueryService,
        version_service: VersionTrackingService,
    ):
        self.session = db_session
        self.lock_manager = FoundryStyleLockManager(db_session)
        self.time_travel_service = time_travel_service
        self.version_service = version_service
    
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
                "branch",
                parent_branch,
                parent_commit
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
                    auto_merge_enabled=False,
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
                    "branch",
                    target_branch,
                    parent_commit
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
                    # 1. Get data for base, ours, theirs
                    # This part needs a way to fetch full schema/data for a given branch/commit
                    # For now, we will mock this data. A dedicated service/client method is needed.
                    base_data = await self._get_data_at_commit(target_branch, parent_commit)
                    ours_data = await self._get_data_at_commit(source_branch, "latest") # Assume latest from source
                    theirs_data = await self._get_data_at_commit(target_branch, "latest") # This is the current state

                    # 2. Perform three-way merge using the powerful engine
                    merger = JsonMerger()
                    merge_result = await merger.merge(base_data, ours_data, theirs_data)
                    
                    if merge_result.has_conflicts:
                        # Raise a specific conflict error with details for resolution
                        raise ConflictError(
                            message="Merge conflict detected",
                            resource_type="merge",
                            resource_id=f"{source_branch}->{target_branch}",
                            merge_hints={"conflicts": merge_result.get_unresolved_conflicts()}
                        )

                    # 3. If successful, the merged_value is the new state of the target branch
                    # The atomic_update_with_conflict_detection will handle creating the new commit hash
                    
                    # Mark source branch as merged
                    source_info.current_state = BranchState.MERGED
                    source_info.state_changed_by = user_id
                    source_info.state_change_reason = f"Merged into {target_branch}"
                    await self._store_branch_info(source_info)
                    
                    return merge_result.merged_value
                
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
    
    async def _get_data_at_commit(self, branch: str, commit_ref: str) -> Dict[str, Any]:
        """
        Gets the entire data snapshot for a branch at a specific commit.
        """
        logger.debug(f"Fetching data for commit '{commit_ref}' on branch '{branch}'.")

        if commit_ref == "latest":
            # For 'latest', we might need a different way to get the most recent full state.
            # Assuming query_as_of with current time works for this.
            timestamp = datetime.now(timezone.utc)
        else:
            # Get the timestamp for the given commit hash
            version_info = await self.version_service.get_version_by_commit_hash(commit_ref)
            if not version_info:
                raise ValueError(f"Commit '{commit_ref}' not found.")
            timestamp = version_info.current_version.last_modified

        # Use the TimeTravelQueryService to get the state of all resources at that time
        # We assume for now that a "full snapshot" is a collection of all ObjectType resources.
        temporal_ref = TemporalReference(
            timestamp=timestamp,
            version=None,
            commit_hash=None,
            relative_time=None
        )
        temporal_query_spec = TemporalQuery(
            operator=TemporalOperator.AS_OF,
            point_in_time=temporal_ref,
            start_time=None,
            end_time=None,
            include_deleted=False,
            include_metadata=True
        )
        query = TemporalResourceQuery(
            resource_type="ObjectType",
            resource_id=None,
            branch=branch,
            temporal=temporal_query_spec,
            filters=None,
            limit=1000, # Ensure we get all objects for the snapshot
            offset=0
        )
        
        result = await self.time_travel_service.query_as_of(query)
        
        # Reconstruct the full data snapshot from the individual resources
        full_snapshot = {res.resource_id: res.content for res in result.resources}
        return full_snapshot
    
    def _generate_merge_commit_id(self) -> str:
        """Generate unique merge commit ID"""
        import uuid
        return f"merge_{uuid.uuid4().hex[:12]}"
    
    async def _get_branch_info(self, branch_name: str) -> Optional[BranchStateInfo]:
        """Get branch info from database using direct SQL"""
        query = "SELECT state_data FROM branch_states WHERE branch_name = $1"
        
        # We need to adapt to the underlying db client's API.
        # Assuming it has a method like `fetch_one` which is common.
        row = await self.session.fetch_one(
            "branch_states", # This seems to be the table name
            {"branch_name": branch_name}
        )

        if row and row.get("state_data"):
            # Assuming state_data is stored as a JSON string
            return BranchStateInfo.model_validate_json(row["state_data"])
        return None
    
    async def _store_branch_info(self, branch_info: BranchStateInfo):
        """Store branch info in database using direct SQL"""

        # Check if record exists to decide between INSERT and UPDATE
        existing = await self._get_branch_info(branch_info.branch_name)

        data_to_store = {
            "branch_name": branch_info.branch_name,
            "state_data": branch_info.model_dump_json(),
            "updated_at": datetime.now(timezone.utc),
            "updated_by": branch_info.state_changed_by
        }

        if existing:
            # UPDATE existing record
            await self.session.update(
                "branch_states",
                existing.branch_name, # Assuming branch_name is the primary key
                {
                    "state_data": data_to_store["state_data"],
                    "updated_at": data_to_store["updated_at"],
                    "updated_by": data_to_store["updated_by"]
                }
            )
        else:
            # INSERT new record
            await self.session.create("branch_states", data_to_store)

        logger.debug(f"Stored state for branch {branch_info.branch_name}")


class ConflictResolutionHelper:
    """
    Helper methods for dealing with merge conflicts
    """
    
    @staticmethod
    def generate_merge_proposal(conflict_error: ConflictError) -> Dict[str, Any]:
        """
        Generate a structured merge proposal from a ConflictError
        """
        if not conflict_error.merge_hints:
            return {
                "error": "Conflict error does not contain merge hints",
                "message": conflict_error.message
            }
            
        return {
            "proposal_type": "rebase_and_merge",
            "source_branch": conflict_error.merge_hints.get("source_branch"),
            "target_branch": conflict_error.merge_hints.get("target_branch"),
            "current_target_head": conflict_error.actual_commit,
            "instructions": [
                f"1. Fetch latest changes from '{conflict_error.merge_hints.get('target_branch')}'",
                f"2. Rebase your branch '{conflict_error.merge_hints.get('source_branch')}' onto the new head",
                "3. Resolve any merge conflicts locally",
                "4. Push the rebased branch and retry the merge"
            ],
            "details": {
                "conflict_details": conflict_error.message
            }
        }
    
    @staticmethod
    def can_auto_merge(
        source_changes: Dict[str, Any],
        target_changes: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Check if changes can be auto-merged (simple case)
        
        Returns:
            (can_merge, conflict_reasons)
        """
        conflicts = []
        
        source_keys = set(source_changes.keys())
        target_keys = set(target_changes.keys())
        
        if not source_keys.isdisjoint(target_keys):
            conflicts.append("Both branches modified the same files/resources")
        
        # Add more sophisticated checks here
        
        return not conflicts, conflicts