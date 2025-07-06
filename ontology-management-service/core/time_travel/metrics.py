"""
Time Travel Query Metrics
Prometheus metrics and Jaeger tracing for temporal queries
"""
from typing import Optional, Callable, Any
from functools import wraps
import time
import asyncio

from prometheus_client import Counter, Histogram, Gauge
from core.resilience.unified_circuit_breaker import circuit_breaker
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from common_logging.setup import get_logger

logger = get_logger(__name__)

# Prometheus Metrics
temporal_query_requests = Counter(
    "temporal_query_requests_total",
    "Total temporal query requests",
    ["query_type", "resource_type", "status"]
)

temporal_query_duration = Histogram(
    "temporal_query_duration_seconds",
    "Temporal query execution duration",
    ["query_type", "resource_type"]
)

temporal_query_cache_hits = Counter(
    "temporal_query_cache_hits_total",
    "Temporal query cache hits",
    ["query_type", "resource_type"]
)

temporal_query_cache_misses = Counter(
    "temporal_query_cache_misses_total",
    "Temporal query cache misses",
    ["query_type", "resource_type"]
)

temporal_versions_scanned = Histogram(
    "temporal_versions_scanned",
    "Number of versions scanned per query",
    ["query_type", "resource_type"]
)

temporal_result_size = Histogram(
    "temporal_result_size_bytes",
    "Size of temporal query results",
    ["query_type", "resource_type"]
)

active_temporal_queries = Gauge(
    "active_temporal_queries",
    "Currently executing temporal queries"
)

# Jaeger Tracer
tracer = trace.get_tracer(__name__)


def track_temporal_query(query_type: str):
    """
    Decorator to track temporal query metrics and tracing
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Extract resource type from query
            resource_type = "unknown"
            if len(args) > 1 and hasattr(args[1], 'resource_type'):
                resource_type = args[1].resource_type
            
            # Start timer
            start_time = time.time()
            
            # Update active queries gauge
            active_temporal_queries.inc()
            
            # Start Jaeger span
            with tracer.start_as_current_span(
                f"temporal_query.{query_type}",
                attributes={
                    "query.type": query_type,
                    "resource.type": resource_type,
                    "resource.id": getattr(args[1], 'resource_id', None) if len(args) > 1 else None,
                    "branch": getattr(args[1], 'branch', 'main') if len(args) > 1 else 'main'
                }
            ) as span:
                try:
                    # Execute query
                    result = await func(*args, **kwargs)
                    
                    # Record success metrics
                    duration = time.time() - start_time
                    temporal_query_duration.labels(
                        query_type=query_type,
                        resource_type=resource_type
                    ).observe(duration)
                    
                    temporal_query_requests.labels(
                        query_type=query_type,
                        resource_type=resource_type,
                        status="success"
                    ).inc()
                    
                    # Record result metrics
                    if hasattr(result, 'versions_scanned'):
                        temporal_versions_scanned.labels(
                            query_type=query_type,
                            resource_type=resource_type
                        ).observe(result.versions_scanned)
                    
                    if hasattr(result, 'cache_hit'):
                        if result.cache_hit:
                            temporal_query_cache_hits.labels(
                                query_type=query_type,
                                resource_type=resource_type
                            ).inc()
                        else:
                            temporal_query_cache_misses.labels(
                                query_type=query_type,
                                resource_type=resource_type
                            ).inc()
                    
                    # Add span attributes
                    span.set_attribute("result.count", len(result.resources) if hasattr(result, 'resources') else 0)
                    span.set_attribute("result.cache_hit", getattr(result, 'cache_hit', False))
                    span.set_attribute("execution.time_ms", getattr(result, 'execution_time_ms', duration * 1000))
                    
                    span.set_status(Status(StatusCode.OK))
                    return result
                    
                except Exception as e:
                    # Record error metrics
                    temporal_query_requests.labels(
                        query_type=query_type,
                        resource_type=resource_type,
                        status="error"
                    ).inc()
                    
                    # Record error in span
                    span.record_exception(e)
                    span.set_status(
                        Status(StatusCode.ERROR, str(e))
                    )
                    
                    logger.error(f"Temporal query {query_type} failed: {e}")
                    raise
                    
                finally:
                    # Update active queries gauge
                    active_temporal_queries.dec()
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For sync functions, run in event loop
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(async_wrapper(*args, **kwargs))
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    return decorator


def track_cache_operation(operation: str):
    """
    Decorator to track cache operations
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            with tracer.start_as_current_span(
                f"temporal_cache.{operation}",
                attributes={
                    "cache.operation": operation
                }
            ) as span:
                try:
                    start_time = time.time()
                    result = await func(*args, **kwargs)
                    
                    duration = time.time() - start_time
                    span.set_attribute("duration_ms", duration * 1000)
                    span.set_status(Status(StatusCode.OK))
                    
                    return result
                    
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(
                        Status(StatusCode.ERROR, str(e))
                    )
                    raise
        
        return async_wrapper
    
    return decorator


class TemporalQueryMetrics:
    """
    Helper class for recording temporal query metrics
    """
    
    @staticmethod
    def record_comparison_metrics(
        time_span_seconds: float,
        total_resources: int,
        changes_found: int
    ):
        """Record metrics for temporal comparison queries"""
        with tracer.start_as_current_span("temporal_comparison_metrics") as span:
            span.set_attribute("time_span.seconds", time_span_seconds)
            span.set_attribute("time_span.days", time_span_seconds / 86400)
            span.set_attribute("resources.total", total_resources)
            span.set_attribute("changes.found", changes_found)
            span.set_attribute("changes.percentage", 
                              (changes_found / total_resources * 100) if total_resources > 0 else 0)
    
    @staticmethod
    def record_timeline_metrics(
        resource_type: str,
        resource_id: str,
        total_versions: int,
        timeline_span_days: float
    ):
        """Record metrics for timeline queries"""
        with tracer.start_as_current_span("temporal_timeline_metrics") as span:
            span.set_attribute("resource.type", resource_type)
            span.set_attribute("resource.id", resource_id)
            span.set_attribute("versions.total", total_versions)
            span.set_attribute("timeline.span_days", timeline_span_days)
            span.set_attribute("versions.per_day", 
                              total_versions / timeline_span_days if timeline_span_days > 0 else 0)
    
    @staticmethod
    def record_snapshot_metrics(
        branch: str,
        total_resources: int,
        total_versions: int,
        include_data: bool
    ):
        """Record metrics for snapshot creation"""
        with tracer.start_as_current_span("temporal_snapshot_metrics") as span:
            span.set_attribute("branch", branch)
            span.set_attribute("resources.total", total_resources)
            span.set_attribute("versions.total", total_versions)
            span.set_attribute("include_data", include_data)
            span.set_attribute("average_versions_per_resource",
                              total_versions / total_resources if total_resources > 0 else 0)


# Export decorators with circuit breaker integration
def temporal_query_with_circuit_breaker(query_type: str):
    """
    Combine temporal query tracking with circuit breaker
    """
    def decorator(func: Callable) -> Callable:
        # Apply both decorators
        func = track_temporal_query(query_type)(func)
        func = unified_circuit_breaker("temporal_query")(func)
        return func
    
    return decorator