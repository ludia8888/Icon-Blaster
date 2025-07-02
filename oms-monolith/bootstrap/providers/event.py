"""Event publisher provider"""

import os
from core.event_publisher.enhanced_event_service import EnhancedEventService
from .base import SingletonProvider

class EventProvider(SingletonProvider[EnhancedEventService]):
    """Provider for event service instances"""
    
    def __init__(self, broker_url: str | None = None):
        super().__init__()
        self.broker_url = broker_url or os.getenv("EVENT_BROKER_URL", "redis://localhost:6379")
    
    async def _create(self) -> EnhancedEventService:
        """Create and initialize event service"""
        service = EnhancedEventService()
        await service.initialize()
        return service
    
    async def shutdown(self) -> None:
        """Close event service connections"""
        if self._instance:
            await self._instance.close()