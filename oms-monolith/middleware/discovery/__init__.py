"""
Service discovery middleware package
"""

from .models import (
    ServiceInstance, ServiceEndpoint, ServiceStatus,
    LoadBalancerStrategy, ServiceRegistration
)
from .providers.base import DiscoveryProvider
from .providers.redis import RedisDiscoveryProvider
from .providers.dns import DnsDiscoveryProvider
from .balancer import LoadBalancer
from .health import HealthChecker
from .coordinator import DiscoveryCoordinator

__all__ = [
    'ServiceInstance',
    'ServiceEndpoint',
    'ServiceStatus',
    'LoadBalancerStrategy',
    'ServiceRegistration',
    'DiscoveryProvider',
    'RedisDiscoveryProvider',
    'DnsDiscoveryProvider',
    'LoadBalancer',
    'HealthChecker',
    'DiscoveryCoordinator',
]