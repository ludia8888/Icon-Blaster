"""
GraphQL Performance Monitoring and Tracing
OpenTelemetry integration with detailed metrics
"""
import time
import asyncio
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import json

from opentelemetry import trace, metrics
from opentelemetry.trace import Status, StatusCode
from opentelemetry.metrics import CallbackOptions, Observation
import prometheus_client

from utils.logger import get_logger

logger = get_logger(__name__)

# OpenTelemetry setup
tracer = trace.get_tracer("graphql.monitoring")
meter = metrics.get_meter("graphql.monitoring")

# Prometheus metrics
query_duration_histogram = prometheus_client.Histogram(
    'graphql_query_duration_seconds',
    'GraphQL query duration in seconds',
    ['operation_type', 'operation_name', 'client_type']
)

query_complexity_histogram = prometheus_client.Histogram(
    'graphql_query_complexity',
    'GraphQL query complexity score',
    ['operation_type', 'operation_name']
)

field_resolution_counter = prometheus_client.Counter(
    'graphql_field_resolutions_total',
    'Total number of field resolutions',
    ['field_name', 'parent_type']
)

error_counter = prometheus_client.Counter(
    'graphql_errors_total',
    'Total number of GraphQL errors',
    ['error_type', 'operation_name']
)

cache_operations = prometheus_client.Counter(
    'graphql_cache_operations_total',
    'GraphQL cache operations',
    ['operation', 'result']  # operation: get/set, result: hit/miss
)

dataloader_batch_size = prometheus_client.Histogram(
    'graphql_dataloader_batch_size',
    'DataLoader batch sizes',
    ['loader_name']
)


@dataclass
class FieldMetrics:
    """Metrics for a single field resolution"""
    field_name: str
    parent_type: str
    start_time: float
    end_time: Optional[float] = None
    error: Optional[str] = None
    resolver_name: Optional[str] = None
    
    @property
    def duration(self) -> float:
        """Duration in milliseconds"""
        if self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0


