# Lock Manager Architecture

## Overview

The Ontology Management Service (OMS) provides a sophisticated distributed locking mechanism to ensure data consistency across multiple instances. This document describes the architecture and migration path from the legacy PostgreSQL-based implementation to the new Redis-based implementation.

## Problem Statement

The original `DistributedLockManager` implementation using PostgreSQL advisory locks had several critical issues:

1. **Deadlock Vulnerabilities**
   - Nested lock acquisition without hierarchy enforcement
   - Transaction-scoped advisory locks causing unexpected releases
   - No deadlock detection or recovery mechanisms

2. **Semantic Field Relationship Issues**
   - Fields merged independently without considering logical relationships
   - Example: `isTaxable: false` with `taxRate: 0.08` creating inconsistent states

3. **Order Information Loss**
   - Converting lists to dictionaries loses critical sequence information
   - UI layouts, execution steps, and other ordered data corrupted

## Solution Architecture

### 1. Redis-based Context-Aware Lock Manager

The new `RedisLockManager` provides:

- **Hierarchical Lock Enforcement**: Prevents deadlocks by enforcing lock acquisition order
- **Context Tracking**: Uses Python's `contextvars` to track held locks per coroutine
- **TTL-based Expiration**: Automatic cleanup of abandoned locks
- **Comprehensive Error Handling**: Distinguishes between conflicts and infrastructure errors

```python
# Example usage
async with redis_lock_manager.acquire_lock(
    resource_id="branch:main",
    lock_type=LockType.EXCLUSIVE,
    lock_scope=LockScope.BRANCH,
    ttl_seconds=300
) as lock_info:
    # Critical section
    await perform_operation()
```

### 2. Lock Hierarchy

```
BRANCH (Level 1)
  └── RESOURCE_TYPE (Level 2)
       └── RESOURCE (Level 3)
```

Locks must be acquired in order from level 1 to 3. Attempting to acquire a higher-level lock while holding a lower-level lock raises `LockHierarchyViolationError`.

### 3. Distributed Lock Adapter

The `DistributedLockAdapter` maintains backward compatibility by implementing the existing `BranchLockManager` interface while using Redis internally.

### 4. Lock Monitor

The `LockMonitor` provides:
- Real-time lock state monitoring
- Deadlock detection using graph algorithms (NetworkX)
- Lock statistics and diagnostics
- Automatic deadlock resolution

## Migration Guide

### Step 1: Update Configuration

Set the environment variable to use Redis:
```bash
export OMS_LOCK_LOCK_BACKEND=redis
export OMS_LOCK_REDIS_URL=redis://localhost:6379/0
```

### Step 2: Deploy Redis

Ensure Redis is available and accessible from all OMS instances.

### Step 3: Update Dependencies

The system will automatically use `DistributedLockAdapter` when Redis backend is selected.

### Step 4: Monitor Migration

Use the lock monitor to track lock usage and detect any issues:
```python
monitor = await get_lock_monitor(redis_client, lock_manager)
stats = monitor.get_lock_statistics()
```

## Semantic Merge Validation

### Field Groups

Related fields are grouped for atomic updates:
```python
FieldGroup(
    name="tax_fields",
    members=["isTaxable", "taxRate", "taxCategory"],
    merge_strategy=MergeStrategy.ATOMIC_UPDATE
)
```

### Validation Rules

Domain-specific validators ensure semantic consistency:
```python
class TaxMergeValidator(MergeValidator):
    def validate(self, merged_data, base, source, target):
        if not merged_data.get("isTaxable") and merged_data.get("taxRate", 0) > 0:
            raise ValidationError("Non-taxable items cannot have tax rate > 0")
```

## List Merge Algorithm

### LCS-based Merging

The new algorithm preserves order information:
```python
lcs_result = merge_with_lcs(
    base=base_props,
    source=source_props,
    target=target_props,
    identity_key="name"
)
```

### Benefits
- Preserves list order
- Detects position changes vs content changes
- Supports reordering operations

## Best Practices

1. **Always specify TTL** for locks to prevent orphaned locks
2. **Use appropriate lock scopes** - don't over-lock resources
3. **Handle lock conflicts gracefully** with retry logic
4. **Monitor lock metrics** to detect contention patterns
5. **Test deadlock scenarios** in development

## Performance Considerations

- Redis locks are faster than PostgreSQL advisory locks
- Lock operations are O(1) in Redis
- Network latency is the primary bottleneck
- Use connection pooling for Redis clients

## Monitoring and Debugging

### Lock Status API
```bash
GET /api/v1/branches/{branch_name}/lock-status
```

### Lock Diagnostics
```python
diagnosis = await monitor.diagnose_lock_issues("branch:main")
```

### Metrics to Track
- Lock acquisition time
- Lock hold duration
- Lock contention rate
- Deadlock frequency
- TTL expiration rate

## Future Enhancements

1. **Distributed Lock Coordination Service**: Consider adopting etcd or Consul for more advanced scenarios
2. **Lock Priority System**: Implement priority-based lock acquisition
3. **Lock Fairness**: Ensure fair lock distribution among competing processes
4. **Advanced Deadlock Prevention**: Implement wound-wait or wait-die algorithms