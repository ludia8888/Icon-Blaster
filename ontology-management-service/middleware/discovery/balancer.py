"""
Load balancer implementation for service discovery
"""
import random
import hashlib
from typing import List, Optional, Dict, Any
from collections import defaultdict
import logging

from .models import ServiceInstance, LoadBalancerStrategy

logger = logging.getLogger(__name__)


class LoadBalancer:
    """Load balancer for distributing requests across service instances"""
    
    def __init__(self, strategy: LoadBalancerStrategy = LoadBalancerStrategy.ROUND_ROBIN):
        self.strategy = strategy
        self.logger = logger
        
        # Round-robin state
        self._rr_counters: Dict[str, int] = defaultdict(int)
        
        # Least connections tracking
        self._connections: Dict[str, int] = defaultdict(int)
        
        # Sticky session mapping
        self._session_mapping: Dict[str, str] = {}
    
    def select_instance(
        self,
        instances: List[ServiceInstance],
        session_id: Optional[str] = None,
        client_ip: Optional[str] = None
    ) -> Optional[ServiceInstance]:
        """Select an instance based on load balancing strategy"""
        if not instances:
            return None
        
        # Filter healthy instances
        healthy_instances = [i for i in instances if i.is_healthy]
        if not healthy_instances:
            self.logger.warning("No healthy instances available")
            return None
        
        # Check sticky session
        if session_id and session_id in self._session_mapping:
            instance_id = self._session_mapping[session_id]
            for instance in healthy_instances:
                if instance.id == instance_id:
                    return instance
        
        # Select based on strategy
        if self.strategy == LoadBalancerStrategy.ROUND_ROBIN:
            instance = self._round_robin(healthy_instances)
        elif self.strategy == LoadBalancerStrategy.WEIGHTED_ROUND_ROBIN:
            instance = self._weighted_round_robin(healthy_instances)
        elif self.strategy == LoadBalancerStrategy.LEAST_CONNECTIONS:
            instance = self._least_connections(healthy_instances)
        elif self.strategy == LoadBalancerStrategy.RANDOM:
            instance = self._random(healthy_instances)
        elif self.strategy == LoadBalancerStrategy.IP_HASH:
            instance = self._ip_hash(healthy_instances, client_ip)
        elif self.strategy == LoadBalancerStrategy.LEAST_RESPONSE_TIME:
            instance = self._least_response_time(healthy_instances)
        else:
            instance = self._round_robin(healthy_instances)
        
        # Update sticky session if needed
        if session_id and instance:
            self._session_mapping[session_id] = instance.id
        
        return instance
    
    def _round_robin(self, instances: List[ServiceInstance]) -> ServiceInstance:
        """Round-robin selection"""
        if not instances:
            return None
        
        # Get service name from first instance
        service_name = instances[0].name
        
        # Get and increment counter
        index = self._rr_counters[service_name] % len(instances)
        self._rr_counters[service_name] += 1
        
        return instances[index]
    
    def _weighted_round_robin(
        self, 
        instances: List[ServiceInstance]
    ) -> ServiceInstance:
        """Weighted round-robin selection"""
        if not instances:
            return None
        
        # Build weighted list
        weighted_instances = []
        for instance in instances:
            # Add instance multiple times based on weight
            weight = max(1, instance.weight)
            weighted_instances.extend([instance] * weight)
        
        # Use regular round-robin on weighted list
        service_name = instances[0].name
        index = self._rr_counters[f"{service_name}_weighted"] % len(weighted_instances)
        self._rr_counters[f"{service_name}_weighted"] += 1
        
        return weighted_instances[index]
    
    def _least_connections(
        self, 
        instances: List[ServiceInstance]
    ) -> ServiceInstance:
        """Select instance with least connections"""
        if not instances:
            return None
        
        # Find instance with minimum connections
        min_connections = float('inf')
        selected = None
        
        for instance in instances:
            connections = instance.active_connections
            if connections < min_connections:
                min_connections = connections
                selected = instance
        
        return selected or instances[0]
    
    def _random(self, instances: List[ServiceInstance]) -> ServiceInstance:
        """Random selection"""
        return random.choice(instances) if instances else None
    
    def _ip_hash(
        self, 
        instances: List[ServiceInstance],
        client_ip: Optional[str]
    ) -> ServiceInstance:
        """Consistent hashing based on client IP"""
        if not instances:
            return None
        
        if not client_ip:
            # Fallback to round-robin if no IP
            return self._round_robin(instances)
        
        # Hash the IP
        hash_value = int(hashlib.md5(client_ip.encode()).hexdigest(), 16)
        
        # Select instance based on hash
        index = hash_value % len(instances)
        return instances[index]
    
    def _least_response_time(
        self, 
        instances: List[ServiceInstance]
    ) -> ServiceInstance:
        """Select instance with lowest response time"""
        if not instances:
            return None
        
        # Find instance with minimum response time
        min_response_time = float('inf')
        selected = None
        
        for instance in instances:
            if instance.response_time_ms < min_response_time:
                min_response_time = instance.response_time_ms
                selected = instance
        
        return selected or instances[0]
    
    def update_instance_metrics(
        self,
        instance_id: str,
        connections: Optional[int] = None,
        response_time_ms: Optional[float] = None,
        error_occurred: bool = False
    ):
        """Update instance metrics for load balancing decisions"""
        # This would typically update the instance in the discovery provider
        # For now, we just track connections locally
        if connections is not None:
            self._connections[instance_id] = connections
    
    def clear_session(self, session_id: str):
        """Clear sticky session mapping"""
        self._session_mapping.pop(session_id, None)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get load balancer statistics"""
        return {
            "strategy": self.strategy.value,
            "round_robin_counters": dict(self._rr_counters),
            "active_sessions": len(self._session_mapping),
            "tracked_connections": dict(self._connections)
        }