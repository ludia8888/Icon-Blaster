"""Schema service provider"""

from core.schema.service_adapter import SchemaServiceAdapter
from core.schema.repository import SchemaRepository
from .base import Provider
from .database import DatabaseProvider
from .event import EventProvider
from .branch import BranchProvider

class SchemaProvider(Provider[SchemaServiceAdapter]):
    """Provider for schema service instances"""
    
    def __init__(self, db_provider: DatabaseProvider, event_provider: EventProvider, branch_provider: BranchProvider):
        self.db_provider = db_provider
        self.event_provider = event_provider
        self.branch_provider = branch_provider
        self._instance: SchemaServiceAdapter | None = None
    
    async def provide(self) -> SchemaServiceAdapter:
        """Create schema service with correct dependencies"""
        if self._instance is None:
            db_client = await self.db_provider.provide()
            event_service = await self.event_provider.provide()
            branch_service = await self.branch_provider.provide()

            # Create repository with the database client
            repository = SchemaRepository(db_client)
            
            self._instance = SchemaServiceAdapter(
                repository=repository,
                branch_service=branch_service,
                event_service=event_service
            )
        return self._instance
    
    async def shutdown(self) -> None:
        """Schema service doesn't need explicit shutdown"""
        pass