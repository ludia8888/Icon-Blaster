"""
ETag Monitoring and Alerting
Comprehensive monitoring for ETag operations with Prometheus metrics and alerting
"""
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import defaultdict
import time
import asyncio

from prometheus_client import (
    Counter, Histogram, Gauge, Summary, Info,
    generate_latest, CONTENT_TYPE_LATEST
)
import structlog

logger = structlog.get_logger(__name__)


# Prometheus Metrics
etag_requests = Counter(
    'etag_requests_total',
    'Total number of ETag requests',
    ['method', 'resource_type', 'result', 'endpoint']
)

etag_cache_effectiveness = Gauge(
    'etag_cache_effectiveness_ratio',
    'Cache hit ratio over the last time window',
    ['resource_type', 'window']
)

etag_validation_latency = Histogram(
    'etag_validation_duration_seconds',
    'Time spent validating ETags',
    ['resource_type', 'cache_hit'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

etag_generation_latency = Histogram(
    'etag_generation_duration_seconds',
    'Time spent generating ETags',
    ['resource_type', 'method'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

etag_delta_size = Histogram(
    'etag_delta_response_bytes',
    'Size of delta responses in bytes',
    ['resource_type'],
    buckets=[100, 500, 1000, 5000, 10000, 50000, 100000, 500000]
)

etag_circuit_breaker_trips = Counter(
    'etag_circuit_breaker_trips_total',
    'Number of circuit breaker trips',
    ['service', 'reason']
)

etag_cache_operations = Counter(
    'etag_cache_operations_total',
    'Cache operations (get, set, evict)',
    ['operation', 'cache_type', 'status']
)

etag_concurrent_requests = Gauge(
    'etag_concurrent_requests',
    'Number of concurrent ETag requests being processed',
    ['resource_type']
)

etag_error_rate = Counter(
    'etag_errors_total',
    'Total number of ETag-related errors',
    ['error_type', 'resource_type', 'severity']
)

etag_slo_violations = Counter(
    'etag_slo_violations_total',
    'Number of SLO violations',
    ['slo_type', 'resource_type']
)

# Summary metrics for percentiles
etag_request_duration_summary = Summary(
    'etag_request_duration_seconds_summary',
    'Summary of ETag request durations',
    ['resource_type']
)

# Info metric for service metadata
etag_service_info = Info(
    'etag_service',
    'ETag service information'
)

# Set service info
etag_service_info.info({
    'version': '2.0.0',
    'implementation': 'resilient-enterprise',
    'cache_backend': 'redis',
    'delta_support': 'true'
})


@dataclass
class SLOConfig:
    """Service Level Objective configuration"""
    name: str
    target_value: float
    window_seconds: int = 300  # 5 minutes default
    error_budget_percent: float = 0.1  # 0.1% error budget


@dataclass
class AlertRule:
    """Alert rule configuration"""
    name: str
    condition: str
    threshold: float
    duration_seconds: int
    severity: str = "warning"
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)


class ETagMonitor:
    """
    Enterprise-grade monitoring for ETag operations
    """
    
    def __init__(self):
        self.start_time = time.time()
        self._concurrent_requests: Dict[str, int] = defaultdict(int)
        self._request_history: List[Dict[str, Any]] = []
        self._max_history_size = 10000
        
        # SLO definitions
        self.slos = [
            SLOConfig("cache_hit_rate", target_value=0.80),  # 80% cache hit rate
            SLOConfig("p95_latency", target_value=0.1),      # 100ms p95 latency
            SLOConfig("availability", target_value=0.999),    # 99.9% availability
            SLOConfig("error_rate", target_value=0.001)       # 0.1% error rate
        ]
        
        # Alert rules
        self.alert_rules = [
            AlertRule(
                name="high_error_rate",
                condition="rate(etag_errors_total[5m]) > 0.01",
                threshold=0.01,
                duration_seconds=300,
                severity="critical",
                annotations={"summary": "High ETag error rate detected"}
            ),
            AlertRule(
                name="low_cache_hit_rate",
                condition="etag_cache_effectiveness_ratio < 0.5",
                threshold=0.5,
                duration_seconds=600,
                severity="warning",
                annotations={"summary": "ETag cache hit rate below 50%"}
            ),
            AlertRule(
                name="high_latency",
                condition="histogram_quantile(0.95, etag_validation_duration_seconds) > 0.5",
                threshold=0.5,
                duration_seconds=300,
                severity="warning",
                annotations={"summary": "High ETag validation latency"}
            ),
            AlertRule(
                name="circuit_breaker_open",
                condition="etag_circuit_breaker_trips_total > 0",
                threshold=0,
                duration_seconds=60,
                severity="critical",
                annotations={"summary": "ETag circuit breaker is open"}
            )
        ]
        
        # Start background tasks
        asyncio.create_task(self._update_metrics_loop())
        
        logger.info("ETag monitoring initialized", slos=len(self.slos), alerts=len(self.alert_rules))
    
    def record_request(
        self,
        method: str,
        resource_type: str,
        result: str,
        endpoint: str,
        duration_seconds: float,
        cache_hit: bool = False,
        error: Optional[str] = None
    ):
        """Record an ETag request"""
        # Update counters
        etag_requests.labels(
            method=method,
            resource_type=resource_type,
            result=result,
            endpoint=endpoint
        ).inc()
        
        # Update duration metrics
        etag_request_duration_summary.labels(resource_type=resource_type).observe(duration_seconds)
        
        if result == "cache_hit":
            etag_validation_latency.labels(
                resource_type=resource_type,
                cache_hit="true"
            ).observe(duration_seconds)
        elif result == "cache_miss":
            etag_validation_latency.labels(
                resource_type=resource_type,
                cache_hit="false"
            ).observe(duration_seconds)
        
        # Track errors
        if error:
            etag_error_rate.labels(
                error_type=error,
                resource_type=resource_type,
                severity="error" if "timeout" in error.lower() else "warning"
            ).inc()
        
        # Store in history
        self._add_to_history({
            "timestamp": datetime.utcnow(),
            "method": method,
            "resource_type": resource_type,
            "result": result,
            "endpoint": endpoint,
            "duration_seconds": duration_seconds,
            "cache_hit": cache_hit,
            "error": error
        })
        
        # Check SLOs
        self._check_slos(resource_type, result, duration_seconds, error)
    
    def track_concurrent_request(self, resource_type: str, increment: int = 1):
        """Track concurrent requests"""
        self._concurrent_requests[resource_type] += increment
        etag_concurrent_requests.labels(resource_type=resource_type).set(
            self._concurrent_requests[resource_type]
        )
    
    def record_cache_operation(
        self,
        operation: str,
        cache_type: str,
        status: str,
        duration_seconds: Optional[float] = None
    ):
        """Record cache operation metrics"""
        etag_cache_operations.labels(
            operation=operation,
            cache_type=cache_type,
            status=status
        ).inc()
    
    def record_delta_response(self, resource_type: str, size_bytes: int):
        """Record delta response size"""
        etag_delta_size.labels(resource_type=resource_type).observe(size_bytes)
    
    def record_circuit_breaker_trip(self, service: str, reason: str):
        """Record circuit breaker trip"""
        etag_circuit_breaker_trips.labels(service=service, reason=reason).inc()
    
    def _add_to_history(self, entry: Dict[str, Any]):
        """Add entry to request history with size limit"""
        self._request_history.append(entry)
        if len(self._request_history) > self._max_history_size:
            self._request_history = self._request_history[-self._max_history_size:]
    
    def _check_slos(
        self,
        resource_type: str,
        result: str,
        duration_seconds: float,
        error: Optional[str]
    ):
        """Check SLO compliance"""
        # Check latency SLO
        if duration_seconds > 0.1:  # 100ms
            etag_slo_violations.labels(
                slo_type="p95_latency",
                resource_type=resource_type
            ).inc()
        
        # Check error rate SLO
        if error:
            etag_slo_violations.labels(
                slo_type="error_rate",
                resource_type=resource_type
            ).inc()
    
    async def _update_metrics_loop(self):
        """Background task to update derived metrics"""
        while True:
            try:
                await asyncio.sleep(60)  # Update every minute
                await self._update_cache_effectiveness()
            except Exception as e:
                logger.error("Error updating metrics", error=str(e))
    
    async def _update_cache_effectiveness(self):
        """Calculate and update cache effectiveness metrics"""
        # Calculate cache effectiveness for different time windows
        windows = [
            ("1m", 60),
            ("5m", 300),
            ("15m", 900),
            ("1h", 3600)
        ]
        
        now = datetime.utcnow()
        
        for window_name, window_seconds in windows:
            cutoff_time = now - timedelta(seconds=window_seconds)
            
            # Group by resource type
            resource_stats: Dict[str, Dict[str, int]] = defaultdict(lambda: {"hits": 0, "total": 0})
            
            for entry in self._request_history:
                if entry["timestamp"] < cutoff_time:
                    continue
                
                resource_type = entry["resource_type"]
                resource_stats[resource_type]["total"] += 1
                
                if entry["result"] == "cache_hit":
                    resource_stats[resource_type]["hits"] += 1
            
            # Update metrics
            for resource_type, stats in resource_stats.items():
                if stats["total"] > 0:
                    effectiveness = stats["hits"] / stats["total"]
                    etag_cache_effectiveness.labels(
                        resource_type=resource_type,
                        window=window_name
                    ).set(effectiveness)
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """Get current metrics summary"""
        now = datetime.utcnow()
        uptime_seconds = time.time() - self.start_time
        
        # Calculate recent stats (last 5 minutes)
        recent_cutoff = now - timedelta(minutes=5)
        recent_requests = [
            r for r in self._request_history 
            if r["timestamp"] > recent_cutoff
        ]
        
        total_recent = len(recent_requests)
        cache_hits = sum(1 for r in recent_requests if r["result"] == "cache_hit")
        errors = sum(1 for r in recent_requests if r.get("error"))
        
        # Calculate latency percentiles
        latencies = [r["duration_seconds"] for r in recent_requests]
        latencies.sort()
        
        def percentile(data: List[float], p: float) -> float:
            if not data:
                return 0
            k = (len(data) - 1) * p
            f = int(k)
            c = k - f
            if f + 1 < len(data):
                return data[f] * (1 - c) + data[f + 1] * c
            return data[f]
        
        return {
            "uptime_seconds": uptime_seconds,
            "total_requests": len(self._request_history),
            "recent_stats": {
                "window": "5m",
                "total_requests": total_recent,
                "cache_hits": cache_hits,
                "cache_hit_rate": cache_hits / total_recent if total_recent > 0 else 0,
                "errors": errors,
                "error_rate": errors / total_recent if total_recent > 0 else 0,
                "latency_p50": percentile(latencies, 0.5),
                "latency_p95": percentile(latencies, 0.95),
                "latency_p99": percentile(latencies, 0.99)
            },
            "concurrent_requests": dict(self._concurrent_requests),
            "slo_compliance": self._calculate_slo_compliance()
        }
    
    def _calculate_slo_compliance(self) -> Dict[str, Dict[str, Any]]:
        """Calculate current SLO compliance"""
        compliance = {}
        
        # This is a simplified example - in production, you'd query
        # actual Prometheus metrics for accurate SLO calculation
        for slo in self.slos:
            compliance[slo.name] = {
                "target": slo.target_value,
                "current": 0.0,  # Would be calculated from metrics
                "compliant": True,
                "error_budget_remaining": slo.error_budget_percent
            }
        
        return compliance
    
    def export_prometheus_alerts(self) -> str:
        """Export Prometheus alert rules in YAML format"""
        rules = []
        
        for rule in self.alert_rules:
            prometheus_rule = {
                "alert": rule.name,
                "expr": rule.condition,
                "for": f"{rule.duration_seconds}s",
                "labels": {
                    "severity": rule.severity,
                    **rule.labels
                },
                "annotations": rule.annotations
            }
            rules.append(prometheus_rule)
        
        import yaml
        return yaml.dump({
            "groups": [{
                "name": "etag_alerts",
                "interval": "30s",
                "rules": rules
            }]
        })


# Global monitor instance
_etag_monitor: Optional[ETagMonitor] = None


def get_etag_monitor() -> ETagMonitor:
    """Get global ETag monitor instance"""
    global _etag_monitor
    if _etag_monitor is None:
        _etag_monitor = ETagMonitor()
    return _etag_monitor


# Prometheus metrics endpoint
async def metrics_endpoint():
    """FastAPI endpoint for Prometheus metrics"""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


# Grafana dashboard configuration
def get_grafana_dashboard() -> Dict[str, Any]:
    """Get Grafana dashboard configuration for ETag monitoring"""
    return {
        "dashboard": {
            "title": "ETag Performance Dashboard",
            "tags": ["etag", "cache", "performance"],
            "timezone": "UTC",
            "panels": [
                {
                    "title": "Cache Hit Rate",
                    "targets": [{
                        "expr": "etag_cache_effectiveness_ratio{window='5m'}"
                    }]
                },
                {
                    "title": "Request Latency (p95)",
                    "targets": [{
                        "expr": "histogram_quantile(0.95, rate(etag_validation_duration_seconds_bucket[5m]))"
                    }]
                },
                {
                    "title": "Error Rate",
                    "targets": [{
                        "expr": "rate(etag_errors_total[5m])"
                    }]
                },
                {
                    "title": "Circuit Breaker Status",
                    "targets": [{
                        "expr": "version_service_circuit_breaker_state"
                    }]
                }
            ]
        }
    }