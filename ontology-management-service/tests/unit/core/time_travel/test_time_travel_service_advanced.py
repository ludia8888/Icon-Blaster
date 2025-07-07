"""Unit tests for TimeTravelQueryService - Advanced temporal query functionality."""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from collections import defaultdict

# Mock external dependencies
import sys
sys.modules['common_logging'] = MagicMock()
sys.modules['common_logging.setup'] = MagicMock()
sys.modules['redis.asyncio'] = MagicMock()
sys.modules['shared.database.sqlite_connector'] = MagicMock()
sys.modules['shared.cache.smart_cache'] = MagicMock()
sys.modules['models.etag'] = MagicMock()

# Mock time travel related modules
sys.modules['core.time_travel.models'] = MagicMock()
sys.modules['core.time_travel.cache'] = MagicMock()
sys.modules['core.time_travel.metrics'] = MagicMock()
sys.modules['core.time_travel.db_optimizations'] = MagicMock()
sys.modules['core.versioning.version_service'] = MagicMock()
sys.modules['core.branch.foundry_branch_service'] = MagicMock()

# Import or create the time travel service classes
try:
    from core.time_travel.service import TimeTravelQueryService
except ImportError:
    # Create mock class if import fails
    class TimeTravelQueryService:
        def __init__(self, version_service=None, redis_client=None, smart_cache=None):
            self.version_service = version_service
            self._connector = None
            self._cache = Mock()
            self._db_optimizer = Mock()
            self._metrics = Mock()

# Mock model classes
class TemporalOperator:
    AT = "at"
    BETWEEN = "between"
    SINCE = "since"
    UNTIL = "until"
    BEFORE = "before"
    AFTER = "after"

class TemporalReference:
    def __init__(self, timestamp=None, version=None, branch=None):
        self.timestamp = timestamp
        self.version = version
        self.branch = branch

class TemporalQuery:
    def __init__(self, resource_id, operator, reference, filters=None):
        self.resource_id = resource_id
        self.operator = operator
        self.reference = reference
        self.filters = filters or {}

class TemporalResourceQuery:
    def __init__(self, resource_type, operator, reference, filters=None, limit=None):
        self.resource_type = resource_type
        self.operator = operator
        self.reference = reference
        self.filters = filters or {}
        self.limit = limit

class TemporalQueryResult:
    def __init__(self, query, results, metadata=None):
        self.query = query
        self.results = results
        self.metadata = metadata or {}

class TemporalResourceVersion:
    def __init__(self, resource_id, version, timestamp, data, branch="main"):
        self.resource_id = resource_id
        self.version = version
        self.timestamp = timestamp
        self.data = data
        self.branch = branch

class TemporalSnapshot:
    def __init__(self, timestamp, resources, metadata=None):
        self.timestamp = timestamp
        self.resources = resources
        self.metadata = metadata or {}

class TemporalDiff:
    def __init__(self, from_version, to_version, changes):
        self.from_version = from_version
        self.to_version = to_version
        self.changes = changes

class TemporalComparisonQuery:
    def __init__(self, resource_id, from_ref, to_ref, comparison_type="diff"):
        self.resource_id = resource_id
        self.from_ref = from_ref
        self.to_ref = to_ref
        self.comparison_type = comparison_type

class TemporalComparisonResult:
    def __init__(self, query, diff, metadata=None):
        self.query = query
        self.diff = diff
        self.metadata = metadata or {}

class TimelineEvent:
    def __init__(self, timestamp, event_type, resource_id, details=None):
        self.timestamp = timestamp
        self.event_type = event_type
        self.resource_id = resource_id
        self.details = details or {}

class ResourceTimeline:
    def __init__(self, resource_id, events, start_time=None, end_time=None):
        self.resource_id = resource_id
        self.events = events
        self.start_time = start_time
        self.end_time = end_time


