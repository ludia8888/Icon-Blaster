# Authentication Migration Guide

## Overview
This guide helps you migrate from the deprecated authentication patterns to the new standardized approach that ensures secure author tracking throughout the system.

## Why This Migration?
1. **Security**: Ensure all database operations track the authenticated user
2. **Consistency**: Single source of truth for authentication
3. **Audit Compliance**: Cryptographically verified author tracking
4. **Simplification**: Remove redundant authentication implementations

## Migration Steps

### Step 1: Update Your Imports

#### ❌ OLD (Deprecated)
```python
# Various deprecated imports
from core.auth.unified_auth import get_current_user
from core.auth.unified_auth import get_current_user_async
from core.auth.unified_auth import get_current_user_sync
from api.graphql.auth import get_current_user as get_current_user_graphql
```

#### ✅ NEW (Correct)
```python
# Single standardized import
from middleware.auth_middleware import get_current_user
```

### Step 2: Update Database Access Patterns

#### ❌ OLD (Insecure - No Author Tracking)
```python
from database.clients.unified_database_client import get_unified_database_client

async def create_object(
    data: dict,
    current_user = Depends(get_current_user)
):
    db = await get_unified_database_client()
    
    # This doesn't track who created the object!
    result = await db.create(
        collection="objects",
        document=data,
        author=current_user.username  # Manual author setting
    )
    return result
```

#### ✅ NEW (Secure - Automatic Author Tracking)
```python
from middleware.auth_middleware import get_current_user
from database.dependencies import get_secure_database
from database.clients.secure_database_adapter import SecureDatabaseAdapter

async def create_object(
    data: dict,
    current_user: UserContext = Depends(get_current_user),
    db: SecureDatabaseAdapter = Depends(get_secure_database)
):
    # Secure author tracking is automatic!
    result = await db.create(
        user_context=current_user,
        collection="objects",
        document=data,
        message="Creating new object"
    )
    return result
```

### Step 3: GraphQL-Specific Migration

#### ❌ OLD (Custom GraphQL Auth)
```python
from api.graphql.auth import get_current_user_graphql
from api.graphql.resolvers.base import BaseResolver

class MyResolver(BaseResolver):
    async def resolve_create_item(self, info, input):
        user = await get_current_user_graphql(info)
        # Custom database access
```

#### ✅ NEW (Standard Middleware Approach)
```python
from api.graphql.resolvers.base import BaseResolver
from database.dependencies import get_secure_database

class MyResolver(BaseResolver):
    async def resolve_create_item(self, info, input):
        # User is already in context from middleware
        user = self.get_current_user(info)
        
        # Get secure database from request
        request = info.context["request"]
        db = await get_secure_database(request, user)
        
        # Secure database operations
        result = await db.create(
            user_context=user,
            collection="items",
            document=input
        )
        return result
```

### Step 4: Update Route Definitions

#### ❌ OLD
```python
from core.auth.unified_auth import get_current_user_async

router = APIRouter()

@router.post("/items")
async def create_item(
    item: ItemCreate,
    user = Depends(get_current_user_async)
):
    # Implementation
```

#### ✅ NEW
```python
from middleware.auth_middleware import get_current_user
from database.dependencies import get_secure_database

router = APIRouter()

@router.post("/items")
async def create_item(
    item: ItemCreate,
    user: UserContext = Depends(get_current_user),
    db: SecureDatabaseAdapter = Depends(get_secure_database)
):
    # Implementation with secure database
```

## Common Patterns

### 1. Read Operations (No Auth Required)
```python
# For public read operations, you can still use direct database access
from database.clients.unified_database_client import get_unified_database_client

async def get_public_data():
    db = await get_unified_database_client()
    return await db.read(collection="public_data")
```

### 2. Write Operations (Auth Required)
```python
# All write operations MUST use SecureDatabaseAdapter
async def update_data(
    doc_id: str,
    updates: dict,
    user: UserContext = Depends(get_current_user),
    db: SecureDatabaseAdapter = Depends(get_secure_database)
):
    return await db.update(
        user_context=user,
        collection="data",
        doc_id=doc_id,
        updates=updates
    )
```

### 3. Transactions
```python
async def complex_operation(
    user: UserContext = Depends(get_current_user),
    db: SecureDatabaseAdapter = Depends(get_secure_database)
):
    async with db.transaction(user, "Complex operation") as tx:
        # All operations in transaction have secure author tracking
        await tx.create("collection1", {...})
        await tx.update("collection2", "doc_id", {...})
```

### 4. Background Tasks
```python
from core.auth.service_account import get_service_context

async def background_task():
    # Use service account for background operations
    service_context = get_service_context("background_worker")
    db = await create_secure_database(service_context)
    
    # Operations are tracked to the service account
    await db.create(
        user_context=service_context,
        collection="jobs",
        document={...}
    )
```

## Validation Checklist

After migration, verify:

- [ ] All imports use `middleware.auth_middleware`
- [ ] No imports from `core.auth.unified_auth`
- [ ] All write operations use `SecureDatabaseAdapter`
- [ ] Database operations include `user_context` parameter
- [ ] GraphQL resolvers use standard middleware approach
- [ ] Background tasks use service accounts
- [ ] Tests updated to use new patterns

## Deprecation Timeline

- **Now**: Deprecation warnings active
- **v1.5**: Increased warnings, metrics on deprecated usage
- **v2.0 (Q1 2025)**: Complete removal of deprecated modules

## Getting Help

If you encounter issues during migration:

1. Check the error messages for specific guidance
2. Review the examples in `/tests/auth/test_migration_patterns.py`
3. Contact the security team for assistance

## Quick Reference

```python
# Imports
from middleware.auth_middleware import get_current_user
from database.dependencies import get_secure_database
from database.clients.secure_database_adapter import SecureDatabaseAdapter

# Route pattern
async def my_endpoint(
    user: UserContext = Depends(get_current_user),
    db: SecureDatabaseAdapter = Depends(get_secure_database)
):
    # Your secure implementation
```