# Time Travel Queries API Documentation

## Overview

The Time Travel Queries API provides temporal query capabilities for accessing historical states of resources in the OMS. This allows you to query data as it existed at any point in time, compare states between different time periods, and analyze change history.

## Key Features

- **Point-in-Time Queries (AS OF)**: Query resources as they were at a specific timestamp
- **Time Range Queries (BETWEEN)**: Get all versions of resources within a time range
- **Version History (ALL_VERSIONS)**: Retrieve complete version history for resources
- **Temporal Comparison**: Compare system state between two points in time
- **Resource Timeline**: View complete change history for individual resources
- **System Snapshots**: Capture entire system state at a specific time

## GraphQL API

### Temporal Query

Execute temporal queries to access historical data.

```graphql
query TemporalQuery {
  temporalQuery(query: {
    resourceType: "object_type"
    resourceId: "User"
    branch: "main"
    temporal: {
      operator: AS_OF
      pointInTime: {
        relativeTime: "-1d"  # 1 day ago
      }
      includeDeleted: false
      includeMetadata: true
    }
    limit: 100
    offset: 0
  }) {
    resources {
      resourceType
      resourceId
      version
      commitHash
      validTime
      content
      modifiedBy
      changeType
      changeSummary
    }
    totalCount
    hasMore
    executionTimeMs
  }
}
```

### Temporal Operators

- **AS_OF**: Query data as it existed at a specific point in time
- **BETWEEN**: Query all versions between two time points
- **FROM_TO**: Similar to BETWEEN with inclusive boundaries
- **ALL_VERSIONS**: Get complete version history
- **BEFORE**: Query data before a specific time
- **AFTER**: Query data after a specific time

### Temporal Reference Options

You can specify time in multiple ways:

```graphql
# Using specific timestamp
pointInTime: {
  timestamp: "2024-01-01T00:00:00Z"
}

# Using relative time
pointInTime: {
  relativeTime: "-7d"  # 7 days ago
}

# Using version number
pointInTime: {
  version: 5
}

# Using commit hash
pointInTime: {
  commitHash: "abc123..."
}
```

### Compare States

Compare resource states between two points in time:

```graphql
query CompareStates {
  temporalComparison(comparison: {
    resourceTypes: ["object_type", "property"]
    branch: "main"
    time1: { relativeTime: "-7d" }
    time2: { timestamp: "2024-01-15T00:00:00Z" }
    includeUnchanged: false
    detailedDiff: true
  }) {
    time1Resolved
    time2Resolved
    differences
    totalCreated
    totalUpdated
    totalDeleted
    totalUnchanged
    executionTimeMs
  }
}
```

### Resource Timeline

Get complete change history for a resource:

```graphql
query ResourceTimeline {
  resourceTimeline(
    resourceType: "object_type"
    resourceId: "User"
    branch: "main"
  ) {
    resourceType
    resourceId
    events {
      timestamp
      version
      commitHash
      eventType
      description
      modifiedBy
      changeSummary
      fieldsChanged
    }
    createdAt
    lastModifiedAt
    deletedAt
    totalVersions
    totalUpdates
    uniqueContributors
    averageTimeBetweenChanges
  }
}
```

### System Snapshot

Capture system state at a specific time:

```graphql
query SystemSnapshot {
  temporalSnapshot(
    branch: "main"
    timestamp: "2024-01-01T00:00:00Z"
    includeData: false
  ) {
    branch
    timestamp
    resourceCounts
    totalResources
    totalVersions
    createdAt
    createdBy
  }
}
```

## REST API

### AS OF Query

```bash
POST /api/v1/time-travel/as-of
Content-Type: application/json

{
  "resource_type": "object_type",
  "resource_id": "User",
  "branch": "main",
  "point_in_time": {
    "relative_time": "-1d"
  },
  "include_deleted": false,
  "limit": 100,
  "offset": 0
}
```

### BETWEEN Query

