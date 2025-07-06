"""
Enterprise-grade event state store implementation.

Features:
- Event sourcing with snapshots
- State reconstruction from events
- Event versioning and migration
- Optimistic concurrency control
- Event replay and time travel
- Aggregate state management
- Event projection support
- CQRS pattern support
"""

import asyncio
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Set, Tuple, Type, TypeVar, Generic
import redis.asyncio as redis
from collections import defaultdict
import logging
import uuid
import hashlib
import pickle
import zlib
import base64

logger = logging.getLogger(__name__)

T = TypeVar('T')


class EventType(Enum):
    """Event types."""
    DOMAIN_EVENT = "domain_event"
    INTEGRATION_EVENT = "integration_event"
    NOTIFICATION_EVENT = "notification_event"
    SYSTEM_EVENT = "system_event"


@dataclass
class Event:
    """Base event class."""
    id: str
    aggregate_id: str
    aggregate_type: str
    event_type: str
    event_version: int
    timestamp: datetime
    data: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    sequence_number: Optional[int] = None
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'aggregate_id': self.aggregate_id,
            'aggregate_type': self.aggregate_type,
            'event_type': self.event_type,
            'event_version': self.event_version,
            'timestamp': self.timestamp.isoformat(),
            'data': self.data,
            'metadata': self.metadata,
            'sequence_number': self.sequence_number,
            'correlation_id': self.correlation_id,
            'causation_id': self.causation_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Event':
        """Create from dictionary."""
        return cls(
            id=data['id'],
            aggregate_id=data['aggregate_id'],
            aggregate_type=data['aggregate_type'],
            event_type=data['event_type'],
            event_version=data['event_version'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            data=data['data'],
            metadata=data.get('metadata', {}),
            sequence_number=data.get('sequence_number'),
            correlation_id=data.get('correlation_id'),
            causation_id=data.get('causation_id')
        )


@dataclass
class Snapshot:
    """Aggregate snapshot."""
    aggregate_id: str
    aggregate_type: str
    version: int
    state: Any
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'aggregate_id': self.aggregate_id,
            'aggregate_type': self.aggregate_type,
            'version': self.version,
            'state': self.state,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Snapshot':
        """Create from dictionary."""
        return cls(
            aggregate_id=data['aggregate_id'],
            aggregate_type=data['aggregate_type'],
            version=data['version'],
            state=data['state'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            metadata=data.get('metadata', {})
        )


class Aggregate(ABC, Generic[T]):
    """Base aggregate class."""
    
    def __init__(self, aggregate_id: str):
        self.aggregate_id = aggregate_id
        self.version = 0
        self.uncommitted_events: List[Event] = []
    
    @abstractmethod
    def apply(self, event: Event) -> None:
        """Apply event to aggregate."""
        pass
    
    @abstractmethod
    def get_state(self) -> T:
        """Get current state."""
        pass
    
    @abstractmethod
    def from_snapshot(self, snapshot: Snapshot) -> None:
        """Restore from snapshot."""
        pass
    
    def raise_event(self, event_type: str, data: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None):
        """Raise a new event."""
        event = Event(
            id=str(uuid.uuid4()),
            aggregate_id=self.aggregate_id,
            aggregate_type=self.__class__.__name__,
            event_type=event_type,
            event_version=1,  # Will be set by event store
            timestamp=datetime.now(),
            data=data,
            metadata=metadata or {}
        )
        
        self.apply(event)
        self.uncommitted_events.append(event)
        self.version += 1
    
    def mark_events_committed(self):
        """Mark uncommitted events as committed."""
        self.uncommitted_events.clear()


class EventStore(ABC):
    """Abstract event store."""
    
    @abstractmethod
    async def save_events(self, events: List[Event]) -> bool:
        """Save events."""
        pass
    
    @abstractmethod
    async def get_events(
        self,
        aggregate_id: str,
        from_version: Optional[int] = None,
        to_version: Optional[int] = None
    ) -> List[Event]:
        """Get events for aggregate."""
        pass
    
    @abstractmethod
    async def save_snapshot(self, snapshot: Snapshot) -> bool:
        """Save snapshot."""
        pass
    
    @abstractmethod
    async def get_snapshot(self, aggregate_id: str) -> Optional[Snapshot]:
        """Get latest snapshot."""
        pass


class RedisEventStore(EventStore):
    """Redis-based event store."""
    
    def __init__(self, redis_client: redis.Redis, enable_compression: bool = True):
        self.redis_client = redis_client
        self.enable_compression = enable_compression
    
    async def save_events(self, events: List[Event]) -> bool:
        """Save events to Redis."""
        if not events:
            return True
        
        try:
            pipeline = self.redis_client.pipeline()
            
            for event in events:
                # Set sequence number
                sequence_key = f"event_store:sequence:{event.aggregate_id}"
                event.sequence_number = await self.redis_client.incr(sequence_key)
                
                # Save event
                event_key = f"event_store:event:{event.aggregate_id}:{event.sequence_number}"
                event_data = self._serialize(event.to_dict())
                pipeline.set(event_key, event_data)
                
                # Add to event stream
                stream_key = f"event_store:stream:{event.aggregate_id}"
                pipeline.zadd(stream_key, {event.id: event.sequence_number})
                
                # Add to global event stream
                global_key = "event_store:global_stream"
                pipeline.zadd(global_key, {event.id: time.time()})
                
                # Add to event type index
                type_key = f"event_store:type:{event.event_type}"
                pipeline.zadd(type_key, {event.id: time.time()})
            
            await pipeline.execute()
            return True
            
        except Exception as e:
            logger.error(f"Failed to save events: {e}")
            return False
    
    async def get_events(
        self,
        aggregate_id: str,
        from_version: Optional[int] = None,
        to_version: Optional[int] = None
    ) -> List[Event]:
        """Get events from Redis."""
        try:
            stream_key = f"event_store:stream:{aggregate_id}"
            
            # Get event IDs in version range
            min_score = from_version or 0
            max_score = to_version or '+inf'
            
            event_ids = await self.redis_client.zrangebyscore(
                stream_key,
                min_score,
                max_score
            )
            
            # Get events
            events = []
            for event_id in event_ids:
                # Get sequence number
                score = await self.redis_client.zscore(stream_key, event_id)
                if score is None:
                    continue
                
                sequence_number = int(score)
                event_key = f"event_store:event:{aggregate_id}:{sequence_number}"
                
                event_data = await self.redis_client.get(event_key)
                if event_data:
                    event_dict = self._deserialize(event_data)
                    events.append(Event.from_dict(event_dict))
            
            # Sort by sequence number
            events.sort(key=lambda e: e.sequence_number or 0)
            
            return events
            
        except Exception as e:
            logger.error(f"Failed to get events: {e}")
            return []
    
    async def save_snapshot(self, snapshot: Snapshot) -> bool:
        """Save snapshot to Redis."""
        try:
            snapshot_key = f"event_store:snapshot:{snapshot.aggregate_id}"
            snapshot_data = self._serialize(snapshot.to_dict())
            
            await self.redis_client.set(snapshot_key, snapshot_data)
            
            # Add to snapshot index
            index_key = f"event_store:snapshots:{snapshot.aggregate_type}"
            await self.redis_client.zadd(
                index_key,
                {snapshot.aggregate_id: snapshot.version}
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to save snapshot: {e}")
            return False
    
    async def get_snapshot(self, aggregate_id: str) -> Optional[Snapshot]:
        """Get snapshot from Redis."""
        try:
            snapshot_key = f"event_store:snapshot:{aggregate_id}"
            snapshot_data = await self.redis_client.get(snapshot_key)
            
            if not snapshot_data:
                return None
            
            snapshot_dict = self._deserialize(snapshot_data)
            return Snapshot.from_dict(snapshot_dict)
            
        except Exception as e:
            logger.error(f"Failed to get snapshot: {e}")
            return None
    
    def _serialize(self, data: Dict[str, Any]) -> bytes:
        """Serialize data."""
        serialized = pickle.dumps(data)
        if self.enable_compression:
            serialized = zlib.compress(serialized)
        return base64.b64encode(serialized)
    
    def _deserialize(self, data: bytes) -> Dict[str, Any]:
        """Deserialize data."""
        decoded = base64.b64decode(data)
        if self.enable_compression:
            decoded = zlib.decompress(decoded)
        return pickle.loads(decoded)


class EventMigration(ABC):
    """Base event migration."""
    
    @property
    @abstractmethod
    def from_version(self) -> int:
        """Source version."""
        pass
    
    @property
    @abstractmethod
    def to_version(self) -> int:
        """Target version."""
        pass
    
    @property
    @abstractmethod
    def event_type(self) -> str:
        """Event type to migrate."""
        pass
    
    @abstractmethod
    def migrate(self, event: Event) -> Event:
        """Migrate event."""
        pass


class EventMigrationManager:
    """Manages event migrations."""
    
    def __init__(self):
        self.migrations: Dict[str, Dict[int, EventMigration]] = defaultdict(dict)
    
    def register_migration(self, migration: EventMigration):
        """Register a migration."""
        self.migrations[migration.event_type][migration.from_version] = migration
    
    def migrate_event(self, event: Event, target_version: int) -> Event:
        """Migrate event to target version."""
        if event.event_version == target_version:
            return event
        
        current_version = event.event_version
        migrated_event = event
        
        # Find migration path
        while current_version < target_version:
            migration = self.migrations.get(event.event_type, {}).get(current_version)
            if not migration:
                raise ValueError(
                    f"No migration found for {event.event_type} "
                    f"from version {current_version}"
                )
            
            migrated_event = migration.migrate(migrated_event)
            current_version = migration.to_version
        
        return migrated_event


class ProjectionHandler(ABC):
    """Base projection handler."""
    
    @abstractmethod
    async def handle(self, event: Event) -> None:
        """Handle event."""
        pass
    
    @abstractmethod
    def handles_event_type(self, event_type: str) -> bool:
        """Check if handler handles event type."""
        pass


class EventStateStore:
    """Main event state store."""
    
    def __init__(
        self,
        event_store: EventStore,
        snapshot_frequency: int = 10,
        enable_projections: bool = True
    ):
        self.event_store = event_store
        self.snapshot_frequency = snapshot_frequency
        self.enable_projections = enable_projections
        
        self.aggregates: Dict[str, Type[Aggregate]] = {}
        self.projections: List[ProjectionHandler] = []
        self.migration_manager = EventMigrationManager()
        
        self._event_handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._projection_tasks: List[asyncio.Task] = []
    
    def register_aggregate(self, aggregate_type: Type[Aggregate]):
        """Register aggregate type."""
        self.aggregates[aggregate_type.__name__] = aggregate_type
    
    def register_projection(self, projection: ProjectionHandler):
        """Register projection handler."""
        self.projections.append(projection)
    
    def register_migration(self, migration: EventMigration):
        """Register event migration."""
        self.migration_manager.register_migration(migration)
    
    async def save(self, aggregate: Aggregate) -> bool:
        """Save aggregate events."""
        if not aggregate.uncommitted_events:
            return True
        
        try:
            # Apply optimistic concurrency control
            current_version = await self._get_aggregate_version(aggregate.aggregate_id)
            expected_version = aggregate.version - len(aggregate.uncommitted_events)
            
            if current_version != expected_version:
                raise ConcurrencyError(
                    f"Expected version {expected_version}, but was {current_version}"
                )
            
            # Save events
            if not await self.event_store.save_events(aggregate.uncommitted_events):
                return False
            
            # Handle projections
            if self.enable_projections:
                for event in aggregate.uncommitted_events:
                    await self._handle_projections(event)
            
            # Create snapshot if needed
            if aggregate.version % self.snapshot_frequency == 0:
                snapshot = Snapshot(
                    aggregate_id=aggregate.aggregate_id,
                    aggregate_type=aggregate.__class__.__name__,
                    version=aggregate.version,
                    state=aggregate.get_state(),
                    timestamp=datetime.now()
                )
                await self.event_store.save_snapshot(snapshot)
            
            # Mark events as committed
            aggregate.mark_events_committed()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to save aggregate: {e}")
            return False
    
    async def load(
        self,
        aggregate_type: Type[T],
        aggregate_id: str,
        version: Optional[int] = None
    ) -> Optional[T]:
        """Load aggregate from events."""
        if aggregate_type.__name__ not in self.aggregates:
            raise ValueError(f"Unknown aggregate type: {aggregate_type.__name__}")
        
        try:
            # Create aggregate instance
            aggregate = aggregate_type(aggregate_id)
            
            # Try to load from snapshot
            snapshot = await self.event_store.get_snapshot(aggregate_id)
            from_version = 0
            
            if snapshot and (version is None or snapshot.version <= version):
                aggregate.from_snapshot(snapshot)
                aggregate.version = snapshot.version
                from_version = snapshot.version + 1
            
            # Load events
            events = await self.event_store.get_events(
                aggregate_id,
                from_version,
                version
            )
            
            # Apply events
            for event in events:
                # Migrate if needed
                current_version = self._get_current_event_version(event.event_type)
                if event.event_version < current_version:
                    event = self.migration_manager.migrate_event(event, current_version)
                
                aggregate.apply(event)
                aggregate.version = event.sequence_number or aggregate.version + 1
            
            return aggregate
            
        except Exception as e:
            logger.error(f"Failed to load aggregate: {e}")
            return None
    
    async def get_events_by_type(
        self,
        event_type: str,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[Event]:
        """Get events by type."""
        # This would need to be implemented in the event store
        # For now, returning empty list
        return []
    
    async def replay_events(
        self,
        aggregate_id: Optional[str] = None,
        event_types: Optional[List[str]] = None,
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
        handler: Optional[Callable[[Event], Any]] = None
    ) -> int:
        """Replay events."""
        count = 0
        
        if aggregate_id:
            # Replay events for specific aggregate
            events = await self.event_store.get_events(aggregate_id)
            
            for event in events:
                if event_types and event.event_type not in event_types:
                    continue
                
                if from_time and event.timestamp < from_time:
                    continue
                
                if to_time and event.timestamp > to_time:
                    continue
                
                if handler:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event)
                    else:
                        handler(event)
                
                count += 1
        
        return count
    
    async def _get_aggregate_version(self, aggregate_id: str) -> int:
        """Get current aggregate version."""
        events = await self.event_store.get_events(aggregate_id)
        if not events:
            return 0
        return events[-1].sequence_number or len(events)
    
    def _get_current_event_version(self, event_type: str) -> int:
        """Get current version for event type."""
        # This would be configured per event type
        return 1
    
    async def _handle_projections(self, event: Event):
        """Handle projections for event."""
        for projection in self.projections:
            if projection.handles_event_type(event.event_type):
                try:
                    await projection.handle(event)
                except Exception as e:
                    logger.error(f"Projection failed for event {event.id}: {e}")


class ConcurrencyError(Exception):
    """Optimistic concurrency error."""
    pass


class AggregateRepository(Generic[T]):
    """Repository for aggregates."""
    
    def __init__(
        self,
        event_store: EventStateStore,
        aggregate_type: Type[T]
    ):
        self.event_store = event_store
        self.aggregate_type = aggregate_type
    
    async def save(self, aggregate: T) -> bool:
        """Save aggregate."""
        return await self.event_store.save(aggregate)
    
    async def get(self, aggregate_id: str) -> Optional[T]:
        """Get aggregate by ID."""
        return await self.event_store.load(self.aggregate_type, aggregate_id)
    
    async def exists(self, aggregate_id: str) -> bool:
        """Check if aggregate exists."""
        aggregate = await self.get(aggregate_id)
        return aggregate is not None


# Example aggregate implementation
class OrderAggregate(Aggregate[Dict[str, Any]]):
    """Example order aggregate."""
    
    def __init__(self, order_id: str):
        super().__init__(order_id)
        self.items: List[Dict[str, Any]] = []
        self.status = "created"
        self.total = 0.0
    
    def apply(self, event: Event) -> None:
        """Apply event to order."""
        if event.event_type == "OrderCreated":
            self.status = "created"
            self.items = event.data.get('items', [])
            self.total = event.data.get('total', 0.0)
        
        elif event.event_type == "ItemAdded":
            self.items.append(event.data['item'])
            self.total += event.data['item']['price'] * event.data['item']['quantity']
        
        elif event.event_type == "OrderConfirmed":
            self.status = "confirmed"
        
        elif event.event_type == "OrderShipped":
            self.status = "shipped"
        
        elif event.event_type == "OrderDelivered":
            self.status = "delivered"
    
    def get_state(self) -> Dict[str, Any]:
        """Get current state."""
        return {
            'order_id': self.aggregate_id,
            'items': self.items,
            'status': self.status,
            'total': self.total,
            'version': self.version
        }
    
    def from_snapshot(self, snapshot: Snapshot) -> None:
        """Restore from snapshot."""
        state = snapshot.state
        self.items = state.get('items', [])
        self.status = state.get('status', 'created')
        self.total = state.get('total', 0.0)
    
    def create(self, items: List[Dict[str, Any]]):
        """Create order."""
        total = sum(item['price'] * item['quantity'] for item in items)
        self.raise_event('OrderCreated', {
            'items': items,
            'total': total
        })
    
    def add_item(self, item: Dict[str, Any]):
        """Add item to order."""
        self.raise_event('ItemAdded', {'item': item})
    
    def confirm(self):
        """Confirm order."""
        if self.status != "created":
            raise ValueError("Can only confirm created orders")
        self.raise_event('OrderConfirmed', {})
    
    def ship(self):
        """Ship order."""
        if self.status != "confirmed":
            raise ValueError("Can only ship confirmed orders")
        self.raise_event('OrderShipped', {})
    
    def deliver(self):
        """Deliver order."""
        if self.status != "shipped":
            raise ValueError("Can only deliver shipped orders")
        self.raise_event('OrderDelivered', {})