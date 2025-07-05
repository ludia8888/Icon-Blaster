import os
from typing import Any, Dict, Optional, List
from contextlib import asynccontextmanager
import logging
from functools import wraps

from database.clients.terminus_db import TerminusDBClient
from core.observability.tracing import trace_method
from data_kernel.hook import CommitHookPipeline
from data_kernel.hook.base import CommitMeta, ValidationError

logger = logging.getLogger(__name__)


class TerminusService:
    """Singleton service wrapper for TerminusDB operations with enhanced tracing and commit metadata."""
    
    _instance = None
    _client: Optional[TerminusDBClient] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._client is None:
            self._client = TerminusDBClient(
                endpoint=os.getenv("TERMINUSDB_ENDPOINT", "http://terminusdb:6363"),
                username=os.getenv("TERMINUSDB_USER", "admin"),
                password=os.getenv("TERMINUSDB_PASS", "changeme-admin-pass"),
                service_name="data-kernel-gateway",
                use_connection_pool=True
            )
    
    async def initialize(self):
        """Initialize the service and verify connection."""
        if self._client:
            await self._client.__aenter__()
            health = await self._client.ping()
            logger.info(f"TerminusDB connection established: {health}")
            return health
    
    async def close(self):
        """Close the service and cleanup connections."""
        if self._client:
            await self._client.__aexit__(None, None, None)
    
    def commit_author(author: str = None):
        """Decorator to inject author information into commits."""
        def decorator(func):
            @wraps(func)
            async def wrapper(self, *args, **kwargs):
                # Extract author from kwargs or use default
                commit_author = kwargs.pop('author', author) or 'system'
                # Add author to commit metadata if method uses commit_msg
                if 'commit_msg' in kwargs:
                    original_msg = kwargs.get('commit_msg', '')
                    kwargs['commit_msg'] = f"[{commit_author}] {original_msg}"
                return await func(self, *args, **kwargs)
            return wrapper
        return decorator
    
    @trace_method
    async def get_document(self, db_name: str, doc_id: str, branch: str = "main", revision: Optional[str] = None) -> Dict[str, Any]:
        """Retrieve a document from TerminusDB."""
        # TODO: Implement branch support in TerminusDB client
        # For now, we'll use the default query mechanism
        # In a real implementation, we'd use TerminusDB's graph_type and revision parameters
        
        # Construct query with branch and revision support
        query = {
            "@type": "Get",
            "document": doc_id
        }
        
        # Add branch/revision to query context if needed
        result = await self._client.query(db_name, query)
        return result.get("bindings", [{}])[0] if result else None
    
    @trace_method
    @commit_author()
    async def insert_document(self, db_name: str, document: Dict[str, Any], commit_msg: str = "Insert document", author: str = None) -> Dict[str, Any]:
        """Insert a new document into TerminusDB."""
        query = {
            "@type": "InsertDocument",
            "document": document
        }
        
        # Execute query
        result = await self._client.query(db_name, query, commit_msg=commit_msg)
        
        # Run commit hooks with validation
        try:
            await self._run_commit_hooks(
                db_name=db_name,
                diff={"after": document},
                commit_msg=commit_msg,
                author=author
            )
        except ValidationError as e:
            # Rollback on validation failure
            logger.error(f"Validation failed, attempting rollback: {e}")
            await self._rollback_commit(db_name, result)
            raise
        
        return result
    
    @trace_method
    @commit_author()
    async def update_document(self, db_name: str, doc_id: str, updates: Dict[str, Any], commit_msg: str = "Update document", author: str = None) -> Dict[str, Any]:
        """Update an existing document in TerminusDB."""
        # Get current document for before state
        before = await self.get_document(db_name, doc_id)
        
        query = {
            "@type": "UpdateDocument",
            "document": {
                "@id": doc_id,
                **updates
            }
        }
        
        # Execute query
        result = await self._client.query(db_name, query, commit_msg=commit_msg)
        
        # Run commit hooks
        await self._run_commit_hooks(
            db_name=db_name,
            diff={"before": before, "after": {"@id": doc_id, **updates}},
            commit_msg=commit_msg,
            author=author
        )
        
        return result
    
    @trace_method
    @commit_author()
    async def delete_document(self, db_name: str, doc_id: str, commit_msg: str = "Delete document", author: str = None) -> Dict[str, Any]:
        """Delete a document from TerminusDB."""
        # Get document before deletion
        before = await self.get_document(db_name, doc_id)
        
        query = {
            "@type": "DeleteDocument",
            "document": doc_id
        }
        
        # Execute query
        result = await self._client.query(db_name, query, commit_msg=commit_msg)
        
        # Run commit hooks
        await self._run_commit_hooks(
            db_name=db_name,
            diff={"before": before, "after": None},
            commit_msg=commit_msg,
            author=author
        )
        
        return result
    
    @trace_method
    async def query(self, db_name: str, query: Dict[str, Any], commit_msg: Optional[str] = None) -> Dict[str, Any]:
        """Execute a raw WOQL query."""
        return await self._client.query(db_name, query, commit_msg=commit_msg)
    
    @trace_method
    async def branch_switch(self, db_name: str, branch_name: str) -> bool:
        """Switch to a different branch (placeholder - needs TerminusDB branch API)."""
        # This would need to be implemented based on TerminusDB's branch API
        logger.info(f"Switching to branch {branch_name} in database {db_name}")
        return True
    
    @trace_method
    async def get_schema(self, db_name: str) -> Dict[str, Any]:
        """Get the schema for a database."""
        return await self._client.get_schema(db_name)
    
    @trace_method
    @commit_author()
    async def update_schema(self, db_name: str, schema: Dict[str, Any], commit_msg: str = "Update schema", author: str = None) -> Dict[str, Any]:
        """Update the schema for a database."""
        return await self._client.update_schema(db_name, schema, commit_msg=commit_msg)
    
    async def health_check(self) -> Dict[str, Any]:
        """Check the health of the TerminusDB connection."""
        return await self._client.ping()
    
    async def _run_commit_hooks(self, db_name: str, diff: Dict[str, Any], commit_msg: str, author: str = None):
        """Run commit hooks after successful operations"""
        try:
            # Get context information
            from shared.terminus_context import get_branch, get_trace_id
            
            # Build commit metadata
            meta = CommitMeta(
                author=author or "system",
                branch=get_branch(),
                trace_id=get_trace_id(),
                commit_msg=commit_msg,
                database=db_name
            )
            
            # Run pipeline
            result = await CommitHookPipeline.run(meta, diff)
            logger.debug(f"Commit hooks completed: {result}")
            
        except Exception as e:
            logger.error(f"Error running commit hooks: {e}")
            # Don't fail the operation if hooks fail
            # This could be configurable
            if isinstance(e, ValidationError):
                raise  # Re-raise validation errors for rollback
    
    async def _rollback_commit(self, db_name: str, commit_result: Dict[str, Any]):
        """Rollback a commit using TerminusDB API"""
        try:
            # Extract commit ID from result
            commit_id = commit_result.get("commit_id") or commit_result.get("head")
            if not commit_id:
                logger.error("Cannot rollback: no commit ID found")
                return
            
            # Get current branch
            from shared.terminus_context import get_branch
            branch = get_branch()
            
            # TODO: Implement actual rollback using TerminusDB API
            # This would use /api/branch/{branch}/reset/{commit_id}
            logger.warning(f"Rollback not implemented: would reset {branch} to before {commit_id}")
            
        except Exception as e:
            logger.error(f"Failed to rollback commit: {e}")


# Global singleton instance
_service_instance: Optional[TerminusService] = None


async def get_service() -> TerminusService:
    """Get or create the singleton TerminusService instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = TerminusService()
        await _service_instance.initialize()
    return _service_instance