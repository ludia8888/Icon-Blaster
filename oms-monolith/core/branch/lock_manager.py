"""
Branch Lock Manager
Manages branch locking for data integrity and schema freeze
"""
import asyncio
from typing import Optional, Dict, List, Set, Any
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import json

from models.branch_state import (
    BranchState, BranchLock, BranchStateInfo, BranchStateTransition,
    LockType, LockScope, is_valid_transition, HeartbeatRecord,
    is_lock_expired_by_ttl, is_lock_expired_by_heartbeat
)
from core.auth import UserContext
from utils.logger import get_logger

logger = get_logger(__name__)


class LockConflictError(Exception):
    """Raised when a lock cannot be acquired due to conflicts"""
    pass


class InvalidStateTransitionError(Exception):
    """Raised when an invalid state transition is attempted"""
    pass


class BranchLockManager:
    """
    Manages branch locks and state transitions for data integrity
    Ensures schema freeze during indexing operations
    """
    
    def __init__(self, cache_service=None, db_service=None):
        self.cache_service = cache_service  # Redis for fast lock checks
        self.db_service = db_service       # Persistent storage
        
        # In-memory cache for high performance (fallback if no Redis)
        self._branch_states: Dict[str, BranchStateInfo] = {}
        self._active_locks: Dict[str, BranchLock] = {}
        
        # Lock timeout settings
        self.default_lock_timeout = timedelta(hours=2)
        self.indexing_lock_timeout = timedelta(hours=4)
        self.maintenance_lock_timeout = timedelta(hours=1)
        
        # Cleanup and heartbeat tasks
        self._cleanup_task = None
        self._heartbeat_checker_task = None
        
        # Heartbeat settings
        self.heartbeat_check_interval = 30  # Check heartbeats every 30 seconds
        self.heartbeat_grace_multiplier = 3  # Allow 3x heartbeat_interval before expiry
    
    async def initialize(self):
        """Initialize the lock manager"""
        # Start cleanup task for expired locks
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_locks_loop())
        
        # Start heartbeat checker task
        self._heartbeat_checker_task = asyncio.create_task(self._heartbeat_checker_loop())
        
        logger.info("Branch Lock Manager initialized with TTL & Heartbeat support")
    
    async def shutdown(self):
        """Shutdown the lock manager"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
        if self._heartbeat_checker_task:
            self._heartbeat_checker_task.cancel()
        logger.info("Branch Lock Manager shutdown")
    
    async def get_branch_state(self, branch_name: str) -> BranchStateInfo:
        """Get current state of a branch"""
        # Try cache first
        if self.cache_service:
            cached = await self.cache_service.get(f"branch_state:{branch_name}")
            if cached:
                return BranchStateInfo.parse_obj(json.loads(cached))
        
        # Check in-memory cache
        if branch_name in self._branch_states:
            return self._branch_states[branch_name]
        
        # Default state for new branches
        default_state = BranchStateInfo(
            branch_name=branch_name,
            current_state=BranchState.ACTIVE,
            state_changed_by="system",
            state_change_reason="Initial state"
        )
        
        await self._store_branch_state(default_state)
        return default_state
    
    async def set_branch_state(
        self,
        branch_name: str,
        new_state: BranchState,
        changed_by: str = "system",
        reason: str = "State change"
    ) -> bool:
        """
        Set branch state directly (for external event handlers)
        
        Returns:
            True if state was changed successfully
            
        Raises:
            InvalidStateTransitionError: If transition is invalid
        """
        try:
            current_state = await self.get_branch_state(branch_name)
            
            # Check if transition is valid
            if current_state.current_state == new_state:
                logger.debug(f"Branch {branch_name} already in state {new_state}")
                return True
            
            # Perform transition
            await self._transition_state(
                current_state,
                new_state,
                changed_by,
                reason
            )
            
            # Special handling for ERROR state - release all locks
            if new_state == BranchState.ERROR:
                await self._release_all_branch_locks(branch_name, "error_state")
            
            await self._store_branch_state(current_state)
            
            logger.info(
                f"Branch state set: {branch_name} -> {new_state} by {changed_by}"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to set branch state for {branch_name}: {e}")
            return False
    
    async def _store_branch_state(self, state_info: BranchStateInfo):
        """Store branch state in cache and persistent storage"""
        # Update in-memory cache
        self._branch_states[state_info.branch_name] = state_info
        
        # Update Redis cache
        if self.cache_service:
            await self.cache_service.set(
                f"branch_state:{state_info.branch_name}",
                state_info.json(),
                ttl=3600  # 1 hour
            )
        
        # Store in persistent DB (if available)
        if self.db_service:
            await self.db_service.store_branch_state(state_info)
    
    async def acquire_lock(
        self,
        branch_name: str,
        lock_type: LockType,
        locked_by: str,
        lock_scope: LockScope = LockScope.BRANCH,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        reason: str = "Lock acquired",
        timeout: Optional[timedelta] = None,
        enable_heartbeat: bool = True,
        heartbeat_interval: int = 60
    ) -> str:
        """
        Acquire a lock on a branch or resource
        
        Returns:
            Lock ID if successful
            
        Raises:
            LockConflictError: If lock cannot be acquired
        """
        lock_id = str(uuid4())
        
        # Determine timeout
        if timeout is None:
            timeout = self._get_default_timeout(lock_type)
        
        expires_at = datetime.now(timezone.utc) + timeout
        
        # Create lock object with TTL & Heartbeat support
        lock = BranchLock(
            id=lock_id,
            branch_name=branch_name,
            lock_type=lock_type,
            lock_scope=lock_scope,
            resource_type=resource_type,
            resource_id=resource_id,
            locked_by=locked_by,
            expires_at=expires_at,
            reason=reason,
            heartbeat_interval=heartbeat_interval if enable_heartbeat else 0,
            last_heartbeat=datetime.now(timezone.utc) if enable_heartbeat else None,
            heartbeat_source=locked_by if enable_heartbeat else None,
            auto_release_enabled=True
        )
        
        # Check for conflicts
        await self._check_lock_conflicts(lock)
        
        # Acquire lock
        current_state = await self.get_branch_state(branch_name)
        
        # Add lock to active locks
        current_state.active_locks.append(lock)
        self._active_locks[lock_id] = lock
        
        # Update branch state if needed
        if lock_type == LockType.INDEXING and lock_scope == LockScope.BRANCH:
            await self._transition_state(
                current_state,
                BranchState.LOCKED_FOR_WRITE,
                locked_by,
                f"Indexing lock acquired: {reason}"
            )
        
        await self._store_branch_state(current_state)
        
        logger.info(
            f"Lock acquired: {lock_id} on {branch_name} by {locked_by} "
            f"({lock_type.value}, expires: {expires_at}, heartbeat: {enable_heartbeat})"
        )
        
        return lock_id
    
    async def release_lock(self, lock_id: str, released_by: Optional[str] = None) -> bool:
        """
        Release a lock
        
        Returns:
            True if lock was released, False if not found
        """
        # Find lock
        lock = self._active_locks.get(lock_id)
        if not lock:
            logger.warning(f"Attempted to release non-existent lock: {lock_id}")
            return False
        
        # Mark lock as released
        lock.is_active = False
        lock.released_at = datetime.now(timezone.utc)
        lock.released_by = released_by or "system"
        
        # Remove from active locks
        del self._active_locks[lock_id]
        
        # Update branch state
        branch_state = await self.get_branch_state(lock.branch_name)
        
        # Remove lock from branch state
        branch_state.active_locks = [
            l for l in branch_state.active_locks if l.id != lock_id
        ]
        
        # Check if we should transition state
        if (lock.lock_type == LockType.INDEXING and 
            lock.lock_scope == LockScope.BRANCH and
            not self._has_active_indexing_locks(branch_state)):
            
            # Transition to READY state
            await self._transition_state(
                branch_state,
                BranchState.READY,
                released_by or "system",
                "Indexing completed, ready for merge"
            )
        
        await self._store_branch_state(branch_state)
        
        logger.info(f"Lock released: {lock_id} by {released_by}")
        return True
    
    async def check_write_permission(
        self,
        branch_name: str,
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None
    ) -> tuple[bool, str]:
        """
        Check if a write operation is allowed
        
        Returns:
            Tuple of (allowed, reason_if_not)
        """
        branch_state = await self.get_branch_state(branch_name)
        return branch_state.can_perform_action(action, resource_type)
    
    async def lock_for_indexing(
        self,
        branch_name: str,
        locked_by: str = "funnel-service",
        reason: str = "Data indexing in progress",
        resource_types: Optional[List[str]] = None,
        force_branch_lock: bool = False
    ) -> List[str]:
        """
        Lock resources for Funnel Service indexing (Foundry-style: minimal scope)
        
        By default, locks only the specific resource types being indexed.
        For full branch locking, use force_branch_lock=True.
        
        Args:
            branch_name: Branch to lock resources in
            locked_by: Service/user acquiring the lock
            reason: Reason for locking
            resource_types: List of resource types to lock (e.g., ["object_type", "link_type"])
                          If None, determines from schema changes
            force_branch_lock: If True, locks entire branch (legacy behavior)
        
        Returns:
            List of Lock IDs
        """
        lock_ids = []
        
        # Legacy mode: full branch lock (only for --force or emergency cases)
        if force_branch_lock:
            logger.warning(
                f"Full branch lock requested for {branch_name} by {locked_by}. "
                f"This may significantly impact developer productivity."
            )
            lock_id = await self.acquire_lock(
                branch_name=branch_name,
                lock_type=LockType.INDEXING,
                locked_by=locked_by,
                lock_scope=LockScope.BRANCH,
                reason=f"FORCE BRANCH LOCK: {reason}",
                timeout=self.indexing_lock_timeout
            )
            lock_ids.append(lock_id)
        else:
            # Foundry-style: minimal resource-type locking
            if not resource_types:
                # Auto-detect resource types from recent schema changes
                resource_types = await self._detect_indexing_resource_types(branch_name)
            
            if not resource_types:
                # Fallback: if we can't detect, lock common schema types
                resource_types = ["object_type", "link_type", "action_type"]
                logger.info(
                    f"No specific resource types detected for indexing {branch_name}, "
                    f"using default types: {resource_types}"
                )
            
            # Lock each resource type separately
            for resource_type in resource_types:
                try:
                    lock_id = await self.acquire_lock(
                        branch_name=branch_name,
                        lock_type=LockType.INDEXING,
                        locked_by=locked_by,
                        lock_scope=LockScope.RESOURCE_TYPE,
                        resource_type=resource_type,
                        reason=f"Indexing {resource_type}: {reason}",
                        timeout=self.indexing_lock_timeout,
                        enable_heartbeat=True,
                        heartbeat_interval=120  # 2 minutes for indexing operations
                    )
                    lock_ids.append(lock_id)
                    logger.info(
                        f"Acquired indexing lock for {resource_type} in {branch_name}: {lock_id}"
                    )
                except LockConflictError as e:
                    logger.warning(
                        f"Could not lock {resource_type} in {branch_name}: {e}. "
                        f"Continuing with other resource types."
                    )
                    # Continue with other resource types - partial indexing is allowed
        
        # Update indexing metadata
        branch_state = await self.get_branch_state(branch_name)
        branch_state.indexing_started_at = datetime.now(timezone.utc)
        branch_state.indexing_service = locked_by
        
        # Only transition to LOCKED_FOR_WRITE if we have a full branch lock and not already in that state
        if force_branch_lock and lock_ids and branch_state.current_state != BranchState.LOCKED_FOR_WRITE:
            await self._transition_state(
                branch_state,
                BranchState.LOCKED_FOR_WRITE,
                locked_by,
                f"Full branch indexing lock acquired: {reason}"
            )
        else:
            # For resource-type locks, don't change branch state - editing can continue
            logger.info(
                f"Resource-type indexing locks acquired for {branch_name}. "
                f"Branch remains ACTIVE - editing other resources is allowed."
            )
        
        await self._store_branch_state(branch_state)
        
        return lock_ids
    
    async def complete_indexing(
        self,
        branch_name: str,
        completed_by: str = "funnel-service",
        resource_types: Optional[List[str]] = None
    ) -> bool:
        """
        Mark indexing as complete and release locks (Foundry-style: granular)
        
        Args:
            branch_name: Branch where indexing completed
            completed_by: Service/user completing the indexing
            resource_types: Specific resource types that completed indexing
                          If None, releases all indexing locks
        
        Returns:
            True if indexing was marked complete
        """
        branch_state = await self.get_branch_state(branch_name)
        
        # Find indexing locks to release
        if resource_types:
            # Release only specific resource type locks
            indexing_locks = [
                lock for lock in branch_state.active_locks
                if (lock.lock_type == LockType.INDEXING and 
                    lock.is_active and
                    lock.resource_type in resource_types)
            ]
            logger.info(
                f"Completing indexing for specific resource types {resource_types} "
                f"in {branch_name}"
            )
        else:
            # Release all indexing locks (legacy behavior)
            indexing_locks = [
                lock for lock in branch_state.active_locks
                if lock.lock_type == LockType.INDEXING and lock.is_active
            ]
            logger.info(f"Completing all indexing for {branch_name}")
        
        if not indexing_locks:
            logger.warning(f"No active indexing locks found for {branch_name}")
            return False
        
        # Release the locks
        released_count = 0
        for lock in indexing_locks:
            success = await self.release_lock(lock.id, completed_by)
            if success:
                released_count += 1
        
        # Update indexing metadata
        branch_state = await self.get_branch_state(branch_name)
        branch_state.indexing_completed_at = datetime.now(timezone.utc)
        
        # Check if all indexing is complete
        remaining_indexing_locks = [
            lock for lock in branch_state.active_locks
            if lock.lock_type == LockType.INDEXING and lock.is_active
        ]
        
        if not remaining_indexing_locks:
            # All indexing complete - transition to READY if was in LOCKED_FOR_WRITE
            if branch_state.current_state == BranchState.LOCKED_FOR_WRITE:
                await self._transition_state(
                    branch_state,
                    BranchState.READY,
                    completed_by,
                    "All indexing completed, ready for merge"
                )
            
            # Check auto-merge conditions
            if branch_state.auto_merge_enabled:
                await self._check_auto_merge_conditions(branch_state)
        else:
            logger.info(
                f"Partial indexing completion for {branch_name}. "
                f"{len(remaining_indexing_locks)} indexing locks still active."
            )
        
        await self._store_branch_state(branch_state)
        
        logger.info(f"Indexing completed for branch {branch_name}")
        return True
    
    async def force_unlock(
        self,
        branch_name: str,
        admin_user: str,
        reason: str = "Administrative unlock"
    ) -> int:
        """
        Force unlock all locks on a branch (admin only)
        
        Returns:
            Number of locks released
        """
        branch_state = await self.get_branch_state(branch_name)
        active_locks = [lock for lock in branch_state.active_locks if lock.is_active]
        
        count = 0
        for lock in active_locks:
            await self.release_lock(lock.id, admin_user)
            count += 1
        
        # Reset state to ACTIVE
        await self._transition_state(
            branch_state,
            BranchState.ACTIVE,
            admin_user,
            f"Force unlock: {reason}"
        )
        
        logger.warning(
            f"Force unlock performed on {branch_name} by {admin_user}: "
            f"{count} locks released. Reason: {reason}"
        )
        
        return count
    
    async def send_heartbeat(
        self,
        lock_id: str,
        service_name: str,
        status: str = "healthy",
        progress_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Send a heartbeat for a lock to indicate the service is still active
        
        Args:
            lock_id: The lock to send heartbeat for
            service_name: Name of the service sending the heartbeat
            status: Status of the service (healthy, warning, error)
            progress_info: Optional progress information
            
        Returns:
            True if heartbeat was recorded successfully
        """
        lock = self._active_locks.get(lock_id)
        if not lock or not lock.is_active:
            logger.warning(f"Attempted to send heartbeat for non-existent or inactive lock: {lock_id}")
            return False
        
        # Update lock heartbeat
        now = datetime.now(timezone.utc)
        lock.last_heartbeat = now
        lock.heartbeat_source = service_name
        
        # Store heartbeat record
        heartbeat = HeartbeatRecord(
            lock_id=lock_id,
            branch_name=lock.branch_name,
            service_name=service_name,
            heartbeat_at=now,
            status=status,
            progress_info=progress_info
        )
        
        # Update branch state
        branch_state = await self.get_branch_state(lock.branch_name)
        await self._store_branch_state(branch_state)
        
        # Store heartbeat record in persistent storage
        if self.db_service:
            await self.db_service.store_heartbeat_record(heartbeat)
        
        logger.debug(
            f"Heartbeat received for lock {lock_id} from {service_name} (status: {status})"
        )
        
        return True
    
    async def list_active_locks(self, branch_name: Optional[str] = None) -> List[BranchLock]:
        """List all active locks, optionally filtered by branch"""
        locks = list(self._active_locks.values())
        
        if branch_name:
            locks = [lock for lock in locks if lock.branch_name == branch_name]
        
        return locks
    
    async def get_lock_status(self, lock_id: str) -> Optional[BranchLock]:
        """Get status of a specific lock"""
        return self._active_locks.get(lock_id)
    
    async def _check_lock_conflicts(self, new_lock: BranchLock):
        """Check if a new lock conflicts with existing locks"""
        branch_state = await self.get_branch_state(new_lock.branch_name)
        
        for existing_lock in branch_state.active_locks:
            if not existing_lock.is_active:
                continue
            
            # Check for scope conflicts
            if self._locks_conflict(existing_lock, new_lock):
                raise LockConflictError(
                    f"Lock conflict: {new_lock.lock_type.value} lock on "
                    f"{new_lock.branch_name} conflicts with existing "
                    f"{existing_lock.lock_type.value} lock {existing_lock.id}"
                )
    
    def _locks_conflict(self, lock1: BranchLock, lock2: BranchLock) -> bool:
        """Check if two locks conflict"""
        # Same branch is required for conflict
        if lock1.branch_name != lock2.branch_name:
            return False
        
        # Branch-level locks conflict with everything
        if (lock1.lock_scope == LockScope.BRANCH or 
            lock2.lock_scope == LockScope.BRANCH):
            return True
        
        # Resource type level conflicts
        if (lock1.lock_scope == LockScope.RESOURCE_TYPE and
            lock2.lock_scope == LockScope.RESOURCE_TYPE and
            lock1.resource_type == lock2.resource_type):
            return True
        
        # Specific resource conflicts
        if (lock1.lock_scope == LockScope.RESOURCE and
            lock2.lock_scope == LockScope.RESOURCE and
            lock1.resource_type == lock2.resource_type and
            lock1.resource_id == lock2.resource_id):
            return True
        
        return False
    
    def _has_active_indexing_locks(self, branch_state: BranchStateInfo) -> bool:
        """Check if branch has any active indexing locks"""
        return any(
            lock.is_active and lock.lock_type == LockType.INDEXING
            for lock in branch_state.active_locks
        )
    
    async def _transition_state(
        self,
        branch_state: BranchStateInfo,
        new_state: BranchState,
        changed_by: str,
        reason: str
    ):
        """Transition branch to new state"""
        old_state = branch_state.current_state
        
        # Validate transition
        if not is_valid_transition(old_state, new_state):
            raise InvalidStateTransitionError(
                f"Invalid state transition: {old_state} -> {new_state}"
            )
        
        # Record transition
        transition = BranchStateTransition(
            branch_name=branch_state.branch_name,
            from_state=old_state,
            to_state=new_state,
            transitioned_by=changed_by,
            reason=reason,
            trigger="lock_manager"
        )
        
        # Update state
        branch_state.previous_state = old_state
        branch_state.current_state = new_state
        branch_state.state_changed_at = datetime.now(timezone.utc)
        branch_state.state_changed_by = changed_by
        branch_state.state_change_reason = reason
        
        # Store transition history
        if self.db_service:
            await self.db_service.store_state_transition(transition)
        
        logger.info(
            f"Branch state transition: {branch_state.branch_name} "
            f"{old_state} -> {new_state} by {changed_by}"
        )
    
    def _get_default_timeout(self, lock_type: LockType) -> timedelta:
        """Get default timeout for lock type"""
        timeouts = {
            LockType.INDEXING: self.indexing_lock_timeout,
            LockType.MAINTENANCE: self.maintenance_lock_timeout,
            LockType.MIGRATION: timedelta(hours=6),
            LockType.BACKUP: timedelta(hours=2),
            LockType.MANUAL: timedelta(hours=24)
        }
        return timeouts.get(lock_type, self.default_lock_timeout)
    
    async def _check_auto_merge_conditions(self, branch_state: BranchStateInfo):
        """Check and potentially trigger auto-merge"""
        if not branch_state.auto_merge_enabled:
            return
        
        if not branch_state.is_ready_for_merge:
            return
        
        # Check all conditions are met
        # This would integrate with other services to check:
        # - No conflicts
        # - Tests passed
        # - Approvals received
        
        logger.info(f"Auto-merge candidate: {branch_state.branch_name}")
        # TODO: Implement actual auto-merge logic
    
    async def _detect_indexing_resource_types(self, branch_name: str) -> List[str]:
        """
        Auto-detect which resource types need indexing based on recent schema changes
        
        This is a simplified implementation. In a real system, this would:
        1. Check the event/commit history for the branch
        2. Analyze what types of schema objects were modified
        3. Return only the resource types that actually need reindexing
        """
        try:
            # For now, use a simple heuristic based on branch name or recent activity
            # In a real implementation, this would query:
            # - Recent commits on the branch
            # - Schema change events
            # - Funnel Service's indexing requirements
            
            detected_types = []
            
            # Heuristic 1: Branch name analysis
            branch_lower = branch_name.lower()
            if "object" in branch_lower or "entity" in branch_lower:
                detected_types.append("object_type")
            if "link" in branch_lower or "relation" in branch_lower:
                detected_types.append("link_type")
            if "action" in branch_lower or "function" in branch_lower:
                detected_types.append("action_type")
            if "function" in branch_lower:
                detected_types.append("function_type")
            
            # Heuristic 2: If nothing detected, check for recent schema activity
            if not detected_types:
                # TODO: Query recent commits/events for this branch
                # For now, assume object_type changes are most common
                detected_types = ["object_type"]
            
            logger.debug(
                f"Auto-detected resource types for indexing in {branch_name}: {detected_types}"
            )
            
            return detected_types
            
        except Exception as e:
            logger.error(f"Failed to detect resource types for {branch_name}: {e}")
            # Safe fallback
            return ["object_type"]
    
    async def _release_all_branch_locks(self, branch_name: str, reason: str = "force_release"):
        """Release all active locks for a branch"""
        branch_state = await self.get_branch_state(branch_name)
        locks_to_release = []
        
        for lock in branch_state.active_locks:
            if lock.is_active:
                locks_to_release.append(lock.id)
        
        for lock_id in locks_to_release:
            await self.release_lock(lock_id, f"system_{reason}")
        
        if locks_to_release:
            logger.info(
                f"Released {len(locks_to_release)} locks for branch {branch_name}: {reason}"
            )
    
    async def _cleanup_expired_locks_loop(self):
        """Background task to cleanup TTL expired locks"""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                await self.cleanup_expired_locks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in TTL lock cleanup: {e}")
    
    async def _heartbeat_checker_loop(self):
        """Background task to check for missed heartbeats"""
        while True:
            try:
                await asyncio.sleep(self.heartbeat_check_interval)
                await self.cleanup_heartbeat_expired_locks()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat cleanup: {e}")
    
    async def cleanup_expired_locks(self):
        """Remove expired locks based on TTL"""
        now = datetime.now(timezone.utc)
        expired_locks = []
        
        for lock_id, lock in list(self._active_locks.items()):
            if is_lock_expired_by_ttl(lock):
                expired_locks.append((lock_id, "TTL_EXPIRED"))
        
        for lock_id, reason in expired_locks:
            lock = self._active_locks.get(lock_id)
            if lock and lock.auto_release_enabled:
                await self.release_lock(lock_id, f"system_cleanup_{reason}")
                logger.info(f"TTL expired lock cleaned up: {lock_id} (reason: {reason})")
        
        if expired_locks:
            logger.info(f"Cleaned up {len(expired_locks)} TTL expired locks")
    
    async def cleanup_heartbeat_expired_locks(self):
        """Remove locks that have missed heartbeats"""
        heartbeat_expired_locks = []
        
        for lock_id, lock in list(self._active_locks.items()):
            if is_lock_expired_by_heartbeat(lock):
                heartbeat_expired_locks.append((lock_id, "HEARTBEAT_MISSED"))
        
        for lock_id, reason in heartbeat_expired_locks:
            lock = self._active_locks.get(lock_id)
            if lock and lock.auto_release_enabled:
                await self.release_lock(lock_id, f"system_cleanup_{reason}")
                logger.warning(
                    f"Heartbeat expired lock cleaned up: {lock_id} "
                    f"(missed heartbeats from {lock.heartbeat_source})"
                )
        
        if heartbeat_expired_locks:
            logger.warning(f"Cleaned up {len(heartbeat_expired_locks)} heartbeat expired locks")
    
    async def get_lock_health_status(self, lock_id: str) -> Optional[Dict[str, Any]]:
        """Get health status and heartbeat information for a lock"""
        lock = self._active_locks.get(lock_id)
        if not lock:
            return None
        
        now = datetime.now(timezone.utc)
        health_status = {
            "lock_id": lock_id,
            "is_active": lock.is_active,
            "heartbeat_enabled": lock.heartbeat_interval > 0,
            "last_heartbeat": lock.last_heartbeat,
            "heartbeat_source": lock.heartbeat_source,
            "ttl_expired": is_lock_expired_by_ttl(lock),
            "heartbeat_expired": is_lock_expired_by_heartbeat(lock),
            "auto_release_enabled": lock.auto_release_enabled
        }
        
        if lock.last_heartbeat:
            seconds_since_heartbeat = (now - lock.last_heartbeat).total_seconds()
            health_status["seconds_since_last_heartbeat"] = int(seconds_since_heartbeat)
            
            if lock.heartbeat_interval > 0:
                health_status["heartbeat_health"] = "healthy" if seconds_since_heartbeat < lock.heartbeat_interval else "warning"
                if seconds_since_heartbeat > lock.heartbeat_interval * self.heartbeat_grace_multiplier:
                    health_status["heartbeat_health"] = "critical"
        
        if lock.expires_at:
            seconds_until_expiry = (lock.expires_at - now).total_seconds()
            health_status["seconds_until_ttl_expiry"] = max(0, int(seconds_until_expiry))
        
        return health_status
    
    async def extend_lock_ttl(
        self,
        lock_id: str,
        extension_duration: timedelta,
        extended_by: str,
        reason: str = "TTL extension"
    ) -> bool:
        """
        Extend the TTL of an existing lock
        
        Args:
            lock_id: Lock to extend
            extension_duration: How much to extend the TTL by
            extended_by: Who is extending the lock
            reason: Reason for extension
            
        Returns:
            True if extension was successful
        """
        lock = self._active_locks.get(lock_id)
        if not lock or not lock.is_active:
            logger.warning(f"Attempted to extend non-existent or inactive lock: {lock_id}")
            return False
        
        old_expires_at = lock.expires_at
        if lock.expires_at:
            lock.expires_at = lock.expires_at + extension_duration
        else:
            lock.expires_at = datetime.now(timezone.utc) + extension_duration
        
        # Update branch state
        branch_state = await self.get_branch_state(lock.branch_name)
        await self._store_branch_state(branch_state)
        
        logger.info(
            f"Lock TTL extended: {lock_id} by {extended_by}. "
            f"Old expiry: {old_expires_at}, New expiry: {lock.expires_at}. Reason: {reason}"
        )
        
        return True


# Global lock manager instance
_lock_manager: Optional[BranchLockManager] = None


def get_lock_manager() -> BranchLockManager:
    """Get global lock manager instance"""
    global _lock_manager
    if _lock_manager is None:
        _lock_manager = BranchLockManager()
    return _lock_manager


async def initialize_lock_manager(cache_service=None, db_service=None):
    """Initialize global lock manager"""
    global _lock_manager
    _lock_manager = BranchLockManager(cache_service, db_service)
    await _lock_manager.initialize()
    return _lock_manager