```bash
POST /api/v1/time-travel/between
Content-Type: application/json

{
  "resource_type": "object_type",
  "branch": "main",
  "start_time": {
    "relative_time": "-7d"
  },
  "end_time": {
    "timestamp": "2024-01-15T00:00:00Z"
  },
  "include_deleted": false,
  "limit": 100
}
```

### Get All Versions

```bash
GET /api/v1/time-travel/versions/object_type/User?branch=main&limit=50
```

### Compare States

```bash
POST /api/v1/time-travel/compare
Content-Type: application/json

{
  "resource_types": ["object_type", "property"],
  "branch": "main",
  "time1": { "relative_time": "-7d" },
  "time2": { "relative_time": "-1d" },
  "include_unchanged": false,
  "detailed_diff": true
}
```

### Get Timeline

```bash
GET /api/v1/time-travel/timeline/object_type/User?branch=main
```

### Get Resource at Time

```bash
GET /api/v1/time-travel/resource-at-time?resource_type=object_type&resource_id=User&branch=main&relative_time=-1d
```

## Use Cases

### 1. Audit Trail

Track all changes to critical resources:

```graphql
query AuditTrail {
  resourceTimeline(
    resourceType: "object_type"
    resourceId: "SensitiveData"
    branch: "main"
  ) {
    events {
      timestamp
      modifiedBy
      changeSummary
      fieldsChanged
    }
  }
}
```

### 2. Change Impact Analysis

Analyze what changed between releases:

```graphql
query ReleaseComparison {
  temporalComparison(comparison: {
    resourceTypes: ["object_type", "property", "link_type"]
    branch: "main"
    time1: { timestamp: "2024-01-01T00:00:00Z" }  # v1.0 release
    time2: { timestamp: "2024-02-01T00:00:00Z" }  # v2.0 release
    detailedDiff: true
  }) {
    differences
    totalCreated
    totalUpdated
    totalDeleted
  }
}
```

### 3. Data Recovery

Recover accidentally deleted resources:

```graphql
query RecoverDeleted {
  temporalQuery(query: {
    resourceType: "object_type"
    resourceId: "DeletedResource"
    branch: "main"
    temporal: {
      operator: AS_OF
      pointInTime: {
        relativeTime: "-1h"  # Before deletion
      }
    }
  }) {
    resources {
      content  # Original resource data
    }
  }
}
```

### 4. Historical Analysis

Analyze system evolution over time:

```graphql
query SystemEvolution {
  # Get snapshots at different times
  snapshot1: temporalSnapshot(
    branch: "main"
    timestamp: "2023-01-01T00:00:00Z"
  ) {
    totalResources
    resourceCounts
  }
  
  snapshot2: temporalSnapshot(
    branch: "main"
    timestamp: "2024-01-01T00:00:00Z"
  ) {
    totalResources
    resourceCounts
  }
}
```

## Performance Considerations

1. **Indexing**: All temporal queries use indexed columns (timestamp, version, resource_type)
2. **Caching**: Query results are cached for repeated access
3. **Batch Operations**: Use batch queries when comparing multiple resources
4. **Time Range Limits**: Be mindful of query time ranges to avoid large result sets

## Best Practices

1. **Use Relative Time**: For recent queries, use relative time (`-1h`, `-7d`) for better readability
2. **Limit Results**: Always specify reasonable limits to prevent overwhelming responses
3. **Include Metadata**: Set `includeMetadata: true` to get additional context about changes
4. **Exclude Deleted**: Unless specifically needed, set `includeDeleted: false` to filter out deleted resources
5. **Detailed Diffs**: Enable `detailedDiff` only when needed as it increases response size

## Error Handling

Common error scenarios:

- **Invalid Temporal Reference**: Ensure time references are valid
- **Resource Not Found**: The resource may not have existed at the specified time
- **Permission Denied**: User may not have access to historical data
- **Time Range Too Large**: Split large queries into smaller time ranges

## Security

- All temporal queries respect the same permissions as regular queries
- Audit logs track all temporal query access
- Sensitive data masking applies to historical data as well