"""
Funnel Service Indexing Event Handler
Handles indexing.completed events from Funnel Service and manages branch state transitions
Supports both traditional locking and Shadow Index + Switch patterns
"""
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from core.branch.lock_manager import get_lock_manager, LockConflictError
from core.shadow_index.manager import get_shadow_manager
from models.branch_state import BranchState
from models.shadow_index import IndexType, SwitchRequest
from models.audit_events import AuditEventV1, AuditAction, create_audit_event, ActorInfo, TargetInfo, ResourceType
from utils.audit_id_generator import AuditIDGenerator
from utils.logger import get_logger

logger = get_logger(__name__)


class FunnelIndexingEventHandler:
    """
    Handles Funnel Service indexing events and manages branch state transitions
    """
    
    def __init__(self):
        self.lock_manager = get_lock_manager()
        self.shadow_manager = get_shadow_manager()
        
        # Auto-merge configuration
        self.auto_merge_config = {
            "enabled": True,
            "require_validation": True,
            "require_no_conflicts": True,
            "timeout_hours": 24  # Auto-merge timeout
        }
        
        # Shadow index configuration
        self.shadow_index_config = {
            "enabled": True,
            "auto_switch": True,
            "validation_checks": ["RECORD_COUNT_VALIDATION", "SIZE_COMPARISON"],
            "backup_before_switch": True
        }
    
    async def handle_indexing_completed(self, event_data: Dict[str, Any]) -> bool:
        """
        Handle Funnel Service indexing.completed event
        
        Expected event structure (Traditional or Shadow Index):
        {
            "id": "indexing-uuid",
            "source": "funnel-service",
            "type": "com.oms.indexing.completed",
            "data": {
                "branch_name": "feature/user-schema",
                "indexing_id": "idx-123",
                "indexing_mode": "shadow",  # "traditional" or "shadow"
                "shadow_index_id": "shadow-123",  # If shadow mode
                "started_at": "2025-06-26T10:00:00Z",
                "completed_at": "2025-06-26T10:30:00Z",
                "status": "success",
                "records_indexed": 1250,
                "index_size_bytes": 52428800,
                "resource_types": ["object_type", "link_type"],
                "errors": [],
                "validation_results": {
                    "passed": true,
                    "errors": []
                }
            }
        }
        """
        try:
            logger.info(f"Processing indexing.completed event: {event_data.get('id')}")
            
            # Extract event data
            data = event_data.get("data", {})
            branch_name = data.get("branch_name")
            indexing_status = data.get("status")
            indexing_mode = data.get("indexing_mode", "traditional")  # Default to traditional
            shadow_index_id = data.get("shadow_index_id")
            
            if not branch_name:
                logger.error(f"Missing branch_name in event: {event_data}")
                return False
            
            # Route to appropriate handler based on indexing mode
            if indexing_mode == "shadow" and shadow_index_id:
                logger.info(f"Processing shadow index completion: {shadow_index_id}")
                success = await self._handle_shadow_indexing_completed(
                    shadow_index_id, branch_name, data, event_data
                )
            else:
                logger.info(f"Processing traditional indexing completion for branch: {branch_name}")
                # Traditional mode - check branch state
                branch_state = await self.lock_manager.get_branch_state(branch_name)
                
                if branch_state.current_state != BranchState.LOCKED_FOR_WRITE:
                    logger.warning(
                        f"Branch {branch_name} is not in LOCKED_FOR_WRITE state. "
                        f"Current state: {branch_state.current_state}"
                    )
                    # Continue processing but log the unexpected state
                
                if indexing_status == "success":
                    success = await self._handle_successful_indexing(
                        branch_name, data, event_data
                    )
                else:
                    success = await self._handle_failed_indexing(
                        branch_name, data, event_data
                    )
                if success:
                    # Check auto-merge conditions
                    await self._check_auto_merge_conditions(branch_name, data)
                return success
                
        except Exception as e:
            logger.error(f"Error handling indexing.completed event: {e}")
            return False
    
    async def _handle_successful_indexing(
        self, 
        branch_name: str, 
        data: Dict[str, Any],
        full_event: Dict[str, Any]
    ) -> bool:
        """
        Handle successful indexing completion
        """
        try:
            # Complete indexing in lock manager (resource-specific or all)
            # Extract which resource types were indexed from event data
            indexed_resource_types = data.get("indexed_resource_types")
            
            success = await self.lock_manager.complete_indexing(
                branch_name=branch_name,
                completed_by="funnel-service",
                resource_types=indexed_resource_types  # None means all indexing locks
            )
            
            if not success:
                logger.error(f"Failed to complete indexing for branch {branch_name}")
                return False
            
            logger.info(
                f"Successfully completed indexing for branch {branch_name}. "
                f"Branch state: LOCKED_FOR_WRITE -> READY"
            )
            
            # Generate audit log
            await self._create_audit_log(
                branch_name=branch_name,
                action=AuditAction.INDEXING_COMPLETED,
                event_data=data,
                success=True
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error handling successful indexing for {branch_name}: {e}")
            return False
    
    async def _handle_failed_indexing(
        self, 
        branch_name: str, 
        data: Dict[str, Any],
        full_event: Dict[str, Any]
    ) -> bool:
        """
        Handle failed indexing
        """
        try:
            # Move branch to ERROR state
            await self.lock_manager.set_branch_state(
                branch_name=branch_name,
                new_state=BranchState.ERROR,
                reason=f"Indexing failed: {data.get('error_message', 'Unknown error')}"
            )
            
            logger.error(
                f"Indexing failed for branch {branch_name}. "
                f"Branch state: LOCKED_FOR_WRITE -> ERROR"
            )
            
            # Generate audit log
            await self._create_audit_log(
                branch_name=branch_name,
                action=AuditAction.INDEXING_FAILED,
                event_data=data,
                success=False
            )
            
            # Send alert for failed indexing
            await self._send_indexing_failure_alert(branch_name, data)
            
            return True
            
        except Exception as e:
            logger.error(f"Error handling failed indexing for {branch_name}: {e}")
            return False
    
    async def _check_auto_merge_conditions(self, branch_name: str, data: Dict[str, Any]):
        """
        Check if auto-merge conditions are met and trigger auto-merge if applicable
        """
        try:
            if not self.auto_merge_config.get("enabled", False):
                logger.debug(f"Auto-merge disabled for branch {branch_name}")
                return
            
            logger.info(f"Checking auto-merge conditions for branch {branch_name}")
            
            # Get current branch state
            branch_state = await self.lock_manager.get_branch_state(branch_name)
            
            if branch_state.current_state != BranchState.READY:
                logger.debug(
                    f"Branch {branch_name} not ready for auto-merge. "
                    f"Current state: {branch_state.current_state}"
                )
                return
            
            # Check validation requirements
            if self.auto_merge_config.get("require_validation", True):
                validation_results = data.get("validation_results", {})
                if not validation_results.get("passed", False):
                    logger.info(
                        f"Auto-merge blocked for {branch_name}: validation failed"
                    )
                    return
            
            # Check for conflicts (simplified check)
            if self.auto_merge_config.get("require_no_conflicts", True):
                conflicts = await self._check_merge_conflicts(branch_name)
                if conflicts:
                    logger.info(
                        f"Auto-merge blocked for {branch_name}: merge conflicts detected"
                    )
                    return
            
            # All conditions met - trigger auto-merge
            logger.info(f"Auto-merge conditions met for branch {branch_name}")
            await self._trigger_auto_merge(branch_name, data)
            
        except Exception as e:
            logger.error(f"Error checking auto-merge conditions for {branch_name}: {e}")
    
    async def _check_merge_conflicts(self, branch_name: str) -> bool:
        """
        Check if there are merge conflicts (simplified implementation)
        In a real system, this would check against the main branch
        """
        # Simplified conflict detection
        # In reality, this would involve comparing schemas, checking for
        # conflicting changes, etc.
        
        # For now, assume no conflicts for non-main branches
        if branch_name == "main":
            return False  # Main branch cannot have conflicts with itself
        
        # TODO: Implement actual conflict detection logic
        # This might involve:
        # - Comparing schema changes
        # - Checking for overlapping modifications
        # - Validating foreign key constraints
        
        return False  # Assume no conflicts for demo
    
    async def _trigger_auto_merge(self, branch_name: str, data: Dict[str, Any]):
        """
        Trigger automatic merge process
        """
        try:
            logger.info(f"Triggering auto-merge for branch {branch_name}")
            
            # Mark branch as ready for merge and transition to ACTIVE
            await self.lock_manager.set_branch_state(
                branch_name=branch_name,
                new_state=BranchState.ACTIVE,
                reason="Auto-merge completed successfully"
            )
            
            # Generate audit log for auto-merge
            await self._create_audit_log(
                branch_name=branch_name,
                action=AuditAction.BRANCH_MERGED,
                event_data={
                    "merge_type": "auto",
                    "trigger": "indexing_completed",
                    "indexing_data": data
                },
                success=True
            )
            
            logger.info(f"Auto-merge completed for branch {branch_name}")
            
            # Send success notification
            await self._send_auto_merge_notification(branch_name, data)
            
        except Exception as e:
            logger.error(f"Error during auto-merge for {branch_name}: {e}")
            # Set branch to ERROR state if auto-merge fails
            await self.lock_manager.set_branch_state(
                branch_name=branch_name,
                new_state=BranchState.ERROR,
                reason=f"Auto-merge failed: {str(e)}"
            )
    
    async def _create_audit_log(
        self,
        branch_name: str,
        action: AuditAction,
        event_data: Dict[str, Any],
        success: bool
    ):
        """
        Create audit log entry for indexing events
        """
        try:
            # Create actor info for system/service
            actor = ActorInfo(
                id="system",
                username="funnel-service",
                service_account=True,
                auth_method="service_account"
            )
            
            # Create target info for branch
            target = TargetInfo(
                resource_type=ResourceType.BRANCH,
                resource_id=branch_name,
                resource_name=branch_name,
                branch=branch_name
            )
            
            # Create audit event
            audit_event = create_audit_event(
                action=action,
                actor=actor,
                target=target,
                success=success,
                metadata={
                    "source_event": "indexing.completed",
                    "records_indexed": event_data.get("records_indexed"),
                    "indexing_duration": self._calculate_duration(
                        event_data.get("started_at"),
                        event_data.get("completed_at")
                    ),
                    "handler": "FunnelIndexingEventHandler",
                    "indexing_data": event_data
                }
            )
            
            # Generate structured audit ID
            audit_id = AuditIDGenerator.generate(
                action=action,
                resource_type=ResourceType.BRANCH,
                resource_id=branch_name,
                timestamp=datetime.now(timezone.utc)
            )
            audit_event.id = audit_id
            
            # TODO: Save to audit database
            logger.info(f"Audit log created: {audit_id} for {action.value} on {branch_name}")
            
        except Exception as e:
            logger.error(f"Failed to create audit log for {branch_name}: {e}")
    
    async def _handle_shadow_indexing_completed(
        self,
        shadow_index_id: str,
        branch_name: str,
        data: Dict[str, Any],
        event_data: Dict[str, Any]
    ) -> bool:
        """
        Handle shadow index completion and optionally trigger automatic switch
        """
        try:
            indexing_status = data.get("status")
            records_indexed = data.get("records_indexed", 0)
            index_size_bytes = data.get("index_size_bytes", 0)
            
            if indexing_status == "success":
                # Mark shadow build as complete
                success = await self.shadow_manager.complete_shadow_build(
                    shadow_index_id=shadow_index_id,
                    index_size_bytes=index_size_bytes,
                    record_count=records_indexed,
                    service_name="funnel-service"
                )
                
                if not success:
                    logger.error(f"Failed to mark shadow build complete: {shadow_index_id}")
                    return False
                
                # Check if auto-switch is enabled
                if self.shadow_index_config.get("auto_switch", False):
                    logger.info(f"Auto-switching shadow index: {shadow_index_id}")
                    
                    # Create switch request
                    switch_request = SwitchRequest(
                        shadow_index_id=shadow_index_id,
                        force_switch=False,
                        validation_checks=self.shadow_index_config.get("validation_checks", []),
                        backup_current=self.shadow_index_config.get("backup_before_switch", True),
                        switch_timeout_seconds=10
                    )
                    
                    # Perform atomic switch
                    switch_result = await self.shadow_manager.request_atomic_switch(
                        shadow_index_id=shadow_index_id,
                        request=switch_request,
                        service_name="funnel-service"
                    )
                    
                    if switch_result.success:
                        logger.info(
                            f"Shadow index auto-switch completed: {shadow_index_id} "
                            f"in {switch_result.switch_duration_ms}ms"
                        )
                        
                        # Create audit log for successful switch
                        await self._create_shadow_audit_log(
                            branch_name, 
                            shadow_index_id, 
                            "SHADOW_INDEX_SWITCHED", 
                            data, 
                            switch_result
                        )
                        
                        # Check auto-merge conditions after successful switch
                        await self._check_auto_merge_conditions(branch_name, data)
                        
                        return True
                    else:
                        logger.error(
                            f"Shadow index auto-switch failed: {shadow_index_id} - {switch_result.message}"
                        )
                        
                        # Create audit log for failed switch
                        await self._create_shadow_audit_log(
                            branch_name, 
                            shadow_index_id, 
                            "SHADOW_INDEX_SWITCH_FAILED", 
                            data, 
                            switch_result
                        )
                        
                        # Don't fail completely - shadow is built and ready for manual switch
                        return True
                else:
                    logger.info(
                        f"Shadow index build completed, ready for manual switch: {shadow_index_id}"
                    )
                    
                    # Create audit log for build completion
                    await self._create_shadow_audit_log(
                        branch_name, 
                        shadow_index_id, 
                        "SHADOW_INDEX_BUILT", 
                        data
                    )
                    
                    return True
            else:
                # Handle shadow build failure
                logger.error(
                    f"Shadow index build failed: {shadow_index_id} - {data.get('error_message', 'Unknown error')}"
                )
                
                # Create audit log for build failure
                await self._create_shadow_audit_log(
                    branch_name, 
                    shadow_index_id, 
                    "SHADOW_INDEX_BUILD_FAILED", 
                    data
                )
                
                # Send alert for shadow build failure
                await self._send_shadow_indexing_failure_alert(shadow_index_id, branch_name, data)
                
                return False
                
        except Exception as e:
            logger.error(f"Error handling shadow indexing completion: {e}")
            return False
    
    async def _create_shadow_audit_log(
        self,
        branch_name: str,
        shadow_index_id: str,
        action_type: str,
        indexing_data: Dict[str, Any],
        switch_result: Optional[Any] = None
    ):
        """
        Create audit log for shadow index operations
        """
        try:
            # Map action types to audit actions
            action_mapping = {
                "SHADOW_INDEX_BUILT": AuditAction.BRANCH_INDEXING_COMPLETED,
                "SHADOW_INDEX_SWITCHED": AuditAction.BRANCH_INDEXING_COMPLETED,
                "SHADOW_INDEX_SWITCH_FAILED": AuditAction.BRANCH_INDEXING_FAILED,
                "SHADOW_INDEX_BUILD_FAILED": AuditAction.BRANCH_INDEXING_FAILED
            }
            
            action = action_mapping.get(action_type, AuditAction.BRANCH_INDEXING_COMPLETED)
            success = "FAILED" not in action_type
            
            # Actor information
            actor = ActorInfo(
                actor_id="funnel-service",
                actor_type="service",
                user_id="system",
                service_name="funnel-service",
                is_service_account=True
            )
            
            # Target information
            target = TargetInfo(
                resource_type=ResourceType.BRANCH,
                resource_id=branch_name,
                resource_name=branch_name,
                branch=branch_name
            )
            
            # Build metadata
            metadata = {
                "source_event": "shadow.indexing.completed",
                "shadow_index_id": shadow_index_id,
                "action_type": action_type,
                "records_indexed": indexing_data.get("records_indexed"),
                "index_size_bytes": indexing_data.get("index_size_bytes"),
                "indexing_duration": self._calculate_duration(
                    indexing_data.get("started_at"),
                    indexing_data.get("completed_at")
                ),
                "handler": "FunnelIndexingEventHandler",
                "indexing_mode": "shadow"
            }
            
            # Add switch result if available
            if switch_result:
                metadata.update({
                    "switch_duration_ms": switch_result.switch_duration_ms,
                    "switch_success": switch_result.success,
                    "validation_passed": switch_result.validation_passed,
                    "verification_passed": switch_result.verification_passed
                })
            
            # Create audit event
            audit_event = create_audit_event(
                action=action,
                actor=actor,
                target=target,
                success=success,
                metadata=metadata
            )
            
            # Generate structured audit ID
            audit_id = AuditIDGenerator.generate(
                action=action,
                resource_type=ResourceType.BRANCH,
                resource_id=branch_name,
                timestamp=datetime.now(timezone.utc)
            )
            audit_event.id = audit_id
            
            # TODO: Save to audit database
            logger.info(f"Shadow index audit log created: {audit_id} for {action_type} on {branch_name}")
            
        except Exception as e:
            logger.error(f"Failed to create shadow index audit log for {branch_name}: {e}")
    
    async def _send_shadow_indexing_failure_alert(
        self,
        shadow_index_id: str,
        branch_name: str,
        data: Dict[str, Any]
    ):
        """
        Send alert for shadow indexing failure
        """
        logger.error(
            f"ALERT: Shadow index build failed for {shadow_index_id} (branch: {branch_name}). "
            f"Error: {data.get('error_message', 'Unknown error')}"
        )
        
        # TODO: Implement actual alerting
        # Could include:
        # - Shadow index ID
        # - Branch name
        # - Build progress when failed
        # - Error details
        # - Suggested remediation steps

    def _calculate_duration(self, started_at: str, completed_at: str) -> Optional[float]:
        """
        Calculate indexing duration in seconds
        """
        try:
            if not started_at or not completed_at:
                return None
            
            start = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
            end = datetime.fromisoformat(completed_at.replace('Z', '+00:00'))
            
            return (end - start).total_seconds()
            
        except Exception as e:
            logger.error(f"Error calculating duration: {e}")
            return None
    
    async def _send_indexing_failure_alert(self, branch_name: str, data: Dict[str, Any]):
        """
        Send alert for indexing failure
        """
        logger.error(
            f"ALERT: Indexing failed for branch {branch_name}. "
            f"Error: {data.get('error_message', 'Unknown error')}"
        )
        
        # TODO: Implement actual alerting (email, Slack, etc.)
        # This could integrate with:
        # - Slack webhooks
        # - Email notifications
        # - PagerDuty alerts
        # - Custom notification service
    
    async def _send_auto_merge_notification(self, branch_name: str, data: Dict[str, Any]):
        """
        Send notification for successful auto-merge
        """
        logger.info(
            f"NOTIFICATION: Auto-merge completed for branch {branch_name}. "
            f"Records indexed: {data.get('records_indexed', 'unknown')}"
        )
        
        # TODO: Implement actual notifications
        # This could send notifications to:
        # - Branch author
        # - Reviewers
        # - Team channels
        # - Integration systems


# Singleton instance
_handler_instance = None

def get_funnel_indexing_handler() -> FunnelIndexingEventHandler:
    """
    Get singleton instance of FunnelIndexingEventHandler
    """
    global _handler_instance
    if _handler_instance is None:
        _handler_instance = FunnelIndexingEventHandler()
    return _handler_instance
