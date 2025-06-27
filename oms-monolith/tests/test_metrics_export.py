#!/usr/bin/env python3
"""
Simple test to verify metrics are exported
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from middleware.etag_analytics import get_etag_analytics
from prometheus_client import REGISTRY, generate_latest

# Import the middleware to register metrics
from middleware.etag_middleware import (
    etag_requests_total,
    etag_cache_hits,
    etag_cache_misses,
    etag_validation_duration,
    etag_generation_duration
)

# Simulate some ETag operations
analytics = get_etag_analytics()

# Record some fake requests
print("Recording test ETag requests...")

# Simulate cache miss
etag_cache_misses.labels(resource_type="object_types").inc()
etag_requests_total.labels(method="GET", resource_type="object_types", result="cache_miss").inc()
etag_generation_duration.labels(resource_type="object_types").observe(0.0452)

analytics.record_request(
    resource_type="object_types",
    is_cache_hit=False,
    response_time_ms=45.2,
    etag='W/"test-123"'
)

# Simulate cache hit
etag_cache_hits.labels(resource_type="object_types").inc()
etag_requests_total.labels(method="GET", resource_type="object_types", result="cache_hit").inc()
etag_validation_duration.labels(resource_type="object_types").observe(0.0021)

analytics.record_request(
    resource_type="object_types", 
    is_cache_hit=True,
    response_time_ms=2.1,
    etag='W/"test-123"'
)

# Another cache miss
etag_cache_misses.labels(resource_type="object_types").inc()
etag_requests_total.labels(method="GET", resource_type="object_types", result="cache_miss").inc()
etag_generation_duration.labels(resource_type="object_types").observe(0.0387)

analytics.record_request(
    resource_type="object_types",
    is_cache_hit=False,
    response_time_ms=38.7,
    etag='W/"test-456"'
)

# Get metrics
metrics = analytics.export_metrics()

print("\n📊 ETag Analytics Summary:")
print(f"Total Requests: {metrics['global']['total_requests']}")
print(f"Cache Hit Rate: {metrics['global']['cache_hit_rate']:.2%}")
print(f"Avg Response Time: {metrics['global']['avg_response_time_ms']:.2f}ms")

print("\n📈 Prometheus Metrics:")
print("=" * 80)
# Get all Prometheus metrics
prometheus_output = generate_latest(REGISTRY).decode('utf-8')

# Filter for ETag metrics
for line in prometheus_output.split('\n'):
    if 'etag' in line.lower() or line.startswith('#'):
        print(line)
        
print("=" * 80)

# Verify metrics exist
etag_metrics = [
    "etag_requests_total",
    "etag_cache_hits_total", 
    "etag_cache_misses_total",
    "etag_validation_duration_seconds",
    "etag_generation_duration_seconds"
]

missing = []
for metric in etag_metrics:
    if metric not in prometheus_output:
        missing.append(metric)

if missing:
    print(f"\n❌ Missing metrics: {missing}")
else:
    print(f"\n✅ All ETag metrics are properly registered and observable!")