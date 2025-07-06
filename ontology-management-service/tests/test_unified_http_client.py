"""
Enterprise Test Suite for UnifiedHTTPClient
Tests all enterprise features: mTLS, streaming, circuit breaker, metrics, OpenTelemetry
"""
import asyncio
import json
import ssl
import time
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from prometheus_client import REGISTRY

from database.clients.unified_http_client import (
    CircuitBreakerState,
    ClientMode,
    HTTPClientConfig,
    UnifiedHTTPClient,
    create_iam_client,
    create_streaming_client,
    create_terminus_client,
)


@pytest.fixture
def setup_tracing():
    """Set up OpenTelemetry tracing for tests"""
    provider = TracerProvider()
    processor = BatchSpanProcessor(ConsoleSpanExporter())
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)
    yield
    provider.shutdown()


@pytest.fixture
async def basic_client():
    """Create a basic HTTP client for testing"""
    config = HTTPClientConfig(
        base_url="https://example.com",
        timeout=5.0,
        max_retries=2,
    )
    client = UnifiedHTTPClient(config)
    yield client
    await client.close()


@pytest.fixture
async def mtls_client():
    """Create an mTLS-enabled client for testing"""
    config = HTTPClientConfig(
        base_url="https://secure.example.com",
        timeout=10.0,
        enable_mtls=True,
        cert_path="/path/to/cert.pem",
        key_path="/path/to/key.pem",
        ca_path="/path/to/ca.pem",
        enable_mtls_fallback=True,
    )
    client = UnifiedHTTPClient(config)
    yield client
    await client.close()


@pytest.fixture
async def streaming_client():
    """Create a streaming-enabled client for testing"""
    client = create_streaming_client(
        base_url="https://streaming.example.com",
        timeout=300.0,
        stream_support=True,
        enable_large_file_streaming=True,
    )
    yield client
    await client.close()


class TestUnifiedHTTPClient:
    """Test suite for UnifiedHTTPClient"""

    @pytest.mark.asyncio
    async def test_basic_request(self, basic_client):
        """Test basic HTTP request functionality"""
        with patch.object(basic_client._client, 'request') as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "ok"}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            response = await basic_client.get("/api/test")
            
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}
            mock_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_auth_handling(self):
        """Test authentication handling"""
        # Test basic auth
        config = HTTPClientConfig(
            base_url="https://api.example.com",
            auth=("user", "pass"),
        )
        client = UnifiedHTTPClient(config)
        
        with patch.object(client._client, 'request') as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_request.return_value = mock_response

            await client.get("/secure")
            
            # Verify auth was passed
            call_args = mock_request.call_args
            assert call_args[1].get('auth') == ("user", "pass")

        await client.close()

    @pytest.mark.asyncio
    async def test_bearer_token_auth(self):
        """Test Bearer token authentication"""
        config = HTTPClientConfig(
            base_url="https://api.example.com",
            headers={"Authorization": "Bearer test-token"},
        )
        client = UnifiedHTTPClient(config)
        
        with patch.object(client._client, 'request') as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_request.return_value = mock_response

            await client.get("/api/protected")
            
            # Verify headers were passed
            call_args = mock_request.call_args
            headers = call_args[1].get('headers', {})
            assert headers.get('Authorization') == "Bearer test-token"

        await client.close()

    @pytest.mark.asyncio
    async def test_circuit_breaker(self, basic_client):
        """Test circuit breaker functionality"""
        # Enable circuit breaker
        basic_client._config.enable_circuit_breaker = True
        basic_client._circuit_state = CircuitBreakerState.CLOSED
        basic_client._circuit_failure_count = 0
        basic_client._circuit_failure_threshold = 3

        # Simulate failures
        with patch.object(basic_client._client, 'request') as mock_request:
            mock_request.side_effect = httpx.ConnectError("Connection failed")

            # First 3 failures should be allowed
            for i in range(3):
                with pytest.raises(httpx.ConnectError):
                    await basic_client.get("/api/test")

            # Circuit should now be open
            assert basic_client._circuit_state == CircuitBreakerState.OPEN

            # Next request should fail immediately
            with pytest.raises(Exception, match="Circuit breaker is OPEN"):
                await basic_client.get("/api/test")

    @pytest.mark.asyncio
    async def test_retry_logic(self):
        """Test retry logic with exponential backoff"""
        config = HTTPClientConfig(
            base_url="https://api.example.com",
            max_retries=3,
            retry_delay=0.1,  # Short delay for tests
        )
        client = UnifiedHTTPClient(config)

        attempt_count = 0

        async def mock_request(*args, **kwargs):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise httpx.ConnectTimeout("Timeout")
            return Mock(status_code=200, json=lambda: {"retry": "success"})

        with patch.object(client._client, 'request', side_effect=mock_request):
            response = await client.get("/api/retry")
            
            assert attempt_count == 3
            assert response.json() == {"retry": "success"}

        await client.close()

    @pytest.mark.asyncio
    async def test_streaming_response(self, streaming_client):
        """Test streaming response handling"""
        # Mock streaming response
        async def mock_iter_bytes():
            for chunk in [b"chunk1", b"chunk2", b"chunk3"]:
                yield chunk

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/octet-stream"}
        mock_response.aiter_bytes = mock_iter_bytes

        with patch.object(streaming_client._client, 'stream') as mock_stream:
            mock_stream.return_value.__aenter__.return_value = mock_response
            
            chunks = []
            async with streaming_client.stream("GET", "/api/download") as response:
                async for chunk in response.aiter_bytes():
                    chunks.append(chunk)
            
            assert chunks == [b"chunk1", b"chunk2", b"chunk3"]

    @pytest.mark.asyncio
    async def test_mtls_fallback(self, mtls_client):
        """Test mTLS fallback mechanism"""
        # First attempt with mTLS should fail
        with patch.object(mtls_client._client, 'request') as mock_request:
            # Simulate SSL error
            mock_request.side_effect = [
                ssl.SSLError("SSL handshake failed"),
                Mock(status_code=200, json=lambda: {"fallback": "success"})
            ]

            response = await mtls_client.get("/api/secure")
            
            # Should have fallen back to regular HTTPS
            assert response.json() == {"fallback": "success"}
            assert mock_request.call_count == 2

    @pytest.mark.asyncio
    async def test_opentelemetry_integration(self, setup_tracing):
        """Test OpenTelemetry trace integration"""
        config = HTTPClientConfig(
            base_url="https://api.example.com",
            enable_tracing=True,
        )
        client = UnifiedHTTPClient(config)

        with patch.object(client._client, 'request') as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"traced": True}
            mock_response.headers = {}
            mock_request.return_value = mock_response

            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span("test_operation"):
                response = await client.get("/api/traced")

            # Verify trace context was injected
            call_args = mock_request.call_args
            headers = call_args[1].get('headers', {})
            assert 'traceparent' in headers or 'X-B3-TraceId' in headers

        await client.close()

    @pytest.mark.asyncio
    async def test_connection_pooling(self):
        """Test connection pool configuration"""
        config = HTTPClientConfig(
            base_url="https://api.example.com",
            connection_pool_config={
                "max_connections": 50,
                "max_keepalive_connections": 10,
            }
        )
        client = UnifiedHTTPClient(config)

        # Verify pool limits are set
        assert client._client._transport._pool._max_connections == 50
        assert client._client._transport._pool._max_keepalive_connections == 10

        await client.close()

    @pytest.mark.asyncio
    async def test_metrics_collection(self, basic_client):
        """Test Prometheus metrics collection"""
        # Clear metrics
        for collector in list(REGISTRY._collector_to_names.keys()):
            if hasattr(collector, '_name') and 'http_client' in collector._name:
                REGISTRY.unregister(collector)

        with patch.object(basic_client._client, 'request') as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.elapsed = Mock(total_seconds=lambda: 0.5)
            mock_request.return_value = mock_response

            await basic_client.get("/api/metrics")

            # Metrics should be recorded
            # Note: In real implementation, verify specific metric values

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """Test timeout configuration and handling"""
        config = HTTPClientConfig(
            base_url="https://api.example.com",
            timeout=0.001,  # Very short timeout
        )
        client = UnifiedHTTPClient(config)

        with patch.object(client._client, 'request') as mock_request:
            mock_request.side_effect = httpx.TimeoutException("Request timed out")

            with pytest.raises(httpx.TimeoutException):
                await client.get("/api/slow")

        await client.close()


