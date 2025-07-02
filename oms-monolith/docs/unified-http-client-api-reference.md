# UnifiedHTTPClient API Reference

## Table of Contents

1. [Core Classes](#core-classes)
2. [Factory Functions](#factory-functions)
3. [Configuration](#configuration)
4. [Methods](#methods)
5. [Exceptions](#exceptions)
6. [Metrics](#metrics)
7. [Examples](#examples)

## Core Classes

### UnifiedHTTPClient

The main HTTP client class providing enterprise features.

```python
class UnifiedHTTPClient:
    def __init__(self, config: HTTPClientConfig) -> None
```

#### Parameters
- `config` (HTTPClientConfig): Configuration object containing all client settings

#### Example
```python
config = HTTPClientConfig(base_url="https://api.example.com")
client = UnifiedHTTPClient(config)
```

### HTTPClientConfig

Configuration class for UnifiedHTTPClient.

```python
@dataclass
class HTTPClientConfig:
    base_url: str
    timeout: float = 30.0
    headers: Optional[Dict[str, str]] = None
    auth: Optional[Tuple[str, str]] = None
    verify_ssl: bool = True
    ssl_context: Optional[ssl.SSLContext] = None
    max_retries: int = 3
    retry_delay: float = 1.0
    retry_backoff_factor: float = 2.0
    retry_on_status_codes: List[int] = field(default_factory=lambda: [502, 503, 504])
    enable_circuit_breaker: bool = False
    circuit_failure_threshold: int = 5
    circuit_timeout: int = 60
    circuit_half_open_max_requests: int = 3
    stream_support: bool = False
    chunk_size: int = 10 * 1024 * 1024  # 10MB
    connection_pool_config: Optional[Dict[str, Any]] = None
    enable_mtls: bool = False
    cert_path: Optional[str] = None
    key_path: Optional[str] = None
    ca_path: Optional[str] = None
    enable_mtls_fallback: bool = False
    enable_tracing: bool = True
    enable_metrics: bool = True
    service_name: str = "unified-http-client"
    mode: ClientMode = ClientMode.PRODUCTION
```

### ClientMode

Enumeration for client operation modes.

```python
class ClientMode(Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
```

### CircuitBreakerState

Enumeration for circuit breaker states.

```python
class CircuitBreakerState(Enum):
    CLOSED = 0
    OPEN = 1
    HALF_OPEN = 2
```

## Factory Functions

### create_streaming_client

Creates a client optimized for streaming operations.

```python
def create_streaming_client(
    base_url: str,
    auth: Optional[Tuple[str, str]] = None,
    timeout: float = 300.0,
    stream_support: bool = True,
    chunk_size: int = 10 * 1024 * 1024,
    enable_large_file_streaming: bool = False,
    **kwargs
) -> UnifiedHTTPClient
```

#### Parameters
- `base_url` (str): Base URL for the API
- `auth` (Optional[Tuple[str, str]]): Basic auth credentials
- `timeout` (float): Request timeout in seconds (default: 300)
- `stream_support` (bool): Enable streaming support (default: True)
- `chunk_size` (int): Size of streaming chunks (default: 10MB)
- `enable_large_file_streaming` (bool): Optimize for very large files
- `**kwargs`: Additional configuration options

#### Example
```python
client = create_streaming_client(
    base_url="https://download.example.com",
    timeout=600.0,
    enable_large_file_streaming=True
)
```

### create_terminus_client

Creates a client for TerminusDB with mTLS support.

```python
def create_terminus_client(
    endpoint: str,
    username: str,
    password: str,
    enable_mtls: bool = False,
    ssl_context: Optional[ssl.SSLContext] = None,
    cert_path: Optional[str] = None,
    key_path: Optional[str] = None,
    ca_path: Optional[str] = None,
    connection_pool_config: Optional[Dict[str, Any]] = None,
    enable_mtls_fallback: bool = True,
    enable_tracing: bool = True,
    **kwargs
) -> UnifiedHTTPClient
```

#### Parameters
- `endpoint` (str): TerminusDB endpoint URL
- `username` (str): Username for basic auth
- `password` (str): Password for basic auth
- `enable_mtls` (bool): Enable mutual TLS
- `ssl_context` (Optional[ssl.SSLContext]): Custom SSL context
- `cert_path` (Optional[str]): Path to client certificate
- `key_path` (Optional[str]): Path to client key
- `ca_path` (Optional[str]): Path to CA certificate
- `connection_pool_config` (Optional[Dict]): Pool configuration
- `enable_mtls_fallback` (bool): Enable fallback on mTLS failure
- `enable_tracing` (bool): Enable OpenTelemetry tracing

#### Example
```python
client = create_terminus_client(
    endpoint="https://terminus.example.com",
    username="admin",
    password="secure_password",
    enable_mtls=True,
    cert_path="/certs/client.pem",
    key_path="/certs/client.key"
)
```

### create_iam_client

Creates a client for IAM services with built-in fallback.

```python
def create_iam_client(
    base_url: str,
    verify_ssl: bool = True,
    enable_fallback: bool = True,
    enable_circuit_breaker: bool = True,
    timeout: float = 10.0,
    headers: Optional[Dict[str, str]] = None,
    **kwargs
) -> UnifiedHTTPClient
```

#### Parameters
- `base_url` (str): IAM service base URL
- `verify_ssl` (bool): Verify SSL certificates
- `enable_fallback` (bool): Enable automatic fallback
- `enable_circuit_breaker` (bool): Enable circuit breaker
- `timeout` (float): Request timeout
- `headers` (Optional[Dict]): Additional headers

#### Example
```python
client = create_iam_client(
    base_url="https://iam.example.com",
    enable_fallback=True,
    timeout=15.0
)
```

## Methods

### Request Methods

#### get
```python
async def get(
    self,
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    **kwargs
) -> Response
```

Performs a GET request.

#### post
```python
async def post(
    self,
    url: str,
    data: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    **kwargs
) -> Response
```

Performs a POST request.

#### put
```python
async def put(
    self,
    url: str,
    data: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    **kwargs
) -> Response
```

Performs a PUT request.

#### patch
```python
async def patch(
    self,
    url: str,
    data: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    **kwargs
) -> Response
```

Performs a PATCH request.

#### delete
```python
async def delete(
    self,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    **kwargs
) -> Response
```

Performs a DELETE request.

#### request
```python
async def request(
    self,
    method: str,
    url: str,
    **kwargs
) -> Response
```

Performs a custom HTTP request.

### Streaming Methods

#### stream
```python
async def stream(
    self,
    method: str,
    url: str,
    **kwargs
) -> AsyncContextManager[Response]
```

Opens a streaming connection.

#### Example
```python
async with client.stream("GET", "/large-file") as response:
    async for chunk in response.aiter_bytes():
        process_chunk(chunk)
```

### Lifecycle Methods

#### close
```python
async def close(self) -> None
```

Closes the client and releases resources.

#### aenter / aexit
The client supports async context manager protocol:

```python
async with UnifiedHTTPClient(config) as client:
    response = await client.get("/api/data")
```

## Response Object

The response object returned by all request methods.

### Attributes
- `status_code` (int): HTTP status code
- `headers` (Dict[str, str]): Response headers
- `content` (bytes): Raw response content
- `text` (str): Response content as text

### Methods

#### json
```python
def json(self) -> Any
```
Parses response as JSON.

#### raise_for_status
```python
def raise_for_status(self) -> None
```
Raises exception for 4xx/5xx status codes.

#### aiter_bytes
```python
async def aiter_bytes(self, chunk_size: Optional[int] = None) -> AsyncIterator[bytes]
```
Iterates over response content in chunks (streaming only).

## Exceptions

### HTTPError
Base exception for HTTP errors.

### ConnectError
Raised when connection cannot be established.

### TimeoutError
Raised when request times out.

### TooManyRedirects
Raised when redirect limit is exceeded.

### CircuitBreakerOpen
Raised when circuit breaker is open.

```python
try:
    response = await client.get("/api/data")
except CircuitBreakerOpen:
    # Handle circuit breaker
    pass
except TimeoutError:
    # Handle timeout
    pass
except HTTPError as e:
    # Handle other HTTP errors
    print(f"HTTP error: {e}")
```

## Metrics

The client automatically collects the following Prometheus metrics:

### Request Metrics
- `http_client_requests_total`: Total requests by method, endpoint, status
- `http_client_request_duration_seconds`: Request duration histogram
- `http_client_errors_total`: Total errors by type and endpoint

### Connection Metrics
- `http_client_connection_pool_size`: Current pool size
- `http_client_connection_pool_hits_total`: Pool hit count
- `http_client_connection_pool_misses_total`: Pool miss count

### Circuit Breaker Metrics
- `http_client_circuit_breaker_state`: Current state (0=closed, 1=open, 2=half-open)
- `http_client_circuit_breaker_failures_total`: Total failures
- `http_client_circuit_breaker_success_rate`: Success rate (0-1)

### mTLS Metrics
- `http_client_mtls_handshake_duration_seconds`: Handshake duration
- `http_client_mtls_fallback_total`: Fallback count
- `http_client_mtls_certificate_expiry_timestamp`: Certificate expiry time

### Streaming Metrics
- `http_client_streaming_bytes_received_total`: Total bytes received
- `http_client_streaming_bytes_sent_total`: Total bytes sent
- `http_client_streaming_chunk_size_bytes`: Chunk size histogram

## Examples

### Basic Usage

```python
from database.clients.unified_http_client import UnifiedHTTPClient, HTTPClientConfig

# Create client
config = HTTPClientConfig(
    base_url="https://api.example.com",
    timeout=30.0,
    max_retries=3
)
client = UnifiedHTTPClient(config)

# Make request
try:
    response = await client.get("/users/123")
    user = response.json()
    print(f"User: {user['name']}")
except Exception as e:
    print(f"Error: {e}")
finally:
    await client.close()
```

### With Authentication

```python
# Basic Auth
config = HTTPClientConfig(
    base_url="https://api.example.com",
    auth=("username", "password")
)

# Bearer Token
config = HTTPClientConfig(
    base_url="https://api.example.com",
    headers={"Authorization": "Bearer your-token-here"}
)
```

### Streaming Large Files

```python
client = create_streaming_client(
    base_url="https://download.example.com",
    timeout=600.0
)

async with client.stream("GET", "/large-dataset.csv") as response:
    with open("output.csv", "wb") as f:
        async for chunk in response.aiter_bytes(chunk_size=1024*1024):
            f.write(chunk)

await client.close()
```

### With Circuit Breaker

```python
config = HTTPClientConfig(
    base_url="https://flaky-api.example.com",
    enable_circuit_breaker=True,
    circuit_failure_threshold=5,
    circuit_timeout=60
)
client = UnifiedHTTPClient(config)

for i in range(10):
    try:
        response = await client.get("/unstable-endpoint")
        print(f"Success: {response.status_code}")
    except CircuitBreakerOpen:
        print("Circuit breaker is open, service unavailable")
        break
    except Exception as e:
        print(f"Request failed: {e}")
```

### With mTLS

```python
client = create_terminus_client(
    endpoint="https://secure-db.example.com",
    username="admin",
    password="secure-pass",
    enable_mtls=True,
    cert_path="/certs/client.pem",
    key_path="/certs/client.key",
    ca_path="/certs/ca.pem",
    enable_mtls_fallback=True
)

try:
    response = await client.get("/api/health")
    if response.status_code == 200:
        print("Connected with mTLS")
except Exception as e:
    print(f"Connection failed: {e}")
finally:
    await client.close()
```

### Concurrent Requests

```python
import asyncio

config = HTTPClientConfig(
    base_url="https://api.example.com",
    connection_pool_config={
        "max_connections": 100,
        "max_keepalive_connections": 20
    }
)
client = UnifiedHTTPClient(config)

# Make 50 concurrent requests
async def fetch_user(user_id: int):
    response = await client.get(f"/users/{user_id}")
    return response.json()

users = await asyncio.gather(*[
    fetch_user(i) for i in range(50)
])

await client.close()
```

### Error Handling

```python
from database.clients.unified_http_client import (
    UnifiedHTTPClient,
    HTTPClientConfig,
    CircuitBreakerOpen,
    TimeoutError,
    HTTPError
)

config = HTTPClientConfig(
    base_url="https://api.example.com",
    timeout=10.0,
    enable_circuit_breaker=True
)
client = UnifiedHTTPClient(config)

try:
    response = await client.post("/api/action", json={"key": "value"})
    response.raise_for_status()
    result = response.json()
    
except CircuitBreakerOpen:
    # Service is unavailable
    print("Service temporarily unavailable")
    
except TimeoutError:
    # Request timed out
    print("Request timed out")
    
except HTTPError as e:
    # HTTP error (4xx, 5xx)
    if e.response.status_code == 404:
        print("Resource not found")
    elif e.response.status_code >= 500:
        print("Server error")
    else:
        print(f"HTTP error: {e}")
        
except Exception as e:
    # Other errors
    print(f"Unexpected error: {e}")
    
finally:
    await client.close()
```

### Custom Retry Logic

```python
config = HTTPClientConfig(
    base_url="https://api.example.com",
    max_retries=5,
    retry_delay=2.0,
    retry_backoff_factor=2.0,
    retry_on_status_codes=[429, 502, 503, 504]
)
client = UnifiedHTTPClient(config)

# Will automatically retry on specified status codes
response = await client.get("/api/data")
```

### Monitoring Integration

```python
from prometheus_client import generate_latest

# Client automatically collects metrics
config = HTTPClientConfig(
    base_url="https://api.example.com",
    enable_metrics=True,
    service_name="my-service"
)
client = UnifiedHTTPClient(config)

# Make some requests
for i in range(100):
    await client.get(f"/api/data/{i}")

# Export metrics
metrics = generate_latest()
print(metrics.decode('utf-8'))
```