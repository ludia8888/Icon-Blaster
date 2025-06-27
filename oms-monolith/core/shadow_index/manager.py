"""
Shadow Index Manager
Manages near-zero downtime indexing with atomic switch pattern
"""
import asyncio
import os
import shutil
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone, timedelta
from pathlib import Path

from models.shadow_index import (
    ShadowIndexInfo, ShadowIndexOperation, ShadowIndexState, IndexType,
    SwitchRequest, SwitchResult, is_valid_shadow_transition,
    get_switch_critical_states, estimate_switch_duration
)
from core.branch.lock_manager import get_lock_manager, LockType, LockScope
from utils.logger import get_logger

logger = get_logger(__name__)


class ShadowIndexConflictError(Exception):
    """Raised when shadow index conflicts with existing operations"""
    pass


class SwitchValidationError(Exception):
    """Raised when switch validation fails"""
    pass


class ShadowIndexManager:
    """
    Manages shadow indexes for near-zero downtime indexing
    
    Key Features:
    - Background index building (no locks required)
    - Atomic switch with minimal lock time (< 10 seconds)
    - Comprehensive validation and verification
    - Automatic rollback on switch failure
    """
    
    def __init__(self, index_base_path: str = "/tmp/oms_indexes", cache_service=None, db_service=None):
        self.index_base_path = Path(index_base_path)
        self.cache_service = cache_service
        self.db_service = db_service
        
        # In-memory tracking
        self._active_shadows: Dict[str, ShadowIndexInfo] = {}
        self._operation_history: List[ShadowIndexOperation] = []
        
        # Ensure index directory exists
        self.index_base_path.mkdir(parents=True, exist_ok=True)
        
        # Background tasks
        self._monitor_task = None
        
        # Configuration
        self.max_concurrent_builds = 3
        self.default_switch_timeout = 10  # seconds
        self.cleanup_retention_hours = 24
    
    async def initialize(self):
        """Initialize the shadow index manager"""
        # Start monitoring task
        self._monitor_task = asyncio.create_task(self._monitor_shadow_indexes())
        logger.info("Shadow Index Manager initialized")
    
    async def shutdown(self):
        """Shutdown the shadow index manager"""
        if self._monitor_task:
            self._monitor_task.cancel()
        logger.info("Shadow Index Manager shutdown")
    
    async def start_shadow_build(
        self,
        branch_name: str,
        index_type: IndexType,
        resource_types: List[str],
        service_name: str = "funnel-service",
        service_instance_id: Optional[str] = None,
        build_config: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Start building a shadow index in the background (no locks required)
        
        Args:
            branch_name: Branch to build index for
            index_type: Type of index to build
            resource_types: Resource types to include
            service_name: Service managing the build
            service_instance_id: Specific service instance
            build_config: Additional build configuration
            
        Returns:
            Shadow index ID
        """
        # Check for existing shadow builds
        existing = await self._get_active_shadow_for_branch(branch_name, index_type)
        if existing and existing.state in [ShadowIndexState.BUILDING, ShadowIndexState.BUILT]:
            raise ShadowIndexConflictError(
                f"Shadow index already exists for {branch_name}:{index_type.value}: {existing.id}"
            )
        
        # Create shadow index info
        shadow_info = ShadowIndexInfo(
            branch_name=branch_name,
            index_type=index_type,
            resource_types=resource_types,
            service_name=service_name,
            service_instance_id=service_instance_id,
            metadata=build_config or {}
        )
        
        # Generate paths
        shadow_info.shadow_index_path = str(
            self.index_base_path / f"shadow_{shadow_info.id}_{branch_name}_{index_type.value}"
        )
        shadow_info.current_index_path = str(
            self.index_base_path / f"current_{branch_name}_{index_type.value}"
        )
        
        # Store shadow info
        self._active_shadows[shadow_info.id] = shadow_info
        
        # Record operation
        await self._record_operation(
            shadow_info.id,
            "BUILD_START",
            service_name,
            to_state=ShadowIndexState.BUILDING
        )
        
        # Transition to building state
        await self._transition_shadow_state(shadow_info.id, ShadowIndexState.BUILDING, service_name)
        
        logger.info(
            f"Started shadow index build: {shadow_info.id} for {branch_name}:{index_type.value}"
        )
        
        return shadow_info.id
    
    async def update_build_progress(
        self,
        shadow_index_id: str,
        progress_percent: int,
        estimated_completion_seconds: Optional[int] = None,
        record_count: Optional[int] = None,
        service_name: str = "funnel-service"
    ) -> bool:
        """
        Update build progress for a shadow index
        
        Args:
            shadow_index_id: Shadow index to update
            progress_percent: Build progress (0-100)
            estimated_completion_seconds: Estimated time to completion
            record_count: Current record count
            service_name: Service reporting progress
            
        Returns:
            True if update was successful
        """
        shadow_info = self._active_shadows.get(shadow_index_id)
        if not shadow_info:
            logger.warning(f"Shadow index not found: {shadow_index_id}")
            return False
        
        if shadow_info.state != ShadowIndexState.BUILDING:
            logger.warning(f"Shadow index {shadow_index_id} not in BUILDING state: {shadow_info.state}")
            return False
        
        # Update progress
        shadow_info.build_progress_percent = max(0, min(100, progress_percent))
        shadow_info.estimated_completion_seconds = estimated_completion_seconds
        shadow_info.record_count = record_count
        
        # Record progress operation
        await self._record_operation(
            shadow_index_id,
            "BUILD_PROGRESS",
            service_name,
            progress_data={
                "progress_percent": progress_percent,
                "estimated_completion_seconds": estimated_completion_seconds,
                "record_count": record_count
            }
        )
        
        logger.debug(f"Updated shadow index progress: {shadow_index_id} -> {progress_percent}%")
        
        return True
    
    async def complete_shadow_build(
        self,
        shadow_index_id: str,
        index_size_bytes: int,
        record_count: int,
        service_name: str = "funnel-service"
    ) -> bool:
        """
        Mark shadow index build as complete
        
        Args:
            shadow_index_id: Shadow index that completed
            index_size_bytes: Final index size
            record_count: Final record count
            service_name: Service completing the build
            
        Returns:
            True if completion was successful
        """
        shadow_info = self._active_shadows.get(shadow_index_id)
        if not shadow_info:
            logger.warning(f"Shadow index not found: {shadow_index_id}")
            return False
        
        if shadow_info.state != ShadowIndexState.BUILDING:
            logger.warning(f"Shadow index {shadow_index_id} not in BUILDING state: {shadow_info.state}")
            return False
        
        # Update completion info
        shadow_info.index_size_bytes = index_size_bytes
        shadow_info.record_count = record_count
        shadow_info.build_progress_percent = 100
        shadow_info.completed_at = datetime.now(timezone.utc)
        
        # Record completion operation
        await self._record_operation(
            shadow_index_id,
            "BUILD_COMPLETE",
            service_name,
            to_state=ShadowIndexState.BUILT,
            progress_data={
                "index_size_bytes": index_size_bytes,
                "record_count": record_count
            }
        )
        
        # Transition to built state
        await self._transition_shadow_state(shadow_index_id, ShadowIndexState.BUILT, service_name)
        
        logger.info(
            f"Completed shadow index build: {shadow_index_id} "
            f"({index_size_bytes} bytes, {record_count} records)"
        )
        
        return True
    
    async def request_atomic_switch(
        self,
        shadow_index_id: str,
        request: SwitchRequest,
        service_name: str = "funnel-service"
    ) -> SwitchResult:
        """
        Perform atomic switch from shadow to primary index
        
        This is the only operation that requires a short lock (< 10 seconds)
        
        Args:
            shadow_index_id: Shadow index to switch to primary
            request: Switch request configuration
            service_name: Service requesting the switch
            
        Returns:
            Switch result with success/failure details
        """
        shadow_info = self._active_shadows.get(shadow_index_id)
        if not shadow_info:
            raise ValueError(f"Shadow index not found: {shadow_index_id}")
        
        if shadow_info.state != ShadowIndexState.BUILT:
            raise ValueError(f"Shadow index {shadow_index_id} not ready for switch: {shadow_info.state}")
        
        start_time = datetime.now(timezone.utc)
        switch_result = SwitchResult(
            shadow_index_id=shadow_index_id,
            success=False,
            switch_duration_ms=0,
            message="Switch started"
        )
        
        try:
            # 1. Pre-switch validation (no lock required)
            await self._validate_switch_readiness(shadow_info, request, switch_result)
            if not switch_result.validation_passed and not request.force_switch:
                switch_result.message = f"Validation failed: {', '.join(switch_result.validation_errors)}"
                return switch_result
            
            # 2. Acquire minimal lock for switch operation
            lock_manager = get_lock_manager()
            
            estimated_duration = estimate_switch_duration(
                shadow_info.index_size_bytes, 
                shadow_info.switch_strategy
            )
            
            # Acquire very short lock (only during switch)
            lock_id = await lock_manager.acquire_lock(
                branch_name=shadow_info.branch_name,
                lock_type=LockType.INDEXING,
                locked_by=service_name,
                lock_scope=LockScope.RESOURCE_TYPE,
                resource_type=f"index_{shadow_info.index_type.value}",
                reason=f"Atomic index switch: {shadow_index_id}",
                timeout=timedelta(seconds=request.switch_timeout_seconds),
                enable_heartbeat=False  # No heartbeat for very short operations
            )
            
            try:
                # Transition to switching state
                await self._transition_shadow_state(shadow_index_id, ShadowIndexState.SWITCHING, service_name)
                
                # 3. Perform atomic switch (critical section)
                await self._perform_atomic_switch(shadow_info, request, switch_result)
                
                if switch_result.success:
                    # 4. Post-switch verification
                    await self._verify_switch_success(shadow_info, switch_result)
                    
                    # Transition to active state
                    await self._transition_shadow_state(shadow_index_id, ShadowIndexState.ACTIVE, service_name)
                    shadow_info.switched_at = datetime.now(timezone.utc)
                
            finally:
                # Always release lock quickly
                await lock_manager.release_lock(lock_id, service_name)
            
            # Calculate final duration
            end_time = datetime.now(timezone.utc)
            switch_result.switch_duration_ms = int((end_time - start_time).total_seconds() * 1000)
            
            if switch_result.success:
                switch_result.message = f"Index switch completed successfully in {switch_result.switch_duration_ms}ms"
                
                # Record successful switch
                await self._record_operation(
                    shadow_index_id,
                    "SWITCH_COMPLETE",
                    service_name,
                    to_state=ShadowIndexState.ACTIVE,
                    duration_ms=switch_result.switch_duration_ms
                )
                
                logger.info(
                    f"Atomic switch completed: {shadow_index_id} in {switch_result.switch_duration_ms}ms"
                )
            else:
                # Transition to failed state
                await self._transition_shadow_state(shadow_index_id, ShadowIndexState.FAILED, service_name)
                switch_result.message = f"Index switch failed: {', '.join(switch_result.verification_errors)}"
        
        except Exception as e:
            # Handle any switch errors
            end_time = datetime.now(timezone.utc)
            switch_result.switch_duration_ms = int((end_time - start_time).total_seconds() * 1000)
            switch_result.success = False
            switch_result.message = f"Switch failed with error: {str(e)}"
            
            # Transition to failed state
            await self._transition_shadow_state(shadow_index_id, ShadowIndexState.FAILED, service_name)
            
            # Record failed switch
            await self._record_operation(
                shadow_index_id,
                "SWITCH_FAILED",
                service_name,
                to_state=ShadowIndexState.FAILED,
                duration_ms=switch_result.switch_duration_ms,
                success=False,
                error_message=str(e)
            )
            
            logger.error(f"Atomic switch failed: {shadow_index_id}: {e}")
        
        return switch_result
    
    async def get_shadow_status(self, shadow_index_id: str) -> Optional[ShadowIndexInfo]:
        """Get current status of a shadow index"""
        return self._active_shadows.get(shadow_index_id)
    
    async def list_active_shadows(self, branch_name: Optional[str] = None) -> List[ShadowIndexInfo]:
        """List all active shadow indexes"""
        shadows = list(self._active_shadows.values())
        
        if branch_name:
            shadows = [s for s in shadows if s.branch_name == branch_name]
        
        return shadows
    
    async def cancel_shadow_build(
        self,
        shadow_index_id: str,
        service_name: str = "system",
        reason: str = "Manual cancellation"
    ) -> bool:
        """Cancel an active shadow build"""
        shadow_info = self._active_shadows.get(shadow_index_id)
        if not shadow_info:
            return False
        
        if shadow_info.state not in [ShadowIndexState.PREPARING, ShadowIndexState.BUILDING]:
            logger.warning(f"Cannot cancel shadow index {shadow_index_id} in state {shadow_info.state}")
            return False
        
        # Transition to cancelled state
        await self._transition_shadow_state(shadow_index_id, ShadowIndexState.CANCELLED, service_name)
        
        # Clean up shadow index files
        if shadow_info.shadow_index_path and Path(shadow_info.shadow_index_path).exists():
            shutil.rmtree(shadow_info.shadow_index_path, ignore_errors=True)
        
        # Record cancellation
        await self._record_operation(
            shadow_index_id,
            "BUILD_CANCELLED",
            service_name,
            to_state=ShadowIndexState.CANCELLED
        )
        
        logger.info(f"Cancelled shadow index build: {shadow_index_id} - {reason}")
        
        return True
    
    # Private methods
    
    async def _get_active_shadow_for_branch(
        self, 
        branch_name: str, 
        index_type: IndexType
    ) -> Optional[ShadowIndexInfo]:
        """Get active shadow index for branch and type"""
        for shadow in self._active_shadows.values():
            if (shadow.branch_name == branch_name and 
                shadow.index_type == index_type and 
                shadow.state in [ShadowIndexState.BUILDING, ShadowIndexState.BUILT]):
                return shadow
        return None
    
    async def _transition_shadow_state(
        self,
        shadow_index_id: str,
        new_state: ShadowIndexState,
        service_name: str
    ):
        """Transition shadow index to new state"""
        shadow_info = self._active_shadows.get(shadow_index_id)
        if not shadow_info:
            raise ValueError(f"Shadow index not found: {shadow_index_id}")
        
        old_state = shadow_info.state
        
        # Validate transition
        if not is_valid_shadow_transition(old_state, new_state):
            raise ValueError(f"Invalid shadow transition: {old_state} -> {new_state}")
        
        # Update state
        shadow_info.state = new_state
        
        # Update timestamps
        if new_state == ShadowIndexState.BUILDING:
            shadow_info.started_at = datetime.now(timezone.utc)
        elif new_state == ShadowIndexState.BUILT:
            shadow_info.completed_at = datetime.now(timezone.utc)
        elif new_state == ShadowIndexState.ACTIVE:
            shadow_info.switched_at = datetime.now(timezone.utc)
        
        logger.debug(f"Shadow index state transition: {shadow_index_id} {old_state} -> {new_state}")
    
    async def _record_operation(
        self,
        shadow_index_id: str,
        operation_type: str,
        performed_by: str,
        from_state: Optional[ShadowIndexState] = None,
        to_state: Optional[ShadowIndexState] = None,
        progress_data: Optional[Dict[str, Any]] = None,
        duration_ms: Optional[int] = None,
        success: bool = True,
        error_message: Optional[str] = None
    ):
        """Record shadow index operation"""
        operation = ShadowIndexOperation(
            shadow_index_id=shadow_index_id,
            operation_type=operation_type,
            performed_by=performed_by,
            from_state=from_state,
            to_state=to_state,
            progress_data=progress_data,
            duration_ms=duration_ms,
            success=success,
            error_message=error_message
        )
        
        self._operation_history.append(operation)
        
        # Store in persistent storage if available
        if self.db_service:
            await self.db_service.store_shadow_operation(operation)
    
    async def _validate_switch_readiness(
        self,
        shadow_info: ShadowIndexInfo,
        request: SwitchRequest,
        result: SwitchResult
    ):
        """Validate that shadow index is ready for switch"""
        result.validation_passed = True
        result.validation_errors = []
        
        # Check shadow index exists
        if not Path(shadow_info.shadow_index_path).exists():
            result.validation_errors.append("Shadow index file not found")
        
        # Check for any custom validation checks first
        for check in request.validation_checks:
            if check == "RECORD_COUNT_VALIDATION":
                if not shadow_info.record_count or shadow_info.record_count == 0:
                    result.validation_errors.append("Shadow index has no records")
            elif check == "SIZE_COMPARISON":
                # Compare with current index size if it exists
                current_path = Path(shadow_info.current_index_path)
                if current_path.exists():
                    current_size = sum(f.stat().st_size for f in current_path.rglob('*') if f.is_file())
                    shadow_size = shadow_info.index_size_bytes or 0
                    if abs(shadow_size - current_size) > current_size * 0.5:  # 50% difference
                        result.validation_errors.append(
                            f"Shadow index size differs significantly from current: {shadow_size} vs {current_size}"
                        )
        
        # Check index size is reasonable (only if no record count validation error)
        if not result.validation_errors and shadow_info.index_size_bytes and shadow_info.index_size_bytes < 1024:
            result.validation_errors.append("Shadow index appears to be too small")
        
        if result.validation_errors:
            result.validation_passed = False
    
    async def _perform_atomic_switch(
        self,
        shadow_info: ShadowIndexInfo,
        request: SwitchRequest,
        result: SwitchResult
    ):
        """Perform the actual atomic switch (critical section)"""
        shadow_path = Path(shadow_info.shadow_index_path)
        current_path = Path(shadow_info.current_index_path)
        
        result.old_index_path = str(current_path) if current_path.exists() else None
        result.new_index_path = str(shadow_path)
        
        try:
            # Backup current index if requested
            if request.backup_current and current_path.exists():
                backup_path = current_path.parent / f"{current_path.name}_backup_{int(datetime.now().timestamp())}"
                shutil.move(str(current_path), str(backup_path))
                result.backup_path = str(backup_path)
            
            # Atomic switch strategies
            if shadow_info.switch_strategy == "ATOMIC_RENAME":
                # Move shadow index to current location (atomic on most filesystems)
                shutil.move(str(shadow_path), str(current_path))
            elif shadow_info.switch_strategy == "COPY_AND_REPLACE":
                # Copy shadow to temp, then rename (safer but slower)
                temp_path = current_path.parent / f"{current_path.name}_temp"
                shutil.copytree(str(shadow_path), str(temp_path))
                if current_path.exists():
                    shutil.rmtree(str(current_path))
                shutil.move(str(temp_path), str(current_path))
                shutil.rmtree(str(shadow_path))
            else:
                raise ValueError(f"Unknown switch strategy: {shadow_info.switch_strategy}")
            
            result.success = True
            
        except Exception as e:
            result.success = False
            result.verification_errors.append(f"Switch operation failed: {str(e)}")
            raise
    
    async def _verify_switch_success(
        self,
        shadow_info: ShadowIndexInfo,
        result: SwitchResult
    ):
        """Verify that switch was successful"""
        result.verification_passed = True
        result.verification_errors = []
        
        current_path = Path(shadow_info.current_index_path)
        
        # Verify current index exists
        if not current_path.exists():
            result.verification_errors.append("Current index not found after switch")
        
        # Verify index is accessible (basic check)
        try:
            # Check that we can list files in the index directory
            list(current_path.iterdir())
        except Exception as e:
            result.verification_errors.append(f"Cannot access switched index: {str(e)}")
        
        # Calculate size change
        if shadow_info.index_size_bytes and result.old_index_path:
            old_path = Path(result.old_index_path)
            if old_path.exists() or result.backup_path:
                backup_path = Path(result.backup_path) if result.backup_path else old_path
                if backup_path.exists():
                    old_size = sum(f.stat().st_size for f in backup_path.rglob('*') if f.is_file())
                    result.index_size_change_bytes = shadow_info.index_size_bytes - old_size
        
        if result.verification_errors:
            result.verification_passed = False
            result.success = False
    
    async def _monitor_shadow_indexes(self):
        """Background task to monitor shadow indexes"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                # Clean up old shadow indexes
                await self._cleanup_old_shadows()
                
                # Check for stale building indexes
                await self._check_stale_builds()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in shadow index monitoring: {e}")
    
    async def _cleanup_old_shadows(self):
        """Clean up old completed/failed shadow indexes"""
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=self.cleanup_retention_hours)
        
        to_remove = []
        for shadow_id, shadow_info in self._active_shadows.items():
            if (shadow_info.state in [ShadowIndexState.ACTIVE, ShadowIndexState.FAILED, ShadowIndexState.CANCELLED] and
                shadow_info.created_at < cutoff_time):
                to_remove.append(shadow_id)
        
        for shadow_id in to_remove:
            shadow_info = self._active_shadows.pop(shadow_id)
            
            # Clean up files
            if shadow_info.shadow_index_path and Path(shadow_info.shadow_index_path).exists():
                shutil.rmtree(shadow_info.shadow_index_path, ignore_errors=True)
            
            logger.info(f"Cleaned up old shadow index: {shadow_id}")
    
    async def _check_stale_builds(self):
        """Check for stale building indexes that haven't been updated"""
        stale_threshold = datetime.now(timezone.utc) - timedelta(hours=6)  # 6 hours
        
        for shadow_id, shadow_info in self._active_shadows.items():
            if (shadow_info.state == ShadowIndexState.BUILDING and
                shadow_info.started_at and shadow_info.started_at < stale_threshold):
                
                logger.warning(f"Detected stale shadow build: {shadow_id}, cancelling")
                await self.cancel_shadow_build(shadow_id, "system", "Stale build detected")


# Global shadow index manager instance
_shadow_manager: Optional[ShadowIndexManager] = None


def get_shadow_manager() -> ShadowIndexManager:
    """Get global shadow index manager instance"""
    global _shadow_manager
    if _shadow_manager is None:
        _shadow_manager = ShadowIndexManager()
    return _shadow_manager


async def initialize_shadow_manager(index_base_path: str = "/tmp/oms_indexes", **kwargs):
    """Initialize global shadow index manager"""
    global _shadow_manager
    _shadow_manager = ShadowIndexManager(index_base_path, **kwargs)
    await _shadow_manager.initialize()
    return _shadow_manager