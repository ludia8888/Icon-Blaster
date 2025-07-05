"""
OutboxService - Transactional Outbox Pattern Implementation
Provides guaranteed event delivery for MSA communication between OMS and Audit Service
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
from uuid import uuid4
from enum import Enum

from database.clients.terminus_db import TerminusDBClient
from shared.infrastructure.nats_client import NATSClient
from .cloudevents_enhanced import EnhancedCloudEvent
from .outbox_processor import OutboxProcessor
from utils.logger import get_logger

logger = get_logger(__name__)


class OutboxEventStatus(str, Enum):
    """Outbox event status enum"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class OutboxEvent:
    """Outbox event model for TerminusDB storage"""
    
    def __init__(
        self,
        event_id: str,
        event_type: str,
        source: str,
        subject: str,
        data: Dict[str, Any],
        correlation_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        status: OutboxEventStatus = OutboxEventStatus.PENDING,
        retry_count: int = 0,
        max_retries: int = 3,
        created_at: Optional[datetime] = None
    ):
        self.event_id = event_id
        self.event_type = event_type
        self.source = source
        self.subject = subject
        self.data = data
        self.correlation_id = correlation_id
        self.idempotency_key = idempotency_key or self._generate_idempotency_key()
        self.metadata = metadata or {}
        self.status = status
        self.retry_count = retry_count
        self.max_retries = max_retries
        self.created_at = created_at or datetime.now(timezone.utc)
        self.processed_at: Optional[datetime] = None
        self.error_message: Optional[str] = None
    
    def _generate_idempotency_key(self) -> str:
        """Generate idempotency key from event data"""
        import hashlib
        data_str = f"{self.event_type}:{self.source}:{self.subject}:{json.dumps(self.data, sort_keys=True)}"
        return hashlib.sha256(data_str.encode()).hexdigest()[:32]
    
    def to_cloudevent(self) -> EnhancedCloudEvent:
        """Convert to CloudEvent for publishing"""
        return EnhancedCloudEvent(
            id=self.event_id,
            type=self.event_type,
            source=self.source,
            subject=self.subject,
            data=self.data,
            time=self.created_at.isoformat(),
            **self.metadata
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for TerminusDB storage"""
        return {
            "@type": "OutboxEvent",
            "@id": self.event_id,
            "event_type": self.event_type,
            "source": self.source,
            "subject": self.subject,
            "data": json.dumps(self.data),
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
            "metadata": json.dumps(self.metadata),
            "status": self.status.value,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "created_at": self.created_at.isoformat(),
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "error_message": self.error_message
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OutboxEvent":
        """Create from TerminusDB document"""
        event = cls(
            event_id=data["@id"],
            event_type=data["event_type"],
            source=data["source"],
            subject=data["subject"],
            data=json.loads(data["data"]),
            correlation_id=data.get("correlation_id"),
            idempotency_key=data["idempotency_key"],
            metadata=json.loads(data.get("metadata", "{}")),
            status=OutboxEventStatus(data["status"]),
            retry_count=data["retry_count"],
            max_retries=data["max_retries"],
            created_at=datetime.fromisoformat(data["created_at"])
        )
        
        if data.get("processed_at"):
            event.processed_at = datetime.fromisoformat(data["processed_at"])
        
        event.error_message = data.get("error_message")
        return event


class OutboxService:
    """
    Transactional Outbox Pattern Implementation
    
    Ensures guaranteed event delivery by:
    1. Storing events in TerminusDB within the same transaction as business data
    2. Processing events asynchronously with retry and dead letter handling
    3. Providing exactly-once delivery semantics via idempotency keys
    """
    
    def __init__(
        self,
        db_client: TerminusDBClient,
        nats_client: Optional[NATSClient] = None,
        database: str = "_outbox",
        batch_size: int = 100,
        process_interval: float = 1.0
    ):
        self.db_client = db_client
        self.nats_client = nats_client
        self.database = database
        self.batch_size = batch_size
        self.process_interval = process_interval
        
        # Use the existing OutboxProcessor for actual event publishing
        self.processor = None
        if nats_client:
            from shared.infrastructure.metrics import MetricsCollector
            metrics = MetricsCollector()
            self.processor = OutboxProcessor(
                tdb_client=db_client,
                nats_client=nats_client,
                metrics=metrics,
                enable_multi_platform=True
            )
        
        # Processing control
        self._processing_task: Optional[asyncio.Task] = None
        self._is_running = False
        
        logger.info("OutboxService initialized with TerminusDB transactional guarantees")
    
    async def initialize(self) -> bool:
        """Initialize outbox database and schema"""
        try:
            # Create outbox database
            await self.db_client.create_database(self.database)
            
            # Create outbox event schema
            outbox_schema = {
                "@type": "Class",
                "@id": "OutboxEvent",
                "@key": {"@type": "Random"},
                "event_type": {"@type": "xsd:string", "@class": "xsd:string"},
                "source": {"@type": "xsd:string", "@class": "xsd:string"},
                "subject": {"@type": "xsd:string", "@class": "xsd:string"},
                "data": {"@type": "xsd:string", "@class": "xsd:string"},  # JSON stringified
                "correlation_id": {"@type": "xsd:string", "@class": "xsd:string"},
                "idempotency_key": {"@type": "xsd:string", "@class": "xsd:string"},
                "metadata": {"@type": "xsd:string", "@class": "xsd:string"},  # JSON stringified
                "status": {"@type": "xsd:string", "@class": "xsd:string"},
                "retry_count": {"@type": "xsd:integer", "@class": "xsd:integer"},
                "max_retries": {"@type": "xsd:integer", "@class": "xsd:integer"},
                "created_at": {"@type": "xsd:dateTime", "@class": "xsd:dateTime"},
                "processed_at": {"@type": "xsd:dateTime", "@class": "xsd:dateTime"},
                "error_message": {"@type": "xsd:string", "@class": "xsd:string"}
            }
            
            await self.db_client.insert_document(
                outbox_schema,
                graph_type="schema",
                database=self.database
            )
            
            # Create unique index on idempotency_key
            index_schema = {
                "@type": "Class",
                "@id": "OutboxIdempotencyIndex",
                "@key": {"@type": "Lexical", "@fields": ["idempotency_key"]},
                "idempotency_key": {"@type": "xsd:string", "@class": "xsd:string"},
                "event_id": {"@type": "xsd:string", "@class": "xsd:string"}
            }
            
            await self.db_client.insert_document(
                index_schema,
                graph_type="schema",
                database=self.database
            )
            
            logger.info(f"Outbox database '{self.database}' initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize outbox database: {e}")
            return False
    
    async def publish_event(
        self,
        event_type: str,
        event_data: Any,
        source: str = "/oms",
        subject: Optional[str] = None,
        correlation_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Publish event to outbox for guaranteed delivery
        
        Args:
            event_type: Type of event (e.g., "audit.activity.v1")
            event_data: Event payload (will be stored as CloudEvent data)
            source: Event source identifier
            subject: Event subject (optional)
            correlation_id: Request correlation ID
            idempotency_key: Custom idempotency key (auto-generated if not provided)
            metadata: Additional metadata
            
        Returns:
            Event ID
            
        Raises:
            Exception: If event storage fails
        """
        event_id = str(uuid4())
        
        # Create outbox event
        outbox_event = OutboxEvent(
            event_id=event_id,
            event_type=event_type,
            source=source,
            subject=subject or f"outbox/{event_id}",
            data=event_data if isinstance(event_data, dict) else {"data": event_data},
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            metadata=metadata or {}
        )
        
        # Check for duplicate idempotency key
        if await self._is_duplicate_event(outbox_event.idempotency_key):
            logger.warning(f"Duplicate event detected: {outbox_event.idempotency_key}")
            # Return the existing event ID
            existing_event = await self._get_event_by_idempotency_key(outbox_event.idempotency_key)
            return existing_event.event_id if existing_event else event_id
        
        # Store event in outbox within transaction
        try:
            # Insert outbox event
            await self.db_client.insert_document(
                outbox_event.to_dict(),
                database=self.database
            )
            
            # Insert idempotency index
            await self.db_client.insert_document(
                {
                    "@type": "OutboxIdempotencyIndex",
                    "idempotency_key": outbox_event.idempotency_key,
                    "event_id": event_id
                },
                database=self.database
            )
            
            logger.debug(f"Event stored in outbox: {event_id} ({event_type})")
            return event_id
            
        except Exception as e:
            logger.error(f"Failed to store event in outbox: {e}")
            raise
    
    async def start_processing(self):
        """Start background event processing"""
        if self._is_running:
            return
        
        self._is_running = True
        self._processing_task = asyncio.create_task(self._process_loop())
        logger.info("Outbox event processing started")
    
    async def stop_processing(self):
        """Stop background event processing"""
        self._is_running = False
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
        logger.info("Outbox event processing stopped")
    
    async def _process_loop(self):
        """Background processing loop"""
        while self._is_running:
            try:
                # Get pending events
                pending_events = await self._get_pending_events(self.batch_size)
                
                if pending_events:
                    # Process events in batch
                    await self._process_events_batch(pending_events)
                else:
                    # No events to process, wait
                    await asyncio.sleep(self.process_interval)
                    
            except Exception as e:
                logger.error(f"Error in outbox processing loop: {e}")
                await asyncio.sleep(5)  # Back off on error
    
    async def _process_events_batch(self, events: List[OutboxEvent]):
        """Process a batch of events"""
        tasks = []
        for event in events:
            task = asyncio.create_task(self._process_single_event(event))
            tasks.append(task)
        
        # Wait for all events to be processed
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Log any exceptions
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Failed to process event {events[i].event_id}: {result}")
    
    async def _process_single_event(self, event: OutboxEvent):
        """Process a single outbox event"""
        try:
            # Mark as processing
            await self._update_event_status(event.event_id, OutboxEventStatus.PROCESSING)
            
            # Publish event - prefer direct NATS for simplicity
            if self.nats_client:
                # Direct NATS publishing
                await self._publish_via_nats(event)
            elif self.processor:
                # Use the existing OutboxProcessor for publishing
                await self._publish_via_processor(event)
            else:
                # No publishing mechanism available - just log
                logger.warning(f"No publishing mechanism available for event {event.event_id}")
                await self._mark_event_completed(event.event_id)
                return
            
            # Mark as completed
            await self._mark_event_completed(event.event_id)
            logger.debug(f"Successfully processed outbox event: {event.event_id}")
            
        except Exception as e:
            # Mark as failed and increment retry count
            await self._mark_event_failed(event.event_id, str(e))
            logger.error(f"Failed to process outbox event {event.event_id}: {e}")
    
    async def _publish_via_processor(self, event: OutboxEvent):
        """Publish event using the existing OutboxProcessor"""
        # Convert to the format expected by OutboxProcessor
        cloud_event = event.to_cloudevent()
        
        # Store in TerminusDB outbox branch for OutboxProcessor to pick up
        outbox_doc = {
            "@type": "OutboxEntry",
            "@id": event.event_id,
            "event": cloud_event.model_dump(),
            "status": "pending",
            "created_at": event.created_at.isoformat()
        }
        
        await self.db_client.insert_document(
            outbox_doc,
            database=self.db_client.database,
            branch="_outbox"
        )
    
    async def _publish_via_nats(self, event: OutboxEvent):
        """Publish event directly via NATS"""
        cloud_event = event.to_cloudevent()
        
        # Publish to NATS JetStream
        subject = f"oms.{event.event_type.replace('.', '_')}"
        message = cloud_event.model_dump_json().encode()
        
        await self.nats_client.publish(subject, message)
    
    async def _get_pending_events(self, limit: int) -> List[OutboxEvent]:
        """Get pending events from outbox"""
        try:
            query = {
                "@type": "Select",
                "query": {
                    "@type": "And",
                    "and": [
                        {
                            "@type": "Triple",
                            "subject": {"@type": "Variable", "name": "Event"},
                            "predicate": "rdf:type",
                            "object": {"@type": "Value", "data": "OutboxEvent"}
                        },
                        {
                            "@type": "Triple",
                            "subject": {"@type": "Variable", "name": "Event"},
                            "predicate": "status",
                            "object": {"@type": "Value", "data": "pending"}
                        }
                    ]
                },
                "select": ["Event"],
                "limit": limit
            }
            
            results = await self.db_client.query_document(
                query,
                database=self.database
            )
            
            events = []
            for result in results:
                event_data = result["Event"]
                event = OutboxEvent.from_dict(event_data)
                
                # Skip events that exceeded max retries
                if event.retry_count >= event.max_retries:
                    continue
                
                events.append(event)
            
            return events
            
        except Exception as e:
            logger.error(f"Failed to get pending events: {e}")
            return []
    
    async def _is_duplicate_event(self, idempotency_key: str) -> bool:
        """Check if event with idempotency key already exists"""
        try:
            query = {
                "@type": "Select",
                "query": {
                    "@type": "Triple",
                    "subject": {"@type": "Variable", "name": "Index"},
                    "predicate": "idempotency_key",
                    "object": {"@type": "Value", "data": idempotency_key}
                },
                "select": ["Index"]
            }
            
            results = await self.db_client.query_document(
                query,
                database=self.database
            )
            
            return len(results) > 0
            
        except Exception as e:
            logger.error(f"Failed to check duplicate event: {e}")
            return False
    
    async def _get_event_by_idempotency_key(self, idempotency_key: str) -> Optional[OutboxEvent]:
        """Get existing event by idempotency key"""
        try:
            query = {
                "@type": "Select",
                "query": {
                    "@type": "And",
                    "and": [
                        {
                            "@type": "Triple",
                            "subject": {"@type": "Variable", "name": "Index"},
                            "predicate": "idempotency_key",
                            "object": {"@type": "Value", "data": idempotency_key}
                        },
                        {
                            "@type": "Triple",
                            "subject": {"@type": "Variable", "name": "Index"},
                            "predicate": "event_id",
                            "object": {"@type": "Variable", "name": "EventId"}
                        },
                        {
                            "@type": "Triple",
                            "subject": {"@type": "Variable", "name": "Event"},
                            "predicate": "@id",
                            "object": {"@type": "Variable", "name": "EventId"}
                        }
                    ]
                },
                "select": ["Event"]
            }
            
            results = await self.db_client.query_document(
                query,
                database=self.database
            )
            
            if results:
                return OutboxEvent.from_dict(results[0]["Event"])
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get event by idempotency key: {e}")
            return None
    
    async def _update_event_status(self, event_id: str, status: OutboxEventStatus):
        """Update event status"""
        try:
            update_doc = {
                "@type": "OutboxEvent",
                "@id": event_id,
                "status": status.value
            }
            
            await self.db_client.replace_document(
                update_doc,
                database=self.database
            )
            
        except Exception as e:
            logger.error(f"Failed to update event status: {e}")
    
    async def _mark_event_completed(self, event_id: str):
        """Mark event as completed"""
        try:
            update_doc = {
                "@type": "OutboxEvent",
                "@id": event_id,
                "status": OutboxEventStatus.COMPLETED.value,
                "processed_at": datetime.now(timezone.utc).isoformat()
            }
            
            await self.db_client.replace_document(
                update_doc,
                database=self.database
            )
            
        except Exception as e:
            logger.error(f"Failed to mark event completed: {e}")
    
    async def _mark_event_failed(self, event_id: str, error_message: str):
        """Mark event as failed and increment retry count"""
        try:
            # Get current event to increment retry count
            event = await self._get_event_by_id(event_id)
            if not event:
                return
            
            new_retry_count = event.retry_count + 1
            new_status = (
                OutboxEventStatus.DEAD_LETTER 
                if new_retry_count >= event.max_retries 
                else OutboxEventStatus.FAILED
            )
            
            update_doc = {
                "@type": "OutboxEvent",
                "@id": event_id,
                "status": new_status.value,
                "retry_count": new_retry_count,
                "error_message": error_message
            }
            
            await self.db_client.replace_document(
                update_doc,
                database=self.database
            )
            
        except Exception as e:
            logger.error(f"Failed to mark event failed: {e}")
    
    async def _get_event_by_id(self, event_id: str) -> Optional[OutboxEvent]:
        """Get event by ID"""
        try:
            query = {
                "@type": "Select",
                "query": {
                    "@type": "Triple",
                    "subject": {"@type": "Variable", "name": "Event"},
                    "predicate": "@id",
                    "object": {"@type": "Value", "data": event_id}
                },
                "select": ["Event"]
            }
            
            results = await self.db_client.query_document(
                query,
                database=self.database
            )
            
            if results:
                return OutboxEvent.from_dict(results[0]["Event"])
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get event by ID: {e}")
            return None
    
    async def cleanup_completed_events(self, older_than_hours: int = 24) -> int:
        """Clean up completed events older than specified hours"""
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
            
            query = {
                "@type": "Select",
                "query": {
                    "@type": "And",
                    "and": [
                        {
                            "@type": "Triple",
                            "subject": {"@type": "Variable", "name": "Event"},
                            "predicate": "status",
                            "object": {"@type": "Value", "data": "completed"}
                        },
                        {
                            "@type": "Triple",
                            "subject": {"@type": "Variable", "name": "Event"},
                            "predicate": "processed_at",
                            "object": {"@type": "Variable", "name": "ProcessedAt"}
                        },
                        {
                            "@type": "Less",
                            "left": {"@type": "Variable", "name": "ProcessedAt"},
                            "right": {"@type": "Value", "data": cutoff_time.isoformat()}
                        }
                    ]
                },
                "select": ["Event"]
            }
            
            results = await self.db_client.query_document(
                query,
                database=self.database
            )
            
            # Delete events and their idempotency index entries
            deleted_count = 0
            for result in results:
                event_data = result["Event"]
                event_id = event_data["@id"]
                idempotency_key = event_data["idempotency_key"]
                
                # Delete event
                await self.db_client.delete_document(event_id, database=self.database)
                
                # Delete idempotency index
                index_query = {
                    "@type": "Select",
                    "query": {
                        "@type": "Triple",
                        "subject": {"@type": "Variable", "name": "Index"},
                        "predicate": "idempotency_key",
                        "object": {"@type": "Value", "data": idempotency_key}
                    },
                    "select": ["Index"]
                }
                
                index_results = await self.db_client.query_document(
                    index_query,
                    database=self.database
                )
                
                for index_result in index_results:
                    index_id = index_result["Index"]["@id"]
                    await self.db_client.delete_document(index_id, database=self.database)
                
                deleted_count += 1
            
            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} completed outbox events")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup completed events: {e}")
            return 0
    
    async def get_statistics(self) -> Dict[str, int]:
        """Get outbox statistics"""
        stats = {
            "pending": 0,
            "processing": 0,
            "completed": 0,
            "failed": 0,
            "dead_letter": 0,
            "total": 0
        }
        
        try:
            for status in OutboxEventStatus:
                query = {
                    "@type": "Select",
                    "query": {
                        "@type": "Triple",
                        "subject": {"@type": "Variable", "name": "Event"},
                        "predicate": "status",
                        "object": {"@type": "Value", "data": status.value}
                    },
                    "select": ["Event"]
                }
                
                results = await self.db_client.query_document(
                    query,
                    database=self.database
                )
                
                count = len(results)
                stats[status.value] = count
                stats["total"] += count
            
        except Exception as e:
            logger.error(f"Failed to get outbox statistics: {e}")
        
        return stats


# Global outbox service instance
_outbox_service: Optional[OutboxService] = None


async def get_outbox_service() -> OutboxService:
    """Get global outbox service instance"""
    global _outbox_service
    if _outbox_service is None:
        from database.clients.terminus_db import TerminusDBClient
        from shared.infrastructure.nats_client import get_nats_client
        
        # Initialize with TerminusDB and NATS clients
        db_client = TerminusDBClient("http://localhost:6363")
        nats_client = await get_nats_client()
        
        _outbox_service = OutboxService(
            db_client=db_client,
            nats_client=nats_client
        )
        
        await _outbox_service.initialize()
        await _outbox_service.start_processing()
    
    return _outbox_service


def set_outbox_service(service: OutboxService):
    """Set global outbox service instance (for testing)"""
    global _outbox_service
    _outbox_service = service