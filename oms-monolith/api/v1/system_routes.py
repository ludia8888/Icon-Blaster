"""System routes for root and metrics"""

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import generate_latest
from middleware.etag_analytics import get_etag_analytics

router = APIRouter(tags=["System"])

@router.get("/")
async def root():
    """API 정보"""
    return {
        "name": "OMS Enterprise API (Fixed)",
        "version": "2.0.1",
        "status": "DB Connection Fixed - Real Data",
        "docs": "/docs",
        "health": "/health"
    }

@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    # Get ETag analytics
    analytics = get_etag_analytics()
    summary = analytics.get_performance_summary()
    
    # Add custom metrics info
    metrics_content = generate_latest().decode('utf-8')
    
    # Add ETag analytics summary as comments
    etag_summary = f"""
# ETag Analytics Summary
# Total Requests: {summary['total_requests']}
# Cache Hit Rate: {summary['cache_hit_rate']:.2%}
# Avg Response Time: {summary['avg_response_time_ms']:.2f}ms
# P95 Response Time: {summary['p95_response_time_ms']:.2f}ms
# P99 Response Time: {summary['p99_response_time_ms']:.2f}ms
"""
    
    return Response(
        content=etag_summary + metrics_content,
        media_type="text/plain; version=0.0.4; charset=utf-8"
    )