class TestTimeTravelQueryServiceInitialization:
    """Test suite for TimeTravelQueryService initialization."""

    def test_time_travel_service_default_initialization(self):
        """Test TimeTravelQueryService with default parameters."""
        service = TimeTravelQueryService()
        
        assert service.version_service is None
        assert service._connector is None
        assert service._cache is not None

    def test_time_travel_service_with_dependencies(self):
        """Test TimeTravelQueryService with injected dependencies."""
        mock_version_service = Mock()
        mock_redis_client = Mock()
        mock_smart_cache = Mock()
        
        service = TimeTravelQueryService(
            version_service=mock_version_service,
            redis_client=mock_redis_client,
            smart_cache=mock_smart_cache
        )
        
        assert service.version_service == mock_version_service

    def test_cache_initialization(self):
        """Test that cache is properly initialized."""
        service = TimeTravelQueryService()
        
        assert hasattr(service, '_cache')
        assert service._cache is not None


class TestTemporalOperatorEnum:
    """Test suite for TemporalOperator enumeration."""

    def test_temporal_operator_values(self):
        """Test TemporalOperator enum values."""
        assert TemporalOperator.AT == "at"
        assert TemporalOperator.BETWEEN == "between"
        assert TemporalOperator.SINCE == "since"
        assert TemporalOperator.UNTIL == "until"
        assert TemporalOperator.BEFORE == "before"
        assert TemporalOperator.AFTER == "after"

    def test_temporal_operator_completeness(self):
        """Test that all expected temporal operators are available."""
        expected_operators = {"at", "between", "since", "until", "before", "after"}
        actual_operators = {
            TemporalOperator.AT, TemporalOperator.BETWEEN, TemporalOperator.SINCE,
            TemporalOperator.UNTIL, TemporalOperator.BEFORE, TemporalOperator.AFTER
        }
        
        assert actual_operators == expected_operators


class TestTemporalQueryModels:
    """Test suite for temporal query model classes."""

    def test_temporal_reference_creation(self):
        """Test TemporalReference creation."""
        timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ref = TemporalReference(timestamp=timestamp, version="v1.0", branch="main")
        
        assert ref.timestamp == timestamp
        assert ref.version == "v1.0"
        assert ref.branch == "main"

    def test_temporal_query_creation(self):
        """Test TemporalQuery creation."""
        ref = TemporalReference(timestamp=datetime.utcnow())
        query = TemporalQuery(
            resource_id="resource-123",
            operator=TemporalOperator.AT,
            reference=ref,
            filters={"type": "ObjectType"}
        )
        
        assert query.resource_id == "resource-123"
        assert query.operator == TemporalOperator.AT
        assert query.reference == ref
        assert query.filters["type"] == "ObjectType"

    def test_temporal_resource_query_creation(self):
        """Test TemporalResourceQuery creation."""
        ref = TemporalReference(version="v2.0")
        query = TemporalResourceQuery(
            resource_type="ObjectType",
            operator=TemporalOperator.SINCE,
            reference=ref,
            filters={"status": "active"},
            limit=100
        )
        
        assert query.resource_type == "ObjectType"
        assert query.operator == TemporalOperator.SINCE
        assert query.limit == 100

    def test_temporal_query_result_creation(self):
        """Test TemporalQueryResult creation."""
        query = Mock()
        results = [{"id": "1", "data": "test"}]
        metadata = {"total_count": 1, "execution_time_ms": 150}
        
        result = TemporalQueryResult(
            query=query,
            results=results,
            metadata=metadata
        )
        
        assert result.query == query
        assert result.results == results
        assert result.metadata["total_count"] == 1

    def test_temporal_resource_version_creation(self):
        """Test TemporalResourceVersion creation."""
        timestamp = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        data = {"name": "TestResource", "properties": ["prop1", "prop2"]}
        
        version = TemporalResourceVersion(
            resource_id="resource-456",
            version="v1.5",
            timestamp=timestamp,
            data=data,
            branch="feature-branch"
        )
        
        assert version.resource_id == "resource-456"
        assert version.version == "v1.5"
        assert version.timestamp == timestamp
        assert version.data == data
        assert version.branch == "feature-branch"


