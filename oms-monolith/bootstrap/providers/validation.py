"""Validation service provider"""

from core.validation.service import ValidationService
from database.simple_terminus_client import SimpleTerminusDBClient
from .base import Provider
from .database import DatabaseProvider

class ValidationProvider(Provider[ValidationService]):
    """Provider for validation service instances"""
    
    def __init__(self, db_provider: DatabaseProvider):
        self.db_provider = db_provider
        self._instance: ValidationService | None = None
    
    async def provide(self) -> ValidationService:
        """Create validation service with dependencies"""
        if self._instance is None:
            db_client = await self.db_provider.provide()
            self._instance = ValidationService(db_client=db_client)
        return self._instance
    
    async def shutdown(self) -> None:
        """Validation service doesn't need explicit shutdown"""
        pass