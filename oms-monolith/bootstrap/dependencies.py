"""FastAPI dependency injection setup"""

from fastapi import Depends
from typing import Annotated
from functools import lru_cache

from bootstrap.config import get_config, AppConfig
from bootstrap.providers import (
    DatabaseProvider, EventProvider, SchemaProvider, ValidationProvider
)
from core.interfaces import (
    SchemaServiceProtocol, ValidationServiceProtocol,
    EventPublisherProtocol, DatabaseClientProtocol
)

# Provider instances (singleton)
_providers = {
    "database": None,
    "event": None,
    "schema": None,
    "validation": None
}

@lru_cache()
def get_database_provider(config: Annotated[AppConfig, Depends(get_config)]) -> DatabaseProvider:
    """Get database provider instance"""
    if _providers["database"] is None:
        _providers["database"] = DatabaseProvider(
            endpoint=config.database.endpoint,
            team=config.database.team,
            db=config.database.db,
            user=config.database.user,
            key=config.database.key
        )
    return _providers["database"]

@lru_cache()
def get_event_provider(config: Annotated[AppConfig, Depends(get_config)]) -> EventProvider:
    """Get event provider instance"""
    if _providers["event"] is None:
        _providers["event"] = EventProvider(broker_url=config.event.broker_url)
    return _providers["event"]

@lru_cache()
def get_schema_provider(
    db_provider: Annotated[DatabaseProvider, Depends(get_database_provider)],
    event_provider: Annotated[EventProvider, Depends(get_event_provider)]
) -> SchemaProvider:
    """Get schema provider instance"""
    if _providers["schema"] is None:
        _providers["schema"] = SchemaProvider(db_provider, event_provider)
    return _providers["schema"]

@lru_cache()
def get_validation_provider(
    db_provider: Annotated[DatabaseProvider, Depends(get_database_provider)]
) -> ValidationProvider:
    """Get validation provider instance"""
    if _providers["validation"] is None:
        _providers["validation"] = ValidationProvider(db_provider)
    return _providers["validation"]

# Service dependencies for route handlers
async def get_db_client(
    provider: Annotated[DatabaseProvider, Depends(get_database_provider)]
) -> DatabaseClientProtocol:
    """Get database client instance"""
    return await provider.provide()

async def get_event_publisher(
    provider: Annotated[EventProvider, Depends(get_event_provider)]
) -> EventPublisherProtocol:
    """Get event publisher instance"""
    return await provider.provide()

async def get_schema_service(
    provider: Annotated[SchemaProvider, Depends(get_schema_provider)]
) -> SchemaServiceProtocol:
    """Get schema service instance"""
    return await provider.provide()

async def get_validation_service(
    provider: Annotated[ValidationProvider, Depends(get_validation_provider)]
) -> ValidationServiceProtocol:
    """Get validation service instance"""
    return await provider.provide()

# Cleanup function for shutdown
async def cleanup_providers():
    """Clean up all provider resources"""
    for provider in _providers.values():
        if provider:
            await provider.shutdown()
    _providers.clear()