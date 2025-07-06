"""FastAPI dependency injection setup"""

from fastapi import Depends
from typing import Annotated, Dict, Any
from functools import lru_cache

from bootstrap.config import get_config, AppConfig
from bootstrap.providers import (
    DatabaseProvider, EventProvider, SchemaProvider, ValidationProvider
)
from bootstrap.providers.branch import BranchProvider
from bootstrap.providers.redis_provider import RedisProvider
from bootstrap.providers.circuit_breaker import CircuitBreakerProvider
from bootstrap.providers.embedding import EmbeddingServiceProvider
from bootstrap.providers.scheduler import SchedulerProvider
from bootstrap.providers.audit import AuditServiceProvider
from bootstrap.providers.terminus_gateway import get_terminus_client as get_terminus_gateway_client
from core.interfaces import (
    SchemaServiceProtocol, ValidationServiceProtocol,
    EventPublisherProtocol, DatabaseClientProtocol
)
from core.branch.service import BranchService

# Provider instances (singleton)
_providers: Dict[str, Any] = {
    "database": None,
    "event": None,
    "schema": None,
    "validation": None,
    "embedding": None,
    "scheduler": None,
    "audit": None,
    "branch": None,
    "redis": None,
    "job_service": None,
    "circuit_breaker": None,
}

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

def get_event_provider() -> EventProvider:
    """Get event provider instance"""
    if _providers["event"] is None:
        _providers["event"] = EventProvider()
    return _providers["event"]

def get_embedding_provider() -> EmbeddingServiceProvider:
    """Get embedding provider instance"""
    if _providers["embedding"] is None:
        _providers["embedding"] = EmbeddingServiceProvider()
    return _providers["embedding"]

def get_scheduler_provider() -> SchedulerProvider:
    """Get scheduler provider instance"""
    if _providers["scheduler"] is None:
        _providers["scheduler"] = SchedulerProvider()
    return _providers["scheduler"]

def get_audit_provider() -> AuditServiceProvider:
    """Get audit service provider instance"""
    if _providers["audit"] is None:
        _providers["audit"] = AuditServiceProvider()
    return _providers["audit"]

def get_branch_provider(
    db_provider: Annotated[DatabaseProvider, Depends(get_database_provider)],
    event_provider: Annotated[EventProvider, Depends(get_event_provider)]
) -> BranchProvider:
    """Get branch provider instance"""
    if _providers["branch"] is None:
        _providers["branch"] = BranchProvider(db_provider, event_provider)
    return _providers["branch"]

def get_schema_provider(
    db_provider: Annotated[DatabaseProvider, Depends(get_database_provider)],
    event_provider: Annotated[EventProvider, Depends(get_event_provider)]
) -> SchemaProvider:
    """Get schema provider instance"""
    if _providers["schema"] is None:
        _providers["schema"] = SchemaProvider(db_provider, event_provider)
    return _providers["schema"]

def get_validation_provider(
    db_provider: Annotated[DatabaseProvider, Depends(get_database_provider)]
) -> ValidationProvider:
    """Get validation provider instance"""
    if _providers["validation"] is None:
        _providers["validation"] = ValidationProvider(db_provider)
    return _providers["validation"]

def get_redis_provider() -> RedisProvider:
    """Get Redis provider instance"""
    if _providers["redis"] is None:
        _providers["redis"] = RedisProvider()
    return _providers["redis"]

def get_circuit_breaker_provider(
    redis_provider: Annotated[RedisProvider, Depends(get_redis_provider)]
) -> CircuitBreakerProvider:
    """Get Circuit Breaker provider instance"""
    if _providers["circuit_breaker"] is None:
        _providers["circuit_breaker"] = CircuitBreakerProvider(redis_provider)
    return _providers["circuit_breaker"]

# Service dependencies for route handlers
async def get_db_client(
    provider: Annotated[DatabaseProvider, Depends(get_database_provider)]
) -> DatabaseClientProtocol:
    """Get database client instance"""
    return await provider.provide()

# TerminusDB specific client (with gateway support)
async def get_terminus_client():
    """Get TerminusDB client (direct or gateway based on config)"""
    return await get_terminus_gateway_client()

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

async def get_embedding_service(
    provider: Annotated[EmbeddingServiceProvider, Depends(get_embedding_provider)]
):
    """Get embedding service instance"""
    return await provider.provide()

async def get_scheduler_service(
    provider: Annotated[SchedulerProvider, Depends(get_scheduler_provider)]
):
    """Get scheduler service instance"""
    return await provider.provide()

async def get_audit_service(
    provider: Annotated[AuditServiceProvider, Depends(get_audit_provider)]
):
    """Get audit service instance"""
    return provider.get()

async def get_branch_service(
    provider: Annotated[BranchProvider, Depends(get_branch_provider)]
) -> BranchService:
    """Get branch service instance"""
    return await provider.provide()

async def get_redis_client(
    provider: Annotated[RedisProvider, Depends(get_redis_provider)]
):
    """Get Redis client instance"""
    return await provider.provide()

async def get_job_service():
    """Get JobService instance with proper dependency injection"""
    if _providers["job_service"] is None:
        from services.job_service import JobService
        _providers["job_service"] = JobService()
        await _providers["job_service"].initialize()
    return _providers["job_service"]

async def get_circuit_breaker_group(
    provider: Annotated[CircuitBreakerProvider, Depends(get_circuit_breaker_provider)]
):
    """Get CircuitBreakerGroup instance"""
    return await provider.provide()

# Cleanup function for shutdown
async def cleanup_providers():
    """Clean up all provider resources"""
    for provider in _providers.values():
        if provider and hasattr(provider, 'shutdown'):
            await provider.shutdown()
    _providers.clear()