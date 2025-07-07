"""
DNS-based service discovery provider
"""
import socket
import asyncio
from typing import List, Optional, Dict, Any
import logging

from .base import DiscoveryProvider
from ..models import ServiceInstance, ServiceRegistration, ServiceStatus, ServiceEndpoint

logger = logging.getLogger(__name__)


class DnsDiscoveryProvider(DiscoveryProvider):
    """
    Service discovery provider using DNS (SRV records)
    Note: This is read-only - registration requires DNS server configuration
    """
    
    def __init__(self, domain: str = "local"):
        self.domain = domain
        self.logger = logger
        self._cache: Dict[str, List[ServiceInstance]] = {}
        self._cache_ttl = 60  # seconds
    
    async def register(self, registration: ServiceRegistration) -> ServiceInstance:
        """DNS registration not supported - requires DNS server configuration"""
        raise NotImplementedError(
            "DNS-based discovery is read-only. "
            "Service registration must be done through DNS server configuration."
        )
    
    async def deregister(self, service_name: str, instance_id: str) -> bool:
        """DNS deregistration not supported"""
        raise NotImplementedError(
            "DNS-based discovery is read-only. "
            "Service deregistration must be done through DNS server configuration."
        )
    
    async def get_instances(self, service_name: str) -> List[ServiceInstance]:
        """Get service instances from DNS SRV records"""
        # Check cache first
        if service_name in self._cache:
            return self._cache[service_name]
        
        instances = []
        
        try:
            # Query SRV records
            srv_name = f"_{service_name}._tcp.{self.domain}"
            
            # Run DNS lookup in executor to avoid blocking
            loop = asyncio.get_event_loop()
            srv_records = await loop.run_in_executor(
                None,
                self._resolve_srv,
                srv_name
            )
            
            # Convert SRV records to ServiceInstances
            for priority, weight, port, target in srv_records:
                # Resolve A record for target
                try:
                    ip = socket.gethostbyname(target)
                    
                    endpoint = ServiceEndpoint(
                        host=ip,
                        port=port,
                        protocol="http"
                    )
                    
                    instance = ServiceInstance(
                        id=f"{service_name}-{target}-{port}",
                        name=service_name,
                        endpoint=endpoint,
                        status=ServiceStatus.UNKNOWN,  # DNS doesn't provide health
                        metadata={
                            "priority": priority,
                            "weight": weight,
                            "target": target
                        },
                        weight=weight
                    )
                    
                    instances.append(instance)
                    
                except socket.gaierror:
                    self.logger.warning(f"Failed to resolve {target}")
            
            # Cache results
            self._cache[service_name] = instances
            
            # Clear cache after TTL
            asyncio.create_task(self._clear_cache_after(service_name))
            
        except Exception as e:
            self.logger.error(f"DNS lookup failed for {service_name}: {e}")
        
        return instances
    
    async def get_instance(
        self, 
        service_name: str, 
        instance_id: str
    ) -> Optional[ServiceInstance]:
        """Get specific instance"""
        instances = await self.get_instances(service_name)
        
        for instance in instances:
            if instance.id == instance_id:
                return instance
        
        return None
    
    async def update_heartbeat(
        self, 
        service_name: str, 
        instance_id: str
    ) -> bool:
        """Heartbeat not supported for DNS discovery"""
        return True  # Always return success
    
    async def update_status(
        self,
        service_name: str,
        instance_id: str,
        status: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Status update not supported for DNS discovery"""
        return True  # Always return success
    
    async def list_services(self) -> List[str]:
        """List services from cache"""
        return list(self._cache.keys())
    
    async def cleanup_expired(self) -> int:
        """No cleanup needed for DNS discovery"""
        return 0
    
    def _resolve_srv(self, srv_name: str) -> List[tuple]:
        """Resolve SRV records"""
        import dns.resolver
        
        results = []
        try:
            answers = dns.resolver.resolve(srv_name, 'SRV')
            
            for rdata in answers:
                results.append((
                    rdata.priority,
                    rdata.weight,
                    rdata.port,
                    str(rdata.target).rstrip('.')
                ))
        except Exception:
            # If dnspython is not available, try basic socket approach
            # This is limited and won't get SRV record details
            try:
                # Fallback to A record lookup
                service_name = srv_name.split('.')[0].strip('_').split('_')[0]
                hosts = socket.gethostbyname_ex(f"{service_name}.{self.domain}")[2]
                
                # Create fake SRV records with default values
                for host in hosts:
                    results.append((10, 100, 80, host))
            except:
                pass
        
        return results
    
    async def _clear_cache_after(self, service_name: str):
        """Clear cache entry after TTL"""
        await asyncio.sleep(self._cache_ttl)
        self._cache.pop(service_name, None)