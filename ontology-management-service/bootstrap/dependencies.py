"""Dependency Injection setup using punq"""

import punq
from fastapi import Request
from typing import Any

from bootstrap.config import AppConfig
from bootstrap.providers.database import (
    PostgresClientProvider, SQLiteClientProvider, UnifiedDatabaseProvider
)
from bootstrap.providers.redis_provider import RedisProvider
from bootstrap.providers.circuit_breaker import CircuitBreakerProvider
from database.clients.postgres_client import PostgresClient
from database.clients.sqlite_client import SQLiteClient
from database.clients.unified_database_client import UnifiedDatabaseClient
from redis import asyncio as aioredis
from middleware.circuit_breaker import CircuitBreakerGroup

# ---- BranchService 관련 import ----
from core.branch.service import BranchService
from bootstrap.providers.branch import BranchProvider
from bootstrap.providers.event import EventProvider


def init_container(config: AppConfig) -> punq.Container:
    """Initialize the DI container with all providers."""
    container = punq.Container()

    # 1. Register Core Configuration
    container.register(AppConfig, instance=config)

    # 2. Register Redis and Circuit Breaker first as they are low-level
    if config.redis:
        redis_provider = RedisProvider()
        container.register(aioredis.Redis, factory=redis_provider.provide, scope=punq.Scope.singleton)
        
        cb_provider = CircuitBreakerProvider(redis_provider)
        container.register(CircuitBreakerGroup, factory=cb_provider.provide, scope=punq.Scope.singleton)

    # 3. Register Individual Database Clients
    if config.postgres:
        pg_provider = PostgresClientProvider(container)
        container.register(PostgresClient, factory=pg_provider.provide, scope=punq.Scope.singleton)
    
    if config.sqlite:
        sqlite_provider = SQLiteClientProvider(container)
        container.register(SQLiteClient, factory=sqlite_provider.provide, scope=punq.Scope.singleton)

    # 4. Register the Unified Database Client
    unified_db_provider = UnifiedDatabaseProvider(container)
    container.register(UnifiedDatabaseClient, factory=unified_db_provider.provide, scope=punq.Scope.singleton)
    
    # ... Register other providers like SchemaProvider, ValidationProvider etc. here ...

    return container


# We will attach the container to the app state instead of using a global variable.
# This makes it accessible via the request object.

# Dependency provider functions for FastAPI routes
def get_db_client(request: Request) -> UnifiedDatabaseClient:
    return request.app.state.container.resolve(UnifiedDatabaseClient)

def get_redis_client(request: Request) -> aioredis.Redis:
    return request.app.state.container.resolve(aioredis.Redis)

def get_circuit_breaker_group(request: Request) -> CircuitBreakerGroup:
    return request.app.state.container.resolve(CircuitBreakerGroup)

# ---------------------------------------------------------------------------
# BranchService Dependency
# ---------------------------------------------------------------------------

# 내부 캐시를 통해 BranchProvider 인스턴스를 재사용합니다.
_branch_provider_cache: dict[str, Any] = {}


async def get_branch_service(request: Request) -> BranchService:  # pragma: no cover
    """FastAPI dependency: BranchService 를 비동기 제공

    1. 컨테이너에서 UnifiedDatabaseClient 를 가져옵니다.
    2. EventProvider 를 전역 캐시에서 재사용합니다.
    3. BranchProvider 를 생성/캐시한 뒤 BranchService 를 반환합니다.
    """

    # 1) 필요 의존성 확보
    container = request.app.state.container
    db_client = container.resolve(UnifiedDatabaseClient)

    # 2) EventProvider 는 상태를 가지지 않으므로 싱글톤처럼 사용 가능
    event_provider = _branch_provider_cache.get("event_provider")
    if event_provider is None:
        event_provider = EventProvider()
        _branch_provider_cache["event_provider"] = event_provider

    # 3) BranchProvider 준비 & 캐싱
    branch_provider = _branch_provider_cache.get("branch_provider")
    if branch_provider is None:
        branch_provider = BranchProvider(
            db_client=db_client,
            event_provider=event_provider,
        )
        _branch_provider_cache["branch_provider"] = branch_provider

    # 4) BranchService 인스턴스 제공 (비동기)
    branch_service: BranchService = await branch_provider.provide()
    return branch_service

# ---------------------------------------------------------------------------
# SchemaService Dependency (임시 스텁)
# ---------------------------------------------------------------------------

class _DummySchemaService:  # pragma: no cover
    """임시 스텁 SchemaService – E2E 테스트용."""

    async def create_object_type(self, *args, **kwargs):
        return None

    async def get_object_type(self, *args, **kwargs):
        return None


async def get_schema_service(request: Request) -> Any:  # pragma: no cover
    """FastAPI dependency: SchemaService (임시).

    실제 구현체가 준비되기 전까지 테스트를 위해 더미 객체를 반환합니다.
    """
    # 이후 컨테이너에서 resolve 하도록 변경 예정
    return _DummySchemaService()

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

# ... Add other dependency providers for your services as needed ...