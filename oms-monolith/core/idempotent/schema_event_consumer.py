"""
Schema Event Consumer
Idempotent consumer for schema change events
"""
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from core.idempotent.consumer_service import IdempotentConsumer
from models.idempotency import EventEnvelope
from models.domain import ObjectType, LinkType
from utils.logger import get_logger

logger = get_logger(__name__)


class SchemaState(BaseModel):
    """State maintained by schema consumer"""
    
    # Object types by ID
    object_types: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    
    # Link types by ID
    link_types: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    
    # Statistics
    total_object_types: int = 0
    total_link_types: int = 0
    last_update: Optional[datetime] = None
    
    # Version tracking
    schema_version: int = 0
    
    def add_object_type(self, type_id: str, type_data: Dict[str, Any]):
        """Add or update object type"""
        is_new = type_id not in self.object_types
        self.object_types[type_id] = type_data
        if is_new:
            self.total_object_types += 1
        self.last_update = datetime.now(timezone.utc)
        self.schema_version += 1
    
    def remove_object_type(self, type_id: str) -> bool:
        """Remove object type"""
        if type_id in self.object_types:
            del self.object_types[type_id]
            self.total_object_types -= 1
            self.last_update = datetime.now(timezone.utc)
            self.schema_version += 1
            return True
        return False
    
    def add_link_type(self, type_id: str, type_data: Dict[str, Any]):
        """Add or update link type"""
        is_new = type_id not in self.link_types
        self.link_types[type_id] = type_data
        if is_new:
            self.total_link_types += 1
        self.last_update = datetime.now(timezone.utc)
        self.schema_version += 1
    
    def remove_link_type(self, type_id: str) -> bool:
        """Remove link type"""
        if type_id in self.link_types:
            del self.link_types[type_id]
            self.total_link_types -= 1
            self.last_update = datetime.now(timezone.utc)
            self.schema_version += 1
            return True
        return False


class EventResult(BaseModel):
    """Result of event processing"""
    success: bool = True
    new_state: Optional[SchemaState] = None
    result: Optional[Dict[str, Any]] = None
    side_effects: List[str] = Field(default_factory=list)
    created_resources: List[str] = Field(default_factory=list)
    updated_resources: List[str] = Field(default_factory=list)


