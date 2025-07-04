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

from terminusdb_client import WOQLClient
from terminusdb_client.errors import DatabaseError

from shared.database.postgres_connector import PostgresConnector
from shared.database.sqlite_connector import SQLiteConnector
from utils.logger import get_logger

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
        terminus_config: Optional[Dict[str, Any]] = None,
        postgres_config: Optional[Dict[str, Any]] = None,
        sqlite_config: Optional[Dict[str, Any]] = None,
        default_backend: DatabaseBackend = DatabaseBackend.TERMINUSDB
    ):
        self.terminus_config = terminus_config or {
            "server_url": "http://localhost:6363",
            "user": "admin",
            "key": "root",
            "account": "admin",
            "team": "admin"
        }
        self.postgres_config = postgres_config
        self.sqlite_config = sqlite_config or {"db_name": "oms_fallback.db"}
        self.default_backend = default_backend
        
        # Client instances
        self._terminus_client: Optional[WOQLClient] = None
        self._postgres_connector: Optional[PostgresConnector] = None
        self._sqlite_connector: Optional[SQLiteConnector] = None
        
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
            
            # Connect to TerminusDB
            if self.default_backend == DatabaseBackend.TERMINUSDB or any(
                backend == DatabaseBackend.TERMINUSDB 
                for backend in self._routing_rules.values()
            ):
                await self._connect_terminus()
            
            # Connect to PostgreSQL if configured
            if self.postgres_config and (
                self.default_backend == DatabaseBackend.POSTGRESQL or
                DatabaseBackend.POSTGRESQL in self._routing_rules.values()
            ):
                await self._connect_postgres()
            
            # Connect to SQLite as fallback
            if not self._postgres_connector:
                await self._connect_sqlite()
            
            self._connected = True
            logger.info("Unified database client connected")
    
    async def _connect_terminus(self):
        """Connect to TerminusDB"""
        try:
            self._terminus_client = WOQLClient(**self.terminus_config)
            # Test connection
            self._terminus_client.connect()
            logger.info("Connected to TerminusDB")
        except Exception as e:
            logger.error(f"Failed to connect to TerminusDB: {e}")
            raise
    
    async def _connect_postgres(self):
        """Connect to PostgreSQL"""
        try:
            self._postgres_connector = PostgresConnector(**self.postgres_config)
            await self._postgres_connector.initialize()
            logger.info("Connected to PostgreSQL")
        except Exception as e:
            logger.warning(f"Failed to connect to PostgreSQL: {e}")
            # Don't raise - fallback to SQLite
    
    async def _connect_sqlite(self):
        """Connect to SQLite as fallback"""
        try:
            self._sqlite_connector = SQLiteConnector(**self.sqlite_config)
            await self._sqlite_connector.initialize()
            logger.info("Connected to SQLite (fallback)")
        except Exception as e:
            logger.error(f"Failed to connect to SQLite: {e}")
            raise
    
    def _get_backend_for_operation(self, collection: str, operation: QueryType) -> DatabaseBackend:
        """Determine which backend to use for an operation"""
        # Check routing rules
        for pattern, backend in self._routing_rules.items():
            if pattern in collection.lower():
                # Check if backend is available
                if backend == DatabaseBackend.POSTGRESQL and not self._postgres_connector:
                    # Fallback to SQLite
                    return DatabaseBackend.SQLITE
                return backend
        
        # Default routing
        return self.default_backend
    
    @asynccontextmanager
    async def transaction(self, message: str = "Transaction", author: str = "system"):
        """
        Unified transaction context across backends
        
        For TerminusDB: Creates a commit
        For PostgreSQL/SQLite: Standard transaction
        """
        terminus_transaction = None
        postgres_transaction = None
        sqlite_transaction = None
        
        try:
            # Start transactions where needed
            if self._terminus_client:
                # TerminusDB doesn't have traditional transactions
                # but we'll track the operation for commit message
                terminus_transaction = {"message": message, "author": author}
            
            if self._postgres_connector:
                postgres_transaction = await self._postgres_connector.begin()
            elif self._sqlite_connector:
                sqlite_transaction = await self._sqlite_connector.begin()
            
            yield self
            
            # Commit all transactions
            if terminus_transaction and self._terminus_client:
                # Commit changes with audit info
                self._terminus_client.commit(
                    message=terminus_transaction["message"],
                    author=terminus_transaction["author"]
                )
            
            if postgres_transaction:
                await postgres_transaction.commit()
            elif sqlite_transaction:
                await sqlite_transaction.commit()
                
        except Exception as e:
            # Rollback all transactions
            if postgres_transaction:
                await postgres_transaction.rollback()
            elif sqlite_transaction:
                await sqlite_transaction.rollback()
            
            # TerminusDB doesn't have explicit rollback
            # Changes are not persisted until commit
            
            logger.error(f"Transaction failed: {e}")
            raise
    
    async def create(
        self,
        collection: str,
        document: Dict[str, Any],
        author: str = "system",
        message: Optional[str] = None
    ) -> str:
        """Create a document in the appropriate backend"""
        backend = self._get_backend_for_operation(collection, QueryType.WRITE)
        
        if backend == DatabaseBackend.TERMINUSDB:
            return await self._create_terminus(collection, document, author, message)
        elif backend == DatabaseBackend.POSTGRESQL:
            return await self._create_postgres(collection, document)
        else:
            return await self._create_sqlite(collection, document)
    
    async def _create_terminus(
        self,
        collection: str,
        document: Dict[str, Any],
        author: str,
        message: Optional[str] = None
    ) -> str:
        """Create document in TerminusDB"""
        doc_id = document.get("@id") or f"{collection}/{document.get('id', datetime.now().timestamp())}"
        document["@id"] = doc_id
        document["@type"] = collection
        
        self._terminus_client.insert_document(document)
        
        # Commit with audit trail
        commit_message = message or f"Created {collection} document: {doc_id}"
        self._terminus_client.commit(message=commit_message, author=author)
        
        return doc_id
    
    async def _create_postgres(self, table: str, data: Dict[str, Any]) -> str:
        """Create record in PostgreSQL"""
        columns = ", ".join(data.keys())
        placeholders = ", ".join([f"${i+1}" for i in range(len(data))])
        
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING id"
        
        result = await self._postgres_connector.fetch_one(query, *data.values())
        return str(result["id"])
    
    async def _create_sqlite(self, table: str, data: Dict[str, Any]) -> str:
        """Create record in SQLite"""
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?" for _ in data])
        
        query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        
        cursor = await self._sqlite_connector.execute(query, list(data.values()))
        return str(cursor.lastrowid)
    
    async def read(
        self,
        collection: str,
        query: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Read documents from appropriate backend"""
        backend = self._get_backend_for_operation(collection, QueryType.READ)
        
        if backend == DatabaseBackend.TERMINUSDB:
            return await self._read_terminus(collection, query, limit, offset)
        elif backend == DatabaseBackend.POSTGRESQL:
            return await self._read_postgres(collection, query, limit, offset)
        else:
            return await self._read_sqlite(collection, query, limit, offset)
    
    async def _read_terminus(
        self,
        collection: str,
        query: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Read documents from TerminusDB"""
        # Build WOQL query
        woql_query = WOQLQuery().type(collection)
        
        if query:
            for key, value in query.items():
                woql_query = woql_query.where(
                    WOQLQuery().triple("v:doc", key, value)
                )
        
        if limit:
            woql_query = woql_query.limit(limit)
        if offset:
            woql_query = woql_query.offset(offset)
        
        results = self._terminus_client.query(woql_query)
        return results.get("bindings", [])
    
    async def update(
        self,
        collection: str,
        doc_id: str,
        updates: Dict[str, Any],
        author: str = "system",
        message: Optional[str] = None
    ) -> bool:
        """Update document in appropriate backend"""
        backend = self._get_backend_for_operation(collection, QueryType.WRITE)
        
        if backend == DatabaseBackend.TERMINUSDB:
            return await self._update_terminus(collection, doc_id, updates, author, message)
        elif backend == DatabaseBackend.POSTGRESQL:
            return await self._update_postgres(collection, doc_id, updates)
        else:
            return await self._update_sqlite(collection, doc_id, updates)
    
    async def _update_terminus(
        self,
        collection: str,
        doc_id: str,
        updates: Dict[str, Any],
        author: str,
        message: Optional[str] = None
    ) -> bool:
        """Update document in TerminusDB"""
        # Get existing document
        doc = self._terminus_client.get_document(doc_id)
        if not doc:
            return False
        
        # Apply updates
        doc.update(updates)
        
        # Update document
        self._terminus_client.update_document(doc)
        
        # Commit with audit trail
        commit_message = message or f"Updated {collection} document: {doc_id}"
        self._terminus_client.commit(message=commit_message, author=author)
        
        return True
    
    async def delete(
        self,
        collection: str,
        doc_id: str,
        author: str = "system",
        message: Optional[str] = None
    ) -> bool:
        """Delete document from appropriate backend"""
        backend = self._get_backend_for_operation(collection, QueryType.WRITE)
        
        if backend == DatabaseBackend.TERMINUSDB:
            return await self._delete_terminus(collection, doc_id, author, message)
        elif backend == DatabaseBackend.POSTGRESQL:
            return await self._delete_postgres(collection, doc_id)
        else:
            return await self._delete_sqlite(collection, doc_id)
    
    async def _delete_terminus(
        self,
        collection: str,
        doc_id: str,
        author: str,
        message: Optional[str] = None
    ) -> bool:
        """Delete document from TerminusDB"""
        try:
            self._terminus_client.delete_document(doc_id)
            
            # Commit with audit trail
            commit_message = message or f"Deleted {collection} document: {doc_id}"
            self._terminus_client.commit(message=commit_message, author=author)
            
            return True
        except Exception as e:
            logger.error(f"Failed to delete document: {e}")
            return False
    
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
        Get audit log from TerminusDB commit history
        
        This leverages TerminusDB's built-in Git-style commit tracking
        """
        if not self._terminus_client:
            logger.error("TerminusDB not connected for audit log")
            return []
        
        try:
            # Get commit history
            history = self._terminus_client.get_commit_history()
            
            # Filter commits based on criteria
            filtered_commits = []
            
            for commit in history:
                # Parse commit metadata
                commit_time = datetime.fromisoformat(commit["timestamp"])
                commit_author = commit.get("author", "unknown")
                commit_message = commit.get("message", "")
                
                # Apply filters
                if start_time and commit_time < start_time:
                    continue
                if end_time and commit_time > end_time:
                    continue
                if author and commit_author != author:
                    continue
                if resource_type and resource_type not in commit_message:
                    continue
                if resource_id and resource_id not in commit_message:
                    continue
                
                # Get diff for this commit
                diff = self._terminus_client.diff(commit["identifier"], commit.get("parent"))
                
                # Format as audit entry
                audit_entry = {
                    "id": commit["identifier"],
                    "timestamp": commit_time.isoformat(),
                    "author": commit_author,
                    "message": commit_message,
                    "changes": self._format_diff_as_changes(diff),
                    "parent_commit": commit.get("parent")
                }
                
                filtered_commits.append(audit_entry)
                
                if len(filtered_commits) >= limit:
                    break
            
            return filtered_commits
            
        except Exception as e:
            logger.error(f"Failed to get audit log: {e}")
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
        if not self._terminus_client:
            return None
        
        try:
            # Find commit closest to timestamp
            history = self._terminus_client.get_commit_history()
            
            target_commit = None
            for commit in history:
                commit_time = datetime.fromisoformat(commit["timestamp"])
                if commit_time <= timestamp:
                    target_commit = commit["identifier"]
                    break
            
            if not target_commit:
                return None
            
            # Get document at that commit
            self._terminus_client.checkout(target_commit)
            doc = self._terminus_client.get_document(doc_id)
            
            # Return to HEAD
            self._terminus_client.checkout("main")
            
            return doc
            
        except Exception as e:
            logger.error(f"Failed to get document at time: {e}")
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
        """Close all database connections"""
        if self._terminus_client:
            # TerminusDB client doesn't need explicit close
            pass
        
        if self._postgres_connector:
            await self._postgres_connector.close()
        
        if self._sqlite_connector:
            await self._sqlite_connector.close()
        
        self._connected = False
        logger.info("Unified database client closed")


# Singleton instance
_unified_client: Optional[UnifiedDatabaseClient] = None


async def get_unified_database_client() -> UnifiedDatabaseClient:
    """Get or create unified database client"""
    global _unified_client
    
    if not _unified_client:
        _unified_client = UnifiedDatabaseClient()
        await _unified_client.connect()
    
    return _unified_client