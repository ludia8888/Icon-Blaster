"""Dependency Injection setup using punq"""

import os
import punq
from fastapi import Request, Depends, Header, HTTPException
from typing import Any
from dependency_injector import containers, providers

from bootstrap.config import AppConfig
from bootstrap.providers.database import (
    PostgresClientProvider, SQLiteClientProvider, UnifiedDatabaseProvider
)
from bootstrap.providers.redis_provider import RedisProvider
from bootstrap.providers.circuit_breaker import CircuitBreakerProvider
from database.clients.postgres_client import PostgresClient
from database.clients.sqlite_client import SQLiteClient
from database.clients.postgres_client_secure import PostgresClientSecure
from database.clients.sqlite_client_secure import SQLiteClientSecure
from database.clients.unified_database_client import UnifiedDatabaseClient, get_unified_database_client
from redis import asyncio as aioredis
from middleware.circuit_breaker import CircuitBreakerGroup
from core.branch.service import BranchService
from bootstrap.providers.branch import BranchProvider
from bootstrap.providers.event import EventProvider, get_event_gateway
from core.schema.service import SchemaService
from core.schema.repository import SchemaRepository
# from core.auth.service import AuthService  # TODO: implement when needed
from bootstrap.config import get_config
# from shared.event_gateway import IEventGateway  # TODO: implement when needed
# from core.versioning.version_service import IVersionService, VersionService, ResilientVersionService  # TODO: implement when needed
from shared.database.sqlite_connector import SQLiteConnector

# ---------------------------------------------------------------------------
# BranchService Dependency
# ---------------------------------------------------------------------------

# 내부 캐시를 통해 BranchProvider 인스턴스를 재사용합니다.
_branch_provider_cache: dict[str, Any] = {}


async def get_branch_service(request: Request) -> BranchService:  # pragma: no cover
    """FastAPI dependency: BranchService 를 비동기 제공"""

    # For now, create a simple BranchService directly
    from database.clients.unified_database_client import UnifiedDatabaseClient, DatabaseBackend
    from database.clients.sqlite_client_secure import SQLiteClientSecure
    from bootstrap.config import get_config
    
    config = get_config()
    
    # Create database client (reuse same pattern as schema service)
    sqlite_client = SQLiteClientSecure(config=config.sqlite.model_dump())
    db_client = UnifiedDatabaseClient(
        postgres_client=None,
        sqlite_client=sqlite_client,
        default_backend=DatabaseBackend.SQLITE
    )
    await db_client.connect()
    
    # Create a simple BranchService
    from shared.event_gateway_stub import get_event_gateway_stub
    from core.branch.diff_engine import DiffEngine
    from core.branch.conflict_resolver import ConflictResolver
    
    tdb_endpoint = os.environ.get("TERMINUSDB_ENDPOINT", "http://localhost:6363")
    event_gateway = get_event_gateway_stub()
    diff_engine = DiffEngine(tdb_endpoint=tdb_endpoint)
    conflict_resolver = ConflictResolver()  # Takes no arguments
    
    branch_service = BranchService(
        tdb_endpoint=tdb_endpoint,
        diff_engine=diff_engine,
        conflict_resolver=conflict_resolver,
        event_publisher=event_gateway
    )
    
    return branch_service

# ---------------------------------------------------------------------------
# SchemaService Dependency
# ---------------------------------------------------------------------------

class Container(containers.DeclarativeContainer):
    """
    DI Container for managing application dependencies.
    """
    config = providers.Singleton(get_config)

    # =============================================================================
    # Core Infrastructure Providers
    # =============================================================================
    redis_provider = providers.Singleton(
        RedisProvider, 
        config=config,
    )

    circuit_breaker_provider = providers.Singleton(
        CircuitBreakerProvider,
        redis_client=redis_provider,
    )

    db_client_provider = providers.Resource(
        get_unified_database_client,
    )

    event_gateway_provider = providers.Factory(
        get_event_gateway,
    )

    schema_repository_provider = providers.Factory(
        SchemaRepository,
        db=db_client_provider,
    )

    branch_service_provider = providers.Factory(
        BranchService,
        db_client=db_client_provider, # BranchService might still need the old name
        event_gateway=event_gateway_provider,
    )

    schema_service_provider = providers.Factory(
        SchemaService,
        repository=schema_repository_provider,
        branch_service=branch_service_provider,
        event_publisher=event_gateway_provider,
    )

