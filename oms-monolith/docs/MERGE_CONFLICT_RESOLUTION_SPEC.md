# OMS Merge Conflict Resolution Specification

## Overview

This document defines the conflict resolution rules for schema merges in OMS, organized by schema class and conflict type.

## Conflict Categories

### 1. ID Conflicts

**Scenario**: Same ID created in different branches with different content

**Resolution Rules by Priority**:
1. **Interface** > Object Type > Link Type > Property
2. **System types** > User-defined types  
3. **Earlier creation timestamp** wins in case of same priority
4. **Explicit user resolution** required if auto-resolution fails

**Example**:
```json
// Branch A
{
  "id": "User",
  "type": "ObjectType",
  "name": "User",
  "properties": ["id", "name", "email"]
}

// Branch B  
{
  "id": "User",
  "type": "Interface",
  "name": "User",
  "implementedBy": ["Employee", "Customer"]
}

// Resolution: Branch B wins (Interface > ObjectType)
```

### 2. Delete-After-Modify Conflicts

**Scenario**: Entity deleted in one branch but modified in another

**Resolution Rules**:
1. **Modification wins** over deletion by default (preserves data)
2. **Exception**: If entity has `deprecated: true`, deletion wins
3. **Cascade deletes** require explicit confirmation

**Example**:
```json
// Branch A: Deletes Property "email"
// Branch B: Modifies Property "email" to required=true

// Resolution: Modification wins, "email" remains with required=true
```

### 3. Property Type Conflicts

**Scenario**: Same property has different data types in branches

**Resolution Matrix**:

| Branch A | Branch B | Resolution | Rationale |
|----------|----------|------------|-----------|
| string | text | text | More permissive |
| integer | long | long | Larger range |
| float | double | double | Higher precision |
| any primitive | json | json | Most flexible |
| enum A | enum A+B | enum A+B | Union of values |

**Breaking Changes**:
- Narrowing conversions (e.g., string → integer) require manual resolution
- Removing enum values requires deprecation period

### 4. Cardinality Conflicts

**Scenario**: Link type cardinality differs between branches

**Resolution Rules**:
```
ONE_TO_ONE + ONE_TO_MANY = ONE_TO_MANY
ONE_TO_ONE + MANY_TO_MANY = MANY_TO_MANY  
ONE_TO_MANY + MANY_TO_MANY = MANY_TO_MANY
```

**Directionality**:
- UNIDIRECTIONAL + BIDIRECTIONAL = BIDIRECTIONAL
- Changes from BIDIRECTIONAL to UNIDIRECTIONAL require manual resolution

### 5. Constraint Conflicts

**Scenario**: Different validation rules for semantic types

**Resolution Strategy**:
1. **Union of constraints** for additive changes
2. **Intersection of constraints** for restrictive changes
3. **Manual resolution** for incompatible constraints

**Examples**:
```yaml
# Branch A: minLength: 5
# Branch B: minLength: 10
# Resolution: minLength: 10 (more restrictive)

# Branch A: pattern: "^[A-Z]"
# Branch B: pattern: "^[a-z]"  
# Resolution: Manual (incompatible patterns)
```

### 6. Naming Conflicts

**Scenario**: Same entity renamed differently in branches

**Resolution Rules**:
1. If one branch only changes casing → preserve semantic change
2. If both change semantically → create alias, deprecate old
3. Display names can differ (multi-language support)

### 7. Interface Implementation Conflicts

**Scenario**: Object type implements different interfaces

**Resolution**: Union of all interfaces (additive only)

**Validation**: Ensure object type satisfies all interface requirements

## Conflict Resolution Strategies

### Three-Way Merge (Default)

```python
def three_way_merge(base, branch_a, branch_b):
    # 1. Identify changes from base
    changes_a = diff(base, branch_a)
    changes_b = diff(base, branch_b)
    
    # 2. Apply non-conflicting changes
    result = apply_non_conflicting(base, changes_a, changes_b)
    
    # 3. Resolve conflicts by rules
    conflicts = find_conflicts(changes_a, changes_b)
    for conflict in conflicts:
        resolution = resolve_by_rules(conflict)
        result = apply_resolution(result, resolution)
    
    return result
```

### Fast-Forward Merge

Allowed when:
- No divergent changes exist
- Target branch is direct ancestor
- No schema validations fail

### Squash Merge

Useful for:
- Feature branches with many iterative changes
- Cleaning up experimental modifications
- Maintaining clean schema history

## Manual Resolution Interface

When automatic resolution fails:

```json
{
  "conflict_id": "uuid",
  "type": "INCOMPATIBLE_CHANGE",
  "entity_type": "Property",
  "entity_id": "User.email",
  "branch_a": {
    "change": "DELETE",
    "reason": "GDPR compliance"
  },
  "branch_b": {
    "change": "MODIFY", 
    "details": "Add encryption, mark required"
  },
  "suggested_resolutions": [
    {
      "action": "KEEP_B_WITH_SOFT_DELETE",
      "description": "Keep property but mark as deprecated"
    },
    {
      "action": "MANUAL_MERGE",
      "description": "Create custom resolution"
    }
  ]
}
```

## Validation After Merge

Post-merge validations:
1. **Referential integrity**: All references valid
2. **Type consistency**: No type mismatches  
3. **Constraint satisfaction**: All constraints met
4. **Deprecation paths**: Proper migration paths
5. **Breaking change detection**: Flag for review

## Special Cases

### 1. Circular Dependencies
- Detected during merge
- Requires refactoring before merge completes

### 2. Cross-Type Renames  
- Entity changes type (e.g., Property → SharedProperty)
- Requires migration strategy

### 3. Bulk Operations
- Multiple related changes across entity types
- Resolved as atomic unit

## Configuration

```yaml
merge:
  conflict_resolution:
    auto_resolve: true
    prefer_modifications: true
    strict_mode: false
    
  strategies:
    default: "three-way"
    allow_fast_forward: true
    allow_squash: true
    
  validation:
    pre_merge: true
    post_merge: true
    breaking_change_detection: true
    
  manual_resolution:
    timeout_hours: 72
    notification_channels: ["email", "slack"]
```

## Audit Trail

All merge operations generate audit events:

```json
{
  "event_type": "SCHEMA_MERGE",
  "timestamp": "2024-01-01T00:00:00Z",
  "user": "admin",
  "source_branch": "feature/new-schema",
  "target_branch": "main",
  "conflicts_resolved": 5,
  "resolution_methods": {
    "automatic": 3,
    "rule_based": 1,
    "manual": 1
  },
  "validation_results": "PASSED",
  "commit_hash": "abc123"
}
```