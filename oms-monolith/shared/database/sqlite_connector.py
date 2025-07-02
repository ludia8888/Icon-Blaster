"""
Common SQLite Connector
Provides shared SQLite connection management for multiple services

DESIGN INTENT:
This module consolidates SQLite connection patterns used by:
- Audit Database (audit logs)
- Issue Tracking Database (issue management)

FEATURES:
- Async connection management with aiosqlite
- Connection pooling and lifecycle management
- Automatic schema migration support
- Transaction management
- Query logging and metrics
- Error handling and retries

USAGE:
    connector = SQLiteConnector("audit.db")
    await connector.initialize()
    
    async with connector.get_connection() as conn:
        await conn.execute("SELECT * FROM events")
"""

import os
import aiosqlite
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any, AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
import logging

from utils.logger import get_logger

logger = get_logger(__name__)


class SQLiteConnectorError(Exception):
    """Base exception for SQLite connector operations"""
    pass


class SQLiteConnector:
    """
    Common SQLite database connector with connection pooling and migration support
    """
    
    def __init__(
        self, 
        db_name: str,
        db_dir: str = "data",
        enable_wal: bool = True,
        busy_timeout: int = 30000,
        max_connections: int = 5,
        enable_foreign_keys: bool = True
    ):
        """
        Initialize SQLite connector
        
        Args:
            db_name: Database filename
            db_dir: Directory to store database file
            enable_wal: Enable Write-Ahead Logging for better concurrency
            busy_timeout: Timeout in milliseconds for busy database
            max_connections: Maximum number of connections in pool
            enable_foreign_keys: Enable foreign key constraints
        """
        self.db_name = db_name
        self.db_dir = db_dir
        self.db_path = os.path.join(db_dir, db_name)
        self.enable_wal = enable_wal
        self.busy_timeout = busy_timeout
        self.max_connections = max_connections
        self.enable_foreign_keys = enable_foreign_keys
        
        # Connection pool
        self._connections: List[aiosqlite.Connection] = []
        self._available_connections: asyncio.Queue = asyncio.Queue(maxsize=max_connections)
        self._lock = asyncio.Lock()
        self._initialized = False
        
        # Statistics
        self.stats = {
            "connections_created": 0,
            "connections_reused": 0,
            "queries_executed": 0,
            "errors": 0
        }
    
    async def initialize(self, migrations: Optional[List[str]] = None):
        """
        Initialize database and connection pool
        
        Args:
            migrations: List of SQL migration scripts to run
        """
        if self._initialized:
            return
        
        async with self._lock:
            if self._initialized:
                return
            
            try:
                # Create data directory if it doesn't exist
                Path(self.db_dir).mkdir(parents=True, exist_ok=True)
                
                # Create initial connection for setup
                async with aiosqlite.connect(self.db_path) as conn:
                    # Enable WAL mode for better concurrency
                    if self.enable_wal:
                        await conn.execute("PRAGMA journal_mode=WAL")
                    
                    # Set busy timeout
                    await conn.execute(f"PRAGMA busy_timeout={self.busy_timeout}")
                    
                    # Enable foreign keys
                    if self.enable_foreign_keys:
                        await conn.execute("PRAGMA foreign_keys=ON")
                    
                    # Run migrations if provided
                    if migrations:
                        for migration in migrations:
                            try:
                                await conn.executescript(migration)
                                await conn.commit()
                            except Exception as e:
                                logger.error(f"Migration failed: {e}")
                                raise SQLiteConnectorError(f"Migration failed: {e}")
                
                # Initialize connection pool
                for _ in range(self.max_connections):
                    conn = await self._create_connection()
                    self._connections.append(conn)
                    await self._available_connections.put(conn)
                
                self._initialized = True
                logger.info(f"SQLite connector initialized: {self.db_path}")
                
            except Exception as e:
                logger.error(f"Failed to initialize SQLite connector: {e}")
                raise SQLiteConnectorError(f"Initialization failed: {e}")
    
    async def _create_connection(self) -> aiosqlite.Connection:
        """Create a new database connection with proper settings"""
        conn = await aiosqlite.connect(self.db_path)
        
        # Apply connection settings
        if self.enable_wal:
            await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute(f"PRAGMA busy_timeout={self.busy_timeout}")
        if self.enable_foreign_keys:
            await conn.execute("PRAGMA foreign_keys=ON")
        
        # Enable row factory for dict-like access
        conn.row_factory = aiosqlite.Row
        
        self.stats["connections_created"] += 1
        return conn
    
    @asynccontextmanager
    async def get_connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """
        Get a connection from the pool
        
        Yields:
            Database connection
        """
        if not self._initialized:
            raise SQLiteConnectorError("Connector not initialized")
        
        conn = None
        try:
            # Get connection from pool with timeout
            conn = await asyncio.wait_for(
                self._available_connections.get(),
                timeout=5.0
            )
            self.stats["connections_reused"] += 1
            
            # Verify connection is still valid
            try:
                await conn.execute("SELECT 1")
            except Exception:
                # Connection is dead, create a new one
                await conn.close()
                conn = await self._create_connection()
            
            yield conn
            
        except asyncio.TimeoutError:
            raise SQLiteConnectorError("Connection pool exhausted")
        finally:
            # Return connection to pool
            if conn:
                await self._available_connections.put(conn)
    
    async def execute(
        self, 
        query: str, 
        params: Optional[Dict[str, Any]] = None,
        commit: bool = True
    ) -> int:
        """
        Execute a single query
        
        Args:
            query: SQL query to execute
            params: Query parameters
            commit: Whether to commit the transaction
            
        Returns:
            Number of affected rows
        """
        async with self.get_connection() as conn:
            try:
                cursor = await conn.execute(query, params or {})
                if commit:
                    await conn.commit()
                self.stats["queries_executed"] += 1
                return cursor.rowcount
            except Exception as e:
                self.stats["errors"] += 1
                logger.error(f"Query execution failed: {e}")
                raise SQLiteConnectorError(f"Query failed: {e}")
    
    async def execute_many(
        self, 
        query: str, 
        params_list: List[Dict[str, Any]],
        commit: bool = True
    ) -> int:
        """
        Execute a query with multiple parameter sets
        
        Args:
            query: SQL query to execute
            params_list: List of parameter dictionaries
            commit: Whether to commit the transaction
            
        Returns:
            Total number of affected rows
        """
        async with self.get_connection() as conn:
            try:
                total_rows = 0
                for params in params_list:
                    cursor = await conn.execute(query, params)
                    total_rows += cursor.rowcount
                
                if commit:
                    await conn.commit()
                
                self.stats["queries_executed"] += len(params_list)
                return total_rows
            except Exception as e:
                self.stats["errors"] += 1
                logger.error(f"Batch execution failed: {e}")
                raise SQLiteConnectorError(f"Batch execution failed: {e}")
    
    async def fetch_one(
        self, 
        query: str, 
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch a single row
        
        Args:
            query: SQL query to execute
            params: Query parameters
            
        Returns:
            Row as dictionary or None
        """
        async with self.get_connection() as conn:
            try:
                cursor = await conn.execute(query, params or {})
                row = await cursor.fetchone()
                self.stats["queries_executed"] += 1
                return dict(row) if row else None
            except Exception as e:
                self.stats["errors"] += 1
                logger.error(f"Fetch one failed: {e}")
                raise SQLiteConnectorError(f"Fetch failed: {e}")
    
    async def fetch_all(
        self, 
        query: str, 
        params: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch all rows
        
        Args:
            query: SQL query to execute
            params: Query parameters
            
        Returns:
            List of rows as dictionaries
        """
        async with self.get_connection() as conn:
            try:
                cursor = await conn.execute(query, params or {})
                rows = await cursor.fetchall()
                self.stats["queries_executed"] += 1
                return [dict(row) for row in rows]
            except Exception as e:
                self.stats["errors"] += 1
                logger.error(f"Fetch all failed: {e}")
                raise SQLiteConnectorError(f"Fetch failed: {e}")
    
    @asynccontextmanager
    async def transaction(self):
        """
        Execute operations within a transaction
        
        Usage:
            async with connector.transaction() as conn:
                await conn.execute("INSERT ...")
                await conn.execute("UPDATE ...")
                # Automatically commits on success, rolls back on error
        """
        async with self.get_connection() as conn:
            try:
                await conn.execute("BEGIN")
                yield conn
                await conn.commit()
            except Exception as e:
                await conn.rollback()
                raise SQLiteConnectorError(f"Transaction failed: {e}")
    
    async def close(self):
        """Close all connections and cleanup"""
        async with self._lock:
            for conn in self._connections:
                await conn.close()
            self._connections.clear()
            self._initialized = False
            logger.info(f"SQLite connector closed: {self.db_path}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get connector statistics"""
        return {
            **self.stats,
            "pool_size": len(self._connections),
            "available_connections": self._available_connections.qsize()
        }


# Convenience functions for backward compatibility

_connectors: Dict[str, SQLiteConnector] = {}


async def get_sqlite_connector(
    db_name: str,
    **kwargs
) -> SQLiteConnector:
    """
    Get or create a SQLite connector instance
    
    Args:
        db_name: Database name
        **kwargs: Additional connector parameters
        
    Returns:
        SQLiteConnector instance
    """
    if db_name not in _connectors:
        _connectors[db_name] = SQLiteConnector(db_name, **kwargs)
    return _connectors[db_name]