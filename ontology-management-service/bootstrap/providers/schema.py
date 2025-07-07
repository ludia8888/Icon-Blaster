"""Schema service provider"""
from typing import Optional

from core.schema.service_adapter import SchemaServiceAdapter
from core.schema.repository import SchemaRepository
from .base import Provider
# from .database import DatabaseProvider # No longer needed
from database.clients.unified_database_client import UnifiedDatabaseClient
from .event import EventProvider
from .branch import BranchProvider

class SchemaProvider(Provider[SchemaServiceAdapter]):
    """Provider for schema service instances"""
    
    def __init__(
        self, 
        db_client: UnifiedDatabaseClient, 
        event_provider: EventProvider, 
        branch_provider: BranchProvider
    ):
        self.db_client = db_client
        self.event_provider = event_provider
        self.branch_provider = branch_provider
        self._instance: Optional[SchemaServiceAdapter] = None
    
    async def provide(self) -> SchemaServiceAdapter:
        """Create schema service with correct dependencies"""
        if self._instance is None:
            # db_client is now injected directly
            event_service = await self.event_provider.provide()
            branch_service = await self.branch_provider.provide()

            # Create repository with the database client
            repository = SchemaRepository(db_client=self.db_client, db_name="oms")
            
            self._instance = SchemaServiceAdapter(
                repository=repository,
                branch_service=branch_service,
                event_service=event_service
            )
        return self._instance
    
    async def shutdown(self) -> None:
        """Schema service doesn't need explicit shutdown"""
        pass