# ---------------------------------------------------------------------------
# JobService Dependency (임시 스텁)
# ---------------------------------------------------------------------------

class _DummyJobService:  # pragma: no cover
    """임시 스텁 JobService – E2E 테스트용."""
    
    async def create_job(self, *args, **kwargs):
        return {"job_id": "dummy-job-id", "status": "pending"}
    
    async def get_job(self, *args, **kwargs):
        return {"job_id": "dummy-job-id", "status": "completed"}

async def get_job_service(request: Request) -> Any:  # pragma: no cover
    """FastAPI dependency: JobService (임시).
    
    실제 구현체가 준비되기 전까지 테스트를 위해 더미 객체를 반환합니다.
    """
    return _DummyJobService()

def get_auth_service(
    # ...
):
    pass

# We will attach the container to the app state instead of using a global variable.
# This makes it accessible via the request object.

# Dependency provider functions for FastAPI routes
def get_db_client(request: Request) -> UnifiedDatabaseClient:
    return request.app.state.container.resolve(UnifiedDatabaseClient)

def get_redis_client(request: Request) -> aioredis.Redis:
    return request.app.state.container.resolve(aioredis.Redis)

def get_circuit_breaker_group(request: Request) -> CircuitBreakerGroup:
    return request.app.state.container.resolve(CircuitBreakerGroup)

async def get_schema_service(
    request: Request,
    db_client: UnifiedDatabaseClient = Depends(get_unified_database_client),
    branch_service: BranchService = Depends(get_branch_service)
) -> SchemaService:
    """
    FastAPI dependency: Provides a fully initialized SchemaService.
    It now depends on get_unified_database_client to ensure the DB is connected.
    """
    schema_repo = SchemaRepository(db=db_client)
    
    # Event publisher is not yet implemented, passing None.
    schema_service = SchemaService(
        repository=schema_repo,
        branch_service=branch_service,
        event_publisher=None,
        version_service=None # version_service is not available in this context yet
    )
    
    return schema_service

# ... Add other dependency providers for your services as needed ...

def init_container(config=None) -> Container:
    """Initialize and return the dependency injection container."""
    container = Container()
    if config:
        container.config.override(config)
    container.init_resources()
    return container

# Create dependency functions for FastAPI
async def get_schema_service_from_container(request: Request) -> SchemaService:
    """Get SchemaService from DI container."""
    # For now, use direct instantiation to avoid async issues with dependency-injector
    from database.clients.unified_database_client import UnifiedDatabaseClient, DatabaseBackend
    from database.clients.postgres_client_secure import PostgresClientSecure
    from database.clients.sqlite_client_secure import SQLiteClientSecure
    from database.clients.terminus_db import TerminusDBClient
    
    # Get config
    from bootstrap.config import get_config
    config = get_config()
    
    # Create TerminusDB client
    terminus_endpoint = os.environ.get("TERMINUSDB_ENDPOINT", "http://localhost:6363")
    terminus_client = TerminusDBClient(
        endpoint=terminus_endpoint,
        username=os.environ.get("TERMINUSDB_USER", "admin"),
        password=os.environ.get("TERMINUSDB_PASSWORD", "changeme-admin-pass")
    )
    
    # Create SQLite client as fallback
    sqlite_client = SQLiteClientSecure(config=config.sqlite.model_dump())
    
    # Create unified database client with TerminusDB as primary
    db_client = UnifiedDatabaseClient(
        terminus_client=terminus_client,
        postgres_client=None,  # Skip PostgreSQL for tests
        sqlite_client=sqlite_client,
        default_backend=DatabaseBackend.TERMINUSDB  # Use TerminusDB as primary
    )
    
    await db_client.connect()
    
    schema_repo = SchemaRepository(db=db_client)
    branch_service = await get_branch_service(request)
    return SchemaService(
        repository=schema_repo,
        branch_service=branch_service,
        event_publisher=None
    )