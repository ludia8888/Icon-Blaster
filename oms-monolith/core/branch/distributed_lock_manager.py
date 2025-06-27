"""
Distributed Lock Manager with PostgreSQL Advisory Locks
Upgrades the existing BranchLockManager to use distributed locks
"""
import asyncio
import hashlib
from typing import Optional, Dict, List, Set, Any, AsyncContextManager
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import json

from models.branch_state import (
    BranchState, BranchLock, BranchStateInfo,
    LockType, LockScope
)
from core.branch.lock_manager import BranchLockManager, LockConflictError
from utils.logger import get_logger

logger = get_logger(__name__)


class DistributedLockManager(BranchLockManager):
    """
    Enhanced BranchLockManager with distributed locking using PostgreSQL
    """
    
    def __init__(self, db_session: AsyncSession, cache_service=None):
        super().__init__(cache_service=cache_service, db_service=None)
        self.db_session = db_session
        self._lock_namespace = "oms_locks"
        
    def _calculate_lock_key(self, resource_id: str) -> int:
        """
        Calculate 64-bit integer key for PostgreSQL advisory lock
        """
        # Create unique key with namespace
        full_key = f"{self._lock_namespace}:{resource_id}"
        hash_bytes = hashlib.sha256(full_key.encode()).digest()
        
        # Use first 8 bytes as signed 64-bit integer
        return int.from_bytes(hash_bytes[:8], byteorder='big', signed=True)
    
    @asynccontextmanager
    async def distributed_lock(
        self,
        resource_id: str,
        timeout_ms: int = 5000,
        lock_type: str = "exclusive"
    ) -> AsyncContextManager[bool]:
        """
        Acquire PostgreSQL advisory lock with automatic release
        
        Args:
            resource_id: Unique identifier for the resource
            timeout_ms: Max time to wait for lock
            lock_type: "exclusive" or "shared"
            
        Yields:
            True if lock acquired, raises LockConflictError if not
        """
        lock_key = self._calculate_lock_key(resource_id)
        acquired = False
        
        try:
            # Set lock timeout
            await self.db_session.execute(
                text("SET LOCAL lock_timeout = :timeout"),
                {"timeout": f"{timeout_ms}ms"}
            )
            
            # Try to acquire lock
            if lock_type == "exclusive":
                result = await self.db_session.execute(
                    text("SELECT pg_try_advisory_xact_lock(:key)"),
                    {"key": lock_key}
                )
                acquired = result.scalar()
                
                if not acquired:
                    # Try with wait
                    try:
                        await self.db_session.execute(
                            text("SELECT pg_advisory_xact_lock(:key)"),
                            {"key": lock_key}
                        )
                        acquired = True
                    except Exception as e:
                        raise LockConflictError(
                            f"Could not acquire exclusive lock for {resource_id}: {e}"
                        )
            else:  # shared lock
                result = await self.db_session.execute(
                    text("SELECT pg_try_advisory_xact_lock_shared(:key)"),
                    {"key": lock_key}
                )
                acquired = result.scalar()
            
            if not acquired:
                raise LockConflictError(
                    f"Could not acquire {lock_type} lock for {resource_id} within {timeout_ms}ms"
                )
            
            logger.debug(f"Acquired distributed {lock_type} lock for {resource_id}")
            yield True
            
        finally:
            # PostgreSQL automatically releases advisory locks at transaction end
            if acquired:
                logger.debug(f"Released distributed lock for {resource_id}")
    
    async def acquire_lock(
        self,
        branch_name: str,
        lock_type: LockType,
        locked_by: str,
        lock_scope: LockScope = LockScope.BRANCH,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        reason: str = "Lock acquired",
        timeout: Optional[timedelta] = None,
        enable_heartbeat: bool = True,
        heartbeat_interval: int = 60
    ) -> str:
        """
        Override to use distributed locks for critical operations
        """
        # Generate resource identifier for distributed lock
        if lock_scope == LockScope.BRANCH:
            dist_resource_id = f"branch:{branch_name}"
        elif lock_scope == LockScope.RESOURCE_TYPE:
            dist_resource_id = f"branch:{branch_name}:type:{resource_type}"
        else:  # RESOURCE
            dist_resource_id = f"branch:{branch_name}:type:{resource_type}:id:{resource_id}"
        
        # Use distributed lock for the operation
        async with self.distributed_lock(dist_resource_id):
            # Call parent implementation within the distributed lock
            return await super().acquire_lock(
                branch_name=branch_name,
                lock_type=lock_type,
                locked_by=locked_by,
                lock_scope=lock_scope,
                resource_type=resource_type,
                resource_id=resource_id,
                reason=reason,
                timeout=timeout,
                enable_heartbeat=enable_heartbeat,
                heartbeat_interval=heartbeat_interval
            )
    
    async def _store_branch_state(self, state_info: BranchStateInfo):
        """
        Override to store in PostgreSQL with proper serialization
        """
        # Store in database
        await self.db_session.execute(
            text("""
                INSERT INTO branch_states 
                (branch_name, state_data, updated_at, updated_by)
                VALUES (:branch_name, :state_data, :updated_at, :updated_by)
                ON CONFLICT (branch_name) DO UPDATE SET
                    state_data = :state_data,
                    updated_at = :updated_at,
                    updated_by = :updated_by
            """),
            {
                "branch_name": state_info.branch_name,
                "state_data": state_info.model_dump_json(),
                "updated_at": datetime.now(timezone.utc),
                "updated_by": state_info.state_changed_by
            }
        )
        
        # Also update cache
        await super()._store_branch_state(state_info)
    
    async def get_branch_state(self, branch_name: str) -> BranchStateInfo:
        """
        Override to load from PostgreSQL
        """
        # Try database first
        result = await self.db_session.execute(
            text("""
                SELECT state_data 
                FROM branch_states 
                WHERE branch_name = :branch_name
            """),
            {"branch_name": branch_name}
        )
        
        row = result.fetchone()
        if row:
            return BranchStateInfo.model_validate_json(row[0])
        
        # Fall back to parent implementation
        return await super().get_branch_state(branch_name)
    
    async def list_active_locks_distributed(self) -> List[Dict[str, Any]]:
        """
        List all active locks across all instances
        """
        result = await self.db_session.execute(
            text("""
                SELECT 
                    branch_name,
                    state_data->'active_locks' as locks
                FROM branch_states
                WHERE jsonb_array_length(state_data->'active_locks') > 0
            """)
        )
        
        all_locks = []
        for row in result:
            branch_name = row[0]
            locks_data = row[1]
            if locks_data:
                for lock_json in locks_data:
                    lock = BranchLock.model_validate(lock_json)
                    if lock.is_active:
                        all_locks.append({
                            "branch": branch_name,
                            "lock": lock.model_dump()
                        })
        
        return all_locks
    
    async def cleanup_expired_locks_distributed(self):
        """
        Cleanup expired locks across all instances
        """
        # Get all branches with active locks
        result = await self.db_session.execute(
            text("""
                SELECT branch_name, state_data
                FROM branch_states
                WHERE jsonb_array_length(state_data->'active_locks') > 0
            """)
        )
        
        for row in result:
            branch_name = row[0]
            state_data = json.loads(row[1])
            state_info = BranchStateInfo.model_validate(state_data)
            
            # Clean up expired locks
            original_count = len(state_info.active_locks)
            active_locks = []
            
            for lock in state_info.active_locks:
                if not lock.is_active:
                    continue
                    
                # Check TTL expiry
                if lock.expires_at and lock.expires_at < datetime.now(timezone.utc):
                    logger.info(f"Removing TTL expired lock {lock.id} from {branch_name}")
                    continue
                
                # Check heartbeat expiry
                if lock.heartbeat_interval > 0 and lock.last_heartbeat:
                    time_since_heartbeat = (
                        datetime.now(timezone.utc) - lock.last_heartbeat
                    ).total_seconds()
                    
                    if time_since_heartbeat > lock.heartbeat_interval * 3:
                        logger.warning(
                            f"Removing heartbeat expired lock {lock.id} from {branch_name}"
                        )
                        continue
                
                active_locks.append(lock)
            
            # Update if locks were removed
            if len(active_locks) < original_count:
                state_info.active_locks = active_locks
                await self._store_branch_state(state_info)
                
                logger.info(
                    f"Cleaned up {original_count - len(active_locks)} "
                    f"expired locks from {branch_name}"
                )