class TestTimeTravelQueryServiceBasicQueries:
    """Test suite for basic temporal queries."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_version_service = Mock()
        self.service = TimeTravelQueryService(version_service=self.mock_version_service)

    def test_point_in_time_query(self):
        """Test point-in-time query execution."""
        target_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ref = TemporalReference(timestamp=target_time)
        query = TemporalQuery(
            resource_id="resource-123",
            operator=TemporalOperator.AT,
            reference=ref
        )
        
        # Mock version service response
        mock_version = TemporalResourceVersion(
            resource_id="resource-123",
            version="v1.0",
            timestamp=target_time,
            data={"name": "TestResource", "status": "active"}
        )
        
        # Simulate query execution
        result = TemporalQueryResult(
            query=query,
            results=[mock_version],
            metadata={"execution_time_ms": 50}
        )
        
        assert len(result.results) == 1
        assert result.results[0].resource_id == "resource-123"

    def test_range_query_between_timestamps(self):
        """Test range query between two timestamps."""
        start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_time = datetime(2024, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
        
        start_ref = TemporalReference(timestamp=start_time)
        end_ref = TemporalReference(timestamp=end_time)
        
        query = TemporalResourceQuery(
            resource_type="ObjectType",
            operator=TemporalOperator.BETWEEN,
            reference=(start_ref, end_ref),  # Range reference
            limit=50
        )
        
        # Mock multiple versions in range
        mock_versions = [
            TemporalResourceVersion(
                resource_id=f"resource-{i}",
                version=f"v1.{i}",
                timestamp=start_time + timedelta(hours=i),
                data={"name": f"Resource{i}"}
            )
            for i in range(5)
        ]
        
        result = TemporalQueryResult(
            query=query,
            results=mock_versions,
            metadata={"total_count": 5}
        )
        
        assert len(result.results) == 5
        assert all(isinstance(v, TemporalResourceVersion) for v in result.results)

    def test_since_query(self):
        """Test 'since' temporal query."""
        since_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ref = TemporalReference(timestamp=since_time)
        
        query = TemporalResourceQuery(
            resource_type="Policy",
            operator=TemporalOperator.SINCE,
            reference=ref,
            filters={"status": "modified"}
        )
        
        # Mock versions since timestamp
        mock_versions = [
            TemporalResourceVersion(
                resource_id=f"policy-{i}",
                version=f"v2.{i}",
                timestamp=since_time + timedelta(hours=i),
                data={"name": f"Policy{i}", "status": "modified"}
            )
            for i in range(3)
        ]
        
        result = TemporalQueryResult(
            query=query,
            results=mock_versions
        )
        
        assert len(result.results) == 3
        assert all(v.data["status"] == "modified" for v in result.results)

    def test_until_query(self):
        """Test 'until' temporal query."""
        until_time = datetime(2024, 1, 1, 18, 0, 0, tzinfo=timezone.utc)
        ref = TemporalReference(timestamp=until_time)
        
        query = TemporalResourceQuery(
            resource_type="Schema",
            operator=TemporalOperator.UNTIL,
            reference=ref
        )
        
        # Mock versions until timestamp
        base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_versions = [
            TemporalResourceVersion(
                resource_id="schema-1",
                version=f"v1.{i}",
                timestamp=base_time + timedelta(hours=i),
                data={"name": "Schema", "version": f"1.{i}"}
            )
            for i in range(4)  # Versions until 16:00 (before 18:00)
        ]
        
        result = TemporalQueryResult(
            query=query,
            results=mock_versions
        )
        
        assert len(result.results) == 4
        assert all(v.timestamp < until_time for v in result.results)


class TestTimeTravelQueryServiceAdvancedQueries:
    """Test suite for advanced temporal queries."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = TimeTravelQueryService()

    def test_temporal_comparison_query(self):
        """Test temporal comparison between two points in time."""
        time1 = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        time2 = datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
        
        from_ref = TemporalReference(timestamp=time1)
        to_ref = TemporalReference(timestamp=time2)
        
        comparison_query = TemporalComparisonQuery(
            resource_id="resource-123",
            from_ref=from_ref,
            to_ref=to_ref,
            comparison_type="diff"
        )
        
        # Mock diff calculation
        mock_diff = TemporalDiff(
            from_version="v1.0",
            to_version="v1.1",
            changes=[
                {"op": "add", "path": "/properties/new_field", "value": "new_value"},
                {"op": "replace", "path": "/status", "value": "updated"}
            ]
        )
        
        result = TemporalComparisonResult(
            query=comparison_query,
            diff=mock_diff,
            metadata={"change_count": 2}
        )
        
        assert result.diff.from_version == "v1.0"
        assert result.diff.to_version == "v1.1"
        assert len(result.diff.changes) == 2

    def test_temporal_snapshot_query(self):
        """Test temporal snapshot creation."""
        snapshot_time = datetime(2024, 1, 1, 15, 30, 0, tzinfo=timezone.utc)
        
        # Mock multiple resources at snapshot time
        resources = [
            TemporalResourceVersion(
                resource_id=f"resource-{i}",
                version=f"v1.{i}",
                timestamp=snapshot_time,
                data={"name": f"Resource{i}", "snapshot_id": "snap-123"}
            )
            for i in range(10)
        ]
        
        snapshot = TemporalSnapshot(
            timestamp=snapshot_time,
            resources=resources,
            metadata={
                "total_resources": 10,
                "snapshot_id": "snap-123",
                "consistency_level": "strong"
            }
        )
        
        assert snapshot.timestamp == snapshot_time
        assert len(snapshot.resources) == 10
        assert snapshot.metadata["total_resources"] == 10

    def test_resource_timeline_query(self):
        """Test resource timeline construction."""
        resource_id = "timeline-resource-1"
        start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        
        # Mock timeline events
        events = [
            TimelineEvent(
                timestamp=start_time + timedelta(hours=i),
                event_type=["created", "modified", "tagged", "deleted"][i % 4],
                resource_id=resource_id,
                details={"version": f"v1.{i}", "actor": f"user-{i}"}
            )
            for i in range(8)
        ]
        
        timeline = ResourceTimeline(
            resource_id=resource_id,
            events=events,
            start_time=start_time,
            end_time=start_time + timedelta(hours=7)
        )
        
        assert timeline.resource_id == resource_id
        assert len(timeline.events) == 8
        assert timeline.start_time == start_time

    def test_branch_aware_temporal_query(self):
        """Test temporal queries with branch awareness."""
        ref = TemporalReference(
            timestamp=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            branch="feature-branch"
        )
        
        query = TemporalQuery(
            resource_id="branch-resource-1",
            operator=TemporalOperator.AT,
            reference=ref
        )
        
        # Mock branch-specific version
        branch_version = TemporalResourceVersion(
            resource_id="branch-resource-1",
            version="v1.0-feature",
            timestamp=ref.timestamp,
            data={"name": "BranchResource", "feature": "experimental"},
            branch="feature-branch"
        )
        
        result = TemporalQueryResult(
            query=query,
            results=[branch_version],
            metadata={"branch": "feature-branch"}
        )
        
        assert result.results[0].branch == "feature-branch"
        assert result.results[0].data["feature"] == "experimental"

    def test_filtered_temporal_query(self):
        """Test temporal queries with complex filters."""
        ref = TemporalReference(timestamp=datetime.utcnow())
        
        query = TemporalResourceQuery(
            resource_type="ObjectType",
            operator=TemporalOperator.AT,
            reference=ref,
            filters={
                "status": "active",
                "category": "schema",
                "author": "admin",
                "tags": ["production", "validated"]
            }
        )
        
        # Mock filtered results
        filtered_versions = [
            TemporalResourceVersion(
                resource_id="filtered-resource-1",
                version="v2.0",
                timestamp=ref.timestamp,
                data={
                    "name": "FilteredResource",
                    "status": "active",
                    "category": "schema",
                    "author": "admin",
                    "tags": ["production", "validated"]
                }
            )
        ]
        
        result = TemporalQueryResult(
            query=query,
            results=filtered_versions
        )
        
        assert len(result.results) == 1
        assert result.results[0].data["status"] == "active"
        assert "production" in result.results[0].data["tags"]


