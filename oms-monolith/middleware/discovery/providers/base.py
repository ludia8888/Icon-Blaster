"""
Base discovery provider interface
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from ..models import ServiceInstance, ServiceRegistration


class DiscoveryProvider(ABC):
    """Abstract base class for service discovery providers"""
    
    @abstractmethod
    async def register(self, registration: ServiceRegistration) -> ServiceInstance:
        """Register a service instance"""
        pass
    
    @abstractmethod
    async def deregister(self, service_name: str, instance_id: str) -> bool:
        """Deregister a service instance"""
        pass
    
    @abstractmethod
    async def get_instances(self, service_name: str) -> List[ServiceInstance]:
        """Get all instances of a service"""
        pass
    
    @abstractmethod
    async def get_instance(self, service_name: str, instance_id: str) -> Optional[ServiceInstance]:
        """Get specific service instance"""
        pass
    
    @abstractmethod
    async def update_heartbeat(self, service_name: str, instance_id: str) -> bool:
        """Update instance heartbeat"""
        pass
    
    @abstractmethod
    async def update_status(
        self, 
        service_name: str, 
        instance_id: str, 
        status: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update instance status"""
        pass
    
    @abstractmethod
    async def list_services(self) -> List[str]:
        """List all registered services"""
        pass
    
    @abstractmethod
    async def cleanup_expired(self) -> int:
        """Clean up expired instances, return count removed"""
        pass