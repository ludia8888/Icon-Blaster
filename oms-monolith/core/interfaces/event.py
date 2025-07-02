"""Event publisher protocol"""

from typing import Protocol, Dict, Any
from datetime import datetime

class EventPublisherProtocol(Protocol):
    """Protocol for event publisher implementations"""
    
    async def initialize(self) -> None:
        """Initialize event publisher connections"""
        ...
    
    async def close(self) -> None:
        """Close event publisher connections"""
        ...
    
    async def publish(self, event_type: str, data: Dict[str, Any],
                     correlation_id: str | None = None) -> None:
        """Publish an event"""
        ...
    
    async def publish_batch(self, events: List[Dict[str, Any]]) -> None:
        """Publish multiple events in batch"""
        ...
    
    def subscribe(self, event_type: str, handler: Any) -> None:
        """Subscribe to an event type"""
        ...
    
    def unsubscribe(self, event_type: str, handler: Any) -> None:
        """Unsubscribe from an event type"""
        ...