"""
Unified Event Publisher with pluggable backends
Consolidates all event publishing implementations

DESIGN INTENT:
This is the central event publishing system that unifies all event emission in OMS.
It provides a pluggable architecture where different backends serve specific purposes:

ARCHITECTURE PHILOSOPHY:
- Single interface (UnifiedEventPublisher) for all event publishing needs
- Backend selection based on use case, not implementation details
- Each backend optimized for its specific requirements
- Graceful degradation and fallback strategies

BACKEND PURPOSES:
1. HTTP: Simple, stateless event delivery for external webhooks
2. NATS: High-throughput, guaranteed delivery for internal microservices
3. EVENTBRIDGE: AWS-native integration for cloud workflows
4. REALTIME: In-memory pub/sub for GraphQL subscriptions (no persistence)
5. AUDIT: Compliance-focused with dual-write to ensure no event loss
6. OUTBOX: Transactional consistency for database + event operations

USE THIS FOR:
- All application event publishing
- Migrating from legacy event systems
- New event-driven features

NOT FOR:
- Direct database writes (use repositories)
- Synchronous request-response (use HTTP clients)
- File-based logging (use logger)

MIGRATION PATH:
1. Replace direct EventPublisher usage with UnifiedEventPublisher
2. Configure appropriate backend based on requirements
3. Remove legacy publisher after verification

Related modules:
- core/event_publisher/: Legacy implementations being consolidated
- shared/events.py: Simple interface being phased out
- api/graphql/realtime_publisher.py: Specialized for GraphQL subscriptions
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Dict, Any, List, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


class PublisherBackend(Enum):
    """Available publisher backends - each serves a specific purpose"""
    HTTP = "http"              # Simple HTTP calls for webhooks/external systems
    NATS = "nats"             # NATS JetStream for high-throughput internal events
    EVENTBRIDGE = "eventbridge"  # AWS EventBridge for cloud-native workflows
    REALTIME = "realtime"      # In-memory for GraphQL subscriptions (no persistence)
    AUDIT = "audit"           # Dual-write for compliance (DB + event stream)
    OUTBOX = "outbox"         # Transactional outbox pattern for consistency


class EventFormat(Enum):
    """Supported event formats"""
    CUSTOM = "custom"         # Legacy/custom formats
    CLOUDEVENTS = "cloudevents"  # CloudEvents 1.0
    EVENTBRIDGE = "eventbridge"  # AWS EventBridge format


@dataclass
class PublisherConfig:
    """Unified configuration for event publisher"""
    
    # Backend selection
    backend: PublisherBackend = PublisherBackend.HTTP
    
    # Connection settings
    endpoint: Optional[str] = None  # HTTP endpoint or NATS URL
    api_key: Optional[str] = None
    timeout: float = 5.0
    
    # Event format
    format: EventFormat = EventFormat.CLOUDEVENTS
    
    # Feature flags
    enable_batching: bool = True
    batch_size: int = 100
    enable_retry: bool = True
    max_retries: int = 3
    retry_delay: float = 1.0
    
    # Security settings
    enable_pii_protection: bool = False
    pii_strategy: str = "mask"  # mask, encrypt, anonymize, block
    allowed_event_types: Optional[List[str]] = None
    blocked_event_types: Optional[List[str]] = None
    
    # NATS specific
    nats_stream: str = "oms-events"
    nats_subject_prefix: str = "oms"
    
    # EventBridge specific
    eventbridge_bus: str = "default"
    aws_region: str = "us-east-1"
    
    # Audit specific
    enable_dual_write: bool = False
    audit_db_client: Optional[Any] = None
    
    # Outbox specific
    enable_outbox: bool = False
    outbox_repository: Optional[Any] = None
    
    # Monitoring
    enable_metrics: bool = True
    on_publish_success: Optional[Callable] = None
    on_publish_error: Optional[Callable] = None
    
    @classmethod
    def http_default(cls) -> "PublisherConfig":
        """Default HTTP configuration"""
        return cls(backend=PublisherBackend.HTTP)
    
    @classmethod
    def nats_streaming(cls, nats_url: str) -> "PublisherConfig":
        """NATS JetStream configuration"""
        return cls(
            backend=PublisherBackend.NATS,
            endpoint=nats_url,
            format=EventFormat.CLOUDEVENTS
        )
    
    @classmethod
    def aws_eventbridge(cls, region: str = "us-east-1") -> "PublisherConfig":
        """AWS EventBridge configuration"""
        return cls(
            backend=PublisherBackend.EVENTBRIDGE,
            format=EventFormat.EVENTBRIDGE,
            aws_region=region
        )
    
    @classmethod
    def audit_compliant(cls, db_client: Any) -> "PublisherConfig":
        """Audit-compliant configuration"""
        return cls(
            backend=PublisherBackend.AUDIT,
            enable_dual_write=True,
            audit_db_client=db_client,
            enable_pii_protection=True,
            enable_outbox=True
        )


class EventPublisherBackend(ABC):
    """Base interface for all publisher backends"""
    
    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to backend"""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to backend"""
        pass
    
    @abstractmethod
    async def publish(self, event: Dict[str, Any]) -> bool:
        """Publish single event"""
        pass
    
    @abstractmethod
    async def publish_batch(self, events: List[Dict[str, Any]]) -> bool:
        """Publish multiple events"""
        pass
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check backend health"""
        pass


