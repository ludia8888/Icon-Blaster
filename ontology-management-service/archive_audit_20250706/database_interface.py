"""
Database Interface for Audit Service
Provides abstraction layer for different database backends
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple, Union
from datetime import datetime

from models.audit_events import AuditEventV1, AuditEventFilter


class AuditDatabaseInterface(ABC):
    """
    Abstract interface for audit database operations
    
    Allows switching between different database backends:
    - SQLite (current default)
    - PostgreSQL (for centralized deployment)
    - TerminusDB (for graph-based audit trails)
    """
    
    @abstractmethod
    async def initialize(self, migrations: Optional[List[str]] = None):
        """Initialize database and run migrations"""
        pass
    
    @abstractmethod
    async def store_audit_event(self, event: AuditEventV1) -> bool:
        """Store a single audit event"""
        pass
    
    @abstractmethod
    async def store_audit_events_batch(self, events: List[AuditEventV1]) -> int:
        """Store multiple audit events in batch"""
        pass
    
    @abstractmethod
    async def query_audit_events(
        self,
        filter_criteria: AuditEventFilter
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Query audit events with filtering and pagination"""
        pass
    
    @abstractmethod
    async def get_audit_event_by_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get specific audit event by ID"""
        pass
    
    @abstractmethod
    async def get_audit_statistics(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get audit statistics for monitoring"""
        pass
    
    @abstractmethod
    async def cleanup_expired_events(self) -> int:
        """Clean up expired audit events"""
        pass
    
    @abstractmethod
    async def verify_integrity(self) -> Dict[str, Any]:
        """Verify audit log integrity"""
        pass
    
    @abstractmethod
    async def close(self):
        """Close database connections"""
        pass


class DatabaseConnectorAdapter:
    """
    Adapter to make database connectors compatible with audit interface
    """
    
    def __init__(self, connector):
        """
        Initialize with a database connector
        
        Args:
            connector: SQLiteConnector or PostgresConnector instance
        """
        self.connector = connector
        self._migrations_applied = False
    
    async def initialize(self, migrations: Optional[List[str]] = None):
        """Initialize connector and apply migrations"""
        if hasattr(self.connector, 'initialize'):
            await self.connector.initialize(migrations)
        self._migrations_applied = True
    
    async def execute(
        self,
        query: str,
        params: Optional[Union[Dict[str, Any], List[Any]]] = None
    ) -> Any:
        """Execute query through connector"""
        return await self.connector.execute(query, params)
    
    async def execute_many(
        self,
        query: str,
        params_list: List[Union[Dict[str, Any], List[Any]]]
    ):
        """Execute batch query through connector"""
        return await self.connector.execute_many(query, params_list)
    
    async def fetch_one(
        self,
        query: str,
        params: Optional[Union[Dict[str, Any], List[Any]]] = None
    ) -> Optional[Dict[str, Any]]:
        """Fetch single row through connector"""
        return await self.connector.fetch_one(query, params)
    
    async def fetch_all(
        self,
        query: str,
        params: Optional[Union[Dict[str, Any], List[Any]]] = None
    ) -> List[Dict[str, Any]]:
        """Fetch all rows through connector"""
        return await self.connector.fetch_all(query, params)
    
    async def close(self):
        """Close connector"""
        if hasattr(self.connector, 'close'):
            await self.connector.close()
    
    @property
    def is_postgres(self) -> bool:
        """Check if using PostgreSQL connector"""
        return self.connector.__class__.__name__ == 'PostgresConnector'
    
    @property
    def is_sqlite(self) -> bool:
        """Check if using SQLite connector"""
        return self.connector.__class__.__name__ == 'SQLiteConnector'