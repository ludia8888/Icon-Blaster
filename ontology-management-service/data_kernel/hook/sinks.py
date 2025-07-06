"""
Event sink implementations for commit hook pipeline
"""
import os
import json
import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime

from .base import BaseSink, DiffContext

# Import existing event publishers
from core.event_publisher.unified_publisher import UnifiedPublisher
from core.event_publisher.nats_backend import NATSBackend
from shared.audit_client import get_audit_client, AuditEvent

logger = logging.getLogger(__name__)


class NATSSink(BaseSink):
    """Publish events to NATS"""
    
    def __init__(self):
        self.publisher = None
        self.topic_prefix = os.getenv("NATS_TOPIC_PREFIX", "terminus.commit")
    
    @property
    def name(self) -> str:
        return "NATSSink"
    
    @property
    def enabled(self) -> bool:
        return os.getenv("ENABLE_NATS_EVENTS", "true").lower() == "true"
    
    async def initialize(self):
        """Initialize NATS connection"""
        try:
            # TODO: Fix UnifiedPublisher initialization
            # For now, we'll create a basic NATS backend
            self.publisher = NATSBackend(
                url=os.getenv("NATS_URL", "nats://localhost:4222")
            )
            await self.publisher.connect()
            logger.info("NATS sink initialized")
        except Exception as e:
            logger.error(f"Failed to initialize NATS sink: {e}")
            self.publisher = None
    
    async def publish(self, context: DiffContext) -> None:
        """Publish commit event to NATS"""
        if not self.publisher:
            logger.warning("NATS publisher not initialized, skipping event")
            return
        
        try:
            # Build event payload
            event = {
                "type": "commit",
                "database": context.meta.database,
                "branch": context.meta.branch,
                "commit_id": context.meta.commit_id,
                "author": context.meta.author,
                "message": context.meta.commit_msg,
                "trace_id": context.meta.trace_id,
                "timestamp": datetime.utcnow().isoformat(),
                "diff": context.diff,
                "affected_types": context.affected_types or [],
                "affected_ids": context.affected_ids or []
            }
            
            # Determine topic based on branch
            env, service, purpose = context.meta.branch.split("/", 2)
            topic = f"{self.topic_prefix}.{env}.{service}"
            
            # Publish with headers
            headers = {
                "trace-id": context.meta.trace_id,
                "author": context.meta.author,
                "branch": context.meta.branch
            }
            
            await self.publisher.publish(
                topic=topic,
                message=event,
                headers=headers
            )
            
            logger.debug(f"Published commit event to {topic}")
            
        except Exception as e:
            logger.error(f"Failed to publish to NATS: {e}")
            # Don't raise - sinks should not fail commits


class AuditSink(BaseSink):
    """Record audit events for commits"""
    
    def __init__(self):
        self.audit_db = os.getenv("AUDIT_DATABASE", "audit_logs.db")
    
    @property
    def name(self) -> str:
        return "AuditSink"
    
    @property
    def enabled(self) -> bool:
        return os.getenv("ENABLE_AUDIT", "true").lower() == "true"
    
    async def publish(self, context: DiffContext) -> None:
        """Record audit event"""
        try:
            # Map commit operation to audit action
            action = "WRITE"
            if context.before and not context.after:
                action = "DELETE"
            elif not context.before and context.after:
                action = "CREATE"
            elif context.before and context.after:
                action = "UPDATE"
            
            # Build audit event using new audit client
            author_parts = context.meta.author.split("@")
            user_id = author_parts[0]
            username = author_parts[0] if len(author_parts) == 1 else f"{author_parts[0]}@{author_parts[1]}"
            
            audit_event = AuditEvent(
                event_type="DATA_COMMIT",
                event_category="DATA_MANAGEMENT",
                user_id=user_id,
                username=username,
                target_type="DOCUMENT",
                target_id=context.meta.commit_id or "unknown",
                operation=action,
                severity="INFO",
                branch=context.meta.branch,
                commit_id=context.meta.commit_id,
                terminus_db=context.meta.database,
                request_id=context.meta.trace_id,
                metadata={
                    "commit_message": context.meta.commit_msg,
                    "affected_types": context.affected_types,
                    "affected_ids": context.affected_ids,
                    "source": "data_kernel_hook"
                }
            )
            
            # Use audit service client
            client = await get_audit_client()
            await client.record_event(audit_event)
            
            logger.debug(f"Recorded audit event for {action} by {context.meta.author}")
            
        except Exception as e:
            logger.error(f"Failed to record audit event: {e}")


class WebhookSink(BaseSink):
    """Send webhooks for commits"""
    
    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or os.getenv("COMMIT_WEBHOOK_URL")
        self.timeout = int(os.getenv("WEBHOOK_TIMEOUT", "5"))
    
    @property
    def name(self) -> str:
        return "WebhookSink"
    
    @property
    def enabled(self) -> bool:
        return bool(self.webhook_url)
    
    async def publish(self, context: DiffContext) -> None:
        """Send webhook notification"""
        if not self.webhook_url:
            return
        
        try:
            import httpx
            
            payload = {
                "event": "terminus.commit",
                "database": context.meta.database,
                "branch": context.meta.branch,
                "commit": {
                    "id": context.meta.commit_id,
                    "author": context.meta.author,
                    "message": context.meta.commit_msg,
                    "timestamp": datetime.utcnow().isoformat()
                },
                "summary": {
                    "affected_types": context.affected_types or [],
                    "affected_ids": context.affected_ids or [],
                    "changes": len(context.diff) if isinstance(context.diff, dict) else 0
                }
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                    headers={
                        "X-Trace-ID": context.meta.trace_id,
                        "X-Event-Type": "terminus.commit"
                    },
                    timeout=self.timeout
                )
                
                if response.status_code >= 400:
                    logger.warning(f"Webhook returned {response.status_code}")
                else:
                    logger.debug(f"Webhook sent successfully to {self.webhook_url}")
                    
        except asyncio.TimeoutError:
            logger.warning(f"Webhook timeout after {self.timeout}s")
        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")


class MetricsSink(BaseSink):
    """Record metrics for commits"""
    
    def __init__(self):
        self.metrics_enabled = os.getenv("ENABLE_METRICS", "true").lower() == "true"
    
    @property
    def name(self) -> str:
        return "MetricsSink"
    
    @property
    def enabled(self) -> bool:
        return self.metrics_enabled
    
    async def publish(self, context: DiffContext) -> None:
        """Record commit metrics"""
        try:
            from prometheus_client import Counter, Histogram
            
            # Define metrics
            commit_counter = Counter(
                'terminus_commits_total',
                'Total number of commits',
                ['database', 'branch', 'author']
            )
            
            commit_size = Histogram(
                'terminus_commit_size_bytes',
                'Size of commit diffs in bytes',
                ['database', 'branch']
            )
            
            # Record metrics
            env, service, _ = context.meta.branch.split("/", 2)
            
            commit_counter.labels(
                database=context.meta.database or "unknown",
                branch=f"{env}/{service}",
                author=context.meta.author.split("@")[1] if "@" in context.meta.author else "unknown"
            ).inc()
            
            # Estimate diff size
            diff_size = len(json.dumps(context.diff))
            commit_size.labels(
                database=context.meta.database or "unknown",
                branch=f"{env}/{service}"
            ).observe(diff_size)
            
            logger.debug(f"Recorded metrics for commit {context.meta.commit_id}")
            
        except Exception as e:
            logger.error(f"Failed to record metrics: {e}")