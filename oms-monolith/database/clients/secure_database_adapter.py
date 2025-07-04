"""
Secure Database Adapter
Wraps UnifiedDatabaseClient to enforce secure author tracking

This adapter ensures all database operations include verified author information
from the authenticated UserContext, preventing unauthorized author spoofing.
"""

from typing import Dict, Any, List, Optional, Union
from contextlib import asynccontextmanager

from database.clients.unified_database_client import UnifiedDatabaseClient
from core.auth import UserContext
from core.auth.secure_author_provider import get_secure_author_provider
from utils.logger import get_logger

logger = get_logger(__name__)


class SecureDatabaseAdapter:
    """
    Database adapter that enforces secure author tracking
    
    All write operations require a verified UserContext
    Author field in commits is cryptographically secured
    """
    
    def __init__(self, unified_client: UnifiedDatabaseClient):
        self.client = unified_client
        self.author_provider = get_secure_author_provider()
    
    @asynccontextmanager
    async def transaction(
        self,
        user_context: UserContext,
        message: str = "Transaction",
        additional_metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Secure transaction with verified author
        
        Args:
            user_context: Authenticated user context (required)
            message: Transaction description
            additional_metadata: Extra metadata for audit
        """
        # Generate secure author
        secure_author = self.author_provider.get_secure_author(user_context)
        
        # Enhance message with context
        enhanced_message = f"{message} | User: {user_context.username}"
        if additional_metadata:
            enhanced_message += f" | Metadata: {additional_metadata}"
        
        # Use underlying transaction with secure author
        async with self.client.transaction(
            message=enhanced_message,
            author=secure_author
        ) as tx:
            # Create a wrapped client that includes user context
            wrapped_tx = SecureTransactionWrapper(
                tx,
                user_context,
                self.author_provider
            )
            yield wrapped_tx
    
    async def create(
        self,
        user_context: UserContext,
        collection: str,
        document: Dict[str, Any],
        message: Optional[str] = None
    ) -> str:
        """
        Create document with secure author tracking
        
        Args:
            user_context: Authenticated user (required)
            collection: Collection name
            document: Document to create
            message: Optional commit message
        """
        secure_author = self.author_provider.get_secure_author(user_context)
        
        # Add audit metadata to document
        document["_created_by"] = user_context.user_id
        document["_created_by_username"] = user_context.username
        document["_created_at"] = self._get_timestamp()
        
        return await self.client.create(
            collection=collection,
            document=document,
            author=secure_author,
            message=message or f"Created {collection} document"
        )
    
    async def update(
        self,
        user_context: UserContext,
        collection: str,
        doc_id: str,
        updates: Dict[str, Any],
        message: Optional[str] = None
    ) -> bool:
        """
        Update document with secure author tracking
        
        Args:
            user_context: Authenticated user (required)
            collection: Collection name
            doc_id: Document ID
            updates: Updates to apply
            message: Optional commit message
        """
        secure_author = self.author_provider.get_secure_author(user_context)
        
        # Add audit metadata to updates
        updates["_updated_by"] = user_context.user_id
        updates["_updated_by_username"] = user_context.username
        updates["_updated_at"] = self._get_timestamp()
        
        return await self.client.update(
            collection=collection,
            doc_id=doc_id,
            updates=updates,
            author=secure_author,
            message=message or f"Updated {collection} document: {doc_id}"
        )
    
    async def delete(
        self,
        user_context: UserContext,
        collection: str,
        doc_id: str,
        message: Optional[str] = None,
        soft_delete: bool = True
    ) -> bool:
        """
        Delete document with secure author tracking
        
        Args:
            user_context: Authenticated user (required)
            collection: Collection name
            doc_id: Document ID
            message: Optional commit message
            soft_delete: If True, mark as deleted instead of removing
        """
        secure_author = self.author_provider.get_secure_author(user_context)
        
        if soft_delete:
            # Soft delete - mark as deleted
            return await self.update(
                user_context=user_context,
                collection=collection,
                doc_id=doc_id,
                updates={
                    "_deleted": True,
                    "_deleted_by": user_context.user_id,
                    "_deleted_by_username": user_context.username,
                    "_deleted_at": self._get_timestamp()
                },
                message=message or f"Soft deleted {collection} document: {doc_id}"
            )
        else:
            # Hard delete
            return await self.client.delete(
                collection=collection,
                doc_id=doc_id,
                author=secure_author,
                message=message or f"Deleted {collection} document: {doc_id}"
            )
    
    async def read(
        self,
        collection: str,
        query: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Read documents (no auth required for reads)
        
        Args:
            collection: Collection name
            query: Query filters
            limit: Max results
            offset: Skip results
            include_deleted: Include soft-deleted documents
        """
        # Enhance query to exclude deleted unless requested
        if not include_deleted and query is None:
            query = {}
        
        if not include_deleted:
            query["_deleted"] = {"$ne": True}
        
        return await self.client.read(
            collection=collection,
            query=query,
            limit=limit,
            offset=offset
        )
    
    async def get_audit_log(
        self,
        user_context: Optional[UserContext] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        start_time: Optional[Any] = None,
        end_time: Optional[Any] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get audit log with author verification
        
        Args:
            user_context: Filter by user (optional)
            resource_type: Filter by resource type
            resource_id: Filter by resource ID
            start_time: Start time filter
            end_time: End time filter
            limit: Max results
        """
        # Get raw audit log
        audit_entries = await self.client.get_audit_log(
            resource_type=resource_type,
            resource_id=resource_id,
            start_time=start_time,
            end_time=end_time,
            author=user_context.username if user_context else None,
            limit=limit
        )
        
        # Enhance with parsed author info
        for entry in audit_entries:
            if "author" in entry:
                parsed = self.author_provider.parse_secure_author(entry["author"])
                entry["author_parsed"] = parsed
                entry["author_verified"] = parsed.get("verified", False)
        
        return audit_entries
    
    def _get_timestamp(self) -> str:
        """Get current ISO timestamp"""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


class SecureTransactionWrapper:
    """
    Wrapper for transaction operations with user context
    """
    
    def __init__(
        self,
        transaction_client,
        user_context: UserContext,
        author_provider
    ):
        self.tx = transaction_client
        self.user_context = user_context
        self.author_provider = author_provider
    
    async def create(self, collection: str, document: Dict[str, Any]) -> str:
        """Create within transaction with secure author"""
        secure_author = self.author_provider.get_secure_author(self.user_context)
        
        # Add audit metadata
        document["_created_by"] = self.user_context.user_id
        document["_created_by_username"] = self.user_context.username
        document["_created_at"] = self._get_timestamp()
        
        # Note: transaction context already has author set
        return await self.tx.create(collection, document)
    
    async def update(
        self,
        collection: str,
        doc_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """Update within transaction with secure author"""
        # Add audit metadata
        updates["_updated_by"] = self.user_context.user_id
        updates["_updated_by_username"] = self.user_context.username
        updates["_updated_at"] = self._get_timestamp()
        
        return await self.tx.update(collection, doc_id, updates)
    
    async def delete(self, collection: str, doc_id: str) -> bool:
        """Delete within transaction with secure author"""
        return await self.tx.delete(collection, doc_id)
    
    async def read(
        self,
        collection: str,
        query: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Read within transaction"""
        return await self.tx.read(collection, query, limit, offset)
    
    def _get_timestamp(self) -> str:
        """Get current ISO timestamp"""
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()


# Factory function
async def create_secure_database(
    user_context: Optional[UserContext] = None
) -> Union[SecureDatabaseAdapter, UnifiedDatabaseClient]:
    """
    Create database client with optional security wrapper
    
    If user_context provided: Returns SecureDatabaseAdapter (enforces auth)
    If no user_context: Returns UnifiedDatabaseClient (for system operations)
    """
    from database.clients.unified_database_client import get_unified_database_client
    
    client = await get_unified_database_client()
    
    if user_context:
        return SecureDatabaseAdapter(client)
    else:
        logger.warning("Creating database client without user context - use only for system operations")
        return client