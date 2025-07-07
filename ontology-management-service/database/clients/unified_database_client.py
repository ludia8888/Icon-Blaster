"""
Unified Database Client - Single interface for all database operations

DESIGN INTENT:
This module provides a unified database abstraction that:
- Eliminates duplicate database connectors (SQLite, PostgreSQL)
- Uses TerminusDB as primary data store with built-in audit
- Provides fallback to PostgreSQL/SQLite for specific use cases
- Reduces boilerplate and transaction management complexity

ARCHITECTURE:
1. TerminusDB as primary for:
   - Business data (schemas, objects, branches)
   - Audit trail (using built-in commit history)
   - Time-travel queries (using commit snapshots)

2. PostgreSQL as secondary for:
   - User authentication data
   - Distributed locks
   - High-frequency metrics
   - Session management

3. SQLite as fallback for:
   - Local development
   - Testing
   - Offline scenarios

BENEFITS:
- Single transaction boundary where possible
- Consistent error handling
- Unified connection pooling
- Reduced data fragmentation
"""

import asyncio
import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, List, Optional, Union, AsyncIterator, TypeVar
from contextlib import asynccontextmanager
import logging

# from terminusdb_client import WOQLClient
# from terminusdb_client.errors import DatabaseError

# from shared.database.postgres_connector import PostgresConnector
# from shared.database.sqlite_connector import SQLiteConnector
from .postgres_client import PostgresClient
from .sqlite_client import SQLiteClient
# Placeholder for the yet-to-be-fixed TerminusDB client
# from .terminusdb_client import TerminusDBClient

from common_logging.setup import get_logger
from core.validation.ports import TerminusPort

logger = get_logger(__name__)

T = TypeVar('T')


class DatabaseBackend(Enum):
    """Available database backends"""
    TERMINUSDB = "terminusdb"
    POSTGRESQL = "postgresql"
    SQLITE = "sqlite"
    MEMORY = "memory"  # For testing


class QueryType(Enum):
    """Types of database operations"""
    READ = "read"
    WRITE = "write"
    AUDIT = "audit"
    ANALYTICS = "analytics"
    TIMESERIES = "timeseries"


