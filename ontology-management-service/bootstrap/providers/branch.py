"""Branch Service Provider"""
from typing import Optional
from core.branch.service import BranchService
from core.branch.diff_engine import DiffEngine
from core.branch.conflict_resolver import ConflictResolver
from bootstrap.providers.database import DatabaseProvider
from bootstrap.providers.event import EventProvider

class BranchProvider:
    """Provides a singleton BranchService instance"""
    def __init__(self, db_provider: DatabaseProvider, event_provider: EventProvider):
        self._db_provider = db_provider
        self._event_provider = event_provider
        self._service: Optional[BranchService] = None

    async def provide(self) -> BranchService:
        """Provide a configured BranchService instance"""
        if self._service is None:
            event_publisher = await self._event_provider.provide()
            
            # Initialize dependencies for BranchService
            diff_engine = DiffEngine(tdb_endpoint=self._db_provider.endpoint)
            conflict_resolver = ConflictResolver()
            
            self._service = BranchService(
                tdb_endpoint=self._db_provider.endpoint,
                diff_engine=diff_engine,
                conflict_resolver=conflict_resolver,
                event_publisher=event_publisher
            )
            await self._service.initialize()
        return self._service

    async def shutdown(self):
        """Shutdown provider resources"""
        self._service = None 