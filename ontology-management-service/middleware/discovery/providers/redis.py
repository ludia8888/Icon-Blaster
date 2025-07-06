"""
Redis-based service discovery provider
"""
import json
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from .base import DiscoveryProvider
from ..models import ServiceInstance, ServiceRegistration, ServiceStatus
from ...common.redis_utils import RedisClient, RedisKeyPatterns

logger = logging.getLogger(__name__)


class RedisDiscoveryProvider(DiscoveryProvider):
    """Service discovery provider using Redis"""
    
    def __init__(self, ttl_seconds: int = 30):
        self.ttl_seconds = ttl_seconds
        self.logger = logger
    
    async def register(self, registration: ServiceRegistration) -> ServiceInstance:
        """Register a service instance"""
        instance_id = f"{registration.name}-{uuid.uuid4().hex[:8]}"
        instance = registration.to_instance(instance_id)
        instance.status = ServiceStatus.HEALTHY
        
        async with RedisClient() as client:
            # Store instance data
            instance_key = RedisKeyPatterns.SERVICE_INSTANCE.format(
                service_name=registration.name,
                instance_id=instance_id
            )
            
            await client.set_json(
                instance_key,
                instance.to_dict(),
                expire=timedelta(seconds=registration.ttl_seconds or self.ttl_seconds)
            )
            
            # Add to service registry set
            registry_key = RedisKeyPatterns.SERVICE_REGISTRY.format(
                service_name=registration.name
            )
            await client.client.sadd(registry_key, instance_id)
            
            # Set TTL on registry key
            await client.client.expire(
                registry_key,
                registration.ttl_seconds * 2
            )
            
            self.logger.info(
                f"Registered service instance: {registration.name}/{instance_id}"
            )
        
        return instance
    
    async def deregister(self, service_name: str, instance_id: str) -> bool:
        """Deregister a service instance"""
        async with RedisClient() as client:
            # Remove instance data
            instance_key = RedisKeyPatterns.SERVICE_INSTANCE.format(
                service_name=service_name,
                instance_id=instance_id
            )
            deleted = await client.client.delete(instance_key)
            
            # Remove from registry set
            registry_key = RedisKeyPatterns.SERVICE_REGISTRY.format(
                service_name=service_name
            )
            await client.client.srem(registry_key, instance_id)
            
            # Remove health status
            health_key = RedisKeyPatterns.SERVICE_HEALTH.format(
                service_name=service_name,
                instance_id=instance_id
            )
            await client.client.delete(health_key)
            
            self.logger.info(
                f"Deregistered service instance: {service_name}/{instance_id}"
            )
            
            return bool(deleted)
    
    async def get_instances(self, service_name: str) -> List[ServiceInstance]:
        """Get all instances of a service"""
        instances = []
        
        async with RedisClient() as client:
            # Get instance IDs from registry
            registry_key = RedisKeyPatterns.SERVICE_REGISTRY.format(
                service_name=service_name
            )
            instance_ids = await client.client.smembers(registry_key)
            
            # Get instance data for each ID
            for instance_id in instance_ids:
                instance = await self._get_instance(
                    client, service_name, instance_id
                )
                if instance:
                    instances.append(instance)
        
        return instances
    
    async def get_instance(
        self, 
        service_name: str, 
        instance_id: str
    ) -> Optional[ServiceInstance]:
        """Get specific service instance"""
        async with RedisClient() as client:
            return await self._get_instance(client, service_name, instance_id)
    
    async def update_heartbeat(
        self, 
        service_name: str, 
        instance_id: str
    ) -> bool:
        """Update instance heartbeat"""
        async with RedisClient() as client:
            instance = await self._get_instance(
                client, service_name, instance_id
            )
            
            if not instance:
                return False
            
            # Update heartbeat
            instance.update_heartbeat()
            
            # Save updated instance
            instance_key = RedisKeyPatterns.SERVICE_INSTANCE.format(
                service_name=service_name,
                instance_id=instance_id
            )
            
            await client.set_json(
                instance_key,
                instance.to_dict(),
                expire=timedelta(seconds=self.ttl_seconds)
            )
            
            # Update health status
            health_key = RedisKeyPatterns.SERVICE_HEALTH.format(
                service_name=service_name,
                instance_id=instance_id
            )
            await client.set_json(
                health_key,
                {
                    "status": instance.status.value,
                    "last_heartbeat": instance.last_heartbeat.isoformat()
                },
                expire=timedelta(seconds=self.ttl_seconds)
            )
            
            return True
    
    async def update_status(
        self,
        service_name: str,
        instance_id: str,
        status: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update instance status"""
        async with RedisClient() as client:
            instance = await self._get_instance(
                client, service_name, instance_id
            )
            
            if not instance:
                return False
            
            # Update status
            instance.status = ServiceStatus(status)
            if metadata:
                instance.metadata.update(metadata)
            
            # Save updated instance
            instance_key = RedisKeyPatterns.SERVICE_INSTANCE.format(
                service_name=service_name,
                instance_id=instance_id
            )
            
            await client.set_json(
                instance_key,
                instance.to_dict(),
                expire=timedelta(seconds=self.ttl_seconds)
            )
            
            return True
    
    async def list_services(self) -> List[str]:
        """List all registered services"""
        services = set()
        
        async with RedisClient() as client:
            # Scan for service registry keys
            cursor = 0
            pattern = "discovery:services:*"
            
            while True:
                cursor, keys = await client.client.scan(
                    cursor, 
                    match=pattern,
                    count=100
                )
                
                for key in keys:
                    # Extract service name from key
                    parts = key.split(":")
                    if len(parts) >= 3:
                        services.add(parts[2])
                
                if cursor == 0:
                    break
        
        return list(services)
    
    async def cleanup_expired(self) -> int:
        """Clean up expired instances"""
        removed_count = 0
        
        async with RedisClient() as client:
            services = await self.list_services()
            
            for service_name in services:
                # Get all instance IDs
                registry_key = RedisKeyPatterns.SERVICE_REGISTRY.format(
                    service_name=service_name
                )
                instance_ids = await client.client.smembers(registry_key)
                
                # Check each instance
                for instance_id in instance_ids:
                    instance_key = RedisKeyPatterns.SERVICE_INSTANCE.format(
                        service_name=service_name,
                        instance_id=instance_id
                    )
                    
                    # If instance key doesn't exist, remove from registry
                    if not await client.client.exists(instance_key):
                        await client.client.srem(registry_key, instance_id)
                        removed_count += 1
                        
                        self.logger.info(
                            f"Cleaned up expired instance: "
                            f"{service_name}/{instance_id}"
                        )
        
        return removed_count
    
    async def _get_instance(
        self,
        client: RedisClient,
        service_name: str,
        instance_id: str
    ) -> Optional[ServiceInstance]:
        """Get instance from Redis"""
        instance_key = RedisKeyPatterns.SERVICE_INSTANCE.format(
            service_name=service_name,
            instance_id=instance_id
        )
        
        data = await client.get_json(instance_key)
        if data:
            return ServiceInstance.from_dict(data)
        
        return None