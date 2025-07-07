"""Validation service provider"""

from typing import Optional

from core.validation.service import ValidationService
from shared.cache.smart_cache import SmartCache
from .base import Provider
# from .database import DatabaseProvider
from database.clients.unified_database_client import UnifiedDatabaseClient
from .event import EventProvider
from .terminus_port_adapter import TerminusPortAdapter

class ValidationProvider(Provider[ValidationService]):
    """Provider for validation service instances"""
    
    def __init__(self, db_client: UnifiedDatabaseClient, event_provider: EventProvider):
        self.db_client = db_client
        self.event_provider = event_provider
        # We can initialize the cache provider here if it exists, or create the cache directly.
        self._instance: Optional[ValidationService] = None
    
    async def provide(self) -> ValidationService:
        """Create validation service with correct dependencies"""
        if self._instance is None:
            # 1. Get underlying clients/services
            # unified_db_client is now injected directly
            event_service = await self.event_provider.provide()
            
            # 2. Create Port implementations (Adapters)
            terminus_port = TerminusPortAdapter(self.db_client)
            cache_port = SmartCache(redis_client=None)

            # 3. Instantiate the service with the ports
            self._instance = ValidationService(
                cache=cache_port,
                tdb=terminus_port,
                events=event_service # EventGatewayStub already fits the EventPort protocol
            )
        return self._instance
    
    async def shutdown(self) -> None:
        """Validation service doesn't need explicit shutdown"""
        pass