# Database schema for distributed lock manager
DISTRIBUTED_LOCK_SCHEMA = """
-- Branch states table for persistent storage
CREATE TABLE IF NOT EXISTS branch_states (
    branch_name VARCHAR(255) PRIMARY KEY,
    state_data JSONB NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_by VARCHAR(255) NOT NULL,
    version INTEGER DEFAULT 1,
    
    INDEX idx_branch_updated (updated_at),
    INDEX idx_active_locks ((jsonb_array_length(state_data->'active_locks')))
);

-- Lock audit table for debugging and monitoring
CREATE TABLE IF NOT EXISTS lock_audit (
    id SERIAL PRIMARY KEY,
    lock_id VARCHAR(255) NOT NULL,
    branch_name VARCHAR(255) NOT NULL,
    lock_type VARCHAR(50) NOT NULL,
    lock_scope VARCHAR(50) NOT NULL,
    resource_type VARCHAR(100),
    resource_id VARCHAR(255),
    locked_by VARCHAR(255) NOT NULL,
    action VARCHAR(50) NOT NULL, -- acquired, released, expired, extended
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB,
    
    INDEX idx_lock_audit_branch (branch_name, timestamp),
    INDEX idx_lock_audit_lock (lock_id, timestamp)
);

-- Function to get active advisory locks (for monitoring)
CREATE OR REPLACE FUNCTION get_active_advisory_locks()
RETURNS TABLE (
    locktype text,
    database oid,
    relation oid,
    page integer,
    tuple smallint,
    virtualxid text,
    transactionid xid,
    classid oid,
    objid oid,
    objsubid smallint,
    virtualtransaction text,
    pid integer,
    mode text,
    granted boolean,
    fastpath boolean
) AS $$
BEGIN
    RETURN QUERY
    SELECT * FROM pg_locks
    WHERE locktype = 'advisory';
END;
$$ LANGUAGE plpgsql;
"""