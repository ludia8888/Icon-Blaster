"""Database provider for TerminusDB connections"""

import os
from database.clients.unified_database_client import UnifiedDatabaseClient
from .base import SingletonProvider

class DatabaseProvider(SingletonProvider[UnifiedDatabaseClient]):
    """Provider for database client instances"""
    
    def __init__(self, endpoint: str | None = None, team: str | None = None, 
                 db: str | None = None, user: str | None = None, 
                 key: str | None = None):
        super().__init__()
        self.endpoint = endpoint or os.getenv("TERMINUSDB_ENDPOINT", "http://localhost:6363")
        self.team = team or os.getenv("TERMINUSDB_TEAM", "admin")
        self.db = db or os.getenv("TERMINUSDB_DB", "oms_db")
        self.user = user or os.getenv("TERMINUSDB_USER", "admin")
        self.key = key or os.getenv("TERMINUSDB_KEY", "root")
    
    async def _create(self) -> UnifiedDatabaseClient:
        """Create and initialize database client"""
        from database.clients.unified_database_client import DatabaseConfig
        
        config = DatabaseConfig(
            endpoint=self.endpoint,
            team=self.team,
            db=self.db,
            user=self.user,
            key=self.key
        )
        client = await UnifiedDatabaseClient.create(config)
        await client.connect()
        return client
    
    async def shutdown(self) -> None:
        """Close database connection"""
        if self._instance:
            await self._instance.close()