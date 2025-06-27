# Distributed Lock Manager Upgrade

## Overview

The DistributedLockManager extends the existing enterprise BranchLockManager to add true distributed locking capabilities using PostgreSQL advisory locks. This upgrade preserves all existing features while enabling safe concurrent operations across multiple service instances.

## Key Features Preserved

1. **TTL (Time-To-Live) Support**
   - Automatic lock expiration after timeout
   - Configurable timeouts per lock type
   - Background cleanup of expired locks

2. **Heartbeat Mechanism**
   - Service health monitoring
   - Automatic release of locks from crashed services
   - Progress tracking for long-running operations

3. **Resource-Level Locking (Foundry-style)**
   - Granular locks on specific resource types
   - Minimal lock scope to maximize concurrency
   - Branch remains ACTIVE during resource-specific indexing

4. **Lock Conflict Detection**
   - Prevents conflicting operations
   - Hierarchical lock scopes (Branch > ResourceType > Resource)
   - Clear error messages with conflict details

## New Distributed Capabilities

### PostgreSQL Advisory Locks
```python
# Automatic distributed lock acquisition
async with manager.distributed_lock("resource_id"):
    # Critical section protected across all instances
    await perform_operation()
```

### Benefits
- **True Distribution**: Locks work across multiple service instances
- **Crash Safety**: Locks automatically released on transaction/connection end
- **Performance**: Minimal overhead using PostgreSQL's built-in features
- **Consistency**: Single source of truth in PostgreSQL

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   DistributedLockManager                    │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Inherits from BranchLockManager         │   │
│  │  • All TTL features preserved                       │   │
│  │  • All heartbeat features preserved                 │   │
│  │  • All resource-level locking preserved             │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │           PostgreSQL Advisory Lock Layer             │   │
│  │  • distributed_lock() context manager                │   │
│  │  • SHA256 hash to 64-bit lock keys                  │   │
│  │  • Transaction-scoped automatic release              │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              Persistent State Storage                │   │
│  │  • branch_states table (JSONB)                       │   │
│  │  • lock_audit table for history                     │   │
│  │  • Replaces in-memory storage                       │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Migration Process

### 1. Prerequisites
- PostgreSQL database with JSONB support
- Existing BranchLockManager instance (optional)

### 2. Run Migration Script
```bash
python migrations/migrate_to_distributed_locks.py
```

The migration:
- Creates necessary database schema
- Migrates existing locks and branch states
- Verifies distributed lock functionality
- Provides rollback capability

### 3. Update Service Configuration
```python
# Before
from core.branch.lock_manager import BranchLockManager
lock_manager = BranchLockManager()

# After
from core.branch.distributed_lock_manager import DistributedLockManager
lock_manager = DistributedLockManager(db_session)
```

## Usage Examples

### Basic Lock Acquisition
```python
# Works exactly like before, but now distributed
lock_id = await lock_manager.acquire_lock(
    branch_name="feature-1",
    lock_type=LockType.INDEXING,
    locked_by="funnel-service",
    lock_scope=LockScope.RESOURCE_TYPE,
    resource_type="object_type",
    reason="Indexing objects"
)
```

### Foundry-Style Minimal Locking
```python
# Lock only what's being indexed (not the whole branch)
lock_ids = await lock_manager.lock_for_indexing(
    branch_name="main",
    locked_by="funnel-service",
    resource_types=["object_type", "link_type"],
    force_branch_lock=False  # Foundry style
)
```

### Direct Distributed Lock Usage
```python
# For custom critical sections
async with lock_manager.distributed_lock("custom:resource:id"):
    # Guaranteed exclusive access across all instances
    await critical_operation()
```

## Database Schema

### branch_states Table
```sql
CREATE TABLE branch_states (
    branch_name VARCHAR(255) PRIMARY KEY,
    state_data JSONB NOT NULL,  -- Full BranchStateInfo as JSON
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_by VARCHAR(255) NOT NULL,
    version INTEGER DEFAULT 1
);
```

### lock_audit Table
```sql
CREATE TABLE lock_audit (
    id SERIAL PRIMARY KEY,
    lock_id VARCHAR(255) NOT NULL,
    branch_name VARCHAR(255) NOT NULL,
    lock_type VARCHAR(50) NOT NULL,
    lock_scope VARCHAR(50) NOT NULL,
    resource_type VARCHAR(100),
    resource_id VARCHAR(255),
    locked_by VARCHAR(255) NOT NULL,
    action VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB
);
```

## Performance Considerations

1. **Lock Key Calculation**: SHA256 hash ensures even distribution
2. **Timeout Configuration**: Default 5 seconds, configurable per operation
3. **Heartbeat Overhead**: Minimal - only updates last_heartbeat timestamp
4. **Concurrent Access**: Non-conflicting resources can be locked simultaneously

## Monitoring

### Active Locks Query
```sql
SELECT branch_name, 
       jsonb_array_length(state_data->'active_locks') as lock_count
FROM branch_states
WHERE jsonb_array_length(state_data->'active_locks') > 0;
```

### Advisory Locks Monitor
```sql
SELECT * FROM get_active_advisory_locks();
```

### Lock History
```sql
SELECT * FROM lock_audit 
WHERE branch_name = 'main' 
ORDER BY timestamp DESC 
LIMIT 100;
```

## Troubleshooting

### Lock Timeout Issues
- Increase timeout: `distributed_lock(resource_id, timeout_ms=10000)`
- Check for long-running transactions
- Monitor lock contention with advisory lock queries

### Heartbeat Expiration
- Verify heartbeat_interval is appropriate for operation duration
- Check network connectivity between service and database
- Monitor heartbeat health with `get_lock_health_status()`

### Migration Issues
- Ensure PostgreSQL version supports JSONB (9.4+)
- Check database permissions for table creation
- Use rollback script if needed: `rollback_migration()`

## Best Practices

1. **Keep Lock Scope Minimal**: Use resource-level locks when possible
2. **Set Appropriate Timeouts**: Match timeout to expected operation duration
3. **Enable Heartbeats**: For long-running operations (>1 minute)
4. **Monitor Lock Health**: Regular cleanup and health checks
5. **Handle Conflicts Gracefully**: Implement retry logic for transient conflicts

## Security Considerations

1. **Database Permissions**: Lock tables should have restricted access
2. **Audit Trail**: All lock operations are logged for compliance
3. **No Bypasses**: Distributed locks cannot be bypassed by local operations
4. **Connection Security**: Use SSL/TLS for database connections