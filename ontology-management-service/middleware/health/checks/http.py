"""
HTTP endpoint health check implementation
"""
import asyncio
from typing import Optional, Dict, Any, List
from database.clients.unified_http_client import create_basic_client
from .base import HealthCheck
from ..models import HealthCheckResult, HealthStatus


class HttpHealthCheck(HealthCheck):
    """Health check for HTTP endpoints"""
    
    def __init__(
        self,
        url: str,
        name: Optional[str] = None,
        timeout: float = 5.0,
        expected_status_codes: Optional[List[int]] = None,
        expected_response: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ):
        super().__init__(name or f"http_{url}", timeout)
        self.url = url
        self.expected_status_codes = expected_status_codes or [200, 201, 204]
        self.expected_response = expected_response
        self.headers = headers or {}
    
    async def check(self) -> HealthCheckResult:
        """Check HTTP endpoint health"""
        try:
            async with create_basic_client(timeout=self.timeout) as client:
                # Make request
                response = await client.get(self.url, headers=self.headers)
                
                # Check status code
                if response.status_code not in self.expected_status_codes:
                    return self.create_result(
                        status=HealthStatus.UNHEALTHY,
                        message=f"Unexpected status code: {response.status_code}",
                        details={
                            "url": self.url,
                            "status_code": response.status_code,
                            "expected_codes": self.expected_status_codes,
                            "response_text": response.text[:500]  # First 500 chars
                        }
                    )
                
                # Parse response if JSON expected
                response_data = None
                if self.expected_response and response.headers.get('content-type', '').startswith('application/json'):
                    try:
                        response_data = response.json()
                    except Exception as e:
                        return self.create_result(
                            status=HealthStatus.UNHEALTHY,
                            message=f"Invalid JSON response: {str(e)}",
                            details={
                                "url": self.url,
                                "error": str(e),
                                "response_text": response.text[:500]
                            }
                        )
                
                # Validate response content if expected
                if self.expected_response and response_data:
                    validation_errors = self._validate_response(response_data, self.expected_response)
                    if validation_errors:
                        return self.create_result(
                            status=HealthStatus.DEGRADED,
                            message="Response validation failed",
                            details={
                                "url": self.url,
                                "validation_errors": validation_errors,
                                "actual_response": response_data
                            }
                        )
                
                # Extract timing information
                request_info = {
                    "url": self.url,
                    "status_code": response.status_code,
                    "response_time_ms": response.elapsed.total_seconds() * 1000,
                    "headers": dict(response.headers)
                }
                
                # Check response time
                if response.elapsed.total_seconds() > self.timeout * 0.8:
                    return self.create_result(
                        status=HealthStatus.DEGRADED,
                        message=f"Slow response time: {response.elapsed.total_seconds():.2f}s",
                        details=request_info
                    )
                
                return self.create_result(
                    status=HealthStatus.HEALTHY,
                    message=f"HTTP endpoint responsive",
                    details=request_info
                )
                
        except Exception as timeout_err:
            if "timeout" in str(timeout_err).lower():
                return self.create_result(
                    status=HealthStatus.UNHEALTHY,
                    message=f"HTTP request timeout ({self.timeout}s)",
                    details={"url": self.url, "timeout": self.timeout}
                )
            elif "connect" in str(timeout_err).lower():
                return self.create_result(
                    status=HealthStatus.UNHEALTHY,
                    message=f"Connection failed: {str(timeout_err)}",
                    details={"url": self.url, "error": str(timeout_err)}
                )
            raise
        except Exception as e:
            return self.create_result(
                status=HealthStatus.UNHEALTHY,
                message=f"HTTP health check failed: {str(e)}",
                details={
                    "url": self.url,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
    
    def _validate_response(
        self, 
        actual: Dict[str, Any], 
        expected: Dict[str, Any]
    ) -> List[str]:
        """Validate response against expected structure"""
        errors = []
        
        for key, expected_value in expected.items():
            if key not in actual:
                errors.append(f"Missing key: {key}")
            elif isinstance(expected_value, dict) and isinstance(actual.get(key), dict):
                # Recursive validation for nested objects
                nested_errors = self._validate_response(actual[key], expected_value)
                errors.extend(f"{key}.{error}" for error in nested_errors)
            elif actual.get(key) != expected_value:
                errors.append(f"Value mismatch for {key}: expected {expected_value}, got {actual.get(key)}")
        
        return errors