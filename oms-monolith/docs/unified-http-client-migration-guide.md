# UnifiedHTTPClient Enterprise Migration Guide

## Overview

This guide provides comprehensive instructions for migrating from `httpx.AsyncClient` to the enterprise-grade `UnifiedHTTPClient`. The new client provides advanced features including mTLS support, connection pooling, circuit breakers, streaming optimization, and comprehensive observability.

## Table of Contents

1. [Migration Overview](#migration-overview)
2. [Key Features](#key-features)
3. [Migration Steps](#migration-steps)
4. [Code Examples](#code-examples)
5. [Configuration Guide](#configuration-guide)
6. [Testing Strategy](#testing-strategy)
7. [Monitoring and Alerts](#monitoring-and-alerts)
8. [Troubleshooting](#troubleshooting)
9. [Performance Considerations](#performance-considerations)
10. [Security Best Practices](#security-best-practices)

## Migration Overview

### Why Migrate?

The `UnifiedHTTPClient` provides:
- **Centralized HTTP client management** - Single source of truth for all HTTP operations
- **Enterprise security** - mTLS, certificate management, secure token handling
- **Resilience** - Circuit breakers, retries, fallback mechanisms
- **Performance** - Connection pooling, streaming support, optimized timeouts
- **Observability** - OpenTelemetry tracing, Prometheus metrics, structured logging

### Migration Scope

The migration covers:
- All `httpx.AsyncClient` instances
- Custom HTTP client wrappers
- Authentication mechanisms
- Error handling patterns
- Retry logic consolidation

## Key Features

### 1. mTLS Support
```python
# Automatic mTLS with fallback
client = create_terminus_client(
    endpoint="https://secure.example.com",
    enable_mtls=True,
    enable_mtls_fallback=True,
    cert_path="/path/to/cert.pem",
    key_path="/path/to/key.pem"
)
```

### 2. Connection Pooling
```python
# Optimized connection reuse
config = HTTPClientConfig(
    connection_pool_config={
        "max_connections": 100,
        "max_keepalive_connections": 20
    }
)
```

### 3. Circuit Breaker
```python
# Automatic circuit breaker protection
config = HTTPClientConfig(
    enable_circuit_breaker=True,
    circuit_failure_threshold=5,
    circuit_timeout=60
)
```

### 4. Streaming Support
```python
# Large file streaming
client = create_streaming_client(
    base_url="https://api.example.com",
    timeout=300.0,
    enable_large_file_streaming=True
)

async with client.stream("GET", "/large-file") as response:
    async for chunk in response.aiter_bytes():
        process_chunk(chunk)
```

### 5. OpenTelemetry Integration
```python
# Automatic trace propagation
config = HTTPClientConfig(
    enable_tracing=True,
    service_name="my-service"
)
```

## Migration Steps

### Step 1: Identify All httpx.AsyncClient Usages

```bash
# Find all httpx imports
rg "import httpx|from httpx" --type py

# Find AsyncClient instantiations
rg "httpx\.AsyncClient|AsyncClient\(" --type py
```

### Step 2: Replace Imports

```python
# Before
import httpx

# After
from database.clients.unified_http_client import (
    UnifiedHTTPClient,
    HTTPClientConfig,
    create_streaming_client,
    create_terminus_client,
    create_iam_client
)
```

### Step 3: Update Client Initialization

#### Basic Usage
```python
# Before
async with httpx.AsyncClient() as client:
    response = await client.get("https://api.example.com/data")

# After
config = HTTPClientConfig(base_url="https://api.example.com")
client = UnifiedHTTPClient(config)
try:
    response = await client.get("/data")
finally:
    await client.close()
```

#### With Authentication
```python
# Before
async with httpx.AsyncClient(auth=("user", "pass")) as client:
    response = await client.get(url)

# After
config = HTTPClientConfig(
    base_url="https://api.example.com",
    auth=("user", "pass")
)
client = UnifiedHTTPClient(config)
```

#### With Custom Headers
```python
# Before
headers = {"Authorization": "Bearer token"}
async with httpx.AsyncClient(headers=headers) as client:
    response = await client.get(url)

# After
config = HTTPClientConfig(
    base_url="https://api.example.com",
    headers={"Authorization": "Bearer token"}
)
client = UnifiedHTTPClient(config)
```

### Step 4: Update URL Construction

```python
# Before
response = await client.get(f"{base_url}/api/endpoint")

# After (URLs are relative to base_url)
response = await client.get("/api/endpoint")
```

### Step 5: Handle Specialized Cases

#### TerminusDB with mTLS
```python
# Before
ssl_context = ssl.create_default_context()
ssl_context.load_cert_chain(cert_path, key_path)
async with httpx.AsyncClient(verify=ssl_context) as client:
    response = await client.get(url, auth=auth)

# After
client = create_terminus_client(
    endpoint=endpoint,
    username=username,
    password=password,
    enable_mtls=True,
    cert_path=cert_path,
    key_path=key_path,
    enable_mtls_fallback=True
)
```

#### IAM Service with Fallback
```python
# Before
try:
    async with httpx.AsyncClient() as client:
        response = await client.post(iam_url, json=data)
except Exception:
    # Manual fallback logic
    pass

# After
client = create_iam_client(
    base_url=iam_url,
    enable_fallback=True,
    enable_circuit_breaker=True
)
# Fallback is automatic
```

#### Large File Streaming
```python
# Before
async with httpx.AsyncClient(timeout=300.0) as client:
    async with client.stream("GET", url) as response:
        async for chunk in response.aiter_bytes():
            process(chunk)

# After
client = create_streaming_client(
    base_url=base_url,
    timeout=300.0,
    enable_large_file_streaming=True
)
async with client.stream("GET", "/path") as response:
    async for chunk in response.aiter_bytes():
        process(chunk)
```

## Code Examples

### Example 1: Simple API Client

```python
# Before
class OldAPIClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
    
    async def get_data(self):
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/data")
            return response.json()

# After
class NewAPIClient:
    def __init__(self, base_url: str):
        self.client = UnifiedHTTPClient(
            HTTPClientConfig(base_url=base_url)
        )
    
    async def get_data(self):
        response = await self.client.get("/data")
        return response.json()
    
    async def close(self):
        await self.client.close()
```

### Example 2: Authenticated Service Client

```python
# Before
class AuthServiceClient:
    async def call_service(self, token: str):
        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(headers=headers, timeout=30.0) as client:
            try:
                response = await client.post("https://api.example.com/action")
                return response.json()
            except httpx.TimeoutException:
                return None

# After
class AuthServiceClient:
    def __init__(self):
        self.client = UnifiedHTTPClient(HTTPClientConfig(
            base_url="https://api.example.com",
            timeout=30.0,
            max_retries=3
        ))
    
    async def call_service(self, token: str):
        response = await self.client.post(
            "/action",
            headers={"Authorization": f"Bearer {token}"}
        )
        return response.json()
    
    async def close(self):
        await self.client.close()
```

### Example 3: Streaming Download

```python
# Before
async def download_large_file(url: str, output_path: str):
    async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
        async with client.stream("GET", url) as response:
            with open(output_path, "wb") as f:
                async for chunk in response.aiter_bytes():
                    f.write(chunk)

# After
async def download_large_file(url: str, output_path: str):
    client = create_streaming_client(
        base_url=url.rsplit('/', 1)[0],
        timeout=300.0,
        enable_large_file_streaming=True
    )
    try:
        async with client.stream("GET", "/" + url.rsplit('/', 1)[1]) as response:
            with open(output_path, "wb") as f:
                async for chunk in response.aiter_bytes():
                    f.write(chunk)
    finally:
        await client.close()
```

## Configuration Guide

### Environment Variables

```bash
# Connection Pool
export HTTP_CLIENT_MAX_CONNECTIONS=100
export HTTP_CLIENT_MAX_KEEPALIVE=20
export HTTP_CLIENT_POOL_TIMEOUT=30

# Circuit Breaker
export HTTP_CLIENT_CIRCUIT_ENABLED=true
export HTTP_CLIENT_CIRCUIT_THRESHOLD=5
export HTTP_CLIENT_CIRCUIT_TIMEOUT=60

# Retry Configuration
export HTTP_CLIENT_MAX_RETRIES=3
export HTTP_CLIENT_RETRY_DELAY=1.0
export HTTP_CLIENT_RETRY_BACKOFF=2.0

# mTLS
export HTTP_CLIENT_MTLS_ENABLED=true
export HTTP_CLIENT_MTLS_CERT_PATH=/path/to/cert.pem
export HTTP_CLIENT_MTLS_KEY_PATH=/path/to/key.pem
export HTTP_CLIENT_MTLS_CA_PATH=/path/to/ca.pem

# Observability
export HTTP_CLIENT_TRACING_ENABLED=true
export HTTP_CLIENT_METRICS_ENABLED=true
export HTTP_CLIENT_LOG_LEVEL=INFO
```

### Configuration Object

```python
config = HTTPClientConfig(
    # Basic settings
    base_url="https://api.example.com",
    timeout=30.0,
    
    # Authentication
    auth=("username", "password"),  # Basic auth
    headers={"Authorization": "Bearer token"},  # Bearer token
    
    # SSL/TLS
    verify_ssl=True,
    ssl_context=custom_ssl_context,
    
    # mTLS
    enable_mtls=True,
    cert_path="/path/to/cert.pem",
    key_path="/path/to/key.pem",
    ca_path="/path/to/ca.pem",
    enable_mtls_fallback=True,
    
    # Connection Pool
    connection_pool_config={
        "max_connections": 100,
        "max_keepalive_connections": 20,
        "keepalive_timeout": 30.0
    },
    
    # Circuit Breaker
    enable_circuit_breaker=True,
    circuit_failure_threshold=5,
    circuit_timeout=60,
    circuit_half_open_max_requests=3,
    
    # Retry
    max_retries=3,
    retry_delay=1.0,
    retry_backoff_factor=2.0,
    retry_on_status_codes=[502, 503, 504],
    
    # Streaming
    stream_support=True,
    chunk_size=10 * 1024 * 1024,  # 10MB
    
    # Observability
    enable_tracing=True,
    enable_metrics=True,
    service_name="my-service",
    
    # Client mode
    mode=ClientMode.PRODUCTION
)
```

## Testing Strategy

### Unit Tests

```python
import pytest
from unittest.mock import Mock, patch

@pytest.mark.asyncio
async def test_unified_client_request():
    config = HTTPClientConfig(base_url="https://api.test.com")
    client = UnifiedHTTPClient(config)
    
    with patch.object(client._client, 'request') as mock_request:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "ok"}
        mock_request.return_value = mock_response
        
        response = await client.get("/test")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
    
    await client.close()
```

### Integration Tests

```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_api_call():
    client = create_iam_client(
        base_url="https://iam.staging.example.com",
        verify_ssl=True
    )
    
    try:
        response = await client.get("/health")
        assert response.status_code == 200
    finally:
        await client.close()
```

### Performance Tests

```python
@pytest.mark.performance
@pytest.mark.asyncio
async def test_concurrent_requests():
    client = UnifiedHTTPClient(HTTPClientConfig(
        base_url="https://api.test.com",
        connection_pool_config={"max_connections": 50}
    ))
    
    start_time = time.time()
    
    # Make 100 concurrent requests
    tasks = [client.get(f"/test/{i}") for i in range(100)]
    responses = await asyncio.gather(*tasks)
    
    duration = time.time() - start_time
    
    assert all(r.status_code == 200 for r in responses)
    assert duration < 5.0  # Should complete within 5 seconds
    
    await client.close()
```

## Monitoring and Alerts

### Key Metrics

1. **Request Rate**: `http_client_requests_total`
2. **Error Rate**: `http_client_errors_total / http_client_requests_total`
3. **Response Time**: `http_client_request_duration_seconds`
4. **Circuit Breaker State**: `http_client_circuit_breaker_state`
5. **Connection Pool Usage**: `http_client_connection_pool_size`
6. **mTLS Fallbacks**: `http_client_mtls_fallback_total`
7. **Streaming Performance**: `http_client_streaming_bytes_received_total`

### Grafana Dashboards

Import the provided dashboard from `/monitoring/grafana-dashboards/unified-http-client-dashboard.json`

### Alert Examples

```yaml
# High error rate
- alert: HTTPClientHighErrorRate
  expr: |
    (sum(rate(http_client_errors_total[5m])) / sum(rate(http_client_requests_total[5m]))) > 0.05
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "High HTTP client error rate: {{ $value | humanizePercentage }}"
```

## Troubleshooting

### Common Issues

#### 1. Connection Pool Exhaustion
**Symptom**: Requests hanging or timing out
**Solution**:
```python
# Increase pool size
config.connection_pool_config = {
    "max_connections": 200,
    "max_keepalive_connections": 50
}
```

#### 2. mTLS Certificate Issues
**Symptom**: SSL handshake failures
**Solution**:
```python
# Enable fallback
config.enable_mtls_fallback = True

# Or disable mTLS temporarily
config.enable_mtls = False
```

#### 3. Circuit Breaker Opening Too Frequently
**Symptom**: Services marked as unavailable
**Solution**:
```python
# Adjust thresholds
config.circuit_failure_threshold = 10
config.circuit_timeout = 30
```

#### 4. Memory Usage with Streaming
**Symptom**: High memory consumption
**Solution**:
```python
# Use smaller chunks
async with client.stream("GET", "/large-file") as response:
    async for chunk in response.aiter_bytes(chunk_size=1024*1024):  # 1MB chunks
        process_chunk(chunk)
        del chunk  # Explicitly free memory
```

### Debug Logging

Enable debug logging for detailed information:

```python
import logging

logging.getLogger("database.clients.unified_http_client").setLevel(logging.DEBUG)
```

## Performance Considerations

### Connection Pooling Best Practices

1. **Set appropriate pool sizes**:
   - `max_connections`: 2-4x expected concurrent requests
   - `max_keepalive_connections`: 25-50% of max_connections

2. **Monitor pool metrics**:
   ```promql
   http_client_connection_pool_size{pool_type="active"} / 
   http_client_connection_pool_size{pool_type="total"}
   ```

3. **Tune keepalive timeout**:
   ```python
   config.connection_pool_config["keepalive_timeout"] = 30.0
   ```

### Streaming Optimization

1. **Use appropriate chunk sizes**:
   - Small files (< 10MB): 1MB chunks
   - Medium files (10MB - 100MB): 5MB chunks
   - Large files (> 100MB): 10MB chunks

2. **Enable streaming only when needed**:
   ```python
   # Regular requests
   response = await client.get("/small-data")
   
   # Streaming for large data
   async with client.stream("GET", "/large-data") as response:
       # Process stream
   ```

3. **Monitor streaming metrics**:
   ```promql
   rate(http_client_streaming_bytes_received_total[5m])
   ```

## Security Best Practices

### 1. Always Use HTTPS
```python
config = HTTPClientConfig(
    base_url="https://api.example.com",  # Always HTTPS
    verify_ssl=True  # Always verify
)
```

### 2. Rotate Certificates
```python
# Monitor certificate expiry
alert: CertificateExpiringSoon
expr: (http_client_mtls_certificate_expiry_timestamp - time()) / 86400 < 30
```

### 3. Secure Token Storage
```python
# Use environment variables or secure vaults
config = HTTPClientConfig(
    headers={"Authorization": f"Bearer {os.getenv('API_TOKEN')}"}
)
```

### 4. Enable mTLS for Sensitive Services
```python
# Always use mTLS for production databases
client = create_terminus_client(
    endpoint=endpoint,
    enable_mtls=True,
    enable_mtls_fallback=False  # No fallback for critical services
)
```

### 5. Audit Failed Requests
```python
# Monitor authentication failures
http_client_errors_total{error_type="AuthenticationError"}
```

## Migration Checklist

- [ ] Identify all httpx.AsyncClient usages
- [ ] Update imports to use UnifiedHTTPClient
- [ ] Replace client initialization code
- [ ] Update URL construction (use relative URLs)
- [ ] Configure authentication properly
- [ ] Set appropriate timeouts
- [ ] Enable circuit breakers for external services
- [ ] Configure connection pools
- [ ] Add proper error handling
- [ ] Update tests
- [ ] Deploy monitoring dashboards
- [ ] Configure alerts
- [ ] Test in staging environment
- [ ] Gradual rollout to production
- [ ] Monitor metrics post-deployment

## Support

For questions or issues:
1. Check the troubleshooting section
2. Review metrics and logs
3. Contact the platform team
4. File an issue in the repository

## Conclusion

The UnifiedHTTPClient provides a robust, enterprise-grade solution for all HTTP communication needs. By following this guide, you can successfully migrate your services to benefit from improved reliability, performance, and observability.