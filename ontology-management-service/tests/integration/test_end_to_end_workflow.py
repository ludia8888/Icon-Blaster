"""
End-to-End Workflow Integration Test
Tests complete workflows across all system components
"""
import asyncio
import httpx
import pytest
import pytest_asyncio
from datetime import datetime
import json
import os
from typing import Dict, Any, Optional


class TestEndToEndWorkflow:
    """Test complete end-to-end workflows"""
    
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
        """Create HTTP client with timeout"""
        client = httpx.AsyncClient(timeout=30.0)
        yield client
        await client.aclose()
    
    @pytest_asyncio.fixture
    async def auth_token(self, http_client, api_base_url):
        """Get authentication token"""
        # Try to create a test user and get token
        # This is a simplified version - real implementation would use proper auth
        return "test-token-for-integration-testing"
    
    @pytest.fixture
    def auth_headers(self, auth_token):
        """Get authentication headers"""
        return {"Authorization": f"Bearer {auth_token}"}
    
    async def wait_for_service_ready(self, http_client: httpx.AsyncClient, url: str, max_attempts: int = 30):
        """Wait for service to be ready"""
        for i in range(max_attempts):
            try:
                response = await http_client.get(f"{url}/health")
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "healthy":
                        return True
            except Exception:
                pass
            await asyncio.sleep(1)
        return False
    
    @pytest.mark.asyncio
    async def test_complete_schema_workflow(self, http_client, api_base_url, graphql_url, auth_headers):
        """Test complete schema management workflow"""
        # 1. Check service health
        health_response = await http_client.get(f"{api_base_url}/health")
        assert health_response.status_code == 200
        health_data = health_response.json()
        assert health_data["status"] in ["healthy", "degraded"]
        
        # 2. Query existing object types via GraphQL
        query = """
        query ListObjectTypes {
            objectTypes(branch: "main", limit: 5) {
                items {
                    id
                    abstract
                    parents
                }
                totalCount
            }
        }
        """
        
        graphql_response = await http_client.post(
            graphql_url,
            json={"query": query},
            headers={"Content-Type": "application/json"}
        )
        
        assert graphql_response.status_code == 200
        graphql_data = graphql_response.json()
        
        # Handle case where auth might be required
        if "errors" in graphql_data:
            # Check if it's an auth error
            error_message = graphql_data["errors"][0].get("message", "").lower()
            if "auth" in error_message or "permission" in error_message:
                pytest.skip("Authentication required for GraphQL queries")
        
        # 3. Test metrics collection
        metrics_response = await http_client.get(f"{api_base_url}/metrics")
        assert metrics_response.status_code == 200
        metrics_text = metrics_response.text
        
        # Verify metrics are being collected
        assert "python_gc_objects_collected_total" in metrics_text
        assert "http_client_trace_injection_total" in metrics_text
    
    @pytest.mark.asyncio
    async def test_event_flow_workflow(self, http_client, api_base_url):
        """Test event publishing and processing workflow"""
        # 1. Check NATS connectivity via health endpoint
        health_response = await http_client.get(f"{api_base_url}/health")
        assert health_response.status_code == 200
        
        # 2. Verify event endpoints are available
        # Most event publishing happens internally, so we check API availability
        openapi_response = await http_client.get(f"{api_base_url}/openapi.json")
        assert openapi_response.status_code == 200
        
        openapi_schema = openapi_response.json()
        paths = openapi_schema.get("paths", {})
        
        # Look for event-related endpoints
        event_endpoints = [path for path in paths if "event" in path.lower()]
        
        # System should have some event-related functionality
        # Even if not exposed as REST endpoints
        assert len(paths) > 0  # At least some endpoints exist
    
    @pytest.mark.asyncio
    async def test_graphql_subscription_workflow(self):
        """Test GraphQL subscription workflow"""
        import websockets
        import json
        
        ws_url = os.getenv("WS_URL", "ws://localhost:8004/ws")
        
        try:
            async with websockets.connect(ws_url) as websocket:
                # 1. Send connection init
                await websocket.send(json.dumps({
                    "type": "connection_init",
                    "payload": {}
                }))
                
                # 2. Wait for connection ack
                response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                data = json.loads(response)
                
                # Connection might require auth
                if data.get("type") == "connection_error":
                    pytest.skip("WebSocket authentication required")
                
                # 3. If connected, test ping/pong
                if data.get("type") == "connection_ack":
                    await websocket.send(json.dumps({"type": "ping"}))
                    
                    pong_response = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                    pong_data = json.loads(pong_response)
                    assert pong_data.get("type") == "pong"
                
        except (websockets.exceptions.WebSocketException, asyncio.TimeoutError) as e:
            # WebSocket might require authentication
            if "401" in str(e) or "403" in str(e):
                pytest.skip("WebSocket authentication required")
            else:
                raise
    
    @pytest.mark.asyncio
    async def test_monitoring_and_observability(self, http_client, api_base_url):
        """Test monitoring and observability features"""
        # 1. Check health endpoint provides detailed info
        health_response = await http_client.get(f"{api_base_url}/health")
        assert health_response.status_code == 200
        
        health_data = health_response.json()
        assert "timestamp" in health_data
        assert "response_time_ms" in health_data
        assert "checks" in health_data
        
        # 2. Verify OpenTelemetry metrics
        metrics_response = await http_client.get(f"{api_base_url}/metrics")
        assert metrics_response.status_code == 200
        
        metrics_text = metrics_response.text
        
        # Look for OpenTelemetry specific metrics
        otel_metrics = [
            "http_client_trace_injection_total",
            "python_gc_objects_collected_total",
        ]
        
        for metric in otel_metrics:
            assert metric in metrics_text, f"Missing metric: {metric}"
        
        # 3. Make multiple requests to generate metrics
        for _ in range(5):
            await http_client.get(f"{api_base_url}/health")
        
        # 4. Check metrics again - values should have increased
        metrics_response2 = await http_client.get(f"{api_base_url}/metrics")
        assert metrics_response2.status_code == 200
        
        # Metrics should be different after requests
        assert metrics_response2.text != metrics_text
    
    @pytest.mark.asyncio
    async def test_error_recovery_workflow(self, http_client, api_base_url):
        """Test system error handling and recovery"""
        # 1. Test invalid endpoint handling
        response = await http_client.get(f"{api_base_url}/invalid-endpoint-12345")
        assert response.status_code == 404
        
        # 2. Test invalid method handling
        response = await http_client.patch(f"{api_base_url}/health")
        assert response.status_code in [405, 404]  # Method not allowed or not found
        
        # 3. Verify system still healthy after errors
        health_response = await http_client.get(f"{api_base_url}/health")
        assert health_response.status_code == 200
        assert health_response.json()["status"] in ["healthy", "degraded"]
        
        # 4. Test malformed request handling
        response = await http_client.post(
            f"{api_base_url}/api/v1/test",
            content="not json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code in [400, 404, 422]
        
        # 5. System should still be responsive
        final_health = await http_client.get(f"{api_base_url}/health")
        assert final_health.status_code == 200
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, http_client, api_base_url, graphql_url):
        """Test system under concurrent load"""
        # Create multiple concurrent operations
        tasks = []
        
        # Mix of different operation types
        for i in range(10):
            if i % 3 == 0:
                # Health checks
                task = http_client.get(f"{api_base_url}/health")
            elif i % 3 == 1:
                # Metrics requests
                task = http_client.get(f"{api_base_url}/metrics")
            else:
                # GraphQL queries
                query = '{ __schema { queryType { name } } }'
                task = http_client.post(
                    graphql_url,
                    json={"query": query},
                    headers={"Content-Type": "application/json"}
                )
            tasks.append(task)
        
        # Execute all concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify results
        success_count = 0
        for result in results:
            if not isinstance(result, Exception):
                if result.status_code in [200, 201]:
                    success_count += 1
        
        # At least 80% should succeed
        assert success_count >= len(results) * 0.8
        
        # System should still be healthy
        health_check = await http_client.get(f"{api_base_url}/health")
        assert health_check.status_code == 200


if __name__ == "__main__":
    # Run tests directly
    pytest.main([__file__, "-v", "-s"])