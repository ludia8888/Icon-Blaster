# GraphQL Enterprise Features - Migration Guide

## Overview

This guide provides a step-by-step approach to migrating from the basic GraphQL implementation to the enterprise-grade GraphQL with DataLoaders, caching, security, and monitoring.

## Current State Assessment

Before starting the migration, verify your current setup:

```bash
# Check if GraphQL is currently mounted
curl http://localhost:8002/graphql

# Check available endpoints
curl http://localhost:8002/health
```

## Migration Phases

### Phase 1: Infrastructure Setup (Day 1-2)

#### 1.1 Redis Deployment
```bash
# Docker Compose for development
docker run -d \
  --name redis-graphql \
  -p 6379:6379 \
  redis:7-alpine \
  redis-server --appendonly yes

# For production, use Redis Cluster or AWS ElastiCache
```

#### 1.2 Environment Configuration
```bash
# Add to .env file
GRAPHQL_ENABLED=true
REDIS_URL=redis://localhost:6379/0
GRAPHQL_CACHE_ENABLED=true
GRAPHQL_SECURITY_ENABLED=true
GRAPHQL_MONITORING_ENABLED=true

# Security settings
GRAPHQL_MAX_DEPTH=10
GRAPHQL_MAX_COMPLEXITY=1000
GRAPHQL_RATE_LIMIT=100

# Performance settings
GRAPHQL_DATALOADER_BATCH_SIZE=100
GRAPHQL_CACHE_TTL=300
```

#### 1.3 Verify Dependencies
```python
# Test Redis connection
import redis.asyncio as redis
client = redis.from_url("redis://localhost:6379")
await client.ping()  # Should return True
```

### Phase 2: Code Deployment (Day 3-4)

#### 2.1 Deploy Batch Endpoints
The batch endpoints are now available at:
- `/api/v1/batch/object-types`
- `/api/v1/batch/properties`
- `/api/v1/batch/link-types`
- `/api/v1/batch/branches`

Test them:
```bash
# Test batch endpoint
curl -X POST http://localhost:8002/api/v1/batch/object-types \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "ids": ["main:User", "main:Post"],
    "include_properties": true
  }'
```

#### 2.2 Enable GraphQL in Main Application
The GraphQL endpoints are now mounted at:
- `/graphql` - Enhanced GraphQL with all enterprise features
- `/graphql-ws` - WebSocket endpoint for subscriptions

Verify:
```bash
# Test GraphQL endpoint
curl -X POST http://localhost:8002/graphql \
  -H "Content-Type: application/json" \
  -d '{
    "query": "{ __typename }"
  }'
```

### Phase 3: Feature Rollout (Day 5-7)

#### 3.1 Enable Features Gradually

**Step 1: Enable Caching Only**
```python
# Start with caching disabled for testing
GRAPHQL_CACHE_ENABLED=false

# Monitor performance baseline
# Then enable caching
GRAPHQL_CACHE_ENABLED=true

# Monitor cache hit rates at /metrics/graphql
```

**Step 2: Enable DataLoaders**
```python
# DataLoaders are automatically used when batch endpoints are available
# Monitor batch efficiency at /metrics/graphql
```

**Step 3: Enable Security**
```python
# Start with relaxed limits
GRAPHQL_MAX_DEPTH=20
GRAPHQL_MAX_COMPLEXITY=5000

# Gradually tighten based on actual usage patterns
GRAPHQL_MAX_DEPTH=10
GRAPHQL_MAX_COMPLEXITY=1000
```

#### 3.2 Client Migration

**Web Clients**
```javascript
// Update Apollo Client configuration
const client = new ApolloClient({
  uri: '/graphql',  // Now points to enhanced endpoint
  cache: new InMemoryCache(),
  defaultOptions: {
    watchQuery: {
      fetchPolicy: 'cache-first',  // Leverage server-side caching
    },
  },
});
```

**Mobile Clients**
```javascript
// Add client type header for BFF optimization
const client = new ApolloClient({
  uri: '/graphql',
  headers: {
    'X-Client-Type': 'mobile',
    'User-Agent': 'MobileApp/1.0'
  }
});
```

### Phase 4: Monitoring & Optimization (Day 8-10)

#### 4.1 Health Monitoring
```bash
# Check overall health
curl http://localhost:8002/graphql/health

# Check readiness (stricter)
curl http://localhost:8002/graphql/ready

# View detailed metrics
curl http://localhost:8002/metrics/graphql
```

#### 4.2 Performance Monitoring

Monitor these key metrics:

1. **DataLoader Efficiency**
   - Batch size (aim for 10-50)
   - Cache hit rate (aim for >70%)
   - Load time (should be <100ms)

2. **Query Performance**
   - P95 response time
   - Query complexity distribution
   - Error rates

3. **Cache Performance**
   - Hit rate by cache level
   - Invalidation frequency
   - Memory usage

#### 4.3 Security Monitoring

```bash
# Check security violations in logs
grep "SecurityViolation" /var/log/graphql.log

# Common issues:
# - Depth exceeded: Simplify nested queries
# - Complexity exceeded: Add pagination
# - Rate limited: Implement client-side caching
```

