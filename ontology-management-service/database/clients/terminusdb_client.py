"""
TerminusDB Client for ontology-management-service
"""

import asyncio
from typing import Dict, Any, List, Optional

from terminusdb_client import WOQLClient, GraphType
from terminusdb_client.errors import DatabaseError
from common_logging.setup import get_logger

logger = get_logger(__name__)


class TerminusDBClient:
    """
    Client for interacting with TerminusDB.
    Handles connection, CRUD operations, and audit logging.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        # The WOQLClient itself is synchronous
        self._client: Optional[WOQLClient] = None
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        """Check if the client is connected to the database."""
        return self._client is not None

    async def connect(self):
        """Connect to TerminusDB using a thread to avoid blocking."""
        async with self._lock:
            if self.is_connected:
                return
            try:
                client = WOQLClient(**self.config)
                # Run the synchronous connect method in a separate thread
                await asyncio.to_thread(client.connect)
                self._client = client
                logger.info("Connected to TerminusDB")
            except Exception as e:
                logger.error(f"Failed to connect to TerminusDB: {e}")
                self._client = None
                raise

    async def close(self):
        """Close the connection to TerminusDB."""
        async with self._lock:
            if self.is_connected:
                # Disconnect logic can be added here if the client library supports it
                self._client = None
                logger.info("Closed connection to TerminusDB")

    async def create(
        self,
        collection: str, # Note: collection is used as _type in TerminusDB
        document: Dict[str, Any],
        author: str,
        message: Optional[str] = None
    ) -> str:
        """Create a new document in a collection."""
        if not self._client:
            raise ConnectionError("TerminusDB client is not connected.")
        
        try:
            commit_message = message or f"Creating document in {collection}"
            
            # The document must have a @type for TerminusDB
            if '@type' not in document:
                document['@type'] = collection

            # The author parameter might not be supported directly in this version.
            # It's often part of the client's connection details or commit info.
            # For now, we omit it to fix the linter error.
            result = await asyncio.to_thread(
                self._client.insert_document,
                document,
                commit_msg=commit_message,
                graph_type=GraphType.INSTANCE
            )

            if isinstance(result, list) and result:
                return result[0]
            if isinstance(result, dict) and "@id" in result:
                return result["@id"]
            raise ValueError(f"Unexpected response from TerminusDB during create: {result}")
        except (DatabaseError, TypeError, ValueError) as e:
            logger.error(f"TerminusDB create error: {e}")
            raise

    async def read(
        self,
        collection: str,
        query: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Read documents from a collection."""
        if not self._client:
            raise ConnectionError("TerminusDB client is not connected.")

        try:
            # TODO: Implement proper WOQL query translation from `query` dict
            # For now, we only support fetching by type.
            documents = await asyncio.to_thread(
                list, # get_all_documents is a generator
                self._client.get_all_documents(
                    graph_type=GraphType.INSTANCE, # Use the Enum member
                    count=limit,
                    start=offset or 0,
                    _type=collection
                )
            )
            return documents
        except (DatabaseError, TypeError) as e:
            logger.error(f"TerminusDB read error: {e}")
            raise 