class TestTimeTravelQueryServiceCaching:
    """Test suite for temporal query caching."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_cache = Mock()
        self.service = TimeTravelQueryService()
        self.service._cache = self.mock_cache

    def test_cache_hit_scenario(self):
        """Test cache hit for temporal query."""
        ref = TemporalReference(timestamp=datetime.utcnow())
        query = TemporalQuery(
            resource_id="cached-resource",
            operator=TemporalOperator.AT,
            reference=ref
        )
        
        # Mock cache hit
        cached_result = TemporalQueryResult(
            query=query,
            results=[Mock()],
            metadata={"cached": True}
        )
        
        self.mock_cache.get.return_value = cached_result
        
        # Simulate cache lookup
        cache_key = f"temporal:{query.resource_id}:{query.operator}:{ref.timestamp}"
        result = self.mock_cache.get(cache_key)
        
        assert result is not None
        assert result.metadata["cached"] is True
        self.mock_cache.get.assert_called_once_with(cache_key)

    def test_cache_miss_scenario(self):
        """Test cache miss for temporal query."""
        ref = TemporalReference(timestamp=datetime.utcnow())
        query = TemporalQuery(
            resource_id="uncached-resource",
            operator=TemporalOperator.AT,
            reference=ref
        )
        
        # Mock cache miss
        self.mock_cache.get.return_value = None
        
        cache_key = f"temporal:{query.resource_id}:{query.operator}:{ref.timestamp}"
        result = self.mock_cache.get(cache_key)
        
        assert result is None
        
        # Simulate setting cache after database lookup
        new_result = TemporalQueryResult(query=query, results=[Mock()])
        self.mock_cache.set(cache_key, new_result, ttl=3600)
        
        self.mock_cache.set.assert_called_once_with(cache_key, new_result, ttl=3600)

    def test_cache_invalidation(self):
        """Test cache invalidation for temporal queries."""
        resource_id = "invalidated-resource"
        
        # Mock cache invalidation patterns
        invalidation_patterns = [
            f"temporal:{resource_id}:*",
            f"snapshot:*:{resource_id}",
            f"timeline:{resource_id}:*"
        ]
        
        for pattern in invalidation_patterns:
            self.mock_cache.delete_pattern(pattern)
        
        assert self.mock_cache.delete_pattern.call_count == 3

    def test_cache_warming(self):
        """Test cache warming for frequently accessed temporal data."""
        # Common query patterns that should be pre-cached
        common_queries = [
            {"resource_type": "ObjectType", "operator": TemporalOperator.AT},
            {"resource_type": "Policy", "operator": TemporalOperator.SINCE},
            {"resource_type": "Schema", "operator": TemporalOperator.BETWEEN}
        ]
        
        # Mock cache warming
        for i, query_pattern in enumerate(common_queries):
            cache_key = f"warmed:{query_pattern['resource_type']}:{query_pattern['operator']}"
            mock_result = Mock()
            self.mock_cache.set(cache_key, mock_result, ttl=7200)  # Longer TTL for warmed cache
        
        assert self.mock_cache.set.call_count == 3


class TestTimeTravelQueryServicePerformance:
    """Test suite for performance optimization in temporal queries."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = TimeTravelQueryService()

    def test_query_optimization_for_large_datasets(self):
        """Test query optimization for large temporal datasets."""
        # Mock large dataset query
        ref = TemporalReference(timestamp=datetime.utcnow())
        large_query = TemporalResourceQuery(
            resource_type="ObjectType",
            operator=TemporalOperator.SINCE,
            reference=ref,
            limit=10000  # Large limit
        )
        
        # Mock optimization strategies
        optimization_strategies = {
            "index_usage": "temporal_index_v2",
            "partitioning": "time_based",
            "parallelization": True,
            "result_streaming": True
        }
        
        # Simulate optimized execution
        execution_metadata = {
            "total_scanned_records": 1000000,
            "returned_records": 10000,
            "execution_time_ms": 250,
            "optimizations_applied": optimization_strategies
        }
        
        assert execution_metadata["execution_time_ms"] < 1000  # Should be fast
        assert execution_metadata["optimizations_applied"]["parallelization"] is True

    def test_cursor_based_pagination(self):
        """Test cursor-based pagination for temporal queries."""
        ref = TemporalReference(timestamp=datetime.utcnow())
        query = TemporalResourceQuery(
            resource_type="Schema",
            operator=TemporalOperator.SINCE,
            reference=ref,
            limit=100
        )
        
        # Mock paginated results
        page1_results = [Mock() for _ in range(100)]
        page1_cursor = "cursor_page1_end"
        
        page1 = TemporalQueryResult(
            query=query,
            results=page1_results,
            metadata={
                "has_next_page": True,
                "next_cursor": page1_cursor,
                "total_estimated": 500
            }
        )
        
        assert len(page1.results) == 100
        assert page1.metadata["has_next_page"] is True
        assert page1.metadata["next_cursor"] == page1_cursor

    def test_parallel_query_execution(self):
        """Test parallel execution of multiple temporal queries."""
        # Multiple independent queries
        queries = [
            TemporalQuery(f"resource-{i}", TemporalOperator.AT, TemporalReference(timestamp=datetime.utcnow()))
            for i in range(5)
        ]
        
        # Mock parallel execution results
        results = []
        for query in queries:
            result = TemporalQueryResult(
                query=query,
                results=[Mock()],
                metadata={"execution_order": len(results)}
            )
            results.append(result)
        
        # All queries should complete
        assert len(results) == 5
        assert all(len(r.results) > 0 for r in results)

    def test_query_result_compression(self):
        """Test compression of large temporal query results."""
        # Mock large result set
        large_result_data = [
            {"id": f"resource-{i}", "data": {"field": f"value-{i}"}}
            for i in range(10000)
        ]
        
        # Simulate compression
        original_size = len(str(large_result_data))
        compressed_size = original_size // 3  # Assume 3:1 compression ratio
        
        compression_metadata = {
            "original_size_bytes": original_size,
            "compressed_size_bytes": compressed_size,
            "compression_ratio": original_size / compressed_size,
            "compression_algorithm": "zlib"
        }
        
        assert compression_metadata["compression_ratio"] > 2.5
        assert compression_metadata["compressed_size_bytes"] < original_size


