"""
Common metrics collection utilities for middleware components
"""
import time
import asyncio
from typing import Dict, Any, Optional, List
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, deque
import logging

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Types of metrics"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


@dataclass
class MetricPoint:
    """Single metric data point"""
    timestamp: datetime
    value: float
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class MetricSummary:
    """Summary statistics for a metric"""
    count: int
    sum: float
    min: float
    max: float
    avg: float
    p50: float
    p95: float
    p99: float


class MetricsCollector:
    """Centralized metrics collection for middleware components"""
    
    def __init__(self, namespace: str = "middleware"):
        self.namespace = namespace
        self._metrics: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = defaultdict(float)
        self._histograms: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self._timers: Dict[str, float] = {}
        
    def increment_counter(
        self, 
        name: str, 
        value: float = 1, 
        labels: Optional[Dict[str, str]] = None
    ):
        """Increment a counter metric"""
        key = self._get_metric_key(name, labels)
        self._counters[key] += value
        self._record_metric(name, MetricType.COUNTER, value, labels)
    
    def set_gauge(
        self, 
        name: str, 
        value: float, 
        labels: Optional[Dict[str, str]] = None
    ):
        """Set a gauge metric"""
        key = self._get_metric_key(name, labels)
        self._gauges[key] = value
        self._record_metric(name, MetricType.GAUGE, value, labels)
    
    def observe_histogram(
        self, 
        name: str, 
        value: float, 
        labels: Optional[Dict[str, str]] = None
    ):
        """Record a histogram observation"""
        key = self._get_metric_key(name, labels)
        self._histograms[key].append(value)
        self._record_metric(name, MetricType.HISTOGRAM, value, labels)
    
    def start_timer(self, name: str) -> str:
        """Start a timer for measuring duration"""
        timer_id = f"{name}:{time.time_ns()}"
        self._timers[timer_id] = time.perf_counter()
        return timer_id
    
    def stop_timer(
        self, 
        timer_id: str, 
        labels: Optional[Dict[str, str]] = None
    ):
        """Stop a timer and record the duration"""
        if timer_id not in self._timers:
            logger.warning(f"Timer {timer_id} not found")
            return
        
        duration = time.perf_counter() - self._timers[timer_id]
        name = timer_id.split(':')[0]
        self.observe_histogram(f"{name}_duration_seconds", duration, labels)
        del self._timers[timer_id]
    
    async def measure_async(self, name: str, labels: Optional[Dict[str, str]] = None):
        """Async context manager for measuring execution time"""
        class AsyncTimer:
            def __init__(self, collector, metric_name, metric_labels):
                self.collector = collector
                self.name = metric_name
                self.labels = metric_labels
                self.start_time = None
            
            async def __aenter__(self):
                self.start_time = time.perf_counter()
                return self
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                duration = time.perf_counter() - self.start_time
                self.collector.observe_histogram(
                    f"{self.name}_duration_seconds", 
                    duration, 
                    self.labels
                )
        
        return AsyncTimer(self, name, labels)
    
    def measure_sync(self, name: str, labels: Optional[Dict[str, str]] = None):
        """Sync context manager for measuring execution time"""
        class SyncTimer:
            def __init__(self, collector, metric_name, metric_labels):
                self.collector = collector
                self.name = metric_name
                self.labels = metric_labels
                self.start_time = None
            
            def __enter__(self):
                self.start_time = time.perf_counter()
                return self
            
            def __exit__(self, exc_type, exc_val, exc_tb):
                duration = time.perf_counter() - self.start_time
                self.collector.observe_histogram(
                    f"{self.name}_duration_seconds", 
                    duration, 
                    self.labels
                )
        
        return SyncTimer(self, name, labels)
    
    def get_counter(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """Get current counter value"""
        key = self._get_metric_key(name, labels)
        return self._counters.get(key, 0)
    
    def get_gauge(self, name: str, labels: Optional[Dict[str, str]] = None) -> float:
        """Get current gauge value"""
        key = self._get_metric_key(name, labels)
        return self._gauges.get(key, 0)
    
    def get_histogram_summary(
        self, 
        name: str, 
        labels: Optional[Dict[str, str]] = None
    ) -> Optional[MetricSummary]:
        """Get histogram summary statistics"""
        key = self._get_metric_key(name, labels)
        values = list(self._histograms.get(key, []))
        
        if not values:
            return None
        
        values.sort()
        count = len(values)
        total = sum(values)
        
        return MetricSummary(
            count=count,
            sum=total,
            min=values[0],
            max=values[-1],
            avg=total / count,
            p50=self._percentile(values, 50),
            p95=self._percentile(values, 95),
            p99=self._percentile(values, 99)
        )
    
    def get_all_metrics(self) -> Dict[str, Any]:
        """Get all collected metrics"""
        metrics = {
            "namespace": self.namespace,
            "timestamp": datetime.utcnow().isoformat(),
            "counters": {},
            "gauges": {},
            "histograms": {}
        }
        
        # Counters
        for key, value in self._counters.items():
            name, labels = self._parse_metric_key(key)
            if name not in metrics["counters"]:
                metrics["counters"][name] = []
            metrics["counters"][name].append({
                "value": value,
                "labels": labels
            })
        
        # Gauges
        for key, value in self._gauges.items():
            name, labels = self._parse_metric_key(key)
            if name not in metrics["gauges"]:
                metrics["gauges"][name] = []
            metrics["gauges"][name].append({
                "value": value,
                "labels": labels
            })
        
        # Histograms
        for key, values in self._histograms.items():
            name, labels = self._parse_metric_key(key)
            if name not in metrics["histograms"]:
                metrics["histograms"][name] = []
            
            summary = self.get_histogram_summary(name, labels)
            if summary:
                metrics["histograms"][name].append({
                    "summary": {
                        "count": summary.count,
                        "sum": summary.sum,
                        "min": summary.min,
                        "max": summary.max,
                        "avg": summary.avg,
                        "p50": summary.p50,
                        "p95": summary.p95,
                        "p99": summary.p99
                    },
                    "labels": labels
                })
        
        return metrics
    
    def reset(self):
        """Reset all metrics"""
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._timers.clear()
        self._metrics.clear()
    
    def _get_metric_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        """Generate unique key for metric with labels"""
        if not labels:
            return name
        
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}:{label_str}"
    
    def _parse_metric_key(self, key: str) -> tuple[str, Dict[str, str]]:
        """Parse metric key back into name and labels"""
        if ':' not in key:
            return key, {}
        
        parts = key.split(':', 1)
        name = parts[0]
        labels = {}
        
        if len(parts) > 1:
            for pair in parts[1].split(','):
                if '=' in pair:
                    k, v = pair.split('=', 1)
                    labels[k] = v
        
        return name, labels
    
    def _record_metric(
        self, 
        name: str, 
        metric_type: MetricType, 
        value: float, 
        labels: Optional[Dict[str, str]]
    ):
        """Record metric data point"""
        key = self._get_metric_key(name, labels)
        if key not in self._metrics:
            self._metrics[key] = {
                "type": metric_type,
                "points": deque(maxlen=1000)
            }
        
        self._metrics[key]["points"].append(MetricPoint(
            timestamp=datetime.utcnow(),
            value=value,
            labels=labels or {}
        ))
    
    def _percentile(self, sorted_values: List[float], percentile: float) -> float:
        """Calculate percentile from sorted values"""
        if not sorted_values:
            return 0
        
        index = int((percentile / 100) * len(sorted_values))
        if index >= len(sorted_values):
            index = len(sorted_values) - 1
        
        return sorted_values[index]


# Global metrics collector instance
global_metrics = MetricsCollector()


def get_metrics_collector(namespace: Optional[str] = None) -> MetricsCollector:
    """Get metrics collector instance"""
    if namespace:
        return MetricsCollector(namespace)
    return global_metrics