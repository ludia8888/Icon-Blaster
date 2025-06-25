"""
Secure HTTP Client with mTLS support
Updated HTTP client for service-to-service communication with mutual TLS
"""

import asyncio
import logging
import time
from typing import Optional

import httpx

from shared.security.mtls_config import create_mtls_client

logger = logging.getLogger(__name__)

class SecureHTTPClient:
    """HTTP client with mTLS, retry logic, and circuit breaker"""

    def __init__(self, service_name: str, base_url: str, use_mtls: bool = True):
        self.service_name = service_name
        self.base_url = base_url.rstrip('/')
        self.use_mtls = use_mtls
        self._client: Optional[httpx.AsyncClient] = None

        # Circuit breaker state
        self.failure_count = 0
        self.failure_threshold = 5
        self.recovery_timeout = 60
        self.last_failure_time = 0
        self.circuit_open = False

    async def __aenter__(self):
        """Async context manager entry"""
        if self.use_mtls:
            try:
                self._client = await create_mtls_client(self.service_name)
                logger.info(f"Created mTLS client for {self.service_name}")
            except Exception as e:
                logger.error(f"Failed to create mTLS client: {e}")
                # Fallback to regular HTTPS client
                self._client = httpx.AsyncClient(
                    verify=True,
                    timeout=httpx.Timeout(30.0)
                )
                logger.warning(f"Using fallback HTTPS client for {self.service_name}")
        else:
            self._client = httpx.AsyncClient(
                verify=True,
                timeout=httpx.Timeout(30.0)
            )

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self._client:
            await self._client.aclose()

    def _is_circuit_open(self) -> bool:
        """Check if circuit breaker is open"""
        if not self.circuit_open:
            return False

        # Check if recovery timeout has passed
        if time.time() - self.last_failure_time > self.recovery_timeout:
            self.circuit_open = False
            self.failure_count = 0
            logger.info(f"Circuit breaker closed for {self.service_name}")
            return False

        return True

    def _record_success(self):
        """Record successful request"""
        self.failure_count = 0
        self.circuit_open = False

    def _record_failure(self):
        """Record failed request"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.circuit_open = True
            logger.warning(f"Circuit breaker opened for {self.service_name}")

    async def _make_request_with_retry(
        self,
        method: str,
        endpoint: str,
        max_retries: int = 3,
        **kwargs
    ) -> httpx.Response:
        """Make HTTP request with exponential backoff retry"""

        # Check circuit breaker
        if self._is_circuit_open():
            raise httpx.RequestError(f"Circuit breaker is open for {self.service_name}")

        url = f"{self.base_url}{endpoint}"
        last_exception = None

        for attempt in range(max_retries + 1):
            try:
                logger.debug(f"Making {method} request to {url} (attempt {attempt + 1})")

                response = await self._client.request(method, url, **kwargs)

                # Record success
                self._record_success()

                # Check for HTTP errors
                if response.status_code >= 500:
                    # Server error - can retry
                    raise httpx.HTTPStatusError(
                        f"Server error: {response.status_code}",
                        request=response.request,
                        response=response
                    )
                elif response.status_code >= 400:
                    # Client error - don't retry
                    response.raise_for_status()

                return response

            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                last_exception = e
                logger.warning(f"Request failed (attempt {attempt + 1}): {e}")

                # Don't retry on last attempt
                if attempt == max_retries:
                    break

                # Don't retry on client errors (4xx)
                if isinstance(e, httpx.HTTPStatusError) and 400 <= e.response.status_code < 500:
                    break

                # Exponential backoff with jitter
                delay = (2 ** attempt) + (time.time() % 1)  # Add jitter
                logger.debug(f"Retrying in {delay:.2f} seconds...")
                await asyncio.sleep(delay)

        # Record failure and re-raise
        self._record_failure()
        raise last_exception

    async def get(self, endpoint: str, **kwargs) -> httpx.Response:
        """Make GET request"""
        return await self._make_request_with_retry("GET", endpoint, **kwargs)

    async def post(self, endpoint: str, **kwargs) -> httpx.Response:
        """Make POST request"""
        return await self._make_request_with_retry("POST", endpoint, **kwargs)

    async def put(self, endpoint: str, **kwargs) -> httpx.Response:
        """Make PUT request"""
        return await self._make_request_with_retry("PUT", endpoint, **kwargs)

    async def delete(self, endpoint: str, **kwargs) -> httpx.Response:
        """Make DELETE request"""
        return await self._make_request_with_retry("DELETE", endpoint, **kwargs)

    async def patch(self, endpoint: str, **kwargs) -> httpx.Response:
        """Make PATCH request"""
        return await self._make_request_with_retry("PATCH", endpoint, **kwargs)

# Service registry for mTLS communication
SERVICE_REGISTRY = {
    "schema-service": "https://schema-service:8000",
    "branch-service": "https://branch-service:8000",
    "validation-service": "https://validation-service:8000",
    "action-service": "https://action-service:8000",
    "api-gateway": "https://api-gateway:8000",
    "event-publisher": "https://event-publisher:8000"
}

async def get_service_client(from_service: str, to_service: str) -> SecureHTTPClient:
    """Get secure HTTP client for service-to-service communication"""

    if to_service not in SERVICE_REGISTRY:
        raise ValueError(f"Unknown service: {to_service}")

    base_url = SERVICE_REGISTRY[to_service]

    # Use mTLS for internal service communication
    use_mtls = True

    # Check if mTLS is disabled (for testing)
    import os
    if os.getenv("DISABLE_MTLS", "false").lower() == "true":
        use_mtls = False
        # Use HTTP for testing
        base_url = base_url.replace("https://", "http://")

    return SecureHTTPClient(
        service_name=from_service,
        base_url=base_url,
        use_mtls=use_mtls
    )

# Convenience function for making secure requests
async def secure_request(
    from_service: str,
    to_service: str,
    method: str,
    endpoint: str,
    **kwargs
) -> httpx.Response:
    """Make a secure request between services"""

    async with await get_service_client(from_service, to_service) as client:
        method_func = getattr(client, method.lower())
        return await method_func(endpoint, **kwargs)

# Health check with mTLS
async def health_check_service(from_service: str, to_service: str) -> bool:
    """Check if a service is healthy using mTLS"""
    try:
        response = await secure_request(
            from_service=from_service,
            to_service=to_service,
            method="GET",
            endpoint="/health"
        )
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Health check failed for {to_service}: {e}")
        return False
