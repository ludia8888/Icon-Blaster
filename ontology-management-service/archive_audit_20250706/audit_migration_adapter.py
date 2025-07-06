"""
Audit Migration Adapter
Provides compatibility layer to migrate from SQLite/PostgreSQL audit to TerminusDB

This adapter allows gradual migration by:
1. Reading from both old and new audit systems
2. Writing to both during transition period
3. Eventually deprecating the old system
"""

from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple

from models.audit_events import AuditEventV1, AuditEventFilter, AuditAction, ResourceType
from .audit_database import AuditDatabase
from .terminusdb_audit_service import TerminusAuditService
from database.clients.unified_database_client import UnifiedDatabaseClient
from utils.logger import get_logger

logger = get_logger(__name__)


class AuditMigrationAdapter:
    """
    Adapter that provides unified interface while migrating from
    SQLite/PostgreSQL audit to TerminusDB-based audit
    """
    
    def __init__(
        self,
        legacy_audit: Optional[AuditDatabase] = None,
        terminus_audit: Optional[TerminusAuditService] = None,
        unified_client: Optional[UnifiedDatabaseClient] = None,
        migration_mode: str = "dual_write"  # dual_write, read_legacy, read_terminus, terminus_only
    ):
        self.legacy_audit = legacy_audit
        self.terminus_audit = terminus_audit
        self.unified_client = unified_client
        self.migration_mode = migration_mode
        
        # Statistics for monitoring migration
        self.stats = {
            "legacy_writes": 0,
            "terminus_writes": 0,
            "legacy_reads": 0,
            "terminus_reads": 0,
            "migration_errors": 0
        }
    
    async def initialize(self):
        """Initialize both audit systems"""
        if self.legacy_audit and self.migration_mode in ["dual_write", "read_legacy"]:
            await self.legacy_audit.initialize()
            logger.info("Legacy audit system initialized")
        
        if self.unified_client and self.migration_mode in ["dual_write", "read_terminus", "terminus_only"]:
            await self.unified_client.connect()
            if not self.terminus_audit:
                self.terminus_audit = TerminusAuditService(self.unified_client._terminus_client)
            logger.info("TerminusDB audit system initialized")
    
    async def store_audit_event(self, event: AuditEventV1) -> bool:
        """
        Store audit event based on migration mode
        
        - dual_write: Write to both systems
        - terminus_only: Write only to TerminusDB
        """
        success = True
        
        # Write to legacy system
        if self.legacy_audit and self.migration_mode in ["dual_write", "read_legacy"]:
            try:
                legacy_success = await self.legacy_audit.store_audit_event(event)
                if legacy_success:
                    self.stats["legacy_writes"] += 1
                else:
                    success = False
            except Exception as e:
                logger.error(f"Failed to write to legacy audit: {e}")
                self.stats["migration_errors"] += 1
                if self.migration_mode != "dual_write":
                    success = False
        
        # Write to TerminusDB
        if self.terminus_audit and self.migration_mode in ["dual_write", "read_terminus", "terminus_only"]:
            try:
                # Convert AuditEventV1 to TerminusDB format
                commit_id = await self.terminus_audit.log_operation(
                    action=event.action,
                    resource_type=event.target.resource_type,
                    resource_id=event.target.resource_id,
                    author=f"{event.actor.username} ({event.actor.id})",
                    changes=event.changes.dict() if event.changes else None,
                    metadata={
                        "actor_id": event.actor.id,
                        "actor_ip": event.actor.ip_address,
                        "actor_user_agent": event.actor.user_agent,
                        "success": event.success,
                        "error_code": event.error_code,
                        "error_message": event.error_message,
                        "duration_ms": event.duration_ms,
                        "request_id": event.request_id,
                        "correlation_id": event.correlation_id,
                        "branch": event.target.branch,
                        "tags": event.tags,
                        "compliance": event.compliance.dict() if event.compliance else None
                    }
                )
                
                if commit_id:
                    self.stats["terminus_writes"] += 1
                    logger.debug(f"Audit event stored in TerminusDB: {commit_id}")
                else:
                    success = False
                    
            except Exception as e:
                logger.error(f"Failed to write to TerminusDB audit: {e}")
                self.stats["migration_errors"] += 1
                if self.migration_mode == "terminus_only":
                    success = False
        
        return success
    
    async def query_audit_events(
        self,
        filter_criteria: AuditEventFilter
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Query audit events based on migration mode
        
        - dual_write/read_legacy: Read from legacy
        - read_terminus/terminus_only: Read from TerminusDB
        """
        if self.migration_mode in ["dual_write", "read_legacy"] and self.legacy_audit:
            self.stats["legacy_reads"] += 1
            return await self.legacy_audit.query_audit_events(filter_criteria)
            
        elif self.terminus_audit:
            self.stats["terminus_reads"] += 1
            
            # Query from TerminusDB
            events, total = await self.terminus_audit.query_audit_log(filter_criteria)
            
            # Convert to legacy format for compatibility
            converted_events = []
            for event in events:
                converted = self._convert_terminus_to_legacy_format(event)
                converted_events.append(converted)
            
            return converted_events, total
        
        return [], 0
    
    async def get_audit_event_by_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get specific audit event by ID"""
        if self.migration_mode in ["dual_write", "read_legacy"] and self.legacy_audit:
            return await self.legacy_audit.get_audit_event_by_id(event_id)
        
        elif self.terminus_audit:
            # In TerminusDB, event_id is commit hash
            commits = await self.terminus_audit.client.get_commit_history()
            
            for commit in commits:
                if commit["identifier"] == event_id:
                    entry = self.terminus_audit._parse_commit_as_audit_entry(commit)
                    if entry:
                        return self._convert_terminus_to_legacy_format(entry)
            
        return None
    
    async def get_audit_statistics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get audit statistics"""
        if self.migration_mode in ["dual_write", "read_legacy"] and self.legacy_audit:
            return await self.legacy_audit.get_audit_statistics(start_time, end_time)
        
        elif self.terminus_audit:
            # Get from TerminusDB
            stats = await self.terminus_audit.get_change_statistics(start_time, end_time)
            
            # Add migration statistics
            stats["migration_stats"] = self.stats
            
            return stats
        
        return {}
    
    async def migrate_historical_data(
        self,
        start_date: Optional[datetime] = None,
        batch_size: int = 100
    ) -> Dict[str, Any]:
        """
        One-time migration of historical audit data from legacy to TerminusDB
        
        This should be run during migration to backfill TerminusDB with
        historical audit data
        """
        if not self.legacy_audit or not self.terminus_audit:
            return {"error": "Both audit systems must be configured for migration"}
        
        migration_result = {
            "total_migrated": 0,
            "failed": 0,
            "start_time": datetime.now(),
            "errors": []
        }
        
        try:
            # Build filter for historical data
            filter_criteria = AuditEventFilter(
                start_time=start_date,
                limit=batch_size,
                offset=0
            )
            
            while True:
                # Get batch from legacy system
                events, total = await self.legacy_audit.query_audit_events(filter_criteria)
                
                if not events:
                    break
                
                # Migrate each event
                for event_dict in events:
                    try:
                        # Reconstruct AuditEventV1 from dict
                        # (simplified - would need proper reconstruction in production)
                        await self.terminus_audit.log_operation(
                            action=AuditAction(event_dict["action"]),
                            resource_type=ResourceType(event_dict["target_resource_type"]),
                            resource_id=event_dict["target_resource_id"],
                            author=event_dict["actor_username"],
                            changes=event_dict.get("changes"),
                            metadata={
                                "migrated_from": "legacy",
                                "original_id": event_dict["id"],
                                "original_timestamp": event_dict["created_at"],
                                **event_dict.get("metadata", {})
                            }
                        )
                        
                        migration_result["total_migrated"] += 1
                        
                    except Exception as e:
                        migration_result["failed"] += 1
                        migration_result["errors"].append({
                            "event_id": event_dict["id"],
                            "error": str(e)
                        })
                
                # Next batch
                filter_criteria.offset += batch_size
                
                # Log progress
                if migration_result["total_migrated"] % 1000 == 0:
                    logger.info(f"Migrated {migration_result['total_migrated']} audit events")
            
            migration_result["end_time"] = datetime.now()
            migration_result["duration"] = (
                migration_result["end_time"] - migration_result["start_time"]
            ).total_seconds()
            
            logger.info(
                f"Audit migration completed: {migration_result['total_migrated']} events migrated, "
                f"{migration_result['failed']} failed"
            )
            
            return migration_result
            
        except Exception as e:
            logger.error(f"Audit migration failed: {e}")
            migration_result["error"] = str(e)
            return migration_result
    
    async def verify_migration_consistency(
        self,
        sample_size: int = 100
    ) -> Dict[str, Any]:
        """
        Verify consistency between legacy and TerminusDB audit data
        
        Useful during dual_write mode to ensure both systems have same data
        """
        if not self.legacy_audit or not self.terminus_audit:
            return {"error": "Both audit systems required for verification"}
        
        verification_result = {
            "consistent": True,
            "checked": 0,
            "mismatches": []
        }
        
        try:
            # Get sample from legacy
            legacy_events, _ = await self.legacy_audit.query_audit_events(
                AuditEventFilter(limit=sample_size)
            )
            
            for legacy_event in legacy_events:
                verification_result["checked"] += 1
                
                # Try to find corresponding event in TerminusDB
                # This is simplified - in practice would need better matching
                terminus_events, _ = await self.terminus_audit.query_audit_log(
                    AuditEventFilter(
                        resource_ids=[legacy_event["target_resource_id"]],
                        limit=10
                    )
                )
                
                found = False
                for terminus_event in terminus_events:
                    if self._events_match(legacy_event, terminus_event):
                        found = True
                        break
                
                if not found:
                    verification_result["consistent"] = False
                    verification_result["mismatches"].append({
                        "legacy_id": legacy_event["id"],
                        "resource": f"{legacy_event['target_resource_type']}/{legacy_event['target_resource_id']}",
                        "action": legacy_event["action"]
                    })
            
            return verification_result
            
        except Exception as e:
            logger.error(f"Migration verification failed: {e}")
            return {"error": str(e)}
    
    def _convert_terminus_to_legacy_format(self, terminus_event: Dict[str, Any]) -> Dict[str, Any]:
        """Convert TerminusDB audit entry to legacy format"""
        # Extract metadata if present
        metadata = terminus_event.get("metadata", {})
        
        return {
            "id": terminus_event["id"],
            "created_at": terminus_event["timestamp"],
            "action": terminus_event.get("action", "unknown"),
            "actor_id": metadata.get("actor_id", "unknown"),
            "actor_username": terminus_event.get("author", "unknown"),
            "actor_is_service": False,  # Would need to determine from metadata
            "target_resource_type": terminus_event.get("resource_type", "unknown"),
            "target_resource_id": terminus_event.get("resource_id", "unknown"),
            "target_resource_name": None,
            "target_branch": metadata.get("branch"),
            "success": metadata.get("success", True),
            "error_code": metadata.get("error_code"),
            "error_message": metadata.get("error_message"),
            "duration_ms": metadata.get("duration_ms"),
            "request_id": metadata.get("request_id"),
            "correlation_id": metadata.get("correlation_id"),
            "causation_id": None,
            "ip_address": metadata.get("actor_ip"),
            "user_agent": metadata.get("actor_user_agent"),
            "changes": terminus_event.get("changes"),
            "metadata": metadata,
            "tags": metadata.get("tags"),
            "compliance": metadata.get("compliance")
        }
    
    def _events_match(self, legacy: Dict[str, Any], terminus: Dict[str, Any]) -> bool:
        """Check if two events represent the same audit entry"""
        # Simple matching - could be more sophisticated
        return (
            legacy["target_resource_id"] == terminus.get("resource_id") and
            legacy["action"] == terminus.get("action") and
            legacy["actor_username"] in terminus.get("author", "")
        )
    
    def get_migration_status(self) -> Dict[str, Any]:
        """Get current migration status and statistics"""
        return {
            "mode": self.migration_mode,
            "statistics": self.stats,
            "legacy_available": self.legacy_audit is not None,
            "terminus_available": self.terminus_audit is not None
        }
    
    async def close(self):
        """Close all connections"""
        if self.legacy_audit:
            await self.legacy_audit.close()
        
        if self.unified_client:
            await self.unified_client.close()