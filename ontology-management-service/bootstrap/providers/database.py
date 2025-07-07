"""Database providers for all database clients"""
import punq
from typing import Optional

from bootstrap.config import AppConfig
# from database.clients.postgres_client import PostgresClient  # This doesn't exist
# from database.clients.sqlite_client import SQLiteClient  # This doesn't exist
from database.clients.postgres_client_secure import PostgresClientSecure
from database.clients.sqlite_client_secure import SQLiteClientSecure
from database.clients.unified_database_client import UnifiedDatabaseClient
# from database.clients.terminusdb_client import TerminusDBClient # TODO
from .base import SingletonProvider


class PostgresClientProvider(SingletonProvider[PostgresClientSecure]):
    """Provider for PostgresClient instances."""

    def __init__(self, container: punq.Container):
        super().__init__()
        self._container = container
        self._instance: Optional[PostgresClientSecure] = None

    async def _create(self) -> PostgresClientSecure:
        config = self._container.resolve(AppConfig)
        if not config.postgres:
            raise ValueError("PostgreSQL configuration is missing.")
        client = PostgresClientSecure(config.postgres.model_dump())
        await client.connect()
        return client

    async def startup(self):
        client = await self.provide()
        await client.connect()

    async def shutdown(self):
        if self._instance is not None:
            client = await self.provide()
            await client.close()


class SQLiteClientProvider(SingletonProvider[SQLiteClientSecure]):
    """Provides a singleton instance of the SQLiteClient."""
    def __init__(self, container: punq.Container):
        super().__init__()
        self._container = container

    async def _create(self) -> SQLiteClientSecure:
        config = self._container.resolve(AppConfig)
        if not config.sqlite:
            raise ValueError("SQLite configuration is missing.")
        client = SQLiteClientSecure(config.sqlite.model_dump())
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
        postgres_client: Optional[PostgresClientSecure] = None
        sqlite_client: Optional[SQLiteClientSecure] = None

        if self._container.is_registered(PostgresClientSecure):
            postgres_client = self._container.resolve(PostgresClientSecure)

        if self._container.is_registered(SQLiteClientSecure):
            sqlite_client = self._container.resolve(SQLiteClientSecure)
        
        # ... TerminusDB client can be resolved here in the future
        
        client = UnifiedDatabaseClient(
            postgres_client=postgres_client,
            sqlite_client=sqlite_client
        )
        return client
    
    async def shutdown(self) -> None:
        pass