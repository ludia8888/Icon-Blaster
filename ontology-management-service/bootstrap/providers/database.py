"""Database providers for all database clients"""
import punq
from typing import Optional

from bootstrap.config import AppConfig
from database.clients.postgres_client import PostgresClient
from database.clients.sqlite_client import SQLiteClient
from database.clients.unified_database_client import UnifiedDatabaseClient
# from database.clients.terminusdb_client import TerminusDBClient # TODO
from .base import SingletonProvider


class PostgresClientProvider(SingletonProvider[PostgresClient]):
    """Provider for PostgresClient instances."""

    def __init__(self, container: punq.Container):
        super().__init__()
        self._container = container
        self._instance: Optional[PostgresClient] = None

    async def _create(self) -> PostgresClient:
        config = self._container.resolve(AppConfig)
        if not config.postgres:
            raise ValueError("PostgreSQL configuration is missing.")
        client = PostgresClient(config.postgres.model_dump())
        await client.connect()
        return client

    async def startup(self):
        client = await self.provide()
        await client.connect()

    async def shutdown(self):
        if self._instance is not None:
            client = await self.provide()
            await client.close()


class SQLiteClientProvider(SingletonProvider[SQLiteClient]):
    """Provides a singleton instance of the SQLiteClient."""
    def __init__(self, container: punq.Container):
        super().__init__()
        self._container = container

    async def _create(self) -> SQLiteClient:
        config = self._container.resolve(AppConfig)
        if not config.sqlite:
            raise ValueError("SQLite configuration is missing.")
        client = SQLiteClient(config.sqlite.model_dump())
        await client.connect()
        return client

    async def startup(self):
        client = await self.provide()
        await client.connect()

    async def shutdown(self):
        if self._instance is not None:
            client = await self.provide()
            await client.close()

# class TerminusDBClientProvider... # TODO: Implement when client is fixed

class UnifiedDatabaseProvider(SingletonProvider[UnifiedDatabaseClient]):
    """Provider for UnifiedDatabaseClient instances."""

    def __init__(self, container: punq.Container):
        self._container = container

    async def _create(self) -> UnifiedDatabaseClient:
        postgres_client: Optional[PostgresClient] = None
        sqlite_client: Optional[SQLiteClient] = None

        if self._container.is_registered(PostgresClient):
            postgres_client = self._container.resolve(PostgresClient)

        if self._container.is_registered(SQLiteClient):
            sqlite_client = self._container.resolve(SQLiteClient)
        
        # ... TerminusDB client can be resolved here in the future
        
        client = UnifiedDatabaseClient(
            postgres_client=postgres_client,
            sqlite_client=sqlite_client
        )
        return client
    
    async def shutdown(self) -> None:
        pass