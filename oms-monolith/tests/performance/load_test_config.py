"""
Load Test Configuration for Phase 6
Performance testing configuration for 10k branches × 100k merges scenario
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
import os


@dataclass
class LoadTestConfig:
    """Configuration for load testing scenarios"""
    
    # Test scale parameters
    num_branches: int = 10_000
    num_merges: int = 100_000
    num_objects_per_branch: int = 100
    num_properties_per_object: int = 20
    
    # Concurrency settings
    concurrent_branches: int = 100
    concurrent_merges: int = 50
    worker_threads: int = os.cpu_count() or 8
    
    # Performance thresholds (milliseconds)
    branch_creation_p95: int = 100
    merge_operation_p95: int = 200
    diff_generation_p95: int = 200
    schema_validation_p95: int = 50
    
    # Resource limits
    max_memory_gb: int = 16
    max_cpu_percent: int = 80
    
    # NATS configuration
    nats_url: str = "nats://localhost:4222"
    nats_cluster_size: int = 3
    nats_max_payload_mb: int = 10
    
    # S3/MinIO configuration
    s3_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "oms-metadata"
    s3_access_key: str = os.getenv("S3_ACCESS_KEY", "minioadmin")
    s3_secret_key: str = os.getenv("S3_SECRET_KEY", "minioadmin")
    
    # Monitoring
    prometheus_pushgateway: str = "http://localhost:9091"
    metrics_interval_seconds: int = 10
    
    @property
    def total_events(self) -> int:
        """Calculate approximate total events"""
        # Each branch: create + objects + properties
        branch_events = self.num_branches * (1 + self.num_objects_per_branch * self.num_properties_per_object)
        # Each merge: diff + validation + commit
        merge_events = self.num_merges * 3
        return branch_events + merge_events
    
    @property
    def estimated_storage_gb(self) -> float:
        """Estimate storage requirements"""
        # Rough estimation: 1KB per event
        return (self.total_events * 1024) / (1024**3)


@dataclass
class MonitoringMetrics:
    """Metrics to track during load testing"""
    
    # Event metrics
    events_published: int = 0
    events_processed: int = 0
    events_failed: int = 0
    event_lag_ms: float = 0
    
    # Branch metrics
    branches_created: int = 0
    branches_merged: int = 0
    merge_conflicts: int = 0
    merge_failures: int = 0
    
    # Performance metrics
    branch_creation_times: list[float] = None
    merge_operation_times: list[float] = None
    diff_generation_times: list[float] = None
    validation_times: list[float] = None
    
    # Resource metrics
    memory_usage_mb: float = 0
    cpu_usage_percent: float = 0
    disk_io_mb_per_sec: float = 0
    network_io_mb_per_sec: float = 0
    
    # Storage metrics
    nats_stream_size_mb: float = 0
    s3_objects_count: int = 0
    s3_total_size_mb: float = 0
    
    def __post_init__(self):
        """Initialize list fields"""
        if self.branch_creation_times is None:
            self.branch_creation_times = []
        if self.merge_operation_times is None:
            self.merge_operation_times = []
        if self.diff_generation_times is None:
            self.diff_generation_times = []
        if self.validation_times is None:
            self.validation_times = []
    
    def to_prometheus(self) -> Dict[str, Any]:
        """Convert to Prometheus metrics format"""
        return {
            # Counters
            "oms_events_total": self.events_published,
            "oms_events_processed_total": self.events_processed,
            "oms_events_failed_total": self.events_failed,
            "oms_branches_created_total": self.branches_created,
            "oms_branches_merged_total": self.branches_merged,
            "oms_merge_conflicts_total": self.merge_conflicts,
            "oms_merge_failures_total": self.merge_failures,
            
            # Gauges
            "oms_event_lag_milliseconds": self.event_lag_ms,
            "oms_memory_usage_megabytes": self.memory_usage_mb,
            "oms_cpu_usage_percent": self.cpu_usage_percent,
            "oms_disk_io_megabytes_per_second": self.disk_io_mb_per_sec,
            "oms_network_io_megabytes_per_second": self.network_io_mb_per_sec,
            "oms_nats_stream_size_megabytes": self.nats_stream_size_mb,
            "oms_s3_objects_count": self.s3_objects_count,
            "oms_s3_total_size_megabytes": self.s3_total_size_mb,
            
            # Histograms (we'll track percentiles separately)
            "oms_branch_creation_duration_milliseconds": self._calculate_percentiles(self.branch_creation_times),
            "oms_merge_operation_duration_milliseconds": self._calculate_percentiles(self.merge_operation_times),
            "oms_diff_generation_duration_milliseconds": self._calculate_percentiles(self.diff_generation_times),
            "oms_validation_duration_milliseconds": self._calculate_percentiles(self.validation_times),
        }
    
    def _calculate_percentiles(self, times: list[float]) -> Dict[str, float]:
        """Calculate percentiles for timing data"""
        if not times:
            return {"p50": 0, "p95": 0, "p99": 0}
        
        import numpy as np
        return {
            "p50": np.percentile(times, 50),
            "p95": np.percentile(times, 95),
            "p99": np.percentile(times, 99),
            "max": max(times),
            "count": len(times)
        }


# Test scenarios
SCENARIOS = {
    "baseline": LoadTestConfig(
        num_branches=100,
        num_merges=1000,
        concurrent_branches=10,
        concurrent_merges=5
    ),
    "stress": LoadTestConfig(
        num_branches=10_000,
        num_merges=100_000,
        concurrent_branches=100,
        concurrent_merges=50
    ),
    "extreme": LoadTestConfig(
        num_branches=50_000,
        num_merges=500_000,
        concurrent_branches=500,
        concurrent_merges=250
    )
}


def get_scenario(name: str = "baseline") -> LoadTestConfig:
    """Get a predefined test scenario"""
    return SCENARIOS.get(name, SCENARIOS["baseline"])