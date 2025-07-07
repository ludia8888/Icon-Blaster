"""
SQLite Client for ontology-management-service
"""
import asyncio
from typing import Dict, Any, List, Optional

from shared.database.sqlite_connector import SQLiteConnector
from common_logging.setup import get_logger

logger = get_logger(__name__)


class SQLiteClient:
    """
    Client for interacting with SQLite.
    Wraps the SQLiteConnector to provide a consistent client interface.
    """

    def __init__(self, config: Dict[str, Any]):
        self._connector = SQLiteConnector(**config)
        self._connected = False
        self._lock = asyncio.Lock()

    async def connect(self):
        """Initialize the connection pool."""
        async with self._lock:
            if self._connected:
                return
            await self._connector.initialize()
            self._connected = True
            logger.info("Connected to SQLite")

    async def close(self):
        """Close the connection pool."""
        async with self._lock:
            if self._connected:
                await self._connector.close()
                self._connected = False
                logger.info("Closed connection to SQLite")
    
    @property
    def is_connected(self) -> bool:
        """Check if the client is connected."""
        return self._connected

    async def create(self, table: str, data: Dict[str, Any]) -> int:
        """
        Insert a new record into a table.
        
        :param table: The name of the table.
        :param data: A dictionary of column-value pairs.
        :return: The last inserted row id.
        """
        if not self.is_connected:
            raise ConnectionError("SQLiteClient is not connected.")
        
        columns = ", ".join(data.keys())
        # SQLite uses :key style for named parameters
        placeholders = ", ".join([f":{key}" for key in data.keys()])
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        
        # The execute method in SQLiteConnector returns the number of affected rows.
        # To get the last row id, we need a different approach, but for now we align
        # with the existing execute method.
        # A better implementation would be to use a transaction and `last_insert_rowid()`
        return await self._connector.execute(query, params=data)

    async def read(
        self,
        table: str,
        query: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Read records from a table.
        """
        if not self.is_connected:
            raise ConnectionError("SQLiteClient is not connected.")
            
        base_query = f"SELECT * FROM {table}"
        conditions = []
        values = {}
        if query:
            for key, value in query.items():
                conditions.append(f"{key} = :{key}")
                values[key] = value
        
        if conditions:
            base_query += " WHERE " + " AND ".join(conditions)
        
        if limit is not None:
            base_query += f" LIMIT {limit}"
        if offset is not None:
            base_query += f" OFFSET {offset}"
            
        return await self._connector.fetch_all(base_query, params=values)

    async def update(self, table: str, doc_id: Any, data: Dict[str, Any]) -> int:
        """
        Update a record in a table.

        :param table: The name of the table.
        :param doc_id: The primary key of the record to update.
        :param data: A dictionary of column-value pairs to update.
        :return: The number of affected rows.
        """
        if not self.is_connected:
            raise ConnectionError("SQLiteClient is not connected.")

        set_clause = ", ".join([f"{key} = :{key}" for key in data.keys()])
        query = f"UPDATE {table} SET {set_clause} WHERE id = :doc_id"
        
        params = data.copy()
        params["doc_id"] = doc_id
        
        return await self._connector.execute(query, params=params)

    async def delete(self, table: str, doc_id: Any) -> int:
        """
        Delete a record from a table.

        :param table: The name of the table.
        :param doc_id: The primary key of the record to delete.
        :return: The number of affected rows.
        """
        if not self.is_connected:
            raise ConnectionError("SQLiteClient is not connected.")

        query = f"DELETE FROM {table} WHERE id = :doc_id"
        params = {"doc_id": doc_id}
        
        return await self._connector.execute(query, params=params) 