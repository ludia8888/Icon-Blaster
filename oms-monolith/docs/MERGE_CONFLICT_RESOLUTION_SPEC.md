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

**Resolution Matrix with Severity Grades**:

| Branch A | Branch B | Resolution | Severity | Rationale |
|----------|----------|------------|----------|------------|
| string | text | text | INFO | More permissive |
| integer | long | long | INFO | Larger range |
| float | double | double | INFO | Higher precision |
| any primitive | json | json | WARN | Type safety loss |
| enum A | enum A+B | enum A+B | INFO | Union of values |
| string | integer | MANUAL | ERROR | Data loss risk |
| double | integer | MANUAL | ERROR | Precision loss |
| json | primitive | MANUAL | ERROR | Structure loss |
| enum A+B | enum A | MANUAL | WARN | Value restriction |

**Severity Levels**:
- **INFO**: Safe automatic resolution, no data loss
- **WARN**: Automatic resolution with potential side effects
- **ERROR**: Manual resolution required, high risk of data loss
- **BLOCK**: Cannot proceed without manual intervention

**Breaking Changes**:
- Narrowing conversions (ERROR level) require manual resolution
- Type safety degradation (WARN level) triggers validation
- Removing enum values requires deprecation period and migration plan

### 4. Cardinality Conflicts

**Scenario**: Link type cardinality differs between branches

**Resolution Rules with Migration Impact**:

| Current | Target | Resolution | Migration Impact | Severity |
|---------|--------|------------|------------------|----------|
| ONE_TO_ONE | ONE_TO_MANY | ONE_TO_MANY | FK remains valid | INFO |
| ONE_TO_ONE | MANY_TO_MANY | MANY_TO_MANY | New junction table needed | WARN |
| ONE_TO_MANY | MANY_TO_MANY | MANY_TO_MANY | Junction table + data migration | WARN |
| ONE_TO_MANY | ONE_TO_ONE | MANUAL | Potential data loss (multiple → single) | ERROR |
| MANY_TO_MANY | ONE_TO_ONE | MANUAL | Junction table removal + data loss | ERROR |
| MANY_TO_MANY | ONE_TO_MANY | MANUAL | Complex migration required | ERROR |

**Migration Impact Details**:
- **FK remains valid**: No data migration needed
- **Junction table needed**: Create M:N relationship table, migrate FKs
- **Data loss risk**: Multiple relationships must be reduced to single
- **Complex migration**: Requires custom logic to preserve data integrity

**Directionality**:
- UNIDIRECTIONAL + BIDIRECTIONAL = BIDIRECTIONAL (INFO)
- BIDIRECTIONAL → UNIDIRECTIONAL = MANUAL (WARN) - May break existing queries

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
  "severity": "ERROR",
  "entity_type": "Property",
  "entity_id": "User.email",
  "branch_a": {
    "change": "DELETE",
    "reason": "GDPR compliance",
    "author": "user123",
    "timestamp": "2024-01-01T10:00:00Z"
  },
  "branch_b": {
    "change": "MODIFY", 
    "details": "Add encryption, mark required",
    "author": "user456",
    "timestamp": "2024-01-01T11:00:00Z"
  },
  "suggested_resolutions": [
    {
      "action": "KEEP_B_WITH_SOFT_DELETE",
      "description": "Keep property but mark as deprecated",
      "confidence": 0.85,
      "migration_steps": [
        "Mark property as deprecated",
        "Add deprecation notice to clients",
        "Schedule removal in 90 days"
      ]
    },
    {
      "action": "MANUAL_MERGE",
      "description": "Create custom resolution",
      "requires_approval": ["schema-admin", "security-team"]
    }
  ],
  "resolution_sla": {
    "severity": "ERROR",
    "deadline": "2024-01-02T10:00:00Z",
    "escalation_path": ["team-lead", "architect", "cto"],
    "auto_escalate_after": "24h"
  },
  "permissions": {
    "can_resolve": ["schema-admin", "branch-owner"],
    "can_approve": ["architect", "cto"],
    "can_override": ["cto"]
  },
  "async_resolution": {
    "webhook_url": "https://api.oms.com/conflicts/webhook",
    "notification_channels": ["email", "slack", "jira"],
    "status_endpoint": "/api/v1/conflicts/uuid/status"
  }
}
```

**Resolution Workflow**:
1. Conflict detected → Notification sent to relevant parties
2. SLA timer starts based on severity
3. Authorized users review and select resolution
4. If approval required, request sent to approvers
5. Resolution applied with full audit trail
6. Post-resolution validation and impact assessment
7. Notification of completion with rollback option

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

All merge operations generate comprehensive audit events:

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
  "severity_summary": {
    "INFO": 2,
    "WARN": 2,
    "ERROR": 1,
    "BLOCK": 0
  },
  "validation_results": "PASSED",
  "validation_warnings": [
    {
      "type": "TYPE_SAFETY_DEGRADATION",
      "property": "User.metadata",
      "change": "string → json",
      "affected_clients": ["mobile-v1.2", "web-v2.0"]
    }
  ],
  "breaking_change_flags": [
    {
      "type": "CARDINALITY_REDUCTION",
      "link": "User.addresses",
      "from": "ONE_TO_MANY",
      "to": "ONE_TO_ONE",
      "migration_required": true,
      "estimated_impact": "5000 records"
    }
  ],
  "commit_hash": "abc123",
  "rollback_snapshot": "snapshot-12345"
}
```