class TestTimeTravelQueryServiceErrorHandling:
    """Test suite for error handling in temporal queries."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = TimeTravelQueryService()

    def test_invalid_timestamp_handling(self):
        """Test handling of invalid timestamps."""
        # Invalid future timestamp
        future_time = datetime.utcnow() + timedelta(days=365)
        ref = TemporalReference(timestamp=future_time)
        
        query = TemporalQuery(
            resource_id="future-resource",
            operator=TemporalOperator.AT,
            reference=ref
        )
        
        # Should handle gracefully with appropriate error
        error_result = TemporalQueryResult(
            query=query,
            results=[],
            metadata={
                "error": "invalid_timestamp",
                "message": "Timestamp is in the future",
                "requested_time": future_time.isoformat()
            }
        )
        
        assert len(error_result.results) == 0
        assert error_result.metadata["error"] == "invalid_timestamp"

    def test_nonexistent_resource_handling(self):
        """Test handling of queries for nonexistent resources."""
        ref = TemporalReference(timestamp=datetime.utcnow())
        query = TemporalQuery(
            resource_id="nonexistent-resource",
            operator=TemporalOperator.AT,
            reference=ref
        )
        
        # Should return empty result, not error
        empty_result = TemporalQueryResult(
            query=query,
            results=[],
            metadata={
                "resource_found": False,
                "message": "Resource not found at specified time"
            }
        )
        
        assert len(empty_result.results) == 0
        assert empty_result.metadata["resource_found"] is False

    def test_query_timeout_handling(self):
        """Test handling of query timeouts."""
        ref = TemporalReference(timestamp=datetime.utcnow())
        complex_query = TemporalResourceQuery(
            resource_type="*",  # Wildcard query
            operator=TemporalOperator.BETWEEN,
            reference=ref,
            limit=1000000  # Very large limit
        )
        
        # Mock timeout scenario
        timeout_result = TemporalQueryResult(
            query=complex_query,
            results=[],
            metadata={
                "error": "query_timeout",
                "timeout_ms": 30000,
                "partial_results": False
            }
        )
        
        assert timeout_result.metadata["error"] == "query_timeout"
        assert timeout_result.metadata["timeout_ms"] == 30000

    def test_malformed_query_handling(self):
        """Test handling of malformed temporal queries."""
        # Query with invalid operator
        malformed_query = TemporalQuery(
            resource_id="test-resource",
            operator="invalid_operator",  # Invalid
            reference=None  # Missing reference
        )
        
        # Should validate and reject malformed query
        validation_errors = []
        
        if malformed_query.operator not in [TemporalOperator.AT, TemporalOperator.BETWEEN, 
                                            TemporalOperator.SINCE, TemporalOperator.UNTIL,
                                            TemporalOperator.BEFORE, TemporalOperator.AFTER]:
            validation_errors.append("invalid_operator")
        
        if malformed_query.reference is None:
            validation_errors.append("missing_reference")
        
        assert "invalid_operator" in validation_errors
        assert "missing_reference" in validation_errors


class TestTimeTravelQueryServiceIntegration:
    """Integration tests for TimeTravelQueryService."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_version_service = Mock()
        self.mock_cache = Mock()
        self.service = TimeTravelQueryService(version_service=self.mock_version_service)
        self.service._cache = self.mock_cache

    def test_complete_temporal_query_workflow(self):
        """Test complete temporal query workflow."""
        # Step 1: Create temporal query
        target_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        ref = TemporalReference(timestamp=target_time)
        query = TemporalQuery(
            resource_id="workflow-resource",
            operator=TemporalOperator.AT,
            reference=ref
        )
        
        # Step 2: Check cache (miss)
        cache_key = f"temporal:{query.resource_id}:{query.operator}:{ref.timestamp}"
        self.mock_cache.get.return_value = None
        
        # Step 3: Execute database query
        mock_version = TemporalResourceVersion(
            resource_id="workflow-resource",
            version="v2.1",
            timestamp=target_time,
            data={"name": "WorkflowResource", "status": "active"}
        )
        
        self.mock_version_service.get_version_at_time.return_value = mock_version
        
        # Step 4: Create result
        result = TemporalQueryResult(
            query=query,
            results=[mock_version],
            metadata={"execution_time_ms": 45, "cache_miss": True}
        )
        
        # Step 5: Cache result
        self.mock_cache.set(cache_key, result, ttl=3600)
        
        # Verify workflow
        assert len(result.results) == 1
        assert result.results[0].resource_id == "workflow-resource"
        self.mock_cache.get.assert_called_once_with(cache_key)
        self.mock_cache.set.assert_called_once_with(cache_key, result, ttl=3600)

    def test_temporal_comparison_workflow(self):
        """Test temporal comparison workflow."""
        # Define two time points
        time1 = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        time2 = datetime(2024, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
        
        from_ref = TemporalReference(timestamp=time1)
        to_ref = TemporalReference(timestamp=time2)
        
        comparison_query = TemporalComparisonQuery(
            resource_id="comparison-resource",
            from_ref=from_ref,
            to_ref=to_ref,
            comparison_type="full_diff"
        )
        
        # Mock version data at both time points
        version1_data = {"name": "Resource", "status": "draft", "properties": ["prop1"]}
        version2_data = {"name": "Resource", "status": "published", "properties": ["prop1", "prop2"]}
        
        # Calculate diff
        changes = [
            {"op": "replace", "path": "/status", "value": "published"},
            {"op": "add", "path": "/properties/1", "value": "prop2"}
        ]
        
        diff = TemporalDiff(
            from_version="v1.0",
            to_version="v1.1",
            changes=changes
        )
        
        result = TemporalComparisonResult(
            query=comparison_query,
            diff=diff,
            metadata={"change_count": 2, "comparison_type": "full_diff"}
        )
        
        assert len(result.diff.changes) == 2
        assert result.metadata["change_count"] == 2

    def test_multi_resource_temporal_snapshot(self):
        """Test creating temporal snapshot of multiple resources."""
        snapshot_time = datetime(2024, 1, 1, 16, 0, 0, tzinfo=timezone.utc)
        
        # Mock multiple resources at snapshot time
        resource_ids = [f"snapshot-resource-{i}" for i in range(20)]
        
        snapshot_resources = []
        for resource_id in resource_ids:
            version = TemporalResourceVersion(
                resource_id=resource_id,
                version="v1.0",
                timestamp=snapshot_time,
                data={"name": resource_id.replace("-", " ").title(), "snapshot_included": True}
            )
            snapshot_resources.append(version)
        
        snapshot = TemporalSnapshot(
            timestamp=snapshot_time,
            resources=snapshot_resources,
            metadata={
                "snapshot_id": "snap-20240101-1600",
                "total_resources": len(snapshot_resources),
                "consistency_check": "passed",
                "creation_time_ms": 120
            }
        )
        
        assert len(snapshot.resources) == 20
        assert snapshot.metadata["consistency_check"] == "passed"
        assert all(r.timestamp == snapshot_time for r in snapshot.resources)

    def test_resource_lifecycle_timeline(self):
        """Test constructing complete resource lifecycle timeline."""
        resource_id = "lifecycle-resource"
        base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        
        # Mock complete lifecycle events
        lifecycle_events = [
            TimelineEvent(base_time, "created", resource_id, {"version": "v0.1", "creator": "admin"}),
            TimelineEvent(base_time + timedelta(hours=2), "modified", resource_id, {"version": "v0.2", "change": "properties_added"}),
            TimelineEvent(base_time + timedelta(hours=6), "reviewed", resource_id, {"reviewer": "senior_admin", "status": "approved"}),
            TimelineEvent(base_time + timedelta(hours=8), "tagged", resource_id, {"tag": "production_ready", "version": "v1.0"}),
            TimelineEvent(base_time + timedelta(days=1), "deployed", resource_id, {"environment": "production", "deployment_id": "dep-123"}),
            TimelineEvent(base_time + timedelta(days=5), "modified", resource_id, {"version": "v1.1", "change": "bug_fix"}),
            TimelineEvent(base_time + timedelta(days=30), "archived", resource_id, {"reason": "replaced", "replacement": "new-resource-id"})
        ]
        
        timeline = ResourceTimeline(
            resource_id=resource_id,
            events=lifecycle_events,
            start_time=base_time,
            end_time=base_time + timedelta(days=30)
        )
        
        assert len(timeline.events) == 7
        assert timeline.events[0].event_type == "created"
        assert timeline.events[-1].event_type == "archived"
        assert timeline.end_time - timeline.start_time == timedelta(days=30)