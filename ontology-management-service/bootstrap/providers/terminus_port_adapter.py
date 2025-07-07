"""
TerminusPort Adapter - Connects UnifiedDatabaseClient to TerminusPort protocol.
"""
from typing import Any, Dict, List, Optional
from core.validation.ports import TerminusPort
from database.clients.unified_database_client import UnifiedDatabaseClient

class TerminusPortAdapter(TerminusPort):
    """
    Adapter to make UnifiedDatabaseClient compatible with the TerminusPort protocol.
    It bypasses the complex routing logic of UnifiedDatabaseClient and directly
    uses the underlying _terminus_client for port-related operations.
    """
    def __init__(self, unified_client: UnifiedDatabaseClient):
        self._unified_client = unified_client
        # Direct access to the low-level client
        self._terminus_client = getattr(unified_client, '_terminus_client', None)

    async def query(self, db: str, sparql: str, **opts) -> List[Dict[str, Any]]:
        """Execute a SPARQL query using the low-level TerminusDB client."""
        if self._terminus_client:
            return await self._terminus_client.query(db_name=db, query=sparql)
        return []

    async def get_document(self, doc_id: str, db: str = "oms", branch: str = "main") -> Optional[Dict[str, Any]]:
        """Get a document using the low-level TerminusDB client."""
        if self._terminus_client and hasattr(self._terminus_client, 'get_document'):
            # Assuming the low-level client has this method.
            return await self._terminus_client.get_document(db_name=db, doc_id=doc_id)
        return None

    async def insert_document(self, document: Dict[str, Any], db: str = "oms", branch: str = "main", author: Optional[str] = None, message: Optional[str] = None) -> str:
        """Insert a document using the low-level TerminusDB client."""
        if self._terminus_client and hasattr(self._terminus_client, 'insert_document'):
            return await self._terminus_client.insert_document(db_name=db, document=document, author=author, commit_msg=message)
        return ""

    async def update_document(self, document: Dict[str, Any], db: str = "oms", branch: str = "main", author: Optional[str] = None, message: Optional[str] = None) -> bool:
        """Update a document using the low-level TerminusDB client."""
        if self._terminus_client and hasattr(self._terminus_client, 'update_document'):
            return await self._terminus_client.update_document(db_name=db, document=document, author=author, commit_msg=message)
        return False

    async def health_check(self) -> bool:
        """Perform a health check using the low-level TerminusDB client."""
        if self._terminus_client and hasattr(self._terminus_client, 'ping'):
            return await self._terminus_client.ping()
        return False 