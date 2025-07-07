"""
Health monitoring coordinator - Facade for health components
"""
import asyncio
from typing import Dict, List, Optional, Any, Set
from datetime import datetime, timedelta
import logging

from .models import (
    HealthStatus, HealthState, ComponentHealth, 
    HealthCheckResult, HealthMetrics, HealthAlert
)
from .checks.base import HealthCheck
from .monitor import HealthMonitor
from .dependency import DependencyGraph
from ..common.redis_utils import RedisClient, RedisKeyPatterns
from ..common.metrics import MetricsCollector

logger = logging.getLogger(__name__)


class HealthCoordinator:
    """
    Facade for coordinating health monitoring components
    """
    
    def __init__(
        self,
        component_name: str = "system",
        check_interval: int = 30,
        alert_threshold: int = 3
    ):
        self.component_name = component_name
        self.check_interval = check_interval
        self.alert_threshold = alert_threshold
        
        # Components
        self.monitor = HealthMonitor(component_name)
        self.dependency_graph = DependencyGraph()
        self.metrics_collector = MetricsCollector(f"health_{component_name}")
        
        # State
        self._health_checks: Dict[str, HealthCheck] = {}
        self._last_check_results: Dict[str, HealthCheckResult] = {}
        self._active_alerts: Dict[str, HealthAlert] = {}
        self._failure_counts: Dict[str, int] = {}
        self._is_running = False
        self._check_task: Optional[asyncio.Task] = None
    
    def register_check(self, check: HealthCheck):
        """Register a health check"""
        self._health_checks[check.name] = check
        logger.info(f"Registered health check: {check.name}")
    
    def register_dependency(self, component: str, depends_on: str):
        """Register component dependency"""
        self.dependency_graph.add_dependency(component, depends_on)
    
    async def start(self):
        """Start health monitoring"""
        if self._is_running:
            logger.warning("Health coordinator already running")
            return
        
        self._is_running = True
        self._check_task = asyncio.create_task(self._health_check_loop())
        logger.info(f"Started health coordinator for {self.component_name}")
    
    async def stop(self):
        """Stop health monitoring"""
        self._is_running = False
        if self._check_task:
            self._check_task.cancel()
            try:
                await self._check_task
            except asyncio.CancelledError:
                pass
        logger.info(f"Stopped health coordinator for {self.component_name}")
    
    async def check_health(self) -> ComponentHealth:
        """Perform health check and return current status"""
        # Run all health checks in parallel
        check_tasks = [
            check.execute() 
            for check in self._health_checks.values()
        ]
        
        results = await asyncio.gather(*check_tasks, return_exceptions=True)
        
        # Process results
        check_results = []
        for i, result in enumerate(results):
            check_name = list(self._health_checks.keys())[i]
            
            if isinstance(result, Exception):
                check_result = HealthCheckResult(
                    name=check_name,
                    status=HealthStatus.UNHEALTHY,
                    message=f"Check failed: {str(result)}",
                    details={"error": str(result)}
                )
            else:
                check_result = result
            
            check_results.append(check_result)
            self._last_check_results[check_name] = check_result
            
            # Update metrics
            self._update_metrics(check_result)
            
            # Handle failures
            await self._handle_check_result(check_result)
        
        # Determine overall status
        overall_status = self._determine_overall_status(check_results)
        
        # Check dependencies
        dependency_status = await self._check_dependencies()
        
        # Create component health
        component_health = ComponentHealth(
            component_name=self.component_name,
            status=overall_status,
            state=HealthState.RUNNING if self._is_running else HealthState.STOPPED,
            checks=check_results,
            dependencies=dependency_status,
            metadata={
                "total_checks": len(check_results),
                "failed_checks": len([r for r in check_results if r.is_unhealthy]),
                "degraded_checks": len([r for r in check_results if r.is_degraded]),
                "active_alerts": len(self._active_alerts)
            },
            uptime_seconds=self.monitor.get_uptime()
        )
        
        # Store in Redis
        await self._store_health_status(component_health)
        
        return component_health
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get health monitoring statistics"""
        metrics = HealthMetrics()
        metrics.update(list(self._last_check_results.values()))
        
        return {
            "component": self.component_name,
            "is_running": self._is_running,
            "total_checks": len(self._health_checks),
            "last_check_results": {
                name: {
                    "status": result.status.value,
                    "message": result.message,
                    "timestamp": result.timestamp.isoformat()
                }
                for name, result in self._last_check_results.items()
            },
            "metrics": {
                "health_percentage": metrics.health_percentage,
                "total_checks": metrics.total_checks,
                "healthy_checks": metrics.healthy_checks,
                "degraded_checks": metrics.degraded_checks,
                "unhealthy_checks": metrics.unhealthy_checks,
                "average_check_duration_ms": metrics.average_check_duration_ms
            },
            "active_alerts": len(self._active_alerts),
            "failure_counts": dict(self._failure_counts)
        }
    
    async def check_system_health(self) -> Dict[str, Any]:
        """Check overall system health (called by middleware coordinator)"""
        component_health = await self.check_health()
        
        return {
            "healthy": component_health.is_healthy,
            "status": component_health.status.value,
            "component": component_health.component_name,
            "failed_checks": [
                {"name": check.name, "message": check.message}
                for check in component_health.failed_checks
            ],
            "degraded_checks": [
                {"name": check.name, "message": check.message}
                for check in component_health.degraded_checks
            ]
        }
    
    async def _health_check_loop(self):
        """Background health check loop"""
        while self._is_running:
            try:
                await self.check_health()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in health check loop: {str(e)}")
                await asyncio.sleep(self.check_interval)
    
    def _determine_overall_status(
        self, 
        results: List[HealthCheckResult]
    ) -> HealthStatus:
        """Determine overall health status from check results"""
        if not results:
            return HealthStatus.UNKNOWN
        
        # If any check is unhealthy, overall is unhealthy
        if any(r.is_unhealthy for r in results):
            return HealthStatus.UNHEALTHY
        
        # If any check is degraded, overall is degraded
        if any(r.is_degraded for r in results):
            return HealthStatus.DEGRADED
        
        # All checks are healthy
        return HealthStatus.HEALTHY
    
    async def _check_dependencies(self) -> Dict[str, HealthStatus]:
        """Check health of dependencies"""
        dependencies = self.dependency_graph.get_dependencies(self.component_name)
        dependency_status = {}
        
        for dep in dependencies:
            # Get dependency health from Redis
            async with RedisClient() as client:
                key = RedisKeyPatterns.HEALTH_STATUS.format(component=dep)
                health_data = await client.get_json(key)
                
                if health_data:
                    dependency_status[dep] = HealthStatus(health_data.get("status", "unknown"))
                else:
                    dependency_status[dep] = HealthStatus.UNKNOWN
        
        return dependency_status
    
    async def _handle_check_result(self, result: HealthCheckResult):
        """Handle individual check result"""
        if result.is_unhealthy:
            # Increment failure count
            self._failure_counts[result.name] = self._failure_counts.get(result.name, 0) + 1
            
            # Create alert if threshold exceeded
            if self._failure_counts[result.name] >= self.alert_threshold:
                await self._create_alert(result)
        else:
            # Reset failure count and resolve alerts
            self._failure_counts.pop(result.name, None)
            await self._resolve_alert(result.name)
    
    async def _create_alert(self, result: HealthCheckResult):
        """Create health alert"""
        alert_key = f"{self.component_name}:{result.name}"
        
        if alert_key not in self._active_alerts:
            alert = HealthAlert(
                component_name=self.component_name,
                alert_type="health_check_failure",
                severity="high" if result.is_unhealthy else "medium",
                message=f"Health check '{result.name}' failed: {result.message}",
                details={
                    "check_name": result.name,
                    "status": result.status.value,
                    "failure_count": self._failure_counts.get(result.name, 0),
                    "check_details": result.details
                }
            )
            
            self._active_alerts[alert_key] = alert
            logger.error(f"Health alert created: {alert.message}")
            
            # TODO: Send alert to notification system
    
    async def _resolve_alert(self, check_name: str):
        """Resolve health alert"""
        alert_key = f"{self.component_name}:{check_name}"
        
        if alert_key in self._active_alerts:
            alert = self._active_alerts[alert_key]
            alert.resolve()
            del self._active_alerts[alert_key]
            logger.info(f"Health alert resolved: {check_name}")
    
    def _update_metrics(self, result: HealthCheckResult):
        """Update metrics for health check result"""
        # Record check duration
        self.metrics_collector.observe_histogram(
            "health_check_duration_seconds",
            result.duration_ms / 1000,
            {"check": result.name, "status": result.status.value}
        )
        
        # Increment status counter
        self.metrics_collector.increment_counter(
            f"health_check_{result.status.value}_total",
            labels={"check": result.name}
        )
    
    async def _store_health_status(self, health: ComponentHealth):
        """Store health status in Redis"""
        async with RedisClient() as client:
            key = RedisKeyPatterns.HEALTH_STATUS.format(component=self.component_name)
            await client.set_json(
                key,
                health.to_dict(),
                expire=timedelta(seconds=self.check_interval * 2)
            )