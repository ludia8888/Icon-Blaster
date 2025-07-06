"""
Optimistic Concurrency Control with Foundry-style conflict resolution
"""
import hashlib
from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timezone
from contextlib import asynccontextmanager
import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from models.exceptions import ConcurrencyError, ConflictError
from common_logging.setup import get_logger

logger = get_logger(__name__)


class OptimisticConcurrencyControl:
    """
    Foundry-style optimistic concurrency control
    - Prefer conflict detection over blocking
    - Use commit hashes for version tracking
    - Advisory locks only for critical metadata operations
    """
    
    def __init__(self, db_session: AsyncSession):
        self.session = db_session
        
    async def validate_parent_commit(
        self, 
        resource_type: str,
        resource_id: str,
        parent_commit: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate that parent commit matches current HEAD
        
        Returns:
            (is_valid, current_commit_hash)
        """
        try:
            result = await self.session.execute(
                text("""
                    SELECT current_commit_hash 
                    FROM resource_versions 
                    WHERE resource_type = :type 
                    AND resource_id = :id 
                    ORDER BY version DESC 
                    LIMIT 1
                """),
                {"type": resource_type, "id": resource_id}
            )
            
            row = result.fetchone()
            if not row:
                # New resource, any parent is valid
                return True, None
                
            current_commit = row[0]
            is_valid = current_commit == parent_commit
            
            if not is_valid:
                logger.warning(
                    f"Commit conflict for {resource_type}:{resource_id}. "
                    f"Expected: {parent_commit}, Current: {current_commit}"
                )
            
            return is_valid, current_commit
            
        except Exception as e:
            logger.error(f"Error validating parent commit: {e}")
            raise
    
    def calculate_resource_hash(self, resource_id: str) -> int:
        """
        Calculate consistent hash for resource ID (for advisory locks)
        PostgreSQL advisory locks use 64-bit integers
        """
        # Use first 8 bytes of SHA256 as int64
        hash_bytes = hashlib.sha256(resource_id.encode()).digest()[:8]
        return int.from_bytes(hash_bytes, byteorder='big', signed=True)
    
    @asynccontextmanager
    async def advisory_lock(self, resource_id: str, timeout_ms: int = 5000):
        """
        Acquire PostgreSQL advisory lock for critical operations
        Auto-releases on transaction end
        """
        lock_key = self.calculate_resource_hash(resource_id)
        
        try:
            # Try to acquire lock with timeout
            result = await self.session.execute(
                text("""
                    SELECT pg_try_advisory_xact_lock(:key)
                """),
                {"key": lock_key}
            )
            
            acquired = result.scalar()
            if not acquired:
                # Try with timeout
                await self.session.execute(
                    text("SET LOCAL lock_timeout = :timeout"),
                    {"timeout": f"{timeout_ms}ms"}
                )
                
                try:
                    await self.session.execute(
                        text("SELECT pg_advisory_xact_lock(:key)"),
                        {"key": lock_key}
                    )
                    acquired = True
                except Exception:
                    acquired = False
            
            if not acquired:
                raise ConcurrencyError(
                    f"Could not acquire lock for resource {resource_id} "
                    f"within {timeout_ms}ms"
                )
            
            logger.debug(f"Acquired advisory lock for {resource_id}")
            yield
            
        finally:
            # Lock automatically released at transaction end
            logger.debug(f"Released advisory lock for {resource_id}")
    
    async def atomic_update_with_conflict_detection(
        self,
        resource_type: str,
        resource_id: str,
        parent_commit: str,
        update_fn: callable,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Perform atomic update with conflict detection
        
        Args:
            resource_type: Type of resource
            resource_id: Resource identifier
            parent_commit: Expected parent commit hash
            update_fn: Function to perform update
            **kwargs: Additional arguments for update_fn
            
        Returns:
            Result dict with new_commit_hash
            
        Raises:
            ConflictError: If parent commit doesn't match
        """
        # Validate parent commit
        is_valid, current_commit = await self.validate_parent_commit(
            resource_type, resource_id, parent_commit
        )
        
        if not is_valid:
            raise ConflictError(
                resource_type=resource_type,
                resource_id=resource_id,
                expected_commit=parent_commit,
                actual_commit=current_commit,
                message="Parent commit mismatch - please rebase and retry"
            )
        
        # Perform update
        result = await update_fn(**kwargs)
        
        # Calculate new commit hash
        new_commit = self._calculate_commit_hash(result)
        
        # Record version
        await self.session.execute(
            text("""
                INSERT INTO resource_versions 
                (resource_type, resource_id, version, parent_commit_hash, 
                 current_commit_hash, created_at, created_by)
                VALUES 
                (:type, :id, 
                 COALESCE((SELECT MAX(version) + 1 FROM resource_versions 
                           WHERE resource_type = :type AND resource_id = :id), 1),
                 :parent, :current, :created_at, :created_by)
            """),
            {
                "type": resource_type,
                "id": resource_id,
                "parent": parent_commit,
                "current": new_commit,
                "created_at": datetime.now(timezone.utc),
                "created_by": kwargs.get("user_id", "system")
            }
        )
        
        return {
            "success": True,
            "new_commit_hash": new_commit,
            "parent_commit_hash": parent_commit,
            "result": result
        }
    
    def _calculate_commit_hash(self, data: Any) -> str:
        """Calculate deterministic hash for data"""
        import json
        
        # Ensure consistent JSON serialization
        json_str = json.dumps(data, sort_keys=True, ensure_ascii=True)
        return hashlib.sha256(json_str.encode()).hexdigest()[:12]


class FoundryStyleLockManager:
    """
    Foundry-style lock manager for critical operations
    - Most operations use optimistic concurrency
    - Only metadata/structure changes use advisory locks
    """
    
    def __init__(self, db_session: AsyncSession):
        self.session = db_session
        self.occ = OptimisticConcurrencyControl(db_session)
    
    @asynccontextmanager
    async def branch_operation_lock(self, branch_name: str):
        """Lock for branch create/delete/merge operations"""
        lock_id = f"branch:{branch_name}"
        async with self.occ.advisory_lock(lock_id):
            yield
    
    @asynccontextmanager
    async def schema_migration_lock(self, schema_id: str):
        """Lock for schema-wide migrations"""
        lock_id = f"schema:migration:{schema_id}"
        async with self.occ.advisory_lock(lock_id):
            yield
    
    @asynccontextmanager
    async def index_rebuild_lock(self, index_name: str):
        """Lock for index rebuild operations"""
        lock_id = f"index:rebuild:{index_name}"
        async with self.occ.advisory_lock(lock_id):
            yield
    
    async def update_with_retry(
        self,
        resource_type: str,
        resource_id: str, 
        parent_commit: str,
        update_fn: callable,
        max_retries: int = 3,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Update with automatic retry on conflicts
        """
        retries = 0
        last_error = None
        
        while retries < max_retries:
            try:
                return await self.occ.atomic_update_with_conflict_detection(
                    resource_type=resource_type,
                    resource_id=resource_id,
                    parent_commit=parent_commit,
                    update_fn=update_fn,
                    **kwargs
                )
            except ConflictError as e:
                last_error = e
                retries += 1
                
                if retries < max_retries:
                    logger.info(
                        f"Conflict detected, retrying ({retries}/{max_retries}). "
                        f"Fetching latest commit: {e.actual_commit}"
                    )
                    # Update parent commit for retry
                    parent_commit = e.actual_commit
                else:
                    logger.error(f"Max retries reached for {resource_type}:{resource_id}")
                    raise
        
        raise last_error


# Database schema for version tracking
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS resource_versions (
    id SERIAL PRIMARY KEY,
    resource_type VARCHAR(100) NOT NULL,
    resource_id VARCHAR(255) NOT NULL,
    version INTEGER NOT NULL,
    parent_commit_hash VARCHAR(64),
    current_commit_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_by VARCHAR(255) NOT NULL,
    metadata JSONB,
    
    UNIQUE(resource_type, resource_id, version),
    INDEX idx_resource_latest (resource_type, resource_id, version DESC),
    INDEX idx_commit_hash (current_commit_hash)
);

-- Function to get latest version
CREATE OR REPLACE FUNCTION get_latest_version(
    p_resource_type VARCHAR,
    p_resource_id VARCHAR
) RETURNS TABLE (
    version INTEGER,
    commit_hash VARCHAR
) AS $$
BEGIN
    RETURN QUERY
    SELECT rv.version, rv.current_commit_hash
    FROM resource_versions rv
    WHERE rv.resource_type = p_resource_type
    AND rv.resource_id = p_resource_id
    ORDER BY rv.version DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;
"""