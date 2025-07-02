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
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Optional, Any, Union, AsyncIterator
import logging

import httpx
from httpx import AsyncClient, Response
from prometheus_client import Counter, Histogram, Gauge
import backoff

from utils.logger import get_logger
from core.resilience.unified_circuit_breaker import UnifiedCircuitBreaker, CircuitBreakerConfig

logger = get_logger(__name__)


# Metrics
http_requests_total = Counter(
    'http_client_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration = Histogram(
    'http_client_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint']
)

circuit_breaker_state = Gauge(
    'http_client_circuit_breaker_state',
    'Circuit breaker state (0=closed, 1=open, 2=half-open)',
    ['service']
)


class ClientMode(Enum):
    """HTTP client operation modes"""
    BASIC = "basic"      # Simple HTTP client, no extra features
    SECURE = "secure"    # With mTLS, circuit breaker, retry
    SERVICE = "service"  # With service registry, metrics


class HTTPClientConfig:
    """Configuration for unified HTTP client"""
    
    def __init__(
        self,
        mode: ClientMode = ClientMode.BASIC,
        base_url: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        # Security
        enable_mtls: bool = False,
        cert_path: Optional[str] = None,
        key_path: Optional[str] = None,
        ca_path: Optional[str] = None,
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
        # Observability
        enable_metrics: bool = True,
        enable_logging: bool = True,
        log_request_body: bool = False,
        log_response_body: bool = False,
    ):
        self.mode = mode
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        # Security
        self.enable_mtls = enable_mtls
        self.cert_path = cert_path
        self.key_path = key_path
        self.ca_path = ca_path
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
        # Observability
        self.enable_metrics = enable_metrics
        self.enable_logging = enable_logging
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
        """Get or create HTTP client instance"""
        if self._client is None:
            # Configure transport
            transport_kwargs = {
                'retries': 0,  # We handle retries ourselves
            }
            
            # Add mTLS if enabled
            if self.config.enable_mtls:
                transport_kwargs.update({
                    'cert': (self.config.cert_path, self.config.key_path) 
                           if self.config.cert_path else None,
                    'verify': self.config.ca_path or True,
                })
            
            # Configure limits
            limits = httpx.Limits(
                max_connections=self.config.max_connections,
                max_keepalive_connections=self.config.max_keepalive_connections,
            )
            
            # Create client
            self._client = AsyncClient(
                base_url=self.config.base_url,
                timeout=httpx.Timeout(self.config.timeout),
                limits=limits,
                transport=httpx.AsyncHTTPTransport(**transport_kwargs),
            )
        
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
        **kwargs
    ) -> Response:
        """
        Make an HTTP request
        
        Args:
            method: HTTP method
            url: Request URL or service name
            **kwargs: Additional request parameters
            
        Returns:
            httpx.Response
        """
        # Use circuit breaker if enabled
        if self._circuit_breaker:
            async def make_request():
                return await self._execute_request(method, url, **kwargs)
            
            return await self._circuit_breaker.call(make_request)
        else:
            return await self._execute_request(method, url, **kwargs)
    
    async def get(self, url: str, **kwargs) -> Response:
        """Make a GET request"""
        return await self.request("GET", url, **kwargs)
    
    async def post(self, url: str, **kwargs) -> Response:
        """Make a POST request"""
        return await self.request("POST", url, **kwargs)
    
    async def put(self, url: str, **kwargs) -> Response:
        """Make a PUT request"""
        return await self.request("PUT", url, **kwargs)
    
    async def delete(self, url: str, **kwargs) -> Response:
        """Make a DELETE request"""
        return await self.request("DELETE", url, **kwargs)
    
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


# Convenience factory functions for migration

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


# Backward compatibility aliases
SecureHTTPClient = create_secure_client  # Deprecated
ServiceClient = create_service_client     # Deprecated