class UnifiedEventPublisher:
    """
    Unified event publisher with pluggable backends
    Provides a consistent interface across all event publishing needs
    """
    
    def __init__(self, config: Optional[PublisherConfig] = None):
        self.config = config or PublisherConfig()
        self._backend: Optional[EventPublisherBackend] = None
        self._connected = False
        self._metrics = {
            "published": 0,
            "failed": 0,
            "batch_published": 0
        }
        
        # Initialize backend based on config
        self._init_backend()
    
    def _init_backend(self):
        """Initialize the appropriate backend"""
        if self.config.backend == PublisherBackend.HTTP:
            from .backends.http_backend import HTTPEventBackend
            self._backend = HTTPEventBackend(self.config)
            
        elif self.config.backend == PublisherBackend.NATS:
            from .backends.nats_backend import NATSEventBackend
            self._backend = NATSEventBackend(self.config)
            
        elif self.config.backend == PublisherBackend.EVENTBRIDGE:
            from .backends.eventbridge_backend import EventBridgeBackend
            self._backend = EventBridgeBackend(self.config)
            
        elif self.config.backend == PublisherBackend.REALTIME:
            from .backends.realtime_backend import RealtimeEventBackend
            self._backend = RealtimeEventBackend(self.config)
            
        elif self.config.backend == PublisherBackend.AUDIT:
            from .backends.audit_backend import AuditEventBackend
            self._backend = AuditEventBackend(self.config)
            
        elif self.config.backend == PublisherBackend.OUTBOX:
            from .backends.outbox_backend import OutboxEventBackend
            self._backend = OutboxEventBackend(self.config)
        
        else:
            raise ValueError(f"Unknown backend: {self.config.backend}")
    
    async def connect(self) -> None:
        """Connect to the backend"""
        if not self._connected:
            await self._backend.connect()
            self._connected = True
            logger.info(f"Connected to {self.config.backend.value} backend")
    
    async def disconnect(self) -> None:
        """Disconnect from the backend"""
        if self._connected:
            await self._backend.disconnect()
            self._connected = False
            logger.info(f"Disconnected from {self.config.backend.value} backend")
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()
    
    async def publish(
        self,
        event_type: str,
        data: Dict[str, Any],
        subject: Optional[str] = None,
        source: Optional[str] = None,
        correlation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Publish a single event
        
        Args:
            event_type: Type/name of the event
            data: Event payload
            subject: Optional subject/topic
            source: Event source
            correlation_id: For tracing
            metadata: Additional metadata
            
        Returns:
            bool: Success status
        """
        # Check if event type is allowed
        if not self._is_event_allowed(event_type):
            logger.warning(f"Event type {event_type} is blocked")
            return False
        
        # Format event based on configuration
        event = self._format_event(
            event_type=event_type,
            data=data,
            subject=subject,
            source=source,
            correlation_id=correlation_id,
            metadata=metadata
        )
        
        # Apply PII protection if enabled
        if self.config.enable_pii_protection:
            event = await self._apply_pii_protection(event)
        
        # Publish with retry logic
        success = await self._publish_with_retry(event)
        
        # Update metrics
        if success:
            self._metrics["published"] += 1
            if self.config.on_publish_success:
                await self._safe_callback(self.config.on_publish_success, event)
        else:
            self._metrics["failed"] += 1
            if self.config.on_publish_error:
                await self._safe_callback(self.config.on_publish_error, event)
        
        return success
    
    async def publish_batch(
        self,
        events: List[Dict[str, Any]]
    ) -> bool:
        """
        Publish multiple events
        
        Args:
            events: List of events to publish
            
        Returns:
            bool: Success status
        """
        if not events:
            return True
        
        # Filter allowed events
        allowed_events = [
            e for e in events 
            if self._is_event_allowed(e.get("type", ""))
        ]
        
        if not allowed_events:
            logger.warning("No allowed events in batch")
            return False
        
        # Apply PII protection if enabled
        if self.config.enable_pii_protection:
            protected_events = []
            for event in allowed_events:
                protected = await self._apply_pii_protection(event)
                protected_events.append(protected)
            allowed_events = protected_events
        
        # Batch by size limit
        batches = [
            allowed_events[i:i + self.config.batch_size]
            for i in range(0, len(allowed_events), self.config.batch_size)
        ]
        
        success = True
        for batch in batches:
            batch_success = await self._publish_batch_with_retry(batch)
            success = success and batch_success
            
            if batch_success:
                self._metrics["batch_published"] += len(batch)
        
        return success
    
    async def _publish_with_retry(self, event: Dict[str, Any]) -> bool:
        """Publish with retry logic"""
        if not self.config.enable_retry:
            return await self._backend.publish(event)
        
        for attempt in range(self.config.max_retries):
            try:
                if await self._backend.publish(event):
                    return True
                    
                # Wait before retry
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                    
            except Exception as e:
                logger.error(f"Publish attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))
        
        return False
    
    async def _publish_batch_with_retry(self, events: List[Dict[str, Any]]) -> bool:
        """Publish batch with retry logic"""
        if not self.config.enable_retry:
            return await self._backend.publish_batch(events)
        
        for attempt in range(self.config.max_retries):
            try:
                if await self._backend.publish_batch(events):
                    return True
                    
                # Wait before retry
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                    
            except Exception as e:
                logger.error(f"Batch publish attempt {attempt + 1} failed: {e}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay * (attempt + 1))
        
        return False
    
    def _format_event(
        self,
        event_type: str,
        data: Dict[str, Any],
        subject: Optional[str] = None,
        source: Optional[str] = None,
        correlation_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Format event based on configuration"""
        
        if self.config.format == EventFormat.CLOUDEVENTS:
            # CloudEvents 1.0 format
            return {
                "specversion": "1.0",
                "id": str(uuid.uuid4()),
                "type": event_type,
                "source": source or "oms-monolith",
                "subject": subject,
                "time": datetime.utcnow().isoformat() + "Z",
                "data": data,
                "datacontenttype": "application/json",
                "correlationid": correlation_id,
                **(metadata or {})
            }
        
        elif self.config.format == EventFormat.EVENTBRIDGE:
            # AWS EventBridge format
            return {
                "Source": source or "oms-monolith",
                "DetailType": event_type,
                "Detail": {
                    "data": data,
                    "subject": subject,
                    "correlationId": correlation_id,
                    "metadata": metadata
                }
            }
        
        else:  # CUSTOM format
            return {
                "type": event_type,
                "data": data,
                "subject": subject,
                "source": source,
                "correlation_id": correlation_id,
                "timestamp": datetime.utcnow().isoformat(),
                "metadata": metadata
            }
    
    def _is_event_allowed(self, event_type: str) -> bool:
        """Check if event type is allowed"""
        if self.config.blocked_event_types and event_type in self.config.blocked_event_types:
            return False
            
        if self.config.allowed_event_types:
            return event_type in self.config.allowed_event_types
            
        return True
    
    async def _apply_pii_protection(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Apply PII protection to event data"""
        # This would integrate with PIIHandler
        # For now, return event as-is
        return event
    
    async def _safe_callback(self, callback: Callable, *args, **kwargs):
        """Safely execute callback"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(*args, **kwargs)
            else:
                callback(*args, **kwargs)
        except Exception as e:
            logger.error(f"Callback error: {e}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get publisher metrics"""
        return {
            "backend": self.config.backend.value,
            "connected": self._connected,
            **self._metrics
        }
    
    async def health_check(self) -> bool:
        """Check backend health"""
        if not self._connected:
            return False
        return await self._backend.health_check()
    
    async def publish_audit_event(
        self,
        action: Any,
        user: Any,
        target: Any,
        changes: Optional[Any] = None,
        success: bool = True,
        error_code: Optional[str] = None,
        request_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Publish audit event - convenience method for AuditMiddleware
        
        Args:
            action: Audit action performed
            user: User context from authentication
            target: Target resource information
            changes: Change details if applicable
            success: Whether action succeeded
            error_code: Error code if failed
            request_id: Request correlation ID
            duration_ms: Request duration
            metadata: Additional metadata
            
        Returns:
            bool: Success status
        """
        from models.audit_events import AuditEventV1, ActorInfo
        
        # Create actor from user context
        actor = ActorInfo(
            id=user.user_id,
            username=user.username,
            email=getattr(user, 'email', None),
            roles=user.roles,
            tenant_id=getattr(user, 'tenant_id', None),
            service_account=user.is_service_account,
            ip_address=metadata.get('ip_address') if metadata else None,
            user_agent=metadata.get('user_agent') if metadata else None
        )
        
        # Create audit event
        audit_event = AuditEventV1(
            action=action,
            actor=actor,
            target=target,
            changes=changes,
            success=success,
            error_code=error_code,
            request_id=request_id,
            duration_ms=duration_ms,
            metadata=metadata or {}
        )
        
        # Publish using standard method
        return await self.publish(
            event_type="audit.activity.v1",
            data=audit_event.model_dump(),
            subject=f"{target.resource_type.value}/{target.resource_id}",
            source="/oms/audit",
            correlation_id=request_id,
            metadata={
                "audit": True,
                "action": action.value,
                "resource_type": target.resource_type.value
            }
        )


# Factory function for backward compatibility
def create_event_publisher(
    backend: str = "http",
    **kwargs
) -> UnifiedEventPublisher:
    """Create event publisher with specified backend"""
    backend_enum = PublisherBackend(backend.lower())
    
    if backend_enum == PublisherBackend.HTTP:
        config = PublisherConfig.http_default()
    elif backend_enum == PublisherBackend.NATS:
        config = PublisherConfig.nats_streaming(kwargs.get("endpoint", "nats://localhost:4222"))
    elif backend_enum == PublisherBackend.EVENTBRIDGE:
        config = PublisherConfig.aws_eventbridge(kwargs.get("region", "us-east-1"))
    elif backend_enum == PublisherBackend.AUDIT:
        config = PublisherConfig.audit_compliant(kwargs.get("db_client"))
    else:
        config = PublisherConfig(backend=backend_enum)
    
    # Apply additional kwargs
    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)
    
    return UnifiedEventPublisher(config)