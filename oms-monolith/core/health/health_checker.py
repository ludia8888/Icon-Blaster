"""
Production-grade health checker with real system verification.
This replaces the fake health check with actual system monitoring.
"""

import asyncio
import psutil
import time
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from enum import Enum
import logging
import redis.asyncio as aioredis
import asyncpg
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthCheck:
    """Individual health check result"""
    def __init__(self, name: str, status: bool, message: str = "", 
                 response_time_ms: Optional[float] = None, 
                 metadata: Optional[Dict[str, Any]] = None):
        self.name = name
        self.status = status
        self.message = message
        self.response_time_ms = response_time_ms
        self.metadata = metadata or {}
        self.timestamp = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "response_time_ms": self.response_time_ms,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat()
        }


class HealthChecker:
    """
    Real health checker that actually verifies system state.
    No lies, no assumptions - only verified facts.
    """
    
    def __init__(self, 
                 db_url: Optional[str] = None,
                 redis_url: Optional[str] = None,
                 critical_services: Optional[List[str]] = None):
        self.db_url = db_url or "postgresql://admin:root@localhost/oms"
        self.redis_url = redis_url or "redis://localhost:6379"
        self.critical_services = critical_services or ["database", "redis"]
        
        # Health check history for trend analysis
        self.check_history: List[Tuple[datetime, Dict[str, Any]]] = []
        self.max_history_size = 100
        
        # Cache for expensive checks
        self._cache: Dict[str, Tuple[datetime, Any]] = {}
        self._cache_ttl = timedelta(seconds=5)

    async def check_database(self) -> HealthCheck:
        """
        Actually check database connectivity and performance.
        """
        start_time = time.time()
        
        try:
            # Try to connect and run a simple query
            conn = await asyncpg.connect(self.db_url, timeout=5)
            try:
                # Run a simple query to verify connection
                result = await conn.fetchval("SELECT 1")
                if result != 1:
                    return HealthCheck(
                        "database", 
                        False, 
                        "Query returned unexpected result",
                        (time.time() - start_time) * 1000
                    )
                
                # Check database size (optional metadata)
                db_size = await conn.fetchval("""
                    SELECT pg_database_size(current_database())
                """)
                
                response_time = (time.time() - start_time) * 1000
                
                return HealthCheck(
                    "database",
                    True,
                    "Database connection successful",
                    response_time,
                    {"size_bytes": db_size, "query_result": result}
                )
            finally:
                await conn.close()
                
        except asyncio.TimeoutError:
            return HealthCheck(
                "database",
                False,
                "Database connection timeout (>5s)",
                5000.0
            )
        except Exception as e:
            return HealthCheck(
                "database",
                False,
                f"Database error: {str(e)}",
                (time.time() - start_time) * 1000
            )

    async def check_redis(self) -> HealthCheck:
        """
        Actually check Redis connectivity and performance.
        """
        start_time = time.time()
        
        try:
            # Connect to Redis using redis-py async
            redis = aioredis.from_url(
                self.redis_url,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            
            try:
                # PING command
                pong = await redis.ping()
                if not pong:
                    return HealthCheck(
                        "redis",
                        False,
                        "PING did not return PONG",
                        (time.time() - start_time) * 1000
                    )
                
                # Get Redis info for metadata
                info = await redis.info()
                memory_used = info.get('used_memory', 0)
                connected_clients = info.get('connected_clients', 0)
                
                response_time = (time.time() - start_time) * 1000
                
                return HealthCheck(
                    "redis",
                    True,
                    "Redis connection successful",
                    response_time,
                    {
                        "memory_used_bytes": memory_used,
                        "connected_clients": connected_clients
                    }
                )
            finally:
                await redis.close()
                
        except asyncio.TimeoutError:
            return HealthCheck(
                "redis",
                False,
                "Redis connection timeout (>5s)",
                5000.0
            )
        except Exception as e:
            return HealthCheck(
                "redis",
                False,
                f"Redis error: {str(e)}",
                (time.time() - start_time) * 1000
            )

    async def check_disk_space(self) -> HealthCheck:
        """
        Check available disk space.
        """
        try:
            disk_usage = psutil.disk_usage('/')
            free_percent = 100 - disk_usage.percent
            
            status = free_percent > 10  # Need at least 10% free
            
            return HealthCheck(
                "disk_space",
                status,
                f"{free_percent:.1f}% free" if status else f"Low disk space: {free_percent:.1f}% free",
                metadata={
                    "total_bytes": disk_usage.total,
                    "used_bytes": disk_usage.used,
                    "free_bytes": disk_usage.free,
                    "percent_used": disk_usage.percent
                }
            )
        except Exception as e:
            return HealthCheck(
                "disk_space",
                False,
                f"Failed to check disk space: {str(e)}"
            )

    async def check_memory(self) -> HealthCheck:
        """
        Check system memory usage.
        """
        try:
            memory = psutil.virtual_memory()
            
            status = memory.percent < 90  # Alert if >90% used
            
            return HealthCheck(
                "memory",
                status,
                f"{memory.percent:.1f}% used" if status else f"High memory usage: {memory.percent:.1f}%",
                metadata={
                    "total_bytes": memory.total,
                    "available_bytes": memory.available,
                    "percent_used": memory.percent,
                    "used_bytes": memory.used
                }
            )
        except Exception as e:
            return HealthCheck(
                "memory",
                False,
                f"Failed to check memory: {str(e)}"
            )

    async def check_cpu(self) -> HealthCheck:
        """
        Check CPU usage with a brief sampling period.
        """
        try:
            # Sample CPU for 0.1 seconds
            cpu_percent = psutil.cpu_percent(interval=0.1)
            
            status = cpu_percent < 90  # Alert if >90% used
            
            return HealthCheck(
                "cpu",
                status,
                f"{cpu_percent:.1f}% used" if status else f"High CPU usage: {cpu_percent:.1f}%",
                metadata={
                    "percent_used": cpu_percent,
                    "cpu_count": psutil.cpu_count()
                }
            )
        except Exception as e:
            return HealthCheck(
                "cpu",
                False,
                f"Failed to check CPU: {str(e)}"
            )

    def _determine_overall_status(self, checks: Dict[str, HealthCheck]) -> HealthStatus:
        """
        Determine overall health status based on individual checks.
        """
        # Check if any critical services are down
        critical_failures = [
            name for name in self.critical_services 
            if name in checks and not checks[name].status
        ]
        
        if critical_failures:
            return HealthStatus.UNHEALTHY
        
        # Count non-critical failures
        all_failures = [name for name, check in checks.items() if not check.status]
        
        if len(all_failures) > len(checks) * 0.3:  # >30% services down
            return HealthStatus.DEGRADED
        elif all_failures:
            return HealthStatus.DEGRADED
        else:
            return HealthStatus.HEALTHY

    async def get_health(self, detailed: bool = False) -> Dict[str, Any]:
        """
        Perform all health checks and return aggregated status.
        
        Args:
            detailed: Include detailed check information
            
        Returns:
            Health status dictionary with real, verified information
        """
        start_time = time.time()
        
        # Run all checks concurrently
        checks_coros = [
            self.check_database(),
            self.check_redis(),
            self.check_disk_space(),
            self.check_memory(),
            self.check_cpu(),
        ]
        
        # Execute all checks
        check_results = await asyncio.gather(*checks_coros, return_exceptions=True)
        
        # Process results
        checks = {}
        for result in check_results:
            if isinstance(result, HealthCheck):
                checks[result.name] = result
            elif isinstance(result, Exception):
                # Handle unexpected errors
                logger.error(f"Health check error: {result}")
                checks["unknown"] = HealthCheck(
                    "unknown",
                    False,
                    f"Unexpected error: {str(result)}"
                )
        
        # Determine overall status
        overall_status = self._determine_overall_status(checks)
        
        # Calculate total response time
        total_time = (time.time() - start_time) * 1000
        
        # Build response
        response = {
            "status": overall_status.value,
            "timestamp": datetime.utcnow().isoformat(),
            "response_time_ms": total_time,
            "checks": {
                name: {
                    "status": check.status,
                    "message": check.message,
                    "response_time_ms": check.response_time_ms
                }
                for name, check in checks.items()
            }
        }
        
        # Add detailed information if requested
        if detailed:
            response["detailed_checks"] = {
                name: check.to_dict()
                for name, check in checks.items()
            }
        
        # Store in history
        self._add_to_history(response)
        
        return response

    def _add_to_history(self, check_result: Dict[str, Any]):
        """Add check result to history for trend analysis."""
        self.check_history.append((datetime.utcnow(), check_result))
        
        # Trim history if too large
        if len(self.check_history) > self.max_history_size:
            self.check_history = self.check_history[-self.max_history_size:]

    async def get_health_trends(self) -> Dict[str, Any]:
        """
        Get health trends from historical data.
        """
        if not self.check_history:
            return {"message": "No historical data available"}
        
        # Analyze trends
        total_checks = len(self.check_history)
        healthy_count = sum(1 for _, check in self.check_history 
                          if check["status"] == HealthStatus.HEALTHY.value)
        degraded_count = sum(1 for _, check in self.check_history 
                           if check["status"] == HealthStatus.DEGRADED.value)
        unhealthy_count = sum(1 for _, check in self.check_history 
                            if check["status"] == HealthStatus.UNHEALTHY.value)
        
        # Calculate average response times
        response_times = [check["response_time_ms"] for _, check in self.check_history 
                         if "response_time_ms" in check]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        return {
            "total_checks": total_checks,
            "healthy_percentage": (healthy_count / total_checks) * 100,
            "degraded_percentage": (degraded_count / total_checks) * 100,
            "unhealthy_percentage": (unhealthy_count / total_checks) * 100,
            "average_response_time_ms": avg_response_time,
            "history_duration": {
                "start": self.check_history[0][0].isoformat(),
                "end": self.check_history[-1][0].isoformat()
            }
        }


# Singleton instance
_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Get or create the health checker singleton."""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker