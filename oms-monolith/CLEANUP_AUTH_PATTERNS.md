# Authentication Pattern Cleanup Plan

## Current State Analysis

### Multiple `get_current_user` Implementations Found:

1. **middleware/auth_middleware.py** (line 196)
   - The canonical implementation
   - Used by most routes via dependency injection
   - Returns `UserContext` from `request.state.user`

2. **core/auth/unified_auth.py** 
   - Attempts to consolidate but adds complexity
   - Has multiple modes (STANDARD, MSA, LIFE_CRITICAL, etc.)
   - Not fully integrated

3. **api/graphql/auth.py**
   - GraphQL-specific implementation
   - Different behavior for optional auth

4. **Various route files**
   - Import from different sources
   - Inconsistent usage patterns

## Cleanup Strategy

### Phase 1: Standardize Import Path
All files should import from one location:
```python
from middleware.auth_middleware import get_current_user
```

### Phase 2: Remove Redundant Implementations
1. Mark `core/auth/unified_auth.py` as deprecated
2. Update GraphQL to use standard middleware approach
3. Remove duplicate implementations in route files

### Phase 3: Ensure Secure Database Usage
1. Update all database operations to use `SecureDatabaseAdapter`
2. Propagate user context through all database calls
3. Remove direct `UnifiedDatabaseClient` usage in authenticated endpoints

## Files to Update

### High Priority (Security Critical):
- [ ] api/v1/schema_routes.py - Use secure database
- [ ] api/v1/document_routes.py - Use secure database
- [ ] api/v1/batch_routes.py - Use secure database
- [ ] core/history/routes.py - Use secure database

### Medium Priority (Cleanup):
- [ ] api/graphql/auth.py - Use standard auth
- [ ] api/graphql/main.py - Remove custom auth
- [ ] core/auth/unified_auth.py - Mark as deprecated

### Low Priority (Documentation):
- [ ] Update API documentation
- [ ] Add migration guide
- [ ] Update tests

## Migration Pattern

### Before:
```python
from core.auth.unified_auth import get_current_user_async
# or
from api.graphql.auth import get_current_user_graphql

async def my_endpoint(
    current_user = Depends(get_current_user_async)
):
    db = await get_unified_database_client()
    # Direct database usage without user context
```

### After:
```python
from middleware.auth_middleware import get_current_user
from database.dependencies import get_secure_database

async def my_endpoint(
    current_user: UserContext = Depends(get_current_user),
    db: SecureDatabaseAdapter = Depends(get_secure_database)
):
    # Database automatically includes user context
    await db.create(
        user_context=current_user,
        collection="my_collection",
        document={"data": "value"}
    )
```

## Testing Requirements

1. Run existing tests to ensure no regression
2. Add tests for secure author tracking
3. Verify audit logs contain correct author information
4. Test middleware chain (Auth → RBAC → Audit → Database)

## Rollback Plan

If issues arise:
1. Keep old implementations but mark as deprecated
2. Add logging to track usage of deprecated methods
3. Gradual migration over multiple releases