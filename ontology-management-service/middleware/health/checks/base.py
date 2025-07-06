"""
Base health check interface
"""
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from ..models import HealthCheckResult, HealthStatus
import logging

logger = logging.getLogger(__name__)


class HealthCheck(ABC):
    """Abstract base class for health checks"""
    
    def __init__(self, name: str, timeout: float = 5.0):
        self.name = name
        self.timeout = timeout
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
    
    @abstractmethod
    async def check(self) -> HealthCheckResult:
        """
        Perform health check and return result.
        Must be implemented by subclasses.
        """
        pass
    
    async def execute(self) -> HealthCheckResult:
        """Execute health check with timing and error handling"""
        start_time = time.perf_counter()
        
        try:
            result = await self.check()
            duration_ms = (time.perf_counter() - start_time) * 1000
            result.duration_ms = duration_ms
            
            self.logger.debug(
                f"Health check '{self.name}' completed in {duration_ms:.2f}ms "
                f"with status: {result.status.value}"
            )
            
            return result
            
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self.logger.error(f"Health check '{self.name}' failed: {str(e)}")
            
            return HealthCheckResult(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {str(e)}",
                details={"error": str(e), "error_type": type(e).__name__},
                duration_ms=duration_ms
            )
    
    def create_result(
        self,
        status: HealthStatus,
        message: str = "",
        details: Optional[Dict[str, Any]] = None
    ) -> HealthCheckResult:
        """Helper method to create health check result"""
        return HealthCheckResult(
            name=self.name,
            status=status,
            message=message,
            details=details or {}
        )