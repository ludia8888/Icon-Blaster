"""
Secure SQLite Client for ontology-management-service
This version includes protection against SQL injection vulnerabilities
"""
import asyncio
import re
from typing import Dict, Any, List, Optional, Set

from shared.database.sqlite_connector import SQLiteConnector
from common_logging.setup import get_logger

logger = get_logger(__name__)


class SQLiteClientSecure:
    """
    Secure client for interacting with SQLite.
    Implements SQL injection protection for table names and numeric parameters.
    """
    
    # Whitelist of allowed table names
    ALLOWED_TABLES: Set[str] = {
        'branches', 'commits', 'nodes', 'properties', 'semantic_types',
        'struct_types', 'events', 'audit_logs', 'users', 'permissions',
        'schemas', 'migrations', 'tasks', 'jobs', 'metadata', 'versions',
        'hooks', 'webhooks', 'validations', 'configurations', 'sessions',
        'cache', 'locks', 'notifications', 'subscriptions', 'embeddings'
    }
    
    # Maximum allowed values for LIMIT and OFFSET
    MAX_LIMIT = 10000
    MAX_OFFSET = 1000000
    
    # Pattern for valid table names (alphanumeric and underscore only)
    TABLE_NAME_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

    def __init__(self, config: Dict[str, Any]):
        self._connector = SQLiteConnector(**config)
        self._connected = False
        self._lock = asyncio.Lock()
        
        # Allow custom table whitelist from config
        if 'allowed_tables' in config:
            self.ALLOWED_TABLES.update(config['allowed_tables'])

    async def connect(self):
        """Initialize the connection pool."""
        async with self._lock:
            if self._connected:
                return
            await self._connector.initialize()
            self._connected = True
            logger.info("Connected to SQLite (Secure)")

    async def close(self):
        """Close the connection pool."""
        async with self._lock:
            if self._connected:
                await self._connector.close()
                self._connected = False
                logger.info("Closed connection to SQLite (Secure)")
    
    @property
    def is_connected(self) -> bool:
        """Check if the client is connected."""
        return self._connected
    
    def _validate_table_name(self, table: str) -> str:
        """
        Validate and sanitize table name to prevent SQL injection.
        
        :param table: The table name to validate
        :return: The validated table name
        :raises ValueError: If table name is invalid or not whitelisted
        """
        # Check if table name matches valid pattern
        if not self.TABLE_NAME_PATTERN.match(table):
            raise ValueError(f"Invalid table name format: {table}")
        
        # Check if table is in whitelist
        if table not in self.ALLOWED_TABLES:
            raise ValueError(f"Table '{table}' is not in the allowed tables whitelist")
        
        return table
    
    def _validate_numeric_param(self, value: Optional[int], param_name: str, 
                               max_value: int) -> Optional[int]:
        """
        Validate numeric parameters like LIMIT and OFFSET.
        
        :param value: The value to validate
        :param param_name: Name of the parameter for error messages
        :param max_value: Maximum allowed value
        :return: The validated value
        :raises ValueError: If value is invalid
        """
        if value is None:
            return None
        
        if not isinstance(value, int):
            raise ValueError(f"{param_name} must be an integer, got {type(value)}")
        
        if value < 0:
            raise ValueError(f"{param_name} must be non-negative, got {value}")
        
        if value > max_value:
            raise ValueError(f"{param_name} exceeds maximum allowed value of {max_value}, got {value}")
        
        return value
    
    def _validate_column_name(self, column: str) -> str:
        """
        Validate column name to prevent SQL injection.
        
        :param column: The column name to validate
        :return: The validated column name
        :raises ValueError: If column name is invalid
        """
        # Allow alphanumeric, underscore, and dot (for table.column notation)
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_.]*$', column):
            raise ValueError(f"Invalid column name: {column}")
        return column

    async def create(self, table: str, data: Dict[str, Any]) -> int:
        """
        Insert a new record into a table with SQL injection protection.
        
        :param table: The name of the table.
        :param data: A dictionary of column-value pairs.
        :return: The last inserted row id.
        """
        if not self.is_connected:
            raise ConnectionError("SQLiteClient is not connected.")
        
        # Validate table name
        safe_table = self._validate_table_name(table)
        
        # Validate column names
        safe_columns = []
        for col in data.keys():
            safe_columns.append(self._validate_column_name(col))
        
        columns = ", ".join(safe_columns)
        placeholders = ", ".join([f":{key}" for key in data.keys()])
        
        # Use the validated table name
        query = f"INSERT INTO {safe_table} ({columns}) VALUES ({placeholders})"
        
        return await self._connector.execute(query, params=data)

    async def read(
        self,
        table: str,
        query: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Read records from a table with SQL injection protection.
        """
        if not self.is_connected:
            raise ConnectionError("SQLiteClient is not connected.")
        
        # Validate table name
        safe_table = self._validate_table_name(table)
        
        # Validate limit and offset
        safe_limit = self._validate_numeric_param(limit, "LIMIT", self.MAX_LIMIT)
        safe_offset = self._validate_numeric_param(offset, "OFFSET", self.MAX_OFFSET)
        
        base_query = f"SELECT * FROM {safe_table}"
        conditions = []
        values = {}
        
        if query:
            for key, value in query.items():
                safe_key = self._validate_column_name(key)
                conditions.append(f"{safe_key} = :{key}")
                values[key] = value
        
        if conditions:
            base_query += " WHERE " + " AND ".join(conditions)
        
        if safe_limit is not None:
            base_query += f" LIMIT {safe_limit}"
        if safe_offset is not None:
            base_query += f" OFFSET {safe_offset}"
            
        return await self._connector.fetch_all(base_query, params=values)

    async def update(self, table: str, doc_id: Any, data: Dict[str, Any]) -> int:
        """
        Update a record in a table with SQL injection protection.

        :param table: The name of the table.
        :param doc_id: The primary key of the record to update.
        :param data: A dictionary of column-value pairs to update.
        :return: The number of affected rows.
        """
        if not self.is_connected:
            raise ConnectionError("SQLiteClient is not connected.")

        # Validate table name
        safe_table = self._validate_table_name(table)
        
        # Validate column names and build SET clause
        set_parts = []
        for key in data.keys():
            safe_key = self._validate_column_name(key)
            set_parts.append(f"{safe_key} = :{key}")
        
        set_clause = ", ".join(set_parts)
        query = f"UPDATE {safe_table} SET {set_clause} WHERE id = :doc_id"
        
        params = data.copy()
        params["doc_id"] = doc_id
        
        return await self._connector.execute(query, params=params)

    async def delete(self, table: str, doc_id: Any) -> int:
        """
        Delete a record from a table with SQL injection protection.

        :param table: The name of the table.
        :param doc_id: The primary key of the record to delete.
        :return: The number of affected rows.
        """
        if not self.is_connected:
            raise ConnectionError("SQLiteClient is not connected.")

        # Validate table name
        safe_table = self._validate_table_name(table)
        
        query = f"DELETE FROM {safe_table} WHERE id = :doc_id"
        params = {"doc_id": doc_id}
        
        return await self._connector.execute(query, params=params)
    
    async def execute_raw(self, query: str, params: Optional[Dict[str, Any]] = None) -> int:
        """
        Execute a raw SQL query.
        WARNING: This method does not provide SQL injection protection.
        Only use with hardcoded queries, never with user input.
        
        :param query: The SQL query to execute
        :param params: Query parameters
        :return: Number of affected rows
        """
        if not self.is_connected:
            raise ConnectionError("SQLiteClient is not connected.")
        
        logger.warning("Executing raw SQL query - ensure query is safe from injection")
        return await self._connector.execute(query, params=params or {})
    
    async def add_allowed_table(self, table_name: str):
        """
        Dynamically add a table to the allowed tables whitelist.
        This should only be called by administrative functions.
        
        :param table_name: The table name to add
        """
        if self._validate_column_name(table_name):  # Use same validation as columns
            self.ALLOWED_TABLES.add(table_name)
            logger.info(f"Added '{table_name}' to allowed tables whitelist")