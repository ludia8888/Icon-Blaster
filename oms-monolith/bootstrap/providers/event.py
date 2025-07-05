"""Event publisher provider"""

import os
from core.events.unified_publisher import UnifiedEventPublisher
from .base import SingletonProvider

class EventProvider(SingletonProvider[UnifiedEventPublisher]):
    """Provider for event service instances"""
    
    def __init__(self, broker_url: str | None = None):
        super().__init__()
        self.broker_url = broker_url or os.getenv("EVENT_BROKER_URL", "redis://localhost:6379")
    
    async def _create(self) -> UnifiedEventPublisher:
        """Create and initialize event service"""
        service = UnifiedEventPublisher()
        await service.initialize()
        return service
    
    async def shutdown(self) -> None:
        """Close event service connections"""
        if self._instance:
            await self._instance.close()