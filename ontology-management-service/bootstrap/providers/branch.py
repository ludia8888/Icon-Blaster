"""Branch service provider"""
from typing import Optional

from core.branch.service import BranchService
from database.clients.unified_database_client import UnifiedDatabaseClient
from .base import Provider
from .event import EventProvider
# Dummy classes to satisfy BranchService dependencies for now
from core.branch.diff_engine import DiffEngine
from core.branch.conflict_resolver import ConflictResolver

class BranchProvider(Provider[BranchService]):
    """Provider for branch service instances"""
    
    def __init__(
        self, 
        db_client: UnifiedDatabaseClient, 
        event_provider: EventProvider
    ):
        self.db_client = db_client
        self.event_provider = event_provider
        self._instance: Optional[BranchService] = None
    
    async def provide(self) -> BranchService:
        """Create branch service with correct dependencies"""
        if self._instance is None:
            event_service = await self.event_provider.provide()
            
            # TODO: This is a temporary fix. BranchService needs to be refactored
            # to accept UnifiedDatabaseClient and other dependencies via DI.
            # We are providing dummy values to allow the application to load.
            self._instance = BranchService(
                tdb_endpoint="", # This should come from config via UDC
                diff_engine=DiffEngine(tdb_endpoint=""), # Dummy
                conflict_resolver=ConflictResolver(), # Dummy
                event_publisher=event_service
            )
        return self._instance
    
    async def shutdown(self) -> None:
        pass 