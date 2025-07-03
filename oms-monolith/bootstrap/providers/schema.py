"""Schema service provider"""

from core.schema.service_adapter import SchemaServiceAdapter
from database.unified_terminus_client import SimpleTerminusDBClient
from core.event_publisher.enhanced_event_service import EnhancedEventService
from .base import Provider
from .database import DatabaseProvider
from .event import EventProvider

class SchemaProvider(Provider[SchemaServiceAdapter]):
    """Provider for schema service instances"""
    
    def __init__(self, db_provider: DatabaseProvider, event_provider: EventProvider):
        self.db_provider = db_provider
        self.event_provider = event_provider
        self._instance: SchemaServiceAdapter | None = None
    
    async def provide(self) -> SchemaServiceAdapter:
        """Create schema service with dependencies"""
        if self._instance is None:
            db_client = await self.db_provider.provide()
            event_service = await self.event_provider.provide()
            
            self._instance = SchemaServiceAdapter(
                db_client=db_client,
                event_publisher=event_service
            )
        return self._instance
    
    async def shutdown(self) -> None:
        """Schema service doesn't need explicit shutdown"""
        pass