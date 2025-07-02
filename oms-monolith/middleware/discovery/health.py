"""
Health checker for service instances
"""
import asyncio
import httpx
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import logging

from .models import ServiceInstance, ServiceStatus
from database.clients.unified_http_client import UnifiedHTTPClient, create_basic_client

logger = logging.getLogger(__name__)


class HealthChecker:
    """Health checker for service instances"""
    
    def __init__(
        self,
        check_interval: int = 10,
        timeout: int = 5,
        unhealthy_threshold: int = 3,
        healthy_threshold: int = 2
    ):
        self.check_interval = check_interval
        self.timeout = timeout
        self.unhealthy_threshold = unhealthy_threshold
        self.healthy_threshold = healthy_threshold
        
        self.logger = logger
        self._failure_counts: Dict[str, int] = {}
        self._success_counts: Dict[str, int] = {}
        self._check_tasks: Dict[str, asyncio.Task] = {}
        self._http_client = create_basic_client(timeout=timeout)
    
    async def start_monitoring(
        self,
        instance: ServiceInstance,
        update_callback: callable
    ):
        """Start health monitoring for an instance"""
        key = f"{instance.name}/{instance.id}"
        
        # Cancel existing task if any
        if key in self._check_tasks:
            self._check_tasks[key].cancel()
        
        # Start new monitoring task
        task = asyncio.create_task(
            self._monitor_instance(instance, update_callback)
        )
        self._check_tasks[key] = task
    
    async def stop_monitoring(self, instance: ServiceInstance):
        """Stop health monitoring for an instance"""
        key = f"{instance.name}/{instance.id}"
        
        if key in self._check_tasks:
            self._check_tasks[key].cancel()
            del self._check_tasks[key]
        
        # Clean up counts
        self._failure_counts.pop(key, None)
        self._success_counts.pop(key, None)
    
    async def check_health(self, instance: ServiceInstance) -> ServiceStatus:
        """Perform single health check"""
        health_endpoint = f"{instance.endpoint.url}/health"
        
        try:
            start_time = asyncio.get_event_loop().time()
            response = await self._http_client.get(health_endpoint)
            response_time = (asyncio.get_event_loop().time() - start_time) * 1000
            
            # Update response time metric
            instance.response_time_ms = response_time
            
            if response.status_code == 200:
                # Try to parse health response
                try:
                    data = response.json()
                    if isinstance(data, dict) and data.get("status") == "healthy":
                        return ServiceStatus.HEALTHY
                except:
                    # If not JSON or no status field, just check status code
                    pass
                
                return ServiceStatus.HEALTHY
            else:
                self.logger.warning(
                    f"Health check failed for {instance.id}: "
                    f"HTTP {response.status_code}"
                )
                return ServiceStatus.UNHEALTHY
                
        except Exception as e:
            # UnifiedHTTPClient handles timeouts and other exceptions uniformly
            if "timeout" in str(e).lower():
                self.logger.warning(
                    f"Health check timeout for {instance.id}"
                )
            else:
                self.logger.error(
                    f"Health check error for {instance.id}: {e}"
                )
            return ServiceStatus.UNHEALTHY
    
    async def _monitor_instance(
        self,
        instance: ServiceInstance,
        update_callback: callable
    ):
        """Monitor instance health continuously"""
        key = f"{instance.name}/{instance.id}"
        
        while True:
            try:
                # Perform health check
                status = await self.check_health(instance)
                
                # Update counts
                if status == ServiceStatus.HEALTHY:
                    self._success_counts[key] = self._success_counts.get(key, 0) + 1
                    self._failure_counts[key] = 0
                else:
                    self._failure_counts[key] = self._failure_counts.get(key, 0) + 1
                    self._success_counts[key] = 0
                
                # Determine if status should change
                new_status = self._determine_status(key, instance.status, status)
                
                if new_status != instance.status:
                    self.logger.info(
                        f"Instance {instance.id} status changed: "
                        f"{instance.status.value} -> {new_status.value}"
                    )
                    
                    # Update instance status
                    instance.status = new_status
                    
                    # Call update callback
                    await update_callback(
                        instance.name,
                        instance.id,
                        new_status.value,
                        {
                            "response_time_ms": instance.response_time_ms,
                            "last_check": datetime.utcnow().isoformat()
                        }
                    )
                
                # Wait for next check
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(
                    f"Error monitoring instance {instance.id}: {e}"
                )
                await asyncio.sleep(self.check_interval)
    
    def _determine_status(
        self,
        key: str,
        current_status: ServiceStatus,
        check_result: ServiceStatus
    ) -> ServiceStatus:
        """Determine if status should change based on thresholds"""
        failures = self._failure_counts.get(key, 0)
        successes = self._success_counts.get(key, 0)
        
        # If currently healthy, need multiple failures to mark unhealthy
        if current_status == ServiceStatus.HEALTHY:
            if failures >= self.unhealthy_threshold:
                return ServiceStatus.UNHEALTHY
            return current_status
        
        # If currently unhealthy, need multiple successes to mark healthy
        elif current_status == ServiceStatus.UNHEALTHY:
            if successes >= self.healthy_threshold:
                return ServiceStatus.HEALTHY
            return current_status
        
        # For other states, use single check result
        else:
            return check_result
    
    def get_stats(self) -> Dict[str, Any]:
        """Get health checker statistics"""
        return {
            "monitored_instances": len(self._check_tasks),
            "failure_counts": dict(self._failure_counts),
            "success_counts": dict(self._success_counts),
            "config": {
                "check_interval": self.check_interval,
                "timeout": self.timeout,
                "unhealthy_threshold": self.unhealthy_threshold,
                "healthy_threshold": self.healthy_threshold
            }
        }