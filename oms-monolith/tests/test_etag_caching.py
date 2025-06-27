"""
ETag Caching Tests
Tests for ETag middleware functionality and performance
"""
import pytest
import httpx
import aiosqlite
import json
import os
from datetime import datetime, timezone
import asyncio
from unittest.mock import patch
import time

from middleware.etag_analytics import get_etag_analytics
from prometheus_client import REGISTRY


@pytest.mark.etag
@pytest.mark.integration
class TestETagCaching:
    """Comprehensive tests for ETag caching functionality"""
    
    @pytest.fixture
    async def setup_version_data(self):
        """Setup test version data in SQLite"""
        version_db_path = os.path.join(
            os.path.dirname(__file__), "..", "data", "versions.db"
        )
        os.makedirs(os.path.dirname(version_db_path), exist_ok=True)
        
        async with aiosqlite.connect(version_db_path) as db:
            # Create schema
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS resource_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    resource_type TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    branch TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    commit_hash TEXT NOT NULL,
                    parent_commit TEXT,
                    content_hash TEXT NOT NULL,
                    content_size INTEGER NOT NULL,
                    etag TEXT NOT NULL,
                    change_type TEXT NOT NULL,
                    change_summary TEXT,
                    fields_changed TEXT,
                    modified_by TEXT NOT NULL,
                    modified_at TIMESTAMP NOT NULL,
                    content TEXT,
                    UNIQUE(resource_type, resource_id, branch, version)
                );
            """)
            
            # Insert test data
            test_content = {"test": "data", "version": 1}
            content_json = json.dumps(test_content)
            content_size = len(content_json)
            
            await db.execute("""
                INSERT OR REPLACE INTO resource_versions 
                (resource_type, resource_id, branch, version, commit_hash, parent_commit,
                 content_hash, content_size, etag, change_type, change_summary, 
                 fields_changed, modified_by, modified_at, content)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "object_types", "test_object_types", "test", 1,
                "commit-test-123", None, "hash-test-123", content_size,
                'W/"hash-test-123"', "create", "Test data",
                json.dumps(["test"]), "test-user",
                datetime.now(timezone.utc).isoformat(), content_json
            ))
            
            await db.commit()
            
        yield
        
        # Cleanup
        if os.path.exists(version_db_path):
            os.remove(version_db_path)
    
    @pytest.mark.etag
    async def test_etag_header_generation(self, client, setup_version_data):
        """Test that ETag headers are generated for versioned resources"""
        response = await client.get("/api/v1/schemas/test/object-types")
        
        assert response.status_code == 200
        assert "ETag" in response.headers
        assert response.headers["ETag"].startswith('W/"')
        assert "X-Version" in response.headers
        assert "Cache-Control" in response.headers
    
    @pytest.mark.etag
    async def test_304_not_modified_response(self, client, setup_version_data):
        """Test that If-None-Match header returns 304 when content unchanged"""
        # First request to get ETag
        response1 = await client.get("/api/v1/schemas/test/object-types")
        assert response1.status_code == 200
        etag = response1.headers.get("ETag")
        assert etag
        
        # Second request with If-None-Match
        response2 = await client.get(
            "/api/v1/schemas/test/object-types",
            headers={"If-None-Match": etag}
        )
        
        assert response2.status_code == 304
        assert "ETag" in response2.headers
        assert response2.headers["ETag"] == etag
    
    @pytest.mark.etag
    async def test_etag_metrics_collection(self, client, setup_version_data):
        """Test that Prometheus metrics are collected for ETag operations"""
        # Reset metrics
        analytics = get_etag_analytics()
        initial_total = analytics.stats["total_requests"]
        
        # Make requests
        response1 = await client.get("/api/v1/schemas/test/object-types")
        etag = response1.headers.get("ETag")
        
        response2 = await client.get(
            "/api/v1/schemas/test/object-types",
            headers={"If-None-Match": etag}
        )
        
        # Check analytics
        assert analytics.stats["total_requests"] >= initial_total + 2
        assert analytics.stats["cache_hits"] > 0
        assert analytics.stats["cache_misses"] > 0
        
        # Check hit rate
        hit_rate = analytics.get_hit_rate("object_types")
        assert 0 <= hit_rate <= 1
    
    @pytest.mark.etag
    async def test_etag_performance_tracking(self, client, setup_version_data):
        """Test that response times are tracked for performance analysis"""
        analytics = get_etag_analytics()
        
        # Make multiple requests
        for _ in range(5):
            response = await client.get("/api/v1/schemas/test/object-types")
            assert response.status_code == 200
        
        # Get performance summary
        summary = analytics.get_performance_summary("object_types")
        
        assert summary["total_requests"] >= 5
        assert summary["avg_response_time_ms"] > 0
        assert "p95_response_time_ms" in summary
        assert "p99_response_time_ms" in summary
    
    @pytest.mark.etag
    @pytest.mark.slow
    async def test_etag_cache_effectiveness_over_time(self, client, setup_version_data):
        """Test cache effectiveness improves over time with repeated requests"""
        analytics = get_etag_analytics()
        
        # First batch - all cache misses
        for _ in range(10):
            response = await client.get("/api/v1/schemas/test/object-types")
            assert response.status_code == 200
            etag = response.headers.get("ETag")
        
        # Second batch - should have cache hits
        for _ in range(10):
            response = await client.get(
                "/api/v1/schemas/test/object-types",
                headers={"If-None-Match": etag}
            )
            assert response.status_code == 304
        
        # Check overall hit rate improved
        hit_rate = analytics.get_hit_rate()
        assert hit_rate >= 0.4  # At least 40% cache hits
    
    @pytest.mark.etag
    async def test_etag_with_different_resources(self, client, setup_version_data):
        """Test ETag works correctly with different resource types"""
        # Test with different endpoints
        endpoints = [
            "/api/v1/schemas/test/object-types",
            "/api/v1/branches",
            "/api/v1/proposals"
        ]
        
        etags = {}
        for endpoint in endpoints:
            response = await client.get(endpoint)
            if response.status_code == 200:
                etag = response.headers.get("ETag")
                if etag:
                    etags[endpoint] = etag
        
        # Verify ETags are unique per resource
        assert len(set(etags.values())) == len(etags)
    
    @pytest.mark.etag
    async def test_analytics_hooks_execution(self, client, setup_version_data):
        """Test that analytics hooks are executed on requests"""
        hook_called = False
        
        def test_hook(resource_type, request_data):
            nonlocal hook_called
            hook_called = True
            assert resource_type == "object_types"
            assert "response_time_ms" in request_data
        
        analytics = get_etag_analytics()
        analytics.add_analytics_hook(test_hook)
        
        # Make request
        await client.get("/api/v1/schemas/test/object-types")
        
        assert hook_called
    
    @pytest.mark.etag
    async def test_prometheus_metrics_export(self, client, setup_version_data):
        """Test that metrics can be exported in Prometheus format"""
        # Make some requests
        for _ in range(3):
            await client.get("/api/v1/schemas/test/object-types")
        
        # Get metrics
        analytics = get_etag_analytics()
        metrics = analytics.export_metrics()
        
        assert "prometheus_metrics" in metrics
        assert "etag_requests_total" in metrics["prometheus_metrics"]
        assert "etag_cache_hits_total" in metrics["prometheus_metrics"]
        assert "etag_validation_duration_seconds" in metrics["prometheus_metrics"]