### Phase 5: Production Rollout (Day 11-14)

#### 5.1 Canary Deployment

```nginx
# Nginx configuration for gradual rollout
upstream graphql_basic {
    server localhost:8001;  # Old GraphQL
}

upstream graphql_enhanced {
    server localhost:8002;  # New GraphQL
}

# Route 10% traffic to new version
split_clients "${remote_addr}${http_user_agent}" $graphql_backend {
    10%     graphql_enhanced;
    *       graphql_basic;
}

location /graphql {
    proxy_pass http://$graphql_backend;
}
```

#### 5.2 Feature Flags

```python
# Use feature flags for gradual enablement
class GraphQLFeatureFlags:
    ENABLE_DATALOADER = os.getenv("FF_GRAPHQL_DATALOADER", "true")
    ENABLE_CACHING = os.getenv("FF_GRAPHQL_CACHE", "true")
    ENABLE_SECURITY = os.getenv("FF_GRAPHQL_SECURITY", "true")
    ENABLE_BFF = os.getenv("FF_GRAPHQL_BFF", "false")
```

#### 5.3 Rollback Plan

If issues arise:

1. **Quick Disable**: Set `GRAPHQL_ENABLED=false` and restart
2. **Revert Mounting**: Comment out GraphQL mounting in main.py
3. **Clear Cache**: `redis-cli FLUSHDB` to clear corrupted cache
4. **Check Logs**: Review `/metrics/graphql` for root cause

### Phase 6: Post-Migration (Day 15+)

#### 6.1 Performance Tuning

Based on production metrics:

```python
# Tune batch sizes
GRAPHQL_DATALOADER_BATCH_SIZE=50  # Reduce if timeouts occur

# Adjust cache TTLs
GRAPHQL_CACHE_TTL_STATIC=3600    # 1 hour for schemas
GRAPHQL_CACHE_TTL_NORMAL=300     # 5 minutes for data
GRAPHQL_CACHE_TTL_VOLATILE=60    # 1 minute for changing data

# Optimize security limits
GRAPHQL_MAX_DEPTH=8              # Based on actual query patterns
GRAPHQL_MAX_COMPLEXITY=800       # Based on P95 complexity
```

#### 6.2 Advanced Features

Once stable, enable advanced features:

1. **Query Whitelisting**
```python
# Only allow pre-approved queries in production
GRAPHQL_WHITELIST_ENABLED=true
GRAPHQL_WHITELIST_FILE=/etc/graphql/queries.json
```

2. **Persisted Queries**
```python
# Reduce bandwidth with query persistence
GRAPHQL_PERSISTED_QUERIES=true
```

3. **Field-Level Caching**
```graphql
type User @cacheControl(maxAge: 300) {
  id: ID!
  name: String! @cacheControl(maxAge: 3600)
  posts: [Post!]! @cacheControl(maxAge: 60)
}
```

## Troubleshooting

### Common Issues

1. **High Memory Usage**
   - Reduce `GRAPHQL_DATALOADER_BATCH_SIZE`
   - Lower `GRAPHQL_CACHE_TTL`
   - Enable cache eviction policies in Redis

2. **Slow Queries**
   - Check `/metrics/graphql` for N+1 patterns
   - Ensure batch endpoints are working
   - Verify DataLoader is batching properly

3. **Cache Inconsistency**
   - Check invalidation patterns
   - Verify event system is publishing updates
   - Consider shorter TTLs for volatile data

4. **Security Blocks Legitimate Queries**
   - Analyze blocked queries in logs
   - Adjust limits based on actual usage
   - Consider whitelisting critical queries

### Monitoring Checklist

Daily:
- [ ] Check health endpoint status
- [ ] Review error rates
- [ ] Monitor cache hit rates
- [ ] Check query performance P95

Weekly:
- [ ] Analyze slow query patterns
- [ ] Review security violations
- [ ] Optimize batch sizes
- [ ] Update cache strategies

Monthly:
- [ ] Review overall architecture
- [ ] Plan capacity scaling
- [ ] Update security policies
- [ ] Optimize field resolvers

## Success Criteria

The migration is successful when:

1. ✅ All health checks pass (`/graphql/health` returns 200)
2. ✅ Cache hit rate > 70%
3. ✅ P95 query time < 200ms
4. ✅ Zero N+1 query patterns
5. ✅ Security violations < 0.1%
6. ✅ Error rate < 0.5%
7. ✅ All clients successfully migrated

## Support

For issues during migration:

1. Check logs: `grep -i error /var/log/graphql*.log`
2. Review metrics: `curl http://localhost:8002/metrics/graphql`
3. Test individual components: Use the test suite
4. Enable debug mode: `GRAPHQL_DEBUG=true`

## Conclusion

This migration brings significant benefits:
- **Performance**: 10x reduction in database queries via DataLoader
- **Reliability**: Redis caching reduces load
- **Security**: Query validation prevents abuse
- **Observability**: Detailed metrics for optimization
- **Scalability**: Ready for high-traffic production use

Follow this guide carefully, test thoroughly at each phase, and monitor continuously for a successful migration to enterprise-grade GraphQL.