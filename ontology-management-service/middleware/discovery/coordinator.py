"""
Service discovery coordinator - Facade for discovery components
"""
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime
import logging

from .models import (
    ServiceInstance, ServiceRegistration, ServiceStatus,
    LoadBalancerStrategy, ServiceDiscoveryConfig
)
from .providers.base import DiscoveryProvider
from .providers.redis import RedisDiscoveryProvider
from .providers.dns import DnsDiscoveryProvider
from .balancer import LoadBalancer
from .health import HealthChecker
from ..common.metrics import MetricsCollector

logger = logging.getLogger(__name__)


class DiscoveryCoordinator:
    """
    Facade for coordinating service discovery components
    """
    
    def __init__(self, config: Optional[ServiceDiscoveryConfig] = None):
        self.config = config or ServiceDiscoveryConfig()
        
        # Initialize provider
        self.provider = self._init_provider()
        
        # Components
        self.load_balancer = LoadBalancer(self.config.default_strategy)
        self.health_checker = HealthChecker(
            check_interval=self.config.health_check_interval,
            timeout=self.config.health_check_timeout,
            unhealthy_threshold=self.config.unhealthy_threshold,
            healthy_threshold=self.config.healthy_threshold
        )
        self.metrics = MetricsCollector("service_discovery")
        
        # State
        self._cleanup_task: Optional[asyncio.Task] = None
        self._is_running = False
    
    def _init_provider(self) -> DiscoveryProvider:
        """Initialize discovery provider based on config"""
        if self.config.provider_type == "redis":
            return RedisDiscoveryProvider(
                ttl_seconds=self.config.deregister_after_seconds
            )
        elif self.config.provider_type == "dns":
            domain = self.config.provider_config.get("domain", "local")
            return DnsDiscoveryProvider(domain)
        else:
            # Default to Redis
            return RedisDiscoveryProvider()
    
    async def start(self):
        """Start discovery coordinator"""
        if self._is_running:
            logger.warning("Discovery coordinator already running")
            return
        
        self._is_running = True
        
        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info("Started service discovery coordinator")
    
    async def stop(self):
        """Stop discovery coordinator"""
        self._is_running = False
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Stopped service discovery coordinator")
    
    async def register_service(
        self,
        name: str,
        host: str,
        port: int,
        **kwargs
    ) -> ServiceInstance:
        """Register a service instance"""
        registration = ServiceRegistration(
            name=name,
            host=host,
            port=port,
            protocol=kwargs.get("protocol", "http"),
            path=kwargs.get("path", "/"),
            version=kwargs.get("version"),
            metadata=kwargs.get("metadata", {}),
            ttl_seconds=kwargs.get("ttl_seconds", 30),
            weight=kwargs.get("weight", 100)
        )
        
        # Register with provider
        instance = await self.provider.register(registration)
        
        # Start health monitoring
        await self.health_checker.start_monitoring(
            instance,
            self.provider.update_status
        )
        
        # Record metrics
        self.metrics.increment_counter(
            "service_registrations_total",
            labels={"service": name}
        )
        
        logger.info(f"Registered service: {name} at {host}:{port}")
        
        return instance
    
    async def deregister_service(
        self,
        service_name: str,
        instance_id: str
    ) -> bool:
        """Deregister a service instance"""
        # Get instance first
        instance = await self.provider.get_instance(service_name, instance_id)
        
        if instance:
            # Stop health monitoring
            await self.health_checker.stop_monitoring(instance)
        
        # Deregister from provider
        success = await self.provider.deregister(service_name, instance_id)
        
        if success:
            self.metrics.increment_counter(
                "service_deregistrations_total",
                labels={"service": service_name}
            )
            logger.info(f"Deregistered service: {service_name}/{instance_id}")
        
        return success
    
    async def discover_service(
        self,
        endpoint: str,
        session_id: Optional[str] = None,
        client_ip: Optional[str] = None
    ) -> Optional[str]:
        """
        Discover and select a service instance for an endpoint
        Called by middleware coordinator
        """
        # Extract service name from endpoint
        service_name = self._extract_service_name(endpoint)
        
        # Get available instances
        instances = await self.provider.get_instances(service_name)
        
        if not instances:
            logger.warning(f"No instances found for service: {service_name}")
            return None
        
        # Select instance using load balancer
        instance = self.load_balancer.select_instance(
            instances,
            session_id,
            client_ip
        )
        
        if instance:
            # Record metrics
            self.metrics.increment_counter(
                "service_discoveries_total",
                labels={
                    "service": service_name,
                    "strategy": self.config.default_strategy.value
                }
            )
            
            return instance.endpoint.url
        
        return None
    
    async def get_service_instances(
        self,
        service_name: str
    ) -> List[ServiceInstance]:
        """Get all instances of a service"""
        return await self.provider.get_instances(service_name)
    
    async def update_heartbeat(
        self,
        service_name: str,
        instance_id: str
    ) -> bool:
        """Update service instance heartbeat"""
        success = await self.provider.update_heartbeat(service_name, instance_id)
        
        if success:
            self.metrics.increment_counter(
                "heartbeats_total",
                labels={"service": service_name}
            )
        
        return success
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get discovery statistics"""
        services = await self.provider.list_services()
        total_instances = 0
        healthy_instances = 0
        
        service_stats = {}
        for service in services:
            instances = await self.provider.get_instances(service)
            total_instances += len(instances)
            healthy_count = sum(1 for i in instances if i.is_healthy)
            healthy_instances += healthy_count
            
            service_stats[service] = {
                "total": len(instances),
                "healthy": healthy_count,
                "unhealthy": len(instances) - healthy_count
            }
        
        return {
            "provider_type": self.config.provider_type,
            "total_services": len(services),
            "total_instances": total_instances,
            "healthy_instances": healthy_instances,
            "unhealthy_instances": total_instances - healthy_instances,
            "services": service_stats,
            "load_balancer": self.load_balancer.get_stats(),
            "health_checker": self.health_checker.get_stats()
        }
    
    async def _cleanup_loop(self):
        """Background cleanup of expired instances"""
        while self._is_running:
            try:
                # Wait for cleanup interval
                await asyncio.sleep(self.config.cleanup_interval)
                
                # Cleanup expired instances
                removed = await self.provider.cleanup_expired()
                
                if removed > 0:
                    logger.info(f"Cleaned up {removed} expired instances")
                    
                    self.metrics.increment_counter(
                        "expired_instances_cleaned_total",
                        value=removed
                    )
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
    
    def _extract_service_name(self, endpoint: str) -> str:
        """Extract service name from endpoint"""
        # Simple extraction - get first path segment
        # e.g., /users/123 -> users
        parts = endpoint.strip('/').split('/')
        return parts[0] if parts else "default"
    
    def configure_load_balancer(
        self,
        strategy: LoadBalancerStrategy,
        **kwargs
    ):
        """Configure load balancer settings"""
        self.load_balancer.strategy = strategy
        self.config.default_strategy = strategy
        
        if kwargs.get("sticky_sessions") is not None:
            self.config.sticky_sessions = kwargs["sticky_sessions"]
        
        logger.info(f"Configured load balancer: {strategy.value}")