class SchemaEventConsumer:
    """
    Idempotent consumer for schema events
    """
    
    def __init__(self, consumer_id: str = "schema_consumer", version: str = "1.0.0"):
        self.consumer = IdempotentConsumer[SchemaState](
            consumer_id=consumer_id,
            consumer_version=version,
            checkpoint_interval=50,
            state_class=SchemaState
        )
        
        # Register event handlers
        self._register_handlers()
    
    async def initialize(self):
        """Initialize consumer"""
        await self.consumer.initialize()
        logger.info("Schema event consumer initialized")
    
    def _register_handlers(self):
        """Register all event handlers"""
        # Object type events
        self.consumer.register_handler("object_type.created", self._handle_object_type_created)
        self.consumer.register_handler("object_type.updated", self._handle_object_type_updated)
        self.consumer.register_handler("object_type.deleted", self._handle_object_type_deleted)
        
        # Link type events
        self.consumer.register_handler("link_type.created", self._handle_link_type_created)
        self.consumer.register_handler("link_type.updated", self._handle_link_type_updated)
        self.consumer.register_handler("link_type.deleted", self._handle_link_type_deleted)
        
        # Schema operations
        self.consumer.register_handler("schema.imported", self._handle_schema_imported)
        self.consumer.register_handler("schema.reset", self._handle_schema_reset)
    
    async def _handle_object_type_created(
        self,
        event: EventEnvelope,
        state: SchemaState
    ) -> EventResult:
        """Handle object type creation"""
        payload = event.payload
        type_id = payload.get("type_id")
        type_data = payload.get("type_data", {})
        
        if not type_id:
            raise ValueError("Missing type_id in event payload")
        
        # Update state
        state.add_object_type(type_id, type_data)
        
        logger.info(f"Created object type {type_id}")
        
        return EventResult(
            success=True,
            new_state=state,
            result={"type_id": type_id, "created": True},
            created_resources=[f"object_type:{type_id}"],
            side_effects=[f"Indexed object type {type_id}"]
        )
    
    async def _handle_object_type_updated(
        self,
        event: EventEnvelope,
        state: SchemaState
    ) -> EventResult:
        """Handle object type update"""
        payload = event.payload
        type_id = payload.get("type_id")
        type_data = payload.get("type_data", {})
        changes = payload.get("changes", {})
        
        if not type_id:
            raise ValueError("Missing type_id in event payload")
        
        # Update state
        existing = state.object_types.get(type_id, {})
        updated = {**existing, **type_data}
        state.add_object_type(type_id, updated)
        
        logger.info(f"Updated object type {type_id} with changes: {list(changes.keys())}")
        
        return EventResult(
            success=True,
            new_state=state,
            result={"type_id": type_id, "updated": True, "fields_changed": list(changes.keys())},
            updated_resources=[f"object_type:{type_id}"],
            side_effects=[f"Re-indexed object type {type_id}"]
        )
    
    async def _handle_object_type_deleted(
        self,
        event: EventEnvelope,
        state: SchemaState
    ) -> EventResult:
        """Handle object type deletion"""
        payload = event.payload
        type_id = payload.get("type_id")
        
        if not type_id:
            raise ValueError("Missing type_id in event payload")
        
        # Update state
        removed = state.remove_object_type(type_id)
        
        if removed:
            logger.info(f"Deleted object type {type_id}")
            side_effects = [
                f"Removed index for object type {type_id}",
                f"Cleaned up related data for {type_id}"
            ]
        else:
            logger.warning(f"Object type {type_id} not found for deletion")
            side_effects = []
        
        return EventResult(
            success=True,
            new_state=state,
            result={"type_id": type_id, "deleted": removed},
            side_effects=side_effects
        )
    
    async def _handle_link_type_created(
        self,
        event: EventEnvelope,
        state: SchemaState
    ) -> EventResult:
        """Handle link type creation"""
        payload = event.payload
        type_id = payload.get("type_id")
        type_data = payload.get("type_data", {})
        
        if not type_id:
            raise ValueError("Missing type_id in event payload")
        
        # Update state
        state.add_link_type(type_id, type_data)
        
        logger.info(f"Created link type {type_id}")
        
        return EventResult(
            success=True,
            new_state=state,
            result={"type_id": type_id, "created": True},
            created_resources=[f"link_type:{type_id}"],
            side_effects=[f"Created link index for {type_id}"]
        )
    
    async def _handle_link_type_updated(
        self,
        event: EventEnvelope,
        state: SchemaState
    ) -> EventResult:
        """Handle link type update"""
        payload = event.payload
        type_id = payload.get("type_id")
        type_data = payload.get("type_data", {})
        changes = payload.get("changes", {})
        
        if not type_id:
            raise ValueError("Missing type_id in event payload")
        
        # Update state
        existing = state.link_types.get(type_id, {})
        updated = {**existing, **type_data}
        state.add_link_type(type_id, updated)
        
        logger.info(f"Updated link type {type_id} with changes: {list(changes.keys())}")
        
        return EventResult(
            success=True,
            new_state=state,
            result={"type_id": type_id, "updated": True, "fields_changed": list(changes.keys())},
            updated_resources=[f"link_type:{type_id}"],
            side_effects=[f"Re-indexed link type {type_id}"]
        )
    
    async def _handle_link_type_deleted(
        self,
        event: EventEnvelope,
        state: SchemaState
    ) -> EventResult:
        """Handle link type deletion"""
        payload = event.payload
        type_id = payload.get("type_id")
        
        if not type_id:
            raise ValueError("Missing type_id in event payload")
        
        # Update state
        removed = state.remove_link_type(type_id)
        
        if removed:
            logger.info(f"Deleted link type {type_id}")
            side_effects = [
                f"Removed link index for {type_id}",
                f"Cleaned up link instances of type {type_id}"
            ]
        else:
            logger.warning(f"Link type {type_id} not found for deletion")
            side_effects = []
        
        return EventResult(
            success=True,
            new_state=state,
            result={"type_id": type_id, "deleted": removed},
            side_effects=side_effects
        )
    
    async def _handle_schema_imported(
        self,
        event: EventEnvelope,
        state: SchemaState
    ) -> EventResult:
        """Handle schema import"""
        payload = event.payload
        object_types = payload.get("object_types", {})
        link_types = payload.get("link_types", {})
        
        # Import all types
        created_resources = []
        
        for type_id, type_data in object_types.items():
            state.add_object_type(type_id, type_data)
            created_resources.append(f"object_type:{type_id}")
        
        for type_id, type_data in link_types.items():
            state.add_link_type(type_id, type_data)
            created_resources.append(f"link_type:{type_id}")
        
        logger.info(
            f"Imported schema with {len(object_types)} object types "
            f"and {len(link_types)} link types"
        )
        
        return EventResult(
            success=True,
            new_state=state,
            result={
                "object_types_imported": len(object_types),
                "link_types_imported": len(link_types)
            },
            created_resources=created_resources,
            side_effects=["Rebuilt all schema indexes"]
        )
    
    async def _handle_schema_reset(
        self,
        event: EventEnvelope,
        state: SchemaState
    ) -> EventResult:
        """Handle schema reset"""
        # Clear all state
        old_object_count = state.total_object_types
        old_link_count = state.total_link_types
        
        state.object_types.clear()
        state.link_types.clear()
        state.total_object_types = 0
        state.total_link_types = 0
        state.schema_version = 0
        state.last_update = datetime.now(timezone.utc)
        
        logger.warning(f"Reset schema - removed {old_object_count} object types and {old_link_count} link types")
        
        return EventResult(
            success=True,
            new_state=state,
            result={
                "object_types_removed": old_object_count,
                "link_types_removed": old_link_count
            },
            side_effects=[
                "Cleared all schema indexes",
                "Reset schema version to 0"
            ]
        )
    
    async def process_event(self, event: EventEnvelope):
        """Process a single event"""
        return await self.consumer.process_event(event)
    
    async def process_batch(self, events: List[EventEnvelope]):
        """Process a batch of events"""
        return await self.consumer.process_batch(events)
    
    async def get_state(self) -> SchemaState:
        """Get current schema state"""
        return await self.consumer.get_state()
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get consumer statistics"""
        state = await self.consumer.get_state()
        info = await self.consumer.get_consumer_info()
        
        return {
            "consumer_id": info.consumer_id,
            "consumer_version": info.consumer_version,
            "state": {
                "object_types": state.total_object_types,
                "link_types": state.total_link_types,
                "schema_version": state.schema_version,
                "last_update": state.last_update.isoformat() if state.last_update else None
            },
            "processing": {
                "events_processed": info.events_processed,
                "events_skipped": info.events_skipped,
                "events_failed": info.events_failed,
                "last_event_id": info.last_processed_event_id,
                "last_processed": info.last_processed_timestamp.isoformat()
                    if info.last_processed_timestamp else None
            },
            "health": {
                "is_healthy": info.is_healthy,
                "error_count": info.error_count,
                "state_hash": info.state_commit_hash[:12]
            }
        }


# Global instance
_schema_consumer: Optional[SchemaEventConsumer] = None


async def get_schema_consumer() -> SchemaEventConsumer:
    """Get global schema consumer instance"""
    global _schema_consumer
    if _schema_consumer is None:
        _schema_consumer = SchemaEventConsumer()
        await _schema_consumer.initialize()
    return _schema_consumer