class UnifiedDatabaseClient:
    """
    Unified database client that intelligently routes operations
    to the appropriate backend based on data type and use case
    """
    
    def __init__(
        self,
        # terminus_client: Optional[TerminusDBClient], # TODO: Re-enable when fixed
        postgres_client: Optional[PostgresClient] = None,
        sqlite_client: Optional[SQLiteClient] = None,
        default_backend: DatabaseBackend = DatabaseBackend.TERMINUSDB
    ):
        # self.terminus_client = terminus_client
        self.postgres_client = postgres_client
        self.sqlite_client = sqlite_client
        self.default_backend = default_backend
        
        # Connection state
        self._connected = False
        self._lock = asyncio.Lock()
        
        # Routing rules
        self._routing_rules = {
            # Business data → TerminusDB
            "schema": DatabaseBackend.TERMINUSDB,
            "object": DatabaseBackend.TERMINUSDB,
            "branch": DatabaseBackend.TERMINUSDB,
            "ontology": DatabaseBackend.TERMINUSDB,
            
            # User/Auth data → PostgreSQL (if available)
            "user": DatabaseBackend.POSTGRESQL,
            "session": DatabaseBackend.POSTGRESQL,
            "auth_token": DatabaseBackend.POSTGRESQL,
            
            # Metrics/Timeseries → PostgreSQL
            "metric": DatabaseBackend.POSTGRESQL,
            "timeseries": DatabaseBackend.POSTGRESQL,
            
            # Locks → PostgreSQL
            "lock": DatabaseBackend.POSTGRESQL,
            
            # Audit → TerminusDB (using commit history)
            "audit": DatabaseBackend.TERMINUSDB
        }
    
    async def connect(self):
        """Connect to all configured backends"""
        async with self._lock:
            if self._connected:
                return
            
            # if self.terminus_client:
            #     await self.terminus_client.connect()
            
            if self.postgres_client:
                await self.postgres_client.connect()
            
            if self.sqlite_client:
                await self.sqlite_client.connect()
            
            self._connected = True
            logger.info("Unified database client connected")
    
    def _get_backend_for_operation(self, collection: str, operation: QueryType) -> DatabaseBackend:
        """Determine which backend to use for an operation"""
        # Check routing rules
        for pattern, backend in self._routing_rules.items():
            if pattern in collection.lower():
                # Check if backend is available
                if backend == DatabaseBackend.POSTGRESQL and (not self.postgres_client or not self.postgres_client.is_connected):
                    # Fallback to SQLite
                    return DatabaseBackend.SQLITE
                return backend
        
        # Default routing
        return self.default_backend
    
    async def create(
        self,
        collection: str,
        document: Dict[str, Any],
        author: str = "system",
        message: Optional[str] = None
    ) -> Any:
        """Create a document in the appropriate backend."""
        backend = self._get_backend_for_operation(collection, QueryType.WRITE)

        if backend == DatabaseBackend.POSTGRESQL:
            if not self.postgres_client:
                raise ConnectionError("Postgres client not configured.")
            return await self.postgres_client.create(collection, document)
        elif backend == DatabaseBackend.SQLITE:
            if not self.sqlite_client:
                raise ConnectionError("SQLite client not configured.")
            return await self.sqlite_client.create(collection, document)
        elif backend == DatabaseBackend.TERMINUSDB:
            # if not self.terminus_client:
            #     raise ConnectionError("TerminusDB client not configured.")
            # return await self.terminus_client.create(collection, document, author, message)
            raise NotImplementedError("TerminusDB client is not yet integrated.")
        else:
            raise ValueError(f"Unsupported backend for create: {backend}")
    
    async def read(
        self,
        collection: str,
        query: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Read documents from the appropriate backend."""
        backend = self._get_backend_for_operation(collection, QueryType.READ)

        if backend == DatabaseBackend.POSTGRESQL:
            if not self.postgres_client:
                raise ConnectionError("Postgres client not configured.")
            return await self.postgres_client.read(collection, query, limit, offset)
        elif backend == DatabaseBackend.SQLITE:
            if not self.sqlite_client:
                raise ConnectionError("SQLite client not configured.")
            return await self.sqlite_client.read(collection, query, limit, offset)
        elif backend == DatabaseBackend.TERMINUSDB:
            # if not self.terminus_client:
            #     raise ConnectionError("TerminusDB client not configured.")
            # return await self.terminus_client.read(collection, query, limit, offset)
            raise NotImplementedError("TerminusDB client is not yet integrated.")
        else:
            raise ValueError(f"Unsupported backend for read: {backend}")
    
    async def update(
        self,
        collection: str,
        doc_id: str,
        updates: Dict[str, Any],
        author: str = "system",
        message: Optional[str] = None
    ) -> bool:
        """Update a document in the appropriate backend."""
        backend = self._get_backend_for_operation(collection, QueryType.WRITE)

        if backend == DatabaseBackend.POSTGRESQL:
            if not self.postgres_client:
                raise ConnectionError("Postgres client not configured.")
            affected_rows = await self.postgres_client.update(collection, doc_id, updates)
            return affected_rows > 0
        elif backend == DatabaseBackend.SQLITE:
            if not self.sqlite_client:
                raise ConnectionError("SQLite client not configured.")
            affected_rows = await self.sqlite_client.update(collection, doc_id, updates)
            return affected_rows > 0
        elif backend == DatabaseBackend.TERMINUSDB:
            # if not self.terminus_client:
            #     raise ConnectionError("TerminusDB client not configured.")
            # return await self.terminus_client.update(collection, doc_id, updates, author, message)
            raise NotImplementedError("TerminusDB client is not yet integrated.")
        else:
            raise ValueError(f"Unsupported backend for update: {backend}")
    
    async def delete(
        self,
        collection: str,
        doc_id: str,
        author: str = "system",
        message: Optional[str] = None
    ) -> bool:
        """Delete a document from the appropriate backend."""
        backend = self._get_backend_for_operation(collection, QueryType.WRITE)

        if backend == DatabaseBackend.POSTGRESQL:
            if not self.postgres_client:
                raise ConnectionError("Postgres client not configured.")
            affected_rows = await self.postgres_client.delete(collection, doc_id)
            return affected_rows > 0
        elif backend == DatabaseBackend.SQLITE:
            if not self.sqlite_client:
                raise ConnectionError("SQLite client not configured.")
            affected_rows = await self.sqlite_client.delete(collection, doc_id)
            return affected_rows > 0
        elif backend == DatabaseBackend.TERMINUSDB:
            # if not self.terminus_client:
            #     raise ConnectionError("TerminusDB client not configured.")
            # return await self.terminus_client.delete(collection, doc_id, author, message)
            raise NotImplementedError("TerminusDB client is not yet integrated.")
        else:
            raise ValueError(f"Unsupported backend for delete: {backend}")
    
    # Audit-specific methods using TerminusDB commit history
    
    async def get_audit_log(
        self,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        author: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get audit log for resources.
        This currently only supports TerminusDB.
        """
        # if not self.terminus_client:
        #     logger.error("TerminusDB not connected for audit log")
        #     return []
        
        # This functionality is deferred until TerminusDB client is fixed.
        logger.warning("get_audit_log is not implemented for non-TerminusDB backends.")
        return []
    
    async def get_document_at_time(
        self,
        collection: str,
        doc_id: str,
        timestamp: datetime
    ) -> Optional[Dict[str, Any]]:
        """
        Get document state at specific point in time
        
        Uses TerminusDB's time-travel capability
        """
        # if not self.terminus_client:
        #     return None
        
        # try:
        #     # Find commit closest to timestamp
        #     history = self.terminus_client.get_commit_history()
        #     
        #     target_commit = None
        #     for commit in history:
        #         commit_time = datetime.fromisoformat(commit["timestamp"])
        #         if commit_time <= timestamp:
        #             target_commit = commit["identifier"]
        #             break
        #     
        #     if not target_commit:
        #         return None
        #     
        #     # Get document at that commit
        #     self.terminus_client.checkout(target_commit)
        #     doc = self.terminus_client.get_document(doc_id)
        #     
        #     # Return to HEAD
        #     self.terminus_client.checkout("main")
        #     
        #     return doc
        #     
        # except Exception as e:
        #     logger.error(f"Failed to get document at time: {e}")
        #     return None
        
        # This functionality is deferred until TerminusDB client is fixed.
        logger.warning("get_document_at_time is not implemented for non-TerminusDB backends.")
        return None
    
    def _format_diff_as_changes(self, diff: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Format TerminusDB diff as change entries"""
        changes = []
        
        for operation in diff.get("operations", []):
            change = {
                "operation": operation["@type"],
                "document_id": operation.get("document", {}).get("@id"),
                "document_type": operation.get("document", {}).get("@type")
            }
            
            if operation["@type"] == "UpdateDocument":
                change["before"] = operation.get("before")
                change["after"] = operation.get("after")
            elif operation["@type"] == "InsertDocument":
                change["created"] = operation.get("document")
            elif operation["@type"] == "DeleteDocument":
                change["deleted"] = operation.get("document")
            
            changes.append(change)
        
        return changes
    
    async def close(self):
        """Close connections to all configured backends."""
        async with self._lock:
            if not self._connected:
                return
            
            # if self.terminus_client:
            #     await self.terminus_client.close()
            if self.postgres_client:
                await self.postgres_client.close()
            if self.sqlite_client:
                await self.sqlite_client.close()

            self._connected = False
            logger.info("Unified database client disconnected")


async def get_unified_database_client() -> UnifiedDatabaseClient:
    """
    Factory function for UnifiedDatabaseClient (to be implemented in DI provider)
    """
    # This function will be moved/implemented in a dependency injection provider
    # where it will have access to AppConfig to initialize the individual clients.
    raise NotImplementedError("This factory should be implemented in the DI container.")