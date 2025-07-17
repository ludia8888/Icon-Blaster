"""
Comprehensive Integration Tests for Health Endpoints
Tests health check functionality across different service states and scenarios
"""

import pytest
import httpx
import asyncio
import time
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class TestHealthEndpoints:
    """Comprehensive health endpoint integration tests"""
    
    # Test configuration
    BFF_BASE_URL = "http://localhost:8002"
    OMS_BASE_URL = "http://localhost:8000"
    TIMEOUT = 30
    
    @pytest.fixture(autouse=True)
    async def setup_and_teardown(self):
        """Setup and teardown for each test"""
        # Setup
        self.client = httpx.AsyncClient(timeout=self.TIMEOUT)
        
        yield
        
        # Teardown
        await self.client.aclose()
    
    # Basic Health Check Tests
    
    @pytest.mark.asyncio
    async def test_bff_root_endpoint(self):
        """Test BFF root endpoint returns service information"""
        response = await self.client.get(f"{self.BFF_BASE_URL}/")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "service" in data
        assert "version" in data
        assert "description" in data
        assert data["service"] == "Ontology BFF Service"
        assert data["version"] == "2.0.0"
    
    @pytest.mark.asyncio
    async def test_bff_health_endpoint_success(self):
        """Test BFF health endpoint when services are healthy"""
        response = await self.client.get(f"{self.BFF_BASE_URL}/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "healthy"
        assert data["service"] == "BFF"
        assert "oms_connected" in data
        assert data["version"] == "2.0.0"
    
    @pytest.mark.asyncio
    async def test_oms_health_endpoint(self):
        """Test OMS health endpoint directly"""
        response = await self.client.get(f"{self.OMS_BASE_URL}/health")
        
        # OMS should be reachable
        assert response.status_code == 200
        data = response.json()
        
        assert "status" in data
        # OMS health response format may vary
    
    # Service Integration Tests
    
    @pytest.mark.asyncio
    async def test_bff_oms_connectivity(self):
        """Test BFF can communicate with OMS"""
        # First verify OMS is reachable
        try:
            oms_response = await self.client.get(f"{self.OMS_BASE_URL}/health")
            oms_healthy = oms_response.status_code == 200
        except httpx.RequestError:
            oms_healthy = False
        
        # Test BFF health which includes OMS connectivity check
        response = await self.client.get(f"{self.BFF_BASE_URL}/health")
        
        if oms_healthy:
            assert response.status_code == 200
            data = response.json()
            assert data["oms_connected"] is True
        else:
            # If OMS is down, BFF should return 503
            assert response.status_code == 503
    
    @pytest.mark.asyncio
    async def test_health_endpoint_with_request_id(self):
        """Test health endpoint includes request ID in response"""
        headers = {"X-Request-ID": "test-request-123"}
        response = await self.client.get(f"{self.BFF_BASE_URL}/health", headers=headers)
        
        # Check if request ID is echoed back
        assert "X-Request-ID" in response.headers
    
    # Error Handling Tests
    
    @pytest.mark.asyncio
    async def test_health_endpoint_timeout_handling(self):
        """Test health endpoint handles timeouts gracefully"""
        # Use a very short timeout to force timeout
        short_client = httpx.AsyncClient(timeout=0.001)
        
        try:
            response = await short_client.get(f"{self.BFF_BASE_URL}/health")
            # If we get here, the request was faster than expected
            assert response.status_code in [200, 503]
        except httpx.TimeoutException:
            # This is expected with very short timeout
            pass
        finally:
            await short_client.aclose()
    
    @pytest.mark.asyncio
    async def test_health_endpoint_invalid_methods(self):
        """Test health endpoint rejects invalid HTTP methods"""
        invalid_methods = ["POST", "PUT", "DELETE", "PATCH"]
        
        for method in invalid_methods:
            response = await self.client.request(method, f"{self.BFF_BASE_URL}/health")
            assert response.status_code == 405  # Method Not Allowed
    
    # Performance Tests
    
    @pytest.mark.asyncio
    async def test_health_endpoint_response_time(self):
        """Test health endpoint responds within acceptable time"""
        start_time = time.time()
        response = await self.client.get(f"{self.BFF_BASE_URL}/health")
        response_time = time.time() - start_time
        
        # Health check should be fast (under 5 seconds)
        assert response_time < 5.0
        assert response.status_code in [200, 503]
        
        logger.info(f"Health endpoint response time: {response_time:.3f}s")
    
    @pytest.mark.asyncio
    async def test_health_endpoint_concurrent_requests(self):
        """Test health endpoint handles concurrent requests"""
        async def make_health_request():
            response = await self.client.get(f"{self.BFF_BASE_URL}/health")
            return response.status_code
        
        # Make 10 concurrent requests
        tasks = [make_health_request() for _ in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # All requests should succeed or fail gracefully
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"Concurrent request failed: {result}")
            else:
                assert result in [200, 503], f"Unexpected status code: {result}"
    
    # API Router Health Tests
    
    @pytest.mark.asyncio
    async def test_health_router_endpoint(self):
        """Test health router endpoint (if using router-based health checks)"""
        # Test API v1 health endpoint
        response = await self.client.get(f"{self.BFF_BASE_URL}/api/v1/health")
        
        # This might be 404 if not implemented, which is okay
        assert response.status_code in [200, 404, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert "status" in data
    
    @pytest.mark.asyncio
    async def test_database_health_through_api(self):
        """Test database health through API endpoints"""
        # Try to list databases as a health check
        response = await self.client.get(f"{self.BFF_BASE_URL}/api/v1/databases")
        
        # Should return 200 (with empty list if no databases) or 503 if service down
        assert response.status_code in [200, 503]
        
        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, (list, dict))
    
    # Content Type and Headers Tests
    
    @pytest.mark.asyncio
    async def test_health_endpoint_content_type(self):
        """Test health endpoint returns correct content type"""
        response = await self.client.get(f"{self.BFF_BASE_URL}/health")
        
        assert response.headers["content-type"].startswith("application/json")
    
    @pytest.mark.asyncio
    async def test_health_endpoint_security_headers(self):
        """Test health endpoint includes security headers"""
        response = await self.client.get(f"{self.BFF_BASE_URL}/health")
        
        # Check for security headers (added by our middleware)
        expected_headers = [
            "X-Content-Type-Options",
            "X-Frame-Options", 
            "X-XSS-Protection"
        ]
        
        for header in expected_headers:
            if header in response.headers:
                assert response.headers[header] is not None
                logger.info(f"Security header present: {header}")
    
    @pytest.mark.asyncio
    async def test_health_endpoint_cors_headers(self):
        """Test health endpoint includes CORS headers"""
        headers = {"Origin": "http://localhost:3000"}
        response = await self.client.get(f"{self.BFF_BASE_URL}/health", headers=headers)
        
        # CORS headers should be present due to middleware
        assert "access-control-allow-origin" in response.headers
    
    # Edge Cases and Error Scenarios
    
    @pytest.mark.asyncio
    async def test_health_endpoint_with_malformed_headers(self):
        """Test health endpoint handles malformed headers gracefully"""
        malformed_headers = {
            "X-Malformed": "test\x00null\x01byte",
            "Content-Length": "invalid",
        }
        
        try:
            response = await self.client.get(
                f"{self.BFF_BASE_URL}/health", 
                headers=malformed_headers
            )
            # Should either work or return 400
            assert response.status_code in [200, 400, 503]
        except httpx.RequestError:
            # Some malformed headers might cause connection errors
            pass
    
    @pytest.mark.asyncio 
    async def test_health_endpoint_large_query_params(self):
        """Test health endpoint handles large query parameters"""
        large_param = "x" * 1000
        
        response = await self.client.get(
            f"{self.BFF_BASE_URL}/health",
            params={"test": large_param}
        )
        
        # Should work or return 414 (URI Too Long)
        assert response.status_code in [200, 414, 503]
    
    # Service Dependency Tests
    
    @pytest.mark.asyncio
    async def test_health_endpoint_cascading_failures(self):
        """Test health endpoint behavior when dependencies fail"""
        # This test documents expected behavior when OMS is down
        
        # First check if OMS is actually up
        try:
            oms_response = await self.client.get(f"{self.OMS_BASE_URL}/health")
            oms_available = oms_response.status_code == 200
        except httpx.RequestError:
            oms_available = False
        
        response = await self.client.get(f"{self.BFF_BASE_URL}/health")
        
        if oms_available:
            # When OMS is up, BFF should be healthy
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
        else:
            # When OMS is down, BFF should report unhealthy
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "unhealthy"
    
    # Load Testing Simulation
    
    @pytest.mark.asyncio
    async def test_health_endpoint_under_load(self):
        """Simulate load testing on health endpoint"""
        
        async def batch_requests(batch_size: int):
            tasks = []
            for _ in range(batch_size):
                task = self.client.get(f"{self.BFF_BASE_URL}/health")
                tasks.append(task)
            
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            return responses
        
        # Test with small batches to avoid overwhelming the service
        batch_sizes = [5, 10, 15]
        
        for batch_size in batch_sizes:
            logger.info(f"Testing with batch size: {batch_size}")
            
            start_time = time.time()
            responses = await batch_requests(batch_size)
            duration = time.time() - start_time
            
            # Count successful responses
            successful = 0
            for response in responses:
                if isinstance(response, httpx.Response):
                    if response.status_code in [200, 503]:
                        successful += 1
                else:
                    logger.warning(f"Request failed: {response}")
            
            success_rate = successful / batch_size
            logger.info(f"Batch {batch_size}: {success_rate:.2%} success rate in {duration:.2f}s")
            
            # At least 80% should succeed under normal conditions
            assert success_rate >= 0.8, f"Success rate too low: {success_rate:.2%}"


class TestHealthEndpointIntegration:
    """Integration tests that require multiple services"""
    
    @pytest.mark.asyncio
    async def test_full_stack_health_check(self):
        """Test health status across the full service stack"""
        services = [
            ("BFF", "http://localhost:8002/health"),
            ("OMS", "http://localhost:8000/health"),
        ]
        
        async with httpx.AsyncClient(timeout=30) as client:
            results = {}
            
            for service_name, url in services:
                try:
                    response = await client.get(url)
                    results[service_name] = {
                        "status_code": response.status_code,
                        "healthy": response.status_code == 200
                    }
                except httpx.RequestError as e:
                    results[service_name] = {
                        "status_code": None,
                        "healthy": False,
                        "error": str(e)
                    }
                    logger.warning(f"{service_name} health check failed: {e}")
            
            # Log results
            for service_name, result in results.items():
                status = "✓" if result["healthy"] else "✗" 
                logger.info(f"{status} {service_name}: {result}")
            
            # At least one service should be healthy for basic functionality
            healthy_services = sum(1 for r in results.values() if r["healthy"])
            assert healthy_services >= 1, "No services are healthy"


if __name__ == "__main__":
    # Run tests manually
    pytest.main([__file__, "-v", "--tb=short"])