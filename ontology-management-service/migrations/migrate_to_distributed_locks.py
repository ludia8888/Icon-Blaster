"""
Migration script to upgrade from BranchLockManager to DistributedLockManager
Preserves all existing locks and state while adding distributed capabilities
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from core.branch.lock_manager import BranchLockManager
from core.branch.distributed_lock_manager import DistributedLockManager, DISTRIBUTED_LOCK_SCHEMA
from models.branch_state import BranchStateInfo
from common_logging.setup import get_logger

logger = get_logger(__name__)


class DistributedLockMigration:
    """
    Migrates from in-memory BranchLockManager to distributed PostgreSQL locks
    """
    
    def __init__(self, postgres_url: str):
        self.postgres_url = postgres_url
        self.engine = None
        self.async_session = None
        
    async def initialize(self):
        """Initialize database connection"""
        self.engine = create_async_engine(self.postgres_url)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )
        
    async def create_schema(self):
        """Create PostgreSQL schema for distributed locks"""
        logger.info("Creating distributed lock schema...")
        
        async with self.engine.begin() as conn:
            # Execute the schema SQL
            for statement in DISTRIBUTED_LOCK_SCHEMA.split(';'):
                if statement.strip():
                    await conn.execute(text(statement))
        
        logger.info("Schema created successfully")
    
    async def migrate_existing_state(self, current_manager: BranchLockManager) -> Dict[str, int]:
        """
        Migrate existing branch states and locks from current manager
        
        Returns:
            Statistics about migrated data
        """
        stats = {
            "branches_migrated": 0,
            "active_locks_migrated": 0,
            "errors": 0
        }
        
        logger.info("Starting migration of existing state...")
        
        async with self.async_session() as session:
            # Migrate all branch states
            for branch_name, state_info in current_manager._branch_states.items():
                try:
                    await self._migrate_branch_state(session, state_info)
                    stats["branches_migrated"] += 1
                    
                    # Count active locks
                    active_locks = [l for l in state_info.active_locks if l.is_active]
                    stats["active_locks_migrated"] += len(active_locks)
                    
                except Exception as e:
                    logger.error(f"Failed to migrate branch {branch_name}: {e}")
                    stats["errors"] += 1
            
            await session.commit()
        
        logger.info(f"Migration completed: {stats}")
        return stats
    
    async def _migrate_branch_state(self, session: AsyncSession, state_info: BranchStateInfo):
        """Migrate a single branch state to PostgreSQL"""
        await session.execute(
            text("""
                INSERT INTO branch_states 
                (branch_name, state_data, updated_at, updated_by, version)
                VALUES (:branch_name, :state_data, :updated_at, :updated_by, 1)
                ON CONFLICT (branch_name) DO UPDATE SET
                    state_data = :state_data,
                    updated_at = :updated_at,
                    updated_by = :updated_by,
                    version = branch_states.version + 1
            """),
            {
                "branch_name": state_info.branch_name,
                "state_data": state_info.json(),
                "updated_at": datetime.now(timezone.utc),
                "updated_by": "migration"
            }
        )
        
        # Log active locks for audit
        for lock in state_info.active_locks:
            if lock.is_active:
                await session.execute(
                    text("""
                        INSERT INTO lock_audit
                        (lock_id, branch_name, lock_type, lock_scope, 
                         resource_type, resource_id, locked_by, action, metadata)
                        VALUES 
                        (:lock_id, :branch_name, :lock_type, :lock_scope,
                         :resource_type, :resource_id, :locked_by, 'migrated', :metadata)
                    """),
                    {
                        "lock_id": lock.id,
                        "branch_name": lock.branch_name,
                        "lock_type": lock.lock_type.value,
                        "lock_scope": lock.lock_scope.value,
                        "resource_type": lock.resource_type,
                        "resource_id": lock.resource_id,
                        "locked_by": lock.locked_by,
                        "metadata": json.dumps({
                            "reason": lock.reason,
                            "expires_at": lock.expires_at.isoformat() if lock.expires_at else None,
                            "heartbeat_enabled": lock.heartbeat_interval > 0
                        })
                    }
                )
    
    async def verify_migration(self) -> Dict[str, any]:
        """Verify the migration was successful"""
        verification = {
            "total_branches": 0,
            "total_active_locks": 0,
            "branches_with_locks": []
        }
        
        async with self.async_session() as session:
            # Count branches
            result = await session.execute(
                text("SELECT COUNT(*) FROM branch_states")
            )
            verification["total_branches"] = result.scalar()
            
            # Count active locks
            result = await session.execute(
                text("""
                    SELECT branch_name, jsonb_array_length(state_data->'active_locks') as lock_count
                    FROM branch_states
                    WHERE jsonb_array_length(state_data->'active_locks') > 0
                """)
            )
            
            for row in result:
                branch_name, lock_count = row
                verification["total_active_locks"] += lock_count
                verification["branches_with_locks"].append({
                    "branch": branch_name,
                    "lock_count": lock_count
                })
        
        return verification
    
    async def test_distributed_lock(self) -> bool:
        """Test that distributed locks work correctly"""
        logger.info("Testing distributed lock functionality...")
        
        async with self.async_session() as session:
            manager = DistributedLockManager(session)
            
            try:
                # Try to acquire a test lock
                test_resource = "migration:test:resource"
                
                async with manager.distributed_lock(test_resource, timeout_ms=5000):
                    logger.info("Successfully acquired distributed lock")
                    
                    # Try to acquire same lock from another "instance"
                    # This should fail
                    try:
                        async with manager.distributed_lock(test_resource, timeout_ms=100):
                            logger.error("ERROR: Was able to acquire same lock twice!")
                            return False
                    except Exception:
                        logger.info("Good: Second lock acquisition correctly failed")
                
                logger.info("Distributed lock test passed")
                return True
                
            except Exception as e:
                logger.error(f"Distributed lock test failed: {e}")
                return False
    
    async def cleanup(self):
        """Cleanup resources"""
        if self.engine:
            await self.engine.dispose()


async def perform_migration(
    postgres_url: str,
    current_lock_manager: Optional[BranchLockManager] = None
) -> DistributedLockManager:
    """
    Perform the complete migration to distributed locks
    
    Args:
        postgres_url: PostgreSQL connection URL
        current_lock_manager: Existing lock manager to migrate from
        
    Returns:
        New DistributedLockManager instance
    """
    migration = DistributedLockMigration(postgres_url)
    
    try:
        # Initialize
        await migration.initialize()
        
        # Create schema
        await migration.create_schema()
        
        # Migrate existing state if provided
        if current_lock_manager:
            stats = await migration.migrate_existing_state(current_lock_manager)
            logger.info(f"Migration statistics: {stats}")
        
        # Verify migration
        verification = await migration.verify_migration()
        logger.info(f"Verification results: {verification}")
        
        # Test distributed locks
        test_passed = await migration.test_distributed_lock()
        if not test_passed:
            raise Exception("Distributed lock test failed")
        
        # Create new distributed manager
        async with migration.async_session() as session:
            distributed_manager = DistributedLockManager(session)
            await distributed_manager.initialize()
            
            logger.info("Migration completed successfully!")
            return distributed_manager
            
    finally:
        await migration.cleanup()


async def rollback_migration(postgres_url: str):
    """
    Rollback the migration (for emergency use)
    
    WARNING: This will drop all distributed lock data!
    """
    logger.warning("Starting rollback of distributed lock migration...")
    
    engine = create_async_engine(postgres_url)
    
    try:
        async with engine.begin() as conn:
            # Drop tables in reverse order
            await conn.execute(text("DROP TABLE IF EXISTS lock_audit CASCADE"))
            await conn.execute(text("DROP TABLE IF EXISTS branch_states CASCADE"))
            await conn.execute(text("DROP FUNCTION IF EXISTS get_active_advisory_locks CASCADE"))
            
        logger.info("Rollback completed")
        
    finally:
        await engine.dispose()


# Example usage
if __name__ == "__main__":
    import os
    
    async def main():
        # Get PostgreSQL URL from environment
        postgres_url = os.getenv(
            "POSTGRES_URL",
            "postgresql+asyncpg://user:password@localhost/oms_db"
        )
        
        # Create a sample lock manager with some state
        current_manager = BranchLockManager()
        await current_manager.initialize()
        
        # Add some test data
        from models.branch_state import BranchStateInfo, BranchState
        test_state = BranchStateInfo(
            branch_name="test-branch",
            current_state=BranchState.ACTIVE,
            state_changed_by="test-user",
            state_change_reason="Testing migration"
        )
        await current_manager._store_branch_state(test_state)
        
        # Perform migration
        try:
            distributed_manager = await perform_migration(
                postgres_url,
                current_manager
            )
            
            print("Migration successful!")
            
            # Test the new manager
            lock_id = await distributed_manager.acquire_lock(
                branch_name="test-branch",
                lock_type=LockType.MANUAL,
                locked_by="migration-test",
                reason="Testing after migration"
            )
            
            print(f"Successfully acquired lock: {lock_id}")
            
            await distributed_manager.release_lock(lock_id, "migration-test")
            print("Successfully released lock")
            
        finally:
            await current_manager.shutdown()
    
    asyncio.run(main())