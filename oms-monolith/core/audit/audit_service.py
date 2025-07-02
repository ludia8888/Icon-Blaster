"""
Audit Service
High-level service for audit log management with enterprise features
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from contextlib import asynccontextmanager

from models.audit_events import AuditEventV1, AuditEventFilter, AuditAction, ResourceType
from core.audit.audit_database import get_audit_database, AuditDatabase
from core.events.unified_publisher import UnifiedEventPublisher, PublisherBackend, PublisherConfig
from utils.logger import get_logger

logger = get_logger(__name__)


class AuditServiceError(Exception):
    """Base exception for audit service operations"""
    pass


class AuditService:
    """
    Enterprise Audit Service
    
    Features:
    - Dual-write to database and event stream
    - Background batch processing for performance
    - Compliance and retention management
    - Real-time monitoring and alerting
    - GDPR compliance support
    """
    
    def __init__(self):
        self.database: Optional[AuditDatabase] = None
        self.publisher = None
        self._batch_queue: List[AuditEventV1] = []
        self._batch_lock = asyncio.Lock()
        self._background_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # Configuration
        self.batch_size = 50
        self.batch_timeout_seconds = 10.0
        self.max_queue_size = 1000
        self.enable_realtime_alerts = True
        
        # Statistics
        self.stats = {
            "events_processed": 0,
            "events_failed": 0,
            "batches_processed": 0,
            "last_batch_time": None,
            "queue_size": 0
        }
    
    async def initialize(self):
        """Initialize audit service components"""
        try:
            # Initialize database
            self.database = await get_audit_database()
            
            # Initialize publisher with audit backend
            config = PublisherConfig(
                backend=PublisherBackend.AUDIT,
                enable_dual_write=True,
                audit_db_client=self.database,
                enable_metrics=True
            )
            self.publisher = UnifiedEventPublisher(config)
            
            # Start background batch processor
            self._background_task = asyncio.create_task(self._batch_processor())
            
            logger.info("Audit service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize audit service: {e}")
            raise AuditServiceError(f"Initialization failed: {e}")
    
    async def shutdown(self):
        """Gracefully shutdown audit service"""
        logger.info("Shutting down audit service...")
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Wait for background task to complete
        if self._background_task:
            try:
                await asyncio.wait_for(self._background_task, timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning("Background task didn't complete within timeout, cancelling")
                self._background_task.cancel()
        
        # Process remaining events in queue
        if self._batch_queue:
            await self._process_batch(self._batch_queue.copy())
            self._batch_queue.clear()
        
        logger.info("Audit service shutdown complete")
    
    async def log_audit_event(self, event: AuditEventV1, immediate: bool = False) -> bool:
        """
        Log an audit event
        
        Args:
            event: Audit event to log
            immediate: If True, bypass batching and store immediately
            
        Returns:
            True if event was queued/stored successfully
        """
        try:
            if immediate:
                # Store immediately for critical events
                success = await self._store_event_immediate(event)
                if success:
                    self.stats["events_processed"] += 1
                else:
                    self.stats["events_failed"] += 1
                return success
            else:
                # Add to batch queue
                async with self._batch_lock:
                    if len(self._batch_queue) >= self.max_queue_size:
                        logger.warning(f"Audit queue full ({self.max_queue_size}), dropping event")
                        self.stats["events_failed"] += 1
                        return False
                    
                    self._batch_queue.append(event)
                    self.stats["queue_size"] = len(self._batch_queue)
                    
                    # Trigger immediate processing if batch is full
                    if len(self._batch_queue) >= self.batch_size:
                        await self._trigger_batch_processing()
                
                return True
                
        except Exception as e:
            logger.error(f"Failed to log audit event {event.id}: {e}")
            self.stats["events_failed"] += 1
            return False
    
    async def query_audit_events(
        self, 
        filter_criteria: AuditEventFilter
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query audit events with filtering and pagination"""
        if not self.database:
            raise AuditServiceError("Audit database not initialized")
        
        return await self.database.query_audit_events(filter_criteria)
    
    async def get_audit_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get specific audit event by ID"""
        if not self.database:
            raise AuditServiceError("Audit database not initialized")
        
        return await self.database.get_audit_event_by_id(event_id)
    
    async def get_audit_statistics(
        self, 
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get audit statistics for monitoring"""
        if not self.database:
            raise AuditServiceError("Audit database not initialized")
        
        db_stats = await self.database.get_audit_statistics(start_time, end_time)
        
        # Combine with service stats
        combined_stats = {
            **db_stats,
            "service_stats": self.stats.copy(),
            "queue_health": {
                "current_queue_size": len(self._batch_queue),
                "max_queue_size": self.max_queue_size,
                "queue_utilization": len(self._batch_queue) / self.max_queue_size,
                "background_task_running": self._background_task and not self._background_task.done()
            }
        }
        
        return combined_stats
    
    async def cleanup_expired_events(self) -> int:
        """Clean up expired audit events"""
        if not self.database:
            raise AuditServiceError("Audit database not initialized")
        
        return await self.database.cleanup_expired_events()
    
    async def verify_integrity(self) -> Dict[str, Any]:
        """Verify audit log integrity"""
        if not self.database:
            raise AuditServiceError("Audit database not initialized")
        
        return await self.database.verify_integrity()
    
    async def export_audit_logs(
        self, 
        filter_criteria: AuditEventFilter,
        format: str = "json"
    ) -> str:
        """Export audit logs for compliance purposes"""
        events, total_count = await self.query_audit_events(filter_criteria)
        
        if format.lower() == "json":
            import json
            return json.dumps({
                "export_metadata": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "total_events": total_count,
                    "filter_criteria": filter_criteria.dict(),
                    "format": format
                },
                "events": events
            }, indent=2)
        else:
            raise AuditServiceError(f"Unsupported export format: {format}")
    
    async def get_compliance_report(
        self, 
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """Generate compliance report for auditors"""
        filter_criteria = AuditEventFilter(
            start_time=start_date,
            end_time=end_date,
            limit=1000  # Get all events in date range
        )
        
        events, total_count = await self.query_audit_events(filter_criteria)
        
        # Analyze compliance metrics
        privileged_actions = [
            AuditAction.ACL_CREATE, AuditAction.ACL_UPDATE, AuditAction.ACL_DELETE,
            AuditAction.SCHEMA_DELETE, AuditAction.AUTH_LOGIN, AuditAction.AUTH_FAILED
        ]
        
        privileged_events = [e for e in events if e['action'] in [a.value for a in privileged_actions]]
        failed_events = [e for e in events if not e['success']]
        
        # Calculate retention compliance
        retention_stats = {}
        for action in AuditAction:
            action_events = [e for e in events if e['action'] == action.value]
            if action_events:
                retention_days = self.database.retention_policy.get_retention_days(action)
                retention_stats[action.value] = {
                    "event_count": len(action_events),
                    "retention_days": retention_days,
                    "oldest_event": min(e['created_at'] for e in action_events),
                    "newest_event": max(e['created_at'] for e in action_events)
                }
        
        return {
            "report_period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "duration_days": (end_date - start_date).days
            },
            "summary": {
                "total_events": total_count,
                "privileged_actions": len(privileged_events),
                "failed_actions": len(failed_events),
                "unique_actors": len(set(e['actor_id'] for e in events)),
                "unique_resources": len(set(f"{e['target_resource_type']}:{e['target_resource_id']}" for e in events))
            },
            "compliance_metrics": {
                "privileged_action_rate": len(privileged_events) / max(total_count, 1),
                "failure_rate": len(failed_events) / max(total_count, 1),
                "retention_policy_compliance": retention_stats
            },
            "security_highlights": {
                "privileged_events": privileged_events[:10],  # Top 10 for review
                "failed_events": failed_events[:10],  # Top 10 failures
                "top_actors_by_activity": self._get_top_actors(events, 5)
            }
        }
    
    # Private methods
    
    async def _store_event_immediate(self, event: AuditEventV1) -> bool:
        """Store event immediately to database and publish"""
        try:
            # Store in database
            db_success = await self.database.store_audit_event(event)
            
            # Publish to event stream (best effort)
            try:
                if self.publisher:
                    await self.publisher.publish_audit_event_direct(event)
            except Exception as e:
                logger.warning(f"Failed to publish audit event to stream: {e}")
            
            # Check for critical events that need alerts
            if self.enable_realtime_alerts:
                await self._check_for_alerts(event)
            
            return db_success
            
        except Exception as e:
            logger.error(f"Failed to store audit event immediately: {e}")
            return False
    
    async def _batch_processor(self):
        """Background task to process batched audit events"""
        logger.info("Starting audit batch processor")
        
        while not self._shutdown_event.is_set():
            try:
                # Wait for timeout or shutdown signal
                await asyncio.wait_for(
                    self._shutdown_event.wait(), 
                    timeout=self.batch_timeout_seconds
                )
                # If we get here, shutdown was signaled
                break
                
            except asyncio.TimeoutError:
                # Timeout reached, process current batch
                await self._trigger_batch_processing()
            
            except Exception as e:
                logger.error(f"Error in batch processor: {e}")
                await asyncio.sleep(1.0)  # Brief pause on error
        
        logger.info("Audit batch processor stopped")
    
    async def _trigger_batch_processing(self):
        """Process current batch of events"""
        async with self._batch_lock:
            if not self._batch_queue:
                return
            
            batch = self._batch_queue.copy()
            self._batch_queue.clear()
            self.stats["queue_size"] = 0
        
        await self._process_batch(batch)
    
    async def _process_batch(self, batch: List[AuditEventV1]):
        """Process a batch of audit events"""
        if not batch:
            return
        
        try:
            # Store batch in database
            stored_count = await self.database.store_audit_events_batch(batch)
            
            # Publish events to stream (best effort)
            if self.publisher:
                for event in batch:
                    try:
                        await self.publisher.publish_audit_event_direct(event)
                    except Exception as e:
                        logger.warning(f"Failed to publish audit event {event.id}: {e}")
            
            # Check for alerts in batch
            if self.enable_realtime_alerts:
                for event in batch:
                    await self._check_for_alerts(event)
            
            # Update statistics
            self.stats["events_processed"] += stored_count
            self.stats["events_failed"] += len(batch) - stored_count
            self.stats["batches_processed"] += 1
            self.stats["last_batch_time"] = datetime.now(timezone.utc).isoformat()
            
            logger.debug(f"Processed batch of {len(batch)} events, {stored_count} stored successfully")
            
        except Exception as e:
            logger.error(f"Failed to process audit batch: {e}")
            self.stats["events_failed"] += len(batch)
    
    async def _check_for_alerts(self, event: AuditEventV1):
        """Check if event should trigger real-time alerts"""
        # Critical security events
        if event.action in [
            AuditAction.AUTH_FAILED, 
            AuditAction.ACL_DELETE,
            AuditAction.SCHEMA_DELETE
        ]:
            await self._send_security_alert(event)
        
        # Multiple failures from same actor
        if not event.success:
            await self._check_failure_patterns(event)
    
    async def _send_security_alert(self, event: AuditEventV1):
        """Send security alert for critical events"""
        logger.warning(
            f"SECURITY ALERT: {event.action.value} by {event.actor.username} "
            f"on {event.target.resource_type.value}:{event.target.resource_id} "
            f"Success: {event.success}"
        )
        
        # TODO: Integrate with alerting system (Slack, email, PagerDuty, etc.)
    
    async def _check_failure_patterns(self, event: AuditEventV1):
        """Check for suspicious failure patterns"""
        # Count recent failures from this actor
        recent_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        filter_criteria = AuditEventFilter(
            start_time=recent_time,
            actor_ids=[event.actor.id],
            success=False,
            limit=10
        )
        
        failed_events, _ = await self.query_audit_events(filter_criteria)
        
        if len(failed_events) >= 5:  # 5 failures in 5 minutes
            logger.warning(
                f"SUSPICIOUS ACTIVITY: {len(failed_events)} failures from {event.actor.username} "
                f"in last 5 minutes"
            )
            # TODO: Implement automatic response (rate limiting, account suspension, etc.)
    
    def _get_top_actors(self, events: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        """Get top actors by activity count"""
        actor_counts = {}
        for event in events:
            actor_id = event['actor_id']
            username = event['actor_username']
            if actor_id not in actor_counts:
                actor_counts[actor_id] = {"username": username, "count": 0}
            actor_counts[actor_id]["count"] += 1
        
        sorted_actors = sorted(
            actor_counts.items(), 
            key=lambda x: x[1]["count"], 
            reverse=True
        )
        
        return [
            {
                "actor_id": actor_id,
                "username": data["username"],
                "event_count": data["count"]
            }
            for actor_id, data in sorted_actors[:limit]
        ]


# Global audit service instance
_audit_service: Optional[AuditService] = None


async def get_audit_service() -> AuditService:
    """Get global audit service instance"""
    global _audit_service
    if _audit_service is None:
        _audit_service = AuditService()
        await _audit_service.initialize()
    return _audit_service


@asynccontextmanager
async def audit_service_context():
    """Context manager for audit service lifecycle"""
    service = await get_audit_service()
    try:
        yield service
    finally:
        await service.shutdown()