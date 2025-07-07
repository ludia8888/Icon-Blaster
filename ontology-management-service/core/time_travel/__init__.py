"""
Time Travel Query Module
Provides temporal query capabilities for point-in-time data access
"""

from .models import (
    TemporalOperator,
    TemporalReference,
    TemporalQuery,
    TemporalResourceQuery,
    TemporalJoinQuery,
    TemporalResourceVersion,
    TemporalQueryResult,
    TemporalDiff,
    TemporalSnapshot,
    TemporalComparisonQuery,
    TemporalComparisonResult,
    TimelineEvent,
    ResourceTimeline
)

from .service import (
    TimeTravelQueryService,
    get_time_travel_service
)

from .cache import TemporalQueryCache
from .metrics import (
    temporal_query_requests,
    temporal_query_duration,
    temporal_query_cache_hits,
    temporal_query_cache_misses,
    temporal_versions_scanned,
    active_temporal_queries
)
from .db_optimizations import TimeTravelDBOptimizer, TemporalCursorPagination

__all__ = [
    # Models
    "TemporalOperator",
    "TemporalReference",
    "TemporalQuery",
    "TemporalResourceQuery",
    "TemporalJoinQuery",
    "TemporalResourceVersion",
    "TemporalQueryResult",
    "TemporalDiff",
    "TemporalSnapshot",
    "TemporalComparisonQuery",
    "TemporalComparisonResult",
    "TimelineEvent",
    "ResourceTimeline",
    
    # Service
    "TimeTravelQueryService",
    "get_time_travel_service",
    
    # Cache
    "TemporalQueryCache",
    
    # Metrics
    "temporal_query_requests",
    "temporal_query_duration",
    "temporal_query_cache_hits",
    "temporal_query_cache_misses",
    "temporal_versions_scanned",
    "active_temporal_queries",
    
    # Optimizations
    "TimeTravelDBOptimizer",
    "TemporalCursorPagination"
]