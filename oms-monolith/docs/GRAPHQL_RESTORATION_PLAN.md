# GraphQL Restoration Plan for OMS

## Executive Summary

GraphQL is **ESSENTIAL** for OMS as it provides:
1. **Real-time subscriptions** for collaborative ontology editing
2. **Flexible querying** for complex ontology relationships
3. **Microservice aggregation** reducing client complexity
4. **Type-safe API** with auto-generated documentation

## Current Status

### ✅ What's Working
- Complete GraphQL schema definitions for ontology types
- Query and Mutation resolvers for CRUD operations
- Subscription support for real-time updates
- WebSocket manager for persistent connections
- Integration with microservices (schema, branch, validation)

### ❌ What Was Broken
- Missing authentication functions in `api.gateway.auth`
- Incorrect import paths
- Not registered in main application

### ✅ What We Fixed
1. Created proper GraphQL auth module (`api/graphql/auth.py`)
2. Implemented missing functions:
   - `get_current_user_optional` - Optional auth for public queries
   - `AuthenticationManager` - Session and token management
   - `GraphQLWebSocketAuth` - WebSocket authentication
3. Updated all imports to use correct auth modules
4. Fixed User type references

## Integration Steps

### 1. Register GraphQL in Main App

Add to `main.py`:

```python
# Import GraphQL app
from api.graphql.main import app as graphql_app

# Register GraphQL routes
app.mount("/graphql", graphql_app)
```

### 2. Environment Configuration

Add GraphQL-specific settings:

```python
# GraphQL Configuration
GRAPHQL_ENABLED = os.getenv("GRAPHQL_ENABLED", "true").lower() == "true"
GRAPHQL_PLAYGROUND = os.getenv("GRAPHQL_PLAYGROUND", "true").lower() == "true"
GRAPHQL_SUBSCRIPTIONS = os.getenv("GRAPHQL_SUBSCRIPTIONS", "true").lower() == "true"
```

### 3. Docker Compose Integration

The GraphQL service has its own Dockerfile and can run as:
- Embedded in main app (recommended for simplicity)
- Separate service (for scaling)

## Benefits of GraphQL for OMS

### 1. Real-time Collaboration
```graphql
subscription OnSchemaChange($branch: String!) {
  schemaChanges(branch: $branch) {
    changeType
    resourceType
    resourceId
    timestamp
    actor {
      id
      username
    }
  }
}
```

### 2. Efficient Data Fetching
```graphql
query GetObjectTypeWithRelations($id: ID!) {
  objectType(id: $id) {
    id
    name
    properties {
      name
      dataType {
        name
        category
      }
    }
    interfaces {
      name
    }
    linkedFrom {
      linkType {
        name
      }
      sourceType {
        name
      }
    }
  }
}
```

### 3. Batch Operations
```graphql
mutation CreateMultipleObjectTypes($inputs: [ObjectTypeInput!]!) {
  createObjectTypes(inputs: $inputs) {
    id
    name
    status
  }
}
```

## Security Considerations

1. **Authentication**: Uses same JWT tokens as REST API
2. **Authorization**: Integrated with RBAC middleware
3. **Query Depth Limiting**: Prevent expensive queries
4. **Rate Limiting**: Applied at gateway level

## Testing Strategy

### Unit Tests
- Resolver logic
- Authentication flows
- Schema validation

### Integration Tests
- GraphQL queries against test database
- Subscription message flow
- WebSocket connection lifecycle

### Load Tests
- Query performance with nested relations
- Subscription scalability
- Connection limits

## Migration Path

### Phase 1: Enable GraphQL Alongside REST (Current)
- Both APIs available
- Same business logic
- Gradual client migration

### Phase 2: GraphQL-First Development
- New features in GraphQL first
- REST API wraps GraphQL
- Deprecate redundant endpoints

### Phase 3: GraphQL Primary API
- GraphQL as main API
- REST for legacy support
- Real-time features only in GraphQL

## Next Steps

1. **Immediate**: Register GraphQL in main app
2. **Short-term**: Add GraphQL tests
3. **Medium-term**: Migrate UI to use GraphQL
4. **Long-term**: Deprecate redundant REST endpoints

## Conclusion

GraphQL is not "dead code" but an essential component for modern ontology management. The issues were purely technical (missing auth functions) and have been resolved. GraphQL provides critical features that REST cannot match, especially for real-time collaboration and complex relationship queries.