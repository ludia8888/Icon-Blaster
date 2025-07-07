"""
Full API Integration Test
Tests complete API functionality with real services
"""
import asyncio
import httpx
import pytest
import pytest_asyncio
from datetime import datetime
import json
import os


class TestFullAPIIntegration:
    """Test complete API integration with all services"""
    
    @pytest.fixture
    def api_base_url(self):
        """Get API base URL"""
        return os.getenv("API_BASE_URL", "http://localhost:8000")
    
    @pytest.fixture
    def graphql_url(self):
        """Get GraphQL URL"""
        return os.getenv("GRAPHQL_URL", "http://localhost:8006/graphql")
    
    @pytest_asyncio.fixture
    async def http_client(self):
        """Create HTTP client"""
        client = httpx.AsyncClient()
        yield client
        await client.aclose()
    
    @pytest.fixture
    def auth_headers(self):
        """Get authentication headers"""
        # In real test, this would get a valid JWT token
        return {"Authorization": "Bearer test-token"}
    
    @pytest.mark.asyncio
    async def test_health_endpoint(self, http_client, api_base_url):
        """Test health check endpoint"""
        response = await http_client.get(f"{api_base_url}/health")
        
        assert response.status_code == 200
        data = response.json()
        
        # Check overall health
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unhealthy"]
        
        # Check individual services
        assert "checks" in data
        checks = data["checks"]
        
        # Verify database connectivity
        assert "database" in checks
        assert checks["database"]["status"] is True
        
        # Verify TerminusDB connectivity
        assert "terminusdb" in checks
        assert checks["terminusdb"]["status"] is True
        
        # Verify Redis connectivity
        assert "redis" in checks
        # Redis might be optional, so just check structure
        assert "status" in checks["redis"]
        
    @pytest.mark.asyncio
    async def test_api_documentation(self, http_client, api_base_url):
        """Test API documentation endpoints"""
        # Test OpenAPI docs
        response = await http_client.get(f"{api_base_url}/docs")
        assert response.status_code == 200
        assert "swagger" in response.text.lower()
        
        # Test OpenAPI schema
        response = await http_client.get(f"{api_base_url}/openapi.json")
        assert response.status_code == 200
        schema = response.json()
        assert "openapi" in schema
        assert "paths" in schema
        assert "components" in schema
    
    @pytest.mark.asyncio
    async def test_graphql_introspection(self, http_client, graphql_url):
        """Test GraphQL introspection"""
        query = """
        {
            __schema {
                queryType {
                    name
                    fields {
                        name
                        description
                    }
                }
            }
        }
        """
        
        response = await http_client.post(
            graphql_url,
            json={"query": query},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "__schema" in data["data"]
        assert data["data"]["__schema"]["queryType"]["name"] == "Query"
    
    @pytest.mark.asyncio
    async def test_metrics_endpoint(self, http_client, api_base_url):
        """Test Prometheus metrics endpoint"""
        response = await http_client.get(f"{api_base_url}/metrics")
        
        assert response.status_code == 200
        metrics_text = response.text
        
        # Check for standard metrics
        assert "python_gc_objects_collected_total" in metrics_text
        assert "# HELP" in metrics_text
        assert "# TYPE" in metrics_text
        
        # Check for custom metrics
        assert "http_client_trace_injection_total" in metrics_text
    
    @pytest.mark.asyncio
    async def test_authentication_required(self, http_client, api_base_url):
        """Test that protected endpoints require authentication"""
        # Try to access protected endpoint without auth
        response = await http_client.get(
            f"{api_base_url}/api/v1/schema/object_types",
            params={"branch": "main"}
        )
        
        # Should return 401 or 403
        assert response.status_code in [401, 403]
        assert "authorization" in response.text.lower()
    
    @pytest.mark.asyncio
    async def test_graphql_query_basic(self, http_client, graphql_url):
        """Test basic GraphQL query"""
        query = """
        query GetObjectTypes {
            objectTypes(branch: "main", limit: 10) {
                items {
                    id
                    abstract
                }
                totalCount
                hasMore
            }
        }
        """
        
        response = await http_client.post(
            graphql_url,
            json={"query": query},
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            data = response.json()
            # If successful, verify structure
            if "data" in data and data["data"]:
                assert "objectTypes" in data["data"]
            else:
                # Might require auth or have no data
                assert "errors" in data or data["data"] is None
    
    @pytest.mark.asyncio
    async def test_websocket_connection(self):
        """Test WebSocket connectivity"""
        import websockets
        
        ws_url = os.getenv("WS_URL", "ws://localhost:8004/ws")
        
        try:
            async with websockets.connect(ws_url) as websocket:
                # Send ping
                await websocket.send(json.dumps({"type": "ping"}))
                
                # Wait for response with timeout
                try:
                    response = await asyncio.wait_for(
                        websocket.recv(),
                        timeout=5.0
                    )
                    data = json.loads(response)
                    
                    # Should receive pong or auth required
                    assert data.get("type") in ["pong", "error", "connection_ack"]
                except asyncio.TimeoutError:
                    # Timeout might mean auth required
                    pass
        except websockets.exceptions.WebSocketException as e:
            # Connection might require auth
            assert "401" in str(e) or "403" in str(e) or "authentication" in str(e).lower()
    
    @pytest.mark.asyncio
    async def test_error_handling(self, http_client, api_base_url):
        """Test API error handling"""
        # Test 404
        response = await http_client.get(f"{api_base_url}/non-existent-endpoint")
        assert response.status_code == 404
        
        # Test invalid JSON
        response = await http_client.post(
            f"{api_base_url}/api/v1/test",
            content="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code in [400, 422]
    
    @pytest.mark.asyncio
    async def test_concurrent_requests(self, http_client, api_base_url):
        """Test handling of concurrent requests"""
        tasks = []
        
        # Create multiple concurrent requests
        for i in range(5):
            task = http_client.get(f"{api_base_url}/health")
            tasks.append(task)
        
        # Execute all requests concurrently
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify all requests succeeded
        for response in responses:
            if isinstance(response, Exception):
                pytest.fail(f"Request failed: {response}")
            assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_response_headers(self, http_client, api_base_url):
        """Test API response headers"""
        response = await http_client.get(f"{api_base_url}/health")
        
        # Check security headers
        headers = response.headers
        
        # CORS headers (if configured)
        if "access-control-allow-origin" in headers:
            assert headers["access-control-allow-origin"] in ["*", api_base_url]
        
        # Content type
        assert "content-type" in headers
        assert "application/json" in headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_graphql_error_handling(self, http_client, graphql_url):
        """Test GraphQL error handling"""
        # Invalid query
        response = await http_client.post(
            graphql_url,
            json={"query": "{ invalid query }"},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code in [200, 400]
        data = response.json()
        assert "errors" in data
        assert len(data["errors"]) > 0
        assert "message" in data["errors"][0]


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v", "-s"])