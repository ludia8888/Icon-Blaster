"""
Unified HTTP Client - Consolidates all HTTP client implementations

DESIGN INTENT:
This module provides a single, configurable HTTP client that replaces:
- SecureHTTPClient
- ServiceClient  
- Direct httpx.AsyncClient usage

FEATURES:
- mTLS support for secure service-to-service communication
- Circuit breaker for fault tolerance
- Retry logic with exponential backoff
- Service discovery and registration
- Prometheus metrics integration
- Connection pooling
- Request/response logging

MIGRATION PATH:
1. Replace SecureHTTPClient → UnifiedHTTPClient(mode="secure")
2. Replace ServiceClient → UnifiedHTTPClient(mode="service")
3. Replace httpx.AsyncClient() → UnifiedHTTPClient(mode="basic")

USAGE:
    # Basic usage (replaces direct httpx)
    client = UnifiedHTTPClient()
    
    # Secure mode (replaces SecureHTTPClient)
    client = UnifiedHTTPClient(
        mode="secure",
        enable_circuit_breaker=True,
        enable_mtls=True
    )
    
    # Service mode (replaces ServiceClient)
    client = UnifiedHTTPClient(
        mode="service", 
        service_registry={"schema": "http://schema-service:8001"}
    )
"""

import asyncio
import ssl
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Optional, Any, Union, AsyncIterator, Tuple
import logging

import httpx
from httpx import AsyncClient, Response
from prometheus_client import Counter, Histogram, Gauge
import backoff

from utils.logger import get_logger
from core.resilience.unified_circuit_breaker import UnifiedCircuitBreaker, CircuitBreakerConfig

logger = get_logger(__name__)


# Metrics - Enterprise Edition Enhanced
http_requests_total = Counter(
    'http_client_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status', 'client_mode']
)

http_request_duration = Histogram(
    'http_client_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint', 'client_mode'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 300.0)
)

circuit_breaker_state = Gauge(
    'http_client_circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=open, 2=half-open)',
    ['service', 'endpoint']
)

# Enterprise metrics - Enhanced
http_client_stream_bytes_total = Counter(
    'http_client_stream_bytes_total', 
    'Total bytes processed through streaming',
    ['endpoint', 'direction', 'content_type']
)

http_client_mtls_handshake_duration = Histogram(
    'http_client_mtls_handshake_seconds',
    'mTLS handshake duration',
    ['endpoint', 'result'],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)
)

http_client_fallback_total = Counter(
    'http_client_fallback_total',
    'Total fallback activations',
    ['reason', 'endpoint', 'fallback_type']
)

http_client_connection_pool_usage = Gauge(
    'http_client_connection_pool_usage',
    'Connection pool usage',
    ['pool_type', 'endpoint']
)

# New enhanced metrics
http_client_retry_attempts = Counter(
    'http_client_retry_attempts_total',
    'Total retry attempts',
    ['endpoint', 'retry_number', 'reason']
)

http_client_timeout_total = Counter(
    'http_client_timeout_total',
    'Total timeouts',
    ['endpoint', 'timeout_type']
)

http_client_auth_token_refresh = Counter(
    'http_client_auth_token_refresh_total',
    'Auth token refresh attempts',
    ['auth_type', 'result']
)

http_client_trace_injection = Counter(
    'http_client_trace_injection_total',
    'OpenTelemetry trace context injections',
    ['endpoint', 'trace_format']
)

http_client_streaming_chunk_size = Histogram(
    'http_client_streaming_chunk_size_bytes',
    'Size of streaming chunks',
    ['endpoint', 'direction'],
    buckets=(1024, 10240, 102400, 1048576, 10485760, 104857600)
)


class ClientMode(Enum):
    """HTTP client operation modes"""
    BASIC = "basic"      # Simple HTTP client, no extra features
    SECURE = "secure"    # With mTLS, circuit breaker, retry
    SERVICE = "service"  # With service registry, metrics


