"""
Redis health check implementation
"""
import asyncio
from typing import Optional, Dict, Any
from .base import HealthCheck
from ..models import HealthCheckResult, HealthStatus
from ...common.redis_utils import RedisClient, RedisConnectionPool


class RedisHealthCheck(HealthCheck):
    """Health check for Redis connectivity and performance"""
    
    def __init__(
        self,
        name: str = "redis",
        timeout: float = 3.0,
        connection_pool: Optional[RedisConnectionPool] = None
    ):
        super().__init__(name, timeout)
        self.connection_pool = connection_pool or RedisConnectionPool()
    
    async def check(self) -> HealthCheckResult:
        """Check Redis health"""
        try:
            pool = await self.connection_pool.get_pool()
            
            async with RedisClient(pool) as client:
                # Test basic connectivity with PING
                start_time = asyncio.get_event_loop().time()
                pong = await asyncio.wait_for(
                    client.client.ping(),
                    timeout=self.timeout
                )
                latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                
                if not pong:
                    return self.create_result(
                        status=HealthStatus.UNHEALTHY,
                        message="Redis PING failed",
                        details={"ping_response": pong}
                    )
                
                # Get Redis info
                info = await client.client.info()
                
                # Extract key metrics
                metrics = self._extract_metrics(info)
                
                # Determine health status based on metrics
                status, message = self._evaluate_health(metrics)
                
                return self.create_result(
                    status=status,
                    message=message,
                    details={
                        "latency_ms": round(latency_ms, 2),
                        "metrics": metrics,
                        "version": info.get('redis_version', 'unknown')
                    }
                )
                
        except asyncio.TimeoutError:
            return self.create_result(
                status=HealthStatus.UNHEALTHY,
                message=f"Redis connection timeout ({self.timeout}s)",
                details={"timeout": self.timeout}
            )
        except Exception as e:
            return self.create_result(
                status=HealthStatus.UNHEALTHY,
                message=f"Redis connection failed: {str(e)}",
                details={"error": str(e), "error_type": type(e).__name__}
            )
    
    def _extract_metrics(self, info: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant metrics from Redis INFO"""
        return {
            "connected_clients": info.get('connected_clients', 0),
            "used_memory_mb": round(info.get('used_memory', 0) / 1024 / 1024, 2),
            "used_memory_peak_mb": round(info.get('used_memory_peak', 0) / 1024 / 1024, 2),
            "memory_fragmentation_ratio": info.get('mem_fragmentation_ratio', 0),
            "total_commands_processed": info.get('total_commands_processed', 0),
            "instantaneous_ops_per_sec": info.get('instantaneous_ops_per_sec', 0),
            "keyspace_hits": info.get('keyspace_hits', 0),
            "keyspace_misses": info.get('keyspace_misses', 0),
            "evicted_keys": info.get('evicted_keys', 0),
            "rejected_connections": info.get('rejected_connections', 0)
        }
    
    def _evaluate_health(self, metrics: Dict[str, Any]) -> tuple[HealthStatus, str]:
        """Evaluate health status based on metrics"""
        issues = []
        
        # Check memory usage
        memory_usage = metrics.get('used_memory_mb', 0)
        memory_peak = metrics.get('used_memory_peak_mb', 0)
        if memory_peak > 0 and memory_usage / memory_peak > 0.9:
            issues.append("High memory usage (>90% of peak)")
        
        # Check memory fragmentation
        fragmentation = metrics.get('memory_fragmentation_ratio', 1)
        if fragmentation > 1.5:
            issues.append(f"High memory fragmentation ({fragmentation:.2f})")
        
        # Check evicted keys
        evicted = metrics.get('evicted_keys', 0)
        if evicted > 0:
            issues.append(f"Keys being evicted ({evicted})")
        
        # Check rejected connections
        rejected = metrics.get('rejected_connections', 0)
        if rejected > 0:
            issues.append(f"Connections rejected ({rejected})")
        
        # Determine status
        if not issues:
            return HealthStatus.HEALTHY, "Redis is healthy"
        elif len(issues) == 1:
            return HealthStatus.DEGRADED, f"Redis degraded: {issues[0]}"
        else:
            return HealthStatus.DEGRADED, f"Redis has multiple issues: {'; '.join(issues)}"