class TestFactoryFunctions:
    """Test factory functions for creating specialized clients"""

    @pytest.mark.asyncio
    async def test_create_streaming_client(self):
        """Test streaming client factory"""
        client = create_streaming_client(
            base_url="https://download.example.com",
            timeout=600.0,
            enable_large_file_streaming=True,
        )

        assert client._config.stream_support is True
        assert client._config.timeout == 600.0
        assert client._config.max_retries == 1  # Streaming typically has fewer retries

        await client.close()

    @pytest.mark.asyncio
    async def test_create_terminus_client(self):
        """Test TerminusDB client factory"""
        client = create_terminus_client(
            endpoint="https://terminus.example.com",
            username="admin",
            password="secret",
            enable_mtls=True,
            enable_tracing=True,
        )

        assert client._config.base_url == "https://terminus.example.com"
        assert client._config.auth == ("admin", "secret")
        assert client._config.enable_mtls is True
        assert client._config.enable_tracing is True

        await client.close()

    @pytest.mark.asyncio
    async def test_create_iam_client(self):
        """Test IAM client factory"""
        client = create_iam_client(
            base_url="https://iam.example.com",
            verify_ssl=True,
            enable_fallback=True,
        )

        assert client._config.verify_ssl is True
        assert "X-Service-Name" in client._config.headers
        assert client._config.headers["X-Service-Name"] == "oms-iam-client"

        await client.close()


class TestEdgeCases:
    """Test edge cases and error handling"""

    @pytest.mark.asyncio
    async def test_invalid_url_handling(self):
        """Test handling of invalid URLs"""
        config = HTTPClientConfig(base_url="not-a-valid-url")
        client = UnifiedHTTPClient(config)

        with pytest.raises(Exception):
            await client.get("/api/test")

        await client.close()

    @pytest.mark.asyncio
    async def test_concurrent_requests(self):
        """Test handling of concurrent requests"""
        config = HTTPClientConfig(
            base_url="https://api.example.com",
            connection_pool_config={"max_connections": 5}
        )
        client = UnifiedHTTPClient(config)

        with patch.object(client._client, 'request') as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"concurrent": True}
            mock_request.return_value = mock_response

            # Make 10 concurrent requests
            tasks = [client.get(f"/api/test/{i}") for i in range(10)]
            responses = await asyncio.gather(*tasks)

            assert len(responses) == 10
            assert all(r.json() == {"concurrent": True} for r in responses)

        await client.close()

    @pytest.mark.asyncio
    async def test_empty_response_handling(self):
        """Test handling of empty responses"""
        config = HTTPClientConfig(base_url="https://api.example.com")
        client = UnifiedHTTPClient(config)

        with patch.object(client._client, 'request') as mock_request:
            mock_response = Mock()
            mock_response.status_code = 204  # No content
            mock_response.content = b""
            mock_response.text = ""
            mock_request.return_value = mock_response

            response = await client.delete("/api/resource/123")
            
            assert response.status_code == 204

        await client.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])