class HTTPClientConfig:
    """Configuration for unified HTTP client - Enterprise Edition"""
    
    def __init__(
        self,
        mode: ClientMode = ClientMode.BASIC,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        # Authentication & Headers
        auth: Optional[Tuple[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        verify_ssl: bool = True,
        # Security & mTLS
        enable_mtls: bool = False,
        cert_path: Optional[str] = None,
        key_path: Optional[str] = None,
        ca_path: Optional[str] = None,
        ssl_context: Optional[ssl.SSLContext] = None,
        enable_mtls_fallback: bool = False,
        # Circuit breaker
        enable_circuit_breaker: bool = False,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        # Service discovery
        service_registry: Optional[Dict[str, str]] = None,
        # Connection pool
        max_connections: int = 100,
        max_keepalive_connections: int = 20,
        keepalive_expiry: float = 5.0,
        connection_pool_config: Optional[Dict[str, Any]] = None,
        # Streaming & Performance
        stream_support: bool = False,
        enable_http2: bool = False,
        # Observability
        enable_metrics: bool = True,
        enable_logging: bool = True,
        enable_tracing: bool = False,
        log_request_body: bool = False,
        log_response_body: bool = False,
    ):
        self.mode = mode
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        # Authentication & Headers
        self.auth = auth
        self.headers = headers or {}
        self.verify_ssl = verify_ssl
        # Security & mTLS
        self.enable_mtls = enable_mtls
        self.cert_path = cert_path
        self.key_path = key_path
        self.ca_path = ca_path
        self.ssl_context = ssl_context
        self.enable_mtls_fallback = enable_mtls_fallback
        # Circuit breaker
        self.enable_circuit_breaker = enable_circuit_breaker
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        # Service discovery
        self.service_registry = service_registry or {}
        # Connection pool
        self.max_connections = max_connections
        self.max_keepalive_connections = max_keepalive_connections
        self.keepalive_expiry = keepalive_expiry
        self.connection_pool_config = connection_pool_config or {}
        # Streaming & Performance
        self.stream_support = stream_support
        self.enable_http2 = enable_http2
        # Observability
        self.enable_metrics = enable_metrics
        self.enable_logging = enable_logging
        self.enable_tracing = enable_tracing
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body


class AbstractHTTPClient(ABC):
    """Abstract base class for HTTP clients"""
    
    @abstractmethod
    async def request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> Response:
        """Make an HTTP request"""
        pass
    
    @abstractmethod
    async def get(self, url: str, **kwargs) -> Response:
        """Make a GET request"""
        pass
    
    @abstractmethod
    async def post(self, url: str, **kwargs) -> Response:
        """Make a POST request"""
        pass
    
    @abstractmethod
    async def put(self, url: str, **kwargs) -> Response:
        """Make a PUT request"""
        pass
    
    @abstractmethod
    async def delete(self, url: str, **kwargs) -> Response:
        """Make a DELETE request"""
        pass
    
    @abstractmethod
    async def close(self):
        """Close the client and cleanup resources"""
        pass


class UnifiedHTTPClient(AbstractHTTPClient):
    """
    Unified HTTP client implementation
    Consolidates SecureHTTPClient and ServiceClient functionality
    """
    
    def __init__(self, config: Optional[HTTPClientConfig] = None, **kwargs):
        """
        Initialize unified HTTP client
        
        Args:
            config: HTTPClientConfig instance
            **kwargs: Override config parameters
        """
        if config is None:
            # Determine mode from kwargs
            if kwargs.get('enable_mtls') or kwargs.get('enable_circuit_breaker'):
                mode = ClientMode.SECURE
            elif kwargs.get('service_registry'):
                mode = ClientMode.SERVICE
            else:
                mode = ClientMode.BASIC
            
            config = HTTPClientConfig(mode=mode, **kwargs)
        
        self.config = config
        self._client: Optional[AsyncClient] = None
        self._circuit_breaker: Optional[UnifiedCircuitBreaker] = None
        
        # Initialize circuit breaker if enabled
        if self.config.enable_circuit_breaker:
            cb_config = CircuitBreakerConfig(
                failure_threshold=self.config.failure_threshold,
                recovery_timeout=self.config.recovery_timeout,
                half_open_requests=1
            )
            self._circuit_breaker = UnifiedCircuitBreaker(config=cb_config)
    
    async def _get_client(self) -> AsyncClient:
        """Get or create HTTP client instance - Enterprise Edition"""
        if self._client is None:
            # Start timing for mTLS handshake if applicable
            handshake_start = time.time() if self.config.enable_mtls else None
            
            # Configure transport
            transport_kwargs = {
                'retries': 0,  # We handle retries ourselves
            }
            
            # SSL/TLS Configuration
            verify_config = self.config.verify_ssl
            if self.config.ssl_context:
                # Use provided SSL context
                verify_config = self.config.ssl_context
            elif self.config.enable_mtls:
                try:
                    # Create SSL context for mTLS
                    ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
                    if self.config.ca_path:
                        ssl_context.load_verify_locations(self.config.ca_path)
                    if self.config.cert_path and self.config.key_path:
                        ssl_context.load_cert_chain(self.config.cert_path, self.config.key_path)
                    ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
                    verify_config = ssl_context
                    
                    if self.config.enable_logging:
                        logger.info(f"mTLS enabled with cert: {self.config.cert_path}")
                        
                except Exception as e:
                    if self.config.enable_mtls_fallback:
                        logger.warning(f"mTLS setup failed, falling back to standard TLS: {e}")
                        http_client_fallback_total.labels(
                            reason="mtls_failure", 
                            endpoint=self.config.base_url or "unknown"
                        ).inc()
                        verify_config = True  # Standard TLS
                    else:
                        raise
            
            transport_kwargs['verify'] = verify_config
            
            # Configure connection pool limits
            pool_config = self.config.connection_pool_config.copy()
            pool_config.update({
                'max_connections': self.config.max_connections,
                'max_keepalive_connections': self.config.max_keepalive_connections,
            })
            
            limits = httpx.Limits(**pool_config)
            
            # Create client with all configurations
            client_kwargs = {
                'base_url': self.config.base_url,
                'timeout': httpx.Timeout(self.config.timeout),
                'limits': limits,
                'transport': httpx.AsyncHTTPTransport(**transport_kwargs),
                'auth': self.config.auth,
                'headers': self.config.headers,
            }
            
            # Add HTTP/2 support if enabled
            if self.config.enable_http2:
                client_kwargs['http2'] = True
            
            self._client = AsyncClient(**client_kwargs)
            
            # Record mTLS handshake time
            if handshake_start and self.config.enable_metrics:
                handshake_duration = time.time() - handshake_start
                http_client_mtls_handshake_duration.labels(
                    endpoint=self.config.base_url or "unknown"
                ).observe(handshake_duration)
            
            # Record connection pool usage
            if self.config.enable_metrics:
                http_client_connection_pool_usage.labels(
                    pool_type="standard"
                ).set(self.config.max_connections)
        
        return self._client
    
    def _resolve_url(self, url: str) -> str:
        """Resolve URL using service registry if available"""
        # Check if URL is a service name
        for service_name, service_url in self.config.service_registry.items():
            if url.startswith(f"{service_name}/") or url == service_name:
                return url.replace(service_name, service_url, 1)
        return url
    
    @backoff.on_exception(
        backoff.expo,
        (httpx.TimeoutException, httpx.NetworkError),
        max_tries=3,
        max_time=10
    )
    async def _execute_request(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> Response:
        """Execute HTTP request with retry logic"""
        client = await self._get_client()
        
        # Resolve URL
        resolved_url = self._resolve_url(url)
        
        # Log request
        if self.config.enable_logging:
            logger.debug(
                f"HTTP {method} {resolved_url}",
                method=method,
                url=resolved_url,
                body=kwargs.get('json') if self.config.log_request_body else None
            )
        
        # Record metrics
        start_time = time.time()
        
        try:
            response = await client.request(method, resolved_url, **kwargs)
            
            # Record success metrics
            if self.config.enable_metrics:
                http_requests_total.labels(
                    method=method,
                    endpoint=resolved_url,
                    status=response.status_code
                ).inc()
                
                http_request_duration.labels(
                    method=method,
                    endpoint=resolved_url
                ).observe(time.time() - start_time)
            
            # Log response
            if self.config.enable_logging:
                logger.debug(
                    f"HTTP {method} {resolved_url} -> {response.status_code}",
                    method=method,
                    url=resolved_url,
                    status=response.status_code,
                    duration=time.time() - start_time,
                    body=response.text if self.config.log_response_body else None
                )
            
            return response
            
        except Exception as e:
            # Record error metrics
            if self.config.enable_metrics:
                http_requests_total.labels(
                    method=method,
                    endpoint=resolved_url,
                    status='error'
                ).inc()
            
            logger.error(
                f"HTTP {method} {resolved_url} failed",
                method=method,
                url=resolved_url,
                error=str(e),
                duration=time.time() - start_time
            )
            raise
    
    async def request(
        self,
        method: str,
        url: str,
        stream: bool = False,
        **kwargs
    ) -> Response:
        """
        Make an HTTP request - Enterprise Edition
        
        Args:
            method: HTTP method
            url: Request URL or service name
            stream: Enable streaming response
            **kwargs: Additional request parameters
            
        Returns:
            httpx.Response
        """
        # Add stream parameter to kwargs if specified
        if stream and self.config.stream_support:
            kwargs['stream'] = True
        
        # Add OpenTelemetry tracing if enabled
        if self.config.enable_tracing:
            trace_context = self._inject_trace_context(kwargs.get('headers', {}))
            kwargs['headers'] = {**kwargs.get('headers', {}), **trace_context}
        
        # Use circuit breaker if enabled
        if self._circuit_breaker:
            async def make_request():
                return await self._execute_request(method, url, **kwargs)
            
            return await self._circuit_breaker.call(make_request)
        else:
            return await self._execute_request(method, url, **kwargs)
    
    def _inject_trace_context(self, headers: Dict[str, str]) -> Dict[str, str]:
        """Inject OpenTelemetry trace context into headers"""
        if not self.config.enable_tracing:
            return {}
            
        from opentelemetry import trace
        from opentelemetry.propagate import inject
        
        # Create a new headers dict to avoid modifying the original
        trace_headers = headers.copy()
        
        # Inject the current trace context into headers
        # This will add W3C Trace Context headers (traceparent, tracestate)
        # and any other configured propagators (e.g., B3)
        inject(trace_headers)
        
        return trace_headers
    
    async def get(self, url: str, stream: bool = False, **kwargs) -> Response:
        """Make a GET request"""
        return await self.request("GET", url, stream=stream, **kwargs)
    
    async def post(self, url: str, stream: bool = False, **kwargs) -> Response:
        """Make a POST request"""
        return await self.request("POST", url, stream=stream, **kwargs)
    
    async def put(self, url: str, stream: bool = False, **kwargs) -> Response:
        """Make a PUT request"""
        return await self.request("PUT", url, stream=stream, **kwargs)
    
    async def delete(self, url: str, stream: bool = False, **kwargs) -> Response:
        """Make a DELETE request"""
        return await self.request("DELETE", url, stream=stream, **kwargs)
    
    async def close(self):
        """Close the client and cleanup resources"""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()


# Convenience factory functions for migration - Enterprise Edition

def create_basic_client(**kwargs) -> UnifiedHTTPClient:
    """Create a basic HTTP client (replaces httpx.AsyncClient)"""
    return UnifiedHTTPClient(mode=ClientMode.BASIC, **kwargs)


def create_secure_client(**kwargs) -> UnifiedHTTPClient:
    """Create a secure HTTP client (replaces SecureHTTPClient)"""
    return UnifiedHTTPClient(
        mode=ClientMode.SECURE,
        enable_circuit_breaker=True,
        enable_mtls=kwargs.get('enable_mtls', False),
        **kwargs
    )


def create_service_client(service_registry: Dict[str, str], **kwargs) -> UnifiedHTTPClient:
    """Create a service HTTP client (replaces ServiceClient)"""
    return UnifiedHTTPClient(
        mode=ClientMode.SERVICE,
        service_registry=service_registry,
        enable_metrics=True,
        **kwargs
    )


# Enterprise factory functions for specialized use cases

def create_streaming_client(timeout: float = 300.0, **kwargs) -> UnifiedHTTPClient:
    """Create a client optimized for large file streaming"""
    return UnifiedHTTPClient(
        mode=ClientMode.BASIC,
        timeout=timeout,
        stream_support=True,
        max_connections=kwargs.get('max_connections', 50),
        max_keepalive_connections=kwargs.get('max_keepalive_connections', 30),
        enable_logging=False,  # Performance optimization
        max_retries=0,  # No retries for streaming
        **kwargs
    )


def create_terminus_client(
    endpoint: str,
    username: str,
    password: str,
    enable_mtls: bool = False,
    **kwargs
) -> UnifiedHTTPClient:
    """Create a client optimized for TerminusDB communication"""
    # Extract timeout from kwargs if present, otherwise use default
    timeout = kwargs.pop('timeout', 30.0)
    
    config_params = {
        'mode': ClientMode.SECURE if enable_mtls else ClientMode.BASIC,
        'base_url': endpoint,
        'auth': (username, password),
        'headers': {'Content-Type': 'application/json'},
        'timeout': timeout,
        'enable_mtls': enable_mtls,
        'enable_mtls_fallback': True,
        'enable_tracing': True,
        'enable_circuit_breaker': False,  # Let @with_retry handle retries
        **kwargs
    }
    return UnifiedHTTPClient(**config_params)


def create_iam_client(
    base_url: str,
    verify_ssl: bool = True,
    enable_fallback: bool = True,
    **kwargs
) -> UnifiedHTTPClient:
    """Create a client optimized for IAM service communication"""
    # Create config directly to avoid parameter conflicts
    config = HTTPClientConfig(
        mode=ClientMode.SECURE,
        base_url=base_url,
        verify_ssl=verify_ssl,
        timeout=10.0,
        max_retries=0,  # JWT validation doesn't benefit from retries
        enable_circuit_breaker=not enable_fallback,  # Use external CB if fallback enabled
        enable_tracing=True
    )
    
    return UnifiedHTTPClient(config=config)


# Backward compatibility aliases
SecureHTTPClient = create_secure_client  # Deprecated
ServiceClient = create_service_client     # Deprecated