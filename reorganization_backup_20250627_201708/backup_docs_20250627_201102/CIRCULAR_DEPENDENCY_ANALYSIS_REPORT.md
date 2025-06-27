# Circular Dependency Analysis Report

## Executive Summary

This report identifies circular dependencies and import anti-patterns found in the OMS monolith codebase. The analysis focused on the `core/`, `middleware/`, `api/`, and `shared/` directories.

## Critical Circular Dependencies Found

### 1. **models.scope_role_mapping ↔ core.iam.iam_integration**

**Files involved:**
- `/models/scope_role_mapping.py:10` - imports from `core.iam.iam_integration import IAMScope`
- `/core/iam/iam_integration.py:161` - imports from `models.scope_role_mapping import ScopeRoleMatrix`

**Impact:** High - This circular dependency prevents proper module initialization and can cause runtime errors.

**Details:**
- `models.scope_role_mapping` needs `IAMScope` enum from `core.iam.iam_integration`
- `core.iam.iam_integration` needs `ScopeRoleMatrix` from `models.scope_role_mapping` in the `_scopes_to_roles` method

### 2. **core.auth ↔ models.permissions**

**Files involved:**
- `/core/auth.py:7` - imports from `models.permissions import get_permission_checker, PermissionChecker`
- `/middleware/auth_middleware.py:12` - imports from `core.auth import get_permission_checker, UserContext`
- `/middleware/auth_middleware.py:13` - imports from `core.integrations.user_service_client`

**Impact:** Medium - Creates tight coupling between authentication and permission modules.

**Details:**
- `core.auth` imports permission checker from models
- Multiple middleware components depend on both modules, creating a dependency web

## Other Import Anti-Patterns Identified

### 1. **Duplicate UserContext Definitions**

**Issue:** Multiple definitions of `UserContext` class found:
- `/core/auth.py:10-53` - Main definition with comprehensive user context
- `/api/gateway/auth.py:13-20` - Duplicate definition with slightly different fields

**Impact:** This can lead to confusion and type mismatches when different parts of the system use different definitions.

### 2. **Cross-Layer Dependencies**

**Pattern:** Middleware depending on core modules which depend on models:
- `middleware/auth_middleware.py` → `core.auth` → `models.permissions`
- `middleware/auth_middleware.py` → `core.iam.iam_integration` → `models.scope_role_mapping`
- `middleware/rbac_middleware.py` → `models.permissions`

**Impact:** Violates layered architecture principles where middleware should not directly access model layer.

### 3. **Delayed Import Pattern (Code Smell)**

**Location:** `/core/iam/iam_integration.py:161`
```python
async def _scopes_to_roles(self, scopes: List[str]) -> List[str]:
    # Import here to avoid circular dependency
    from models.scope_role_mapping import ScopeRoleMatrix
```

**Impact:** While this works around the circular dependency, it's a code smell indicating poor module organization.

## Dependency Graph

```
┌─────────────────────┐
│ middleware/         │
│ auth_middleware.py  │
└────────┬────────────┘
         │
         ├──────────────────────┐
         ▼                      ▼
┌─────────────────────┐  ┌──────────────────────┐
│ core/auth.py        │  │ core/integrations/   │
│                     │  │ user_service_client  │
└────────┬────────────┘  └──────────┬───────────┘
         │                           │
         ▼                           ▼
┌─────────────────────┐  ┌──────────────────────┐
│ models/permissions  │  │ core/auth (circular) │
└─────────────────────┘  └──────────────────────┘

┌─────────────────────┐
│ core/iam/           │
│ iam_integration.py  │◄────────┐ (circular)
└────────┬────────────┘         │
         │                      │
         ▼                      │
┌─────────────────────┐         │
│ models/             │         │
│ scope_role_mapping  │─────────┘
└─────────────────────┘
```

## Recommendations

### Immediate Actions

1. **Break the scope_role_mapping ↔ iam_integration circular dependency:**
   - Move `IAMScope` enum to a separate module (e.g., `models/iam_scopes.py`)
   - Both modules can then import from this shared location

2. **Consolidate UserContext definitions:**
   - Remove duplicate definition in `api/gateway/auth.py`
   - Use the single definition from `core/auth.py` throughout

3. **Refactor permission checking:**
   - Consider moving permission checking logic to a separate service layer
   - Avoid direct imports between core.auth and models.permissions

### Long-term Improvements

1. **Establish clear dependency rules:**
   - Models should not import from core
   - Core should not import from middleware
   - Middleware can import from core and models
   - API can import from all layers

2. **Create interface/protocol definitions:**
   - Define interfaces for cross-module communication
   - Use dependency injection pattern for loose coupling

3. **Module reorganization suggestions:**
   ```
   shared/
   ├── interfaces/      # Shared interfaces and protocols
   ├── enums/          # Shared enumerations (like IAMScope)
   └── types/          # Shared type definitions
   
   core/
   ├── services/       # Business logic services
   ├── auth/          # Authentication (no model imports)
   └── iam/           # IAM integration
   
   models/
   └── (pure data models, no business logic)
   ```

## Validation Steps

To verify these circular dependencies:

1. Run: `python -c "import models.scope_role_mapping"` - This may fail or show import warnings
2. Check for runtime errors related to incomplete module initialization
3. Use tools like `pydeps` or `import-linter` for automated dependency checking

## Conclusion

The identified circular dependencies, particularly between `models.scope_role_mapping` and `core.iam.iam_integration`, need immediate attention as they can cause runtime failures. The duplicate `UserContext` definitions and cross-layer dependencies should be addressed to improve code maintainability and prevent future issues.