@pytest.mark.etag
@pytest.mark.unit
class TestETagAnalytics:
    """Unit tests for ETag analytics functionality"""
    
    def test_analytics_initialization(self):
        """Test analytics object initializes correctly"""
        analytics = get_etag_analytics()
        assert analytics is not None
        assert analytics.stats["total_requests"] >= 0
    
    def test_request_recording(self):
        """Test recording individual requests"""
        analytics = get_etag_analytics()
        initial_count = analytics.stats["total_requests"]
        
        analytics.record_request(
            resource_type="test_type",
            is_cache_hit=True,
            response_time_ms=50.0,
            etag='W/"test"'
        )
        
        assert analytics.stats["total_requests"] == initial_count + 1
        assert analytics.stats["cache_hits"] > 0
    
    def test_hit_rate_calculation(self):
        """Test cache hit rate calculation"""
        from middleware.etag_analytics import ETagAnalytics
        
        analytics = ETagAnalytics()
        
        # Record some hits and misses
        for i in range(10):
            analytics.record_request(
                resource_type="test",
                is_cache_hit=(i % 2 == 0),  # 50% hit rate
                response_time_ms=10.0
            )
        
        hit_rate = analytics.get_hit_rate("test")
        assert 0.45 <= hit_rate <= 0.55  # Should be around 50%
    
    def test_performance_summary_empty(self):
        """Test performance summary with no data"""
        from middleware.etag_analytics import ETagAnalytics
        
        analytics = ETagAnalytics()
        summary = analytics.get_performance_summary("nonexistent")
        
        assert summary["total_requests"] == 0
        assert summary["cache_hit_rate"] == 0.0
    
    def test_metrics_export_format(self):
        """Test that exported metrics have correct format"""
        analytics = get_etag_analytics()
        metrics = analytics.export_metrics()
        
        assert isinstance(metrics, dict)
        assert "timestamp" in metrics
        assert "global" in metrics
        assert "by_resource_type" in metrics
        assert isinstance(metrics["by_resource_type"], dict)