# GraphQL Enterprise Features Integration Guide

## Current State vs Target State

### Current Implementation
- Direct service calls in resolvers (N+1 queries)
- No caching
- No security validation
- No performance monitoring
- No client-specific optimization

### Target Implementation
- DataLoader batching
- Multi-level caching
- Security policies enforced
- Full observability
- BFF optimization per client

## Integration Steps

### 1. Update Main Application

Replace current GraphQL initialization in `main.py`:

```python
# Instead of importing regular GraphQL
# from api.graphql.main import app as graphql_app

# Import enhanced version
from api.graphql.enhanced_main import app as enhanced_graphql_app

# Mount enhanced GraphQL
if GRAPHQL_ENABLED:
    app.mount("/graphql", enhanced_graphql_app)
```

### 2. Add Batch Endpoints to Services

The schema service needs batch endpoints:

```python
# In schema service
@router.post("/api/v1/batch/object-types")
async def batch_get_object_types(ids: List[str]):
    """Batch endpoint for DataLoader"""
    # SELECT * FROM object_types WHERE id IN (ids)
    return {"data": results}

@router.post("/api/v1/batch/properties")
async def batch_get_properties(object_type_ids: List[str]):
    """Get properties for multiple object types"""
    # SELECT * FROM properties WHERE object_type_id IN (ids)
    return {"data": results}
```

### 3. Update Existing Resolvers

Option A: Gradual Migration (Recommended)
```python
# In existing resolvers, check for enhanced context
@strawberry.field
async def object_types(self, info: Info, ...):
    # Check if enhanced features available
    cache = info.context.get("cache")
    loaders = info.context.get("loaders")
    
    if cache:
        # Use cache
        cached = await cache.get(cache_key)
        if cached:
            return cached
    
    # Existing logic
    result = await service_client.call_service(...)
    
    if cache:
        # Cache result
        await cache.set(cache_key, result)
    
    return result
```

Option B: Full Replacement
- Replace `Query` class with `EnhancedQuery`
- All resolvers use DataLoaders

### 4. Configure Services

Add required endpoints to services:

#### Schema Service
- `/batch/object-types` - Batch load object types
- `/batch/properties` - Batch load properties
- `/batch/link-types` - Batch load link types

#### Branch Service
- `/batch/branches` - Batch load branches
- `/batch/branch-states` - Batch load branch states

### 5. Environment Variables

```bash
# Required for enterprise features
REDIS_URL=redis://localhost:6379
GRAPHQL_CACHE_ENABLED=true
GRAPHQL_SECURITY_ENABLED=true
GRAPHQL_MONITORING_ENABLED=true

# Security settings
GRAPHQL_MAX_DEPTH=10
GRAPHQL_MAX_COMPLEXITY=1000
GRAPHQL_RATE_LIMIT=100

# Performance
GRAPHQL_DATALOADER_BATCH_SIZE=100
GRAPHQL_CACHE_TTL=300
```

## Verification Steps

### 1. Check DataLoader Working
```graphql
# This query should batch load properties
query {
  objectTypes {
    data {
      id
      name
      properties {  # Should trigger ONE batch query, not N queries
        id
        name
      }
    }
  }
}
```

### 2. Check Caching
- First query: Check Redis for cache miss
- Second identical query: Should return from cache
- Modify data: Cache should invalidate

### 3. Check Security
```graphql
# This should be rejected (too deep)
query {
  objectTypes {
    data {
      properties {
        linkedObjectType {
          properties {
            linkedObjectType {
              properties {
                linkedObjectType {
                  properties {
                    linkedObjectType {
                      properties {
                        name
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
```

### 4. Check Monitoring
- Visit `/metrics` endpoint
- Should see GraphQL query metrics
- DataLoader batch sizes
- Cache hit rates

## Gradual Migration Path

### Phase 1: Add Infrastructure (No Breaking Changes)
1. Deploy Redis
2. Add enhanced_main.py alongside existing
3. Add batch endpoints to services
4. Test with enhanced version on different port

### Phase 2: Soft Launch
1. Add feature flag for enhanced GraphQL
2. Route % of traffic to enhanced version
3. Monitor metrics and performance
4. Fix any issues

### Phase 3: Full Migration
1. Update all clients to use enhanced endpoint
2. Remove old GraphQL implementation
3. Optimize based on real usage patterns

## Common Issues and Solutions

### Issue: Batch endpoints not available
**Solution**: Resolvers check for DataLoader in context and fallback to direct calls

### Issue: Redis connection fails
**Solution**: Features gracefully degrade - caching disabled but queries still work

### Issue: Security too restrictive
**Solution**: Different configs for dev/staging/prod environments

### Issue: Performance overhead
**Solution**: Tune batch sizes and cache TTLs based on metrics

## Testing the Integration

### Unit Tests
```python
def test_dataloader_batching():
    # Mock service returns different data based on batch size
    # Verify only one call made for multiple IDs
    
def test_cache_invalidation():
    # Cache result
    # Modify data
    # Verify cache invalidated
    
def test_security_depth_limit():
    # Send deep query
    # Verify rejected with proper error
```

### Load Tests
- Measure N+1 query elimination
- Cache hit rates under load
- Response time improvements

### Integration Tests
- Full query execution with all components
- WebSocket subscriptions with auth
- Error handling and partial results

## Conclusion

The enterprise GraphQL features are designed to integrate gradually with the existing codebase. Start with infrastructure (Redis), add batch endpoints, then enable features one by one. Monitor metrics at each step to ensure improvements.