@dataclass
class QueryMetrics:
    """Metrics for a complete GraphQL query"""
    operation_type: str
    operation_name: Optional[str]
    query_string: str
    start_time: float
    end_time: Optional[float] = None
    complexity_score: int = 0
    depth: int = 0
    field_metrics: List[FieldMetrics] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    cache_hits: int = 0
    cache_misses: int = 0
    dataloader_batches: Dict[str, List[int]] = field(default_factory=lambda: defaultdict(list))
    
    @property
    def duration(self) -> float:
        """Duration in milliseconds"""
        if self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0
    
    @property
    def total_fields(self) -> int:
        """Total number of fields resolved"""
        return len(self.field_metrics)
    
    @property
    def error_count(self) -> int:
        """Total number of errors"""
        return len(self.errors)
    
    def add_field_metric(self, metric: FieldMetrics):
        """Add field resolution metric"""
        self.field_metrics.append(metric)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/storage"""
        return {
            "operation_type": self.operation_type,
            "operation_name": self.operation_name,
            "duration_ms": self.duration,
            "complexity_score": self.complexity_score,
            "depth": self.depth,
            "total_fields": self.total_fields,
            "error_count": self.error_count,
            "cache_hit_rate": self.cache_hits / (self.cache_hits + self.cache_misses) if (self.cache_hits + self.cache_misses) > 0 else 0,
            "slowest_fields": sorted(
                [
                    {
                        "field": f.field_name,
                        "parent": f.parent_type,
                        "duration_ms": f.duration
                    }
                    for f in self.field_metrics
                ],
                key=lambda x: x["duration_ms"],
                reverse=True
            )[:5]  # Top 5 slowest fields
        }


class PerformanceMonitor:
    """
    Central performance monitoring for GraphQL
    Tracks query performance, field resolution times, and resource usage
    """
    
    def __init__(self):
        self.active_queries: Dict[str, QueryMetrics] = {}
        self.completed_queries: List[QueryMetrics] = []
        self.max_completed_queries = 1000  # Keep last N queries
        
        # Real-time metrics
        self.current_active_queries = 0
        self.total_queries_processed = 0
        
        # Create OpenTelemetry metrics
        self._create_otel_metrics()
    
    def _create_otel_metrics(self):
        """Create OpenTelemetry metrics"""
        # Active queries gauge
        meter.create_observable_gauge(
            name="graphql.active_queries",
            callbacks=[self._get_active_queries],
            description="Number of currently active GraphQL queries"
        )
        
        # Query duration histogram
        self.query_duration_metric = meter.create_histogram(
            name="graphql.query.duration",
            unit="ms",
            description="GraphQL query duration in milliseconds"
        )
        
        # Field resolution counter
        self.field_resolution_metric = meter.create_counter(
            name="graphql.field.resolutions",
            description="Number of GraphQL field resolutions"
        )
    
    def _get_active_queries(self, options: CallbackOptions) -> List[Observation]:
        """Callback for active queries metric"""
        return [Observation(self.current_active_queries)]
    
    def start_query(
        self,
        query_id: str,
        operation_type: str,
        operation_name: Optional[str],
        query_string: str
    ) -> QueryMetrics:
        """Start tracking a query"""
        metrics = QueryMetrics(
            operation_type=operation_type,
            operation_name=operation_name,
            query_string=query_string,
            start_time=time.time()
        )
        
        self.active_queries[query_id] = metrics
        self.current_active_queries += 1
        
        return metrics
    
    def end_query(self, query_id: str) -> Optional[QueryMetrics]:
        """End tracking a query"""
        metrics = self.active_queries.pop(query_id, None)
        if not metrics:
            return None
        
        metrics.end_time = time.time()
        self.current_active_queries -= 1
        self.total_queries_processed += 1
        
        # Record metrics
        self._record_query_metrics(metrics)
        
        # Store completed query
        self.completed_queries.append(metrics)
        if len(self.completed_queries) > self.max_completed_queries:
            self.completed_queries.pop(0)
        
        return metrics
    
    def start_field_resolution(
        self,
        query_id: str,
        field_name: str,
        parent_type: str
    ) -> FieldMetrics:
        """Start tracking field resolution"""
        field_metric = FieldMetrics(
            field_name=field_name,
            parent_type=parent_type,
            start_time=time.time()
        )
        
        query_metrics = self.active_queries.get(query_id)
        if query_metrics:
            query_metrics.add_field_metric(field_metric)
        
        return field_metric
    
    def end_field_resolution(
        self,
        field_metric: FieldMetrics,
        error: Optional[str] = None
    ):
        """End tracking field resolution"""
        field_metric.end_time = time.time()
        field_metric.error = error
        
        # Record Prometheus metrics
        field_resolution_counter.labels(
            field_name=field_metric.field_name,
            parent_type=field_metric.parent_type
        ).inc()
        
        # Record OpenTelemetry metrics
        self.field_resolution_metric.add(
            1,
            attributes={
                "field_name": field_metric.field_name,
                "parent_type": field_metric.parent_type,
                "has_error": error is not None
            }
        )
    
    def record_cache_operation(
        self,
        query_id: str,
        operation: str,
        hit: bool
    ):
        """Record cache operation"""
        query_metrics = self.active_queries.get(query_id)
        if query_metrics:
            if hit:
                query_metrics.cache_hits += 1
            else:
                query_metrics.cache_misses += 1
        
        # Prometheus metric
        cache_operations.labels(
            operation=operation,
            result="hit" if hit else "miss"
        ).inc()
    
    def record_dataloader_batch(
        self,
        query_id: str,
        loader_name: str,
        batch_size: int
    ):
        """Record DataLoader batch operation"""
        query_metrics = self.active_queries.get(query_id)
        if query_metrics:
            query_metrics.dataloader_batches[loader_name].append(batch_size)
        
        # Prometheus metric
        dataloader_batch_size.labels(loader_name=loader_name).observe(batch_size)
    
    def record_error(
        self,
        query_id: str,
        error_type: str,
        error_message: str,
        field_name: Optional[str] = None
    ):
        """Record an error"""
        query_metrics = self.active_queries.get(query_id)
        if query_metrics:
            query_metrics.errors.append({
                "type": error_type,
                "message": error_message,
                "field": field_name,
                "timestamp": time.time()
            })
        
        # Prometheus metric
        operation_name = query_metrics.operation_name if query_metrics else "unknown"
        error_counter.labels(
            error_type=error_type,
            operation_name=operation_name
        ).inc()
    
    def _record_query_metrics(self, metrics: QueryMetrics):
        """Record query metrics to monitoring systems"""
        # Prometheus
        query_duration_histogram.labels(
            operation_type=metrics.operation_type,
            operation_name=metrics.operation_name or "anonymous",
            client_type="unknown"  # Would be extracted from context
        ).observe(metrics.duration / 1000)  # Convert to seconds
        
        query_complexity_histogram.labels(
            operation_type=metrics.operation_type,
            operation_name=metrics.operation_name or "anonymous"
        ).observe(metrics.complexity_score)
        
        # OpenTelemetry
        self.query_duration_metric.record(
            metrics.duration,
            attributes={
                "operation_type": metrics.operation_type,
                "operation_name": metrics.operation_name or "anonymous",
                "has_errors": metrics.error_count > 0,
                "complexity": metrics.complexity_score
            }
        )
        
        # Log slow queries
        if metrics.duration > 1000:  # > 1 second
            logger.warning(
                f"Slow GraphQL query detected",
                extra=metrics.to_dict()
            )
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary"""
        if not self.completed_queries:
            return {
                "total_queries": 0,
                "active_queries": self.current_active_queries
            }
        
        durations = [q.duration for q in self.completed_queries]
        complexities = [q.complexity_score for q in self.completed_queries]
        error_rates = [q.error_count for q in self.completed_queries]
        
        return {
            "total_queries": self.total_queries_processed,
            "active_queries": self.current_active_queries,
            "performance": {
                "avg_duration_ms": sum(durations) / len(durations),
                "p50_duration_ms": sorted(durations)[len(durations) // 2],
                "p95_duration_ms": sorted(durations)[int(len(durations) * 0.95)],
                "p99_duration_ms": sorted(durations)[int(len(durations) * 0.99)]
            },
            "complexity": {
                "avg": sum(complexities) / len(complexities),
                "max": max(complexities)
            },
            "errors": {
                "total": sum(error_rates),
                "rate": sum(error_rates) / len(error_rates)
            }
        }


class TracingMiddleware:
    """
    OpenTelemetry tracing middleware for GraphQL
    Creates detailed traces for query execution
    """
    
    def __init__(self, monitor: PerformanceMonitor):
        self.monitor = monitor
    
    async def resolve(self, next_resolver, root, info, **args):
        """Traced field resolution"""
        field_name = info.field_name
        parent_type = info.parent_type.name
        
        # Create span
        with tracer.start_as_current_span(
            f"graphql.resolve.{parent_type}.{field_name}"
        ) as span:
            # Add span attributes
            span.set_attribute("graphql.field.name", field_name)
            span.set_attribute("graphql.field.parent_type", parent_type)
            span.set_attribute("graphql.field.path", ".".join(map(str, info.path.as_list())))
            
            # Get query ID from context
            query_id = info.context.get("query_id")
            if query_id:
                span.set_attribute("graphql.query.id", query_id)
            
            # Start field metric
            field_metric = None
            if query_id:
                field_metric = self.monitor.start_field_resolution(
                    query_id,
                    field_name,
                    parent_type
                )
            
            try:
                # Resolve field
                result = await next_resolver(root, info, **args)
                
                # Record success
                span.set_status(Status(StatusCode.OK))
                
                return result
                
            except Exception as e:
                # Record error
                span.set_status(
                    Status(StatusCode.ERROR, str(e))
                )
                span.record_exception(e)
                
                if field_metric:
                    self.monitor.end_field_resolution(
                        field_metric,
                        error=str(e)
                    )
                
                if query_id:
                    self.monitor.record_error(
                        query_id,
                        type(e).__name__,
                        str(e),
                        field_name
                    )
                
                raise
            
            finally:
                # End field metric
                if field_metric and field_metric.end_time is None:
                    self.monitor.end_field_resolution(field_metric)


# Global monitor instance
_monitor: Optional[PerformanceMonitor] = None


def get_monitor() -> PerformanceMonitor:
    """Get global performance monitor"""
    global _monitor
    if _monitor is None:
        _monitor = PerformanceMonitor()
    return _monitor


def create_monitoring_context(
    operation_type: str,
    operation_name: Optional[str],
    query: str
) -> Dict[str, Any]:
    """Create monitoring context for a query"""
    monitor = get_monitor()
    query_id = f"{operation_type}:{operation_name or 'anonymous'}:{time.time()}"
    
    # Start query tracking
    metrics = monitor.start_query(
        query_id,
        operation_type,
        operation_name,
        query
    )
    
    return {
        "query_id": query_id,
        "query_metrics": metrics,
        "monitor": monitor
    }