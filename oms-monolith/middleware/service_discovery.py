"""
Enterprise-grade service discovery and registration mechanism.

Features:
- Service registration with health checks
- Dynamic service discovery
- Load balancing strategies (round-robin, weighted, least connections)
- Service versioning
- Circuit breaker integration
- Health check monitoring
- Service metadata and tags
- DNS and HTTP-based discovery
"""

import asyncio
import socket
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable, Tuple
import aiohttp
import dns.resolver
import redis.asyncio as redis
from collections import defaultdict
import json
import random
import logging
from urllib.parse import urlparse
import hashlib

logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    """Service status."""
    UP = "up"
    DOWN = "down"
    STARTING = "starting"
    STOPPING = "stopping"
    OUT_OF_SERVICE = "out_of_service"


class LoadBalancingStrategy(Enum):
    """Load balancing strategies."""
    ROUND_ROBIN = "round_robin"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    LEAST_CONNECTIONS = "least_connections"
    RANDOM = "random"
    IP_HASH = "ip_hash"
    LEAST_RESPONSE_TIME = "least_response_time"


@dataclass
class ServiceEndpoint:
    """Service endpoint information."""
    host: str
    port: int
    protocol: str = "http"
    weight: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def url(self) -> str:
        """Get full URL for endpoint."""
        return f"{self.protocol}://{self.host}:{self.port}"
    
    def __hash__(self):
        return hash((self.host, self.port))


@dataclass
class ServiceInstance:
    """Service instance information."""
    id: str
    name: str
    version: str
    endpoints: List[ServiceEndpoint]
    status: ServiceStatus = ServiceStatus.UP
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: Set[str] = field(default_factory=set)
    registered_at: datetime = field(default_factory=datetime.now)
    last_heartbeat: datetime = field(default_factory=datetime.now)
    health_check_url: Optional[str] = None
    
    @property
    def is_healthy(self) -> bool:
        """Check if service is healthy."""
        return self.status == ServiceStatus.UP
    
    def matches_criteria(self, version: Optional[str] = None, tags: Optional[Set[str]] = None) -> bool:
        """Check if instance matches selection criteria."""
        if version and self.version != version:
            return False
        if tags and not tags.issubset(self.tags):
            return False
        return True


@dataclass
class ServiceHealth:
    """Service health information."""
    instance_id: str
    status: ServiceStatus
    response_time: Optional[float] = None
    error: Optional[str] = None
    last_check: datetime = field(default_factory=datetime.now)
    consecutive_failures: int = 0
    total_checks: int = 0
    failed_checks: int = 0
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate."""
        if self.total_checks == 0:
            return 1.0
        return (self.total_checks - self.failed_checks) / self.total_checks


@dataclass
class LoadBalancerState:
    """Load balancer state."""
    current_index: Dict[str, int] = field(default_factory=dict)
    connection_counts: Dict[ServiceEndpoint, int] = field(default_factory=lambda: defaultdict(int))
    response_times: Dict[ServiceEndpoint, List[float]] = field(default_factory=lambda: defaultdict(list))
    last_selected: Dict[str, ServiceEndpoint] = field(default_factory=dict)


class DiscoveryProvider(ABC):
    """Base class for service discovery providers."""
    
    @abstractmethod
    async def register(self, instance: ServiceInstance) -> bool:
        """Register a service instance."""
        pass
    
    @abstractmethod
    async def deregister(self, instance_id: str) -> bool:
        """Deregister a service instance."""
        pass
    
    @abstractmethod
    async def discover(self, service_name: str, version: Optional[str] = None) -> List[ServiceInstance]:
        """Discover service instances."""
        pass
    
    @abstractmethod
    async def update_health(self, instance_id: str, health: ServiceHealth) -> bool:
        """Update service health."""
        pass


class RedisDiscoveryProvider(DiscoveryProvider):
    """Redis-based service discovery provider."""
    
    def __init__(self, redis_client: redis.Redis, ttl: int = 60):
        self.redis_client = redis_client
        self.ttl = ttl
    
    async def register(self, instance: ServiceInstance) -> bool:
        """Register service instance in Redis."""
        try:
            # Service key
            service_key = f"service:{instance.name}:{instance.id}"
            
            # Serialize instance
            instance_data = {
                'id': instance.id,
                'name': instance.name,
                'version': instance.version,
                'endpoints': json.dumps([
                    {
                        'host': ep.host,
                        'port': ep.port,
                        'protocol': ep.protocol,
                        'weight': ep.weight,
                        'metadata': ep.metadata
                    }
                    for ep in instance.endpoints
                ]),
                'status': instance.status.value,
                'metadata': json.dumps(instance.metadata),
                'tags': json.dumps(list(instance.tags)),
                'registered_at': instance.registered_at.isoformat(),
                'last_heartbeat': instance.last_heartbeat.isoformat(),
                'health_check_url': instance.health_check_url or ''
            }
            
            # Store instance data
            await self.redis_client.hset(service_key, mapping=instance_data)
            await self.redis_client.expire(service_key, self.ttl)
            
            # Add to service index
            index_key = f"service_index:{instance.name}"
            await self.redis_client.sadd(index_key, instance.id)
            await self.redis_client.expire(index_key, self.ttl)
            
            # Add to version index
            version_key = f"service_version:{instance.name}:{instance.version}"
            await self.redis_client.sadd(version_key, instance.id)
            await self.redis_client.expire(version_key, self.ttl)
            
            # Add to tag indices
            for tag in instance.tags:
                tag_key = f"service_tag:{instance.name}:{tag}"
                await self.redis_client.sadd(tag_key, instance.id)
                await self.redis_client.expire(tag_key, self.ttl)
            
            logger.info(f"Registered service instance: {instance.name}/{instance.id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register service: {e}")
            return False
    
    async def deregister(self, instance_id: str) -> bool:
        """Deregister service instance from Redis."""
        try:
            # Find service instance
            pattern = f"service:*:{instance_id}"
            keys = []
            async for key in self.redis_client.scan_iter(match=pattern):
                keys.append(key)
            
            if not keys:
                return False
            
            # Get instance data
            service_key = keys[0]
            instance_data = await self.redis_client.hgetall(service_key)
            if not instance_data:
                return False
            
            service_name = instance_data[b'name'].decode()
            version = instance_data[b'version'].decode()
            tags = json.loads(instance_data[b'tags'].decode())
            
            # Remove from indices
            await self.redis_client.srem(f"service_index:{service_name}", instance_id)
            await self.redis_client.srem(f"service_version:{service_name}:{version}", instance_id)
            
            for tag in tags:
                await self.redis_client.srem(f"service_tag:{service_name}:{tag}", instance_id)
            
            # Remove instance data
            await self.redis_client.delete(service_key)
            
            # Remove health data
            health_key = f"service_health:{instance_id}"
            await self.redis_client.delete(health_key)
            
            logger.info(f"Deregistered service instance: {service_name}/{instance_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to deregister service: {e}")
            return False
    
    async def discover(self, service_name: str, version: Optional[str] = None) -> List[ServiceInstance]:
        """Discover service instances from Redis."""
        try:
            instances = []
            
            # Get instance IDs
            if version:
                index_key = f"service_version:{service_name}:{version}"
            else:
                index_key = f"service_index:{service_name}"
            
            instance_ids = await self.redis_client.smembers(index_key)
            
            for instance_id in instance_ids:
                instance_id = instance_id.decode()
                service_key = f"service:{service_name}:{instance_id}"
                
                # Get instance data
                instance_data = await self.redis_client.hgetall(service_key)
                if not instance_data:
                    continue
                
                # Deserialize instance
                instance = ServiceInstance(
                    id=instance_data[b'id'].decode(),
                    name=instance_data[b'name'].decode(),
                    version=instance_data[b'version'].decode(),
                    endpoints=[
                        ServiceEndpoint(**ep)
                        for ep in json.loads(instance_data[b'endpoints'].decode())
                    ],
                    status=ServiceStatus(instance_data[b'status'].decode()),
                    metadata=json.loads(instance_data[b'metadata'].decode()),
                    tags=set(json.loads(instance_data[b'tags'].decode())),
                    registered_at=datetime.fromisoformat(instance_data[b'registered_at'].decode()),
                    last_heartbeat=datetime.fromisoformat(instance_data[b'last_heartbeat'].decode()),
                    health_check_url=instance_data[b'health_check_url'].decode() or None
                )
                
                instances.append(instance)
            
            return instances
            
        except Exception as e:
            logger.error(f"Failed to discover services: {e}")
            return []
    
    async def update_health(self, instance_id: str, health: ServiceHealth) -> bool:
        """Update service health in Redis."""
        try:
            health_key = f"service_health:{instance_id}"
            
            health_data = {
                'instance_id': health.instance_id,
                'status': health.status.value,
                'response_time': str(health.response_time) if health.response_time else '',
                'error': health.error or '',
                'last_check': health.last_check.isoformat(),
                'consecutive_failures': str(health.consecutive_failures),
                'total_checks': str(health.total_checks),
                'failed_checks': str(health.failed_checks)
            }
            
            await self.redis_client.hset(health_key, mapping=health_data)
            await self.redis_client.expire(health_key, self.ttl)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update health: {e}")
            return False


class DnsDiscoveryProvider(DiscoveryProvider):
    """DNS-based service discovery provider."""
    
    def __init__(self, domain: str, resolver: Optional[dns.resolver.Resolver] = None):
        self.domain = domain
        self.resolver = resolver or dns.resolver.Resolver()
        self.cache: Dict[str, Tuple[List[ServiceInstance], float]] = {}
        self.cache_ttl = 60  # seconds
    
    async def register(self, instance: ServiceInstance) -> bool:
        """DNS registration not supported."""
        logger.warning("DNS provider does not support registration")
        return False
    
    async def deregister(self, instance_id: str) -> bool:
        """DNS deregistration not supported."""
        logger.warning("DNS provider does not support deregistration")
        return False
    
    async def discover(self, service_name: str, version: Optional[str] = None) -> List[ServiceInstance]:
        """Discover services via DNS."""
        # Check cache
        cache_key = f"{service_name}:{version or 'any'}"
        if cache_key in self.cache:
            instances, cached_at = self.cache[cache_key]
            if time.time() - cached_at < self.cache_ttl:
                return instances
        
        try:
            instances = []
            
            # Query DNS
            query_name = f"{service_name}.{self.domain}"
            if version:
                query_name = f"{version}.{query_name}"
            
            # Try SRV records first
            try:
                srv_records = await asyncio.get_event_loop().run_in_executor(
                    None, 
                    self.resolver.resolve,
                    f"_http._tcp.{query_name}",
                    'SRV'
                )
                
                for srv in srv_records:
                    endpoint = ServiceEndpoint(
                        host=str(srv.target).rstrip('.'),
                        port=srv.port,
                        weight=srv.weight
                    )
                    
                    instance = ServiceInstance(
                        id=f"{srv.target}:{srv.port}",
                        name=service_name,
                        version=version or "unknown",
                        endpoints=[endpoint]
                    )
                    instances.append(instance)
                    
            except dns.resolver.NXDOMAIN:
                # Try A records
                try:
                    a_records = await asyncio.get_event_loop().run_in_executor(
                        None,
                        self.resolver.resolve,
                        query_name,
                        'A'
                    )
                    
                    for i, a in enumerate(a_records):
                        endpoint = ServiceEndpoint(
                            host=str(a),
                            port=80  # Default HTTP port
                        )
                        
                        instance = ServiceInstance(
                            id=f"{a}:{i}",
                            name=service_name,
                            version=version or "unknown",
                            endpoints=[endpoint]
                        )
                        instances.append(instance)
                        
                except Exception:
                    pass
            
            # Cache results
            self.cache[cache_key] = (instances, time.time())
            
            return instances
            
        except Exception as e:
            logger.error(f"DNS discovery failed: {e}")
            return []
    
    async def update_health(self, instance_id: str, health: ServiceHealth) -> bool:
        """DNS health update not supported."""
        logger.warning("DNS provider does not support health updates")
        return False


class LoadBalancer:
    """Load balancer for service instances."""
    
    def __init__(self, strategy: LoadBalancingStrategy = LoadBalancingStrategy.ROUND_ROBIN):
        self.strategy = strategy
        self.state = LoadBalancerState()
    
    def select(
        self,
        instances: List[ServiceInstance],
        client_ip: Optional[str] = None
    ) -> Optional[ServiceEndpoint]:
        """Select an endpoint using the configured strategy."""
        # Filter healthy instances
        healthy_instances = [i for i in instances if i.is_healthy]
        if not healthy_instances:
            return None
        
        # Collect all endpoints with their instances
        endpoints: List[Tuple[ServiceEndpoint, ServiceInstance]] = []
        for instance in healthy_instances:
            for endpoint in instance.endpoints:
                endpoints.append((endpoint, instance))
        
        if not endpoints:
            return None
        
        # Apply strategy
        if self.strategy == LoadBalancingStrategy.ROUND_ROBIN:
            return self._round_robin(endpoints)
        elif self.strategy == LoadBalancingStrategy.WEIGHTED_ROUND_ROBIN:
            return self._weighted_round_robin(endpoints)
        elif self.strategy == LoadBalancingStrategy.LEAST_CONNECTIONS:
            return self._least_connections(endpoints)
        elif self.strategy == LoadBalancingStrategy.RANDOM:
            return self._random(endpoints)
        elif self.strategy == LoadBalancingStrategy.IP_HASH:
            return self._ip_hash(endpoints, client_ip)
        elif self.strategy == LoadBalancingStrategy.LEAST_RESPONSE_TIME:
            return self._least_response_time(endpoints)
        else:
            return self._round_robin(endpoints)
    
    def _round_robin(self, endpoints: List[Tuple[ServiceEndpoint, ServiceInstance]]) -> ServiceEndpoint:
        """Round-robin selection."""
        key = "round_robin"
        self.state.current_index[key] = (self.state.current_index.get(key, 0) + 1) % len(endpoints)
        return endpoints[self.state.current_index[key]][0]
    
    def _weighted_round_robin(self, endpoints: List[Tuple[ServiceEndpoint, ServiceInstance]]) -> ServiceEndpoint:
        """Weighted round-robin selection."""
        weighted_list = []
        for endpoint, _ in endpoints:
            weighted_list.extend([endpoint] * endpoint.weight)
        
        if not weighted_list:
            return endpoints[0][0]
        
        key = "weighted_round_robin"
        self.state.current_index[key] = (self.state.current_index.get(key, 0) + 1) % len(weighted_list)
        return weighted_list[self.state.current_index[key]]
    
    def _least_connections(self, endpoints: List[Tuple[ServiceEndpoint, ServiceInstance]]) -> ServiceEndpoint:
        """Least connections selection."""
        min_connections = float('inf')
        selected = None
        
        for endpoint, _ in endpoints:
            connections = self.state.connection_counts[endpoint]
            if connections < min_connections:
                min_connections = connections
                selected = endpoint
        
        return selected or endpoints[0][0]
    
    def _random(self, endpoints: List[Tuple[ServiceEndpoint, ServiceInstance]]) -> ServiceEndpoint:
        """Random selection."""
        return random.choice(endpoints)[0]
    
    def _ip_hash(self, endpoints: List[Tuple[ServiceEndpoint, ServiceInstance]], client_ip: Optional[str]) -> ServiceEndpoint:
        """IP hash selection."""
        if not client_ip:
            return self._random(endpoints)
        
        hash_value = int(hashlib.md5(client_ip.encode()).hexdigest(), 16)
        index = hash_value % len(endpoints)
        return endpoints[index][0]
    
    def _least_response_time(self, endpoints: List[Tuple[ServiceEndpoint, ServiceInstance]]) -> ServiceEndpoint:
        """Least response time selection."""
        min_response_time = float('inf')
        selected = None
        
        for endpoint, _ in endpoints:
            response_times = self.state.response_times.get(endpoint, [])
            if response_times:
                avg_time = sum(response_times) / len(response_times)
                if avg_time < min_response_time:
                    min_response_time = avg_time
                    selected = endpoint
        
        return selected or endpoints[0][0]
    
    def start_request(self, endpoint: ServiceEndpoint):
        """Mark request start."""
        self.state.connection_counts[endpoint] += 1
    
    def end_request(self, endpoint: ServiceEndpoint, response_time: float):
        """Mark request end."""
        self.state.connection_counts[endpoint] = max(0, self.state.connection_counts[endpoint] - 1)
        
        # Record response time
        if endpoint not in self.state.response_times:
            self.state.response_times[endpoint] = []
        
        self.state.response_times[endpoint].append(response_time)
        
        # Keep only last 100 response times
        if len(self.state.response_times[endpoint]) > 100:
            self.state.response_times[endpoint] = self.state.response_times[endpoint][-100:]


class ServiceDiscovery:
    """Main service discovery class."""
    
    def __init__(self, providers: Optional[List[DiscoveryProvider]] = None):
        self.providers = providers or []
        self.health_checkers: Dict[str, 'HealthChecker'] = {}
        self.load_balancers: Dict[str, LoadBalancer] = {}
        self._running = False
        self._health_check_task: Optional[asyncio.Task] = None
    
    def add_provider(self, provider: DiscoveryProvider):
        """Add a discovery provider."""
        self.providers.append(provider)
    
    async def register(self, instance: ServiceInstance) -> bool:
        """Register a service instance."""
        success = False
        for provider in self.providers:
            try:
                if await provider.register(instance):
                    success = True
            except Exception as e:
                logger.error(f"Provider registration failed: {e}")
        
        if success:
            # Start health checking
            if instance.health_check_url:
                self.health_checkers[instance.id] = HealthChecker(
                    instance,
                    self._update_health_callback
                )
        
        return success
    
    async def deregister(self, instance_id: str) -> bool:
        """Deregister a service instance."""
        success = False
        
        # Stop health checking
        if instance_id in self.health_checkers:
            checker = self.health_checkers.pop(instance_id)
            await checker.stop()
        
        for provider in self.providers:
            try:
                if await provider.deregister(instance_id):
                    success = True
            except Exception as e:
                logger.error(f"Provider deregistration failed: {e}")
        
        return success
    
    async def discover(
        self,
        service_name: str,
        version: Optional[str] = None,
        tags: Optional[Set[str]] = None
    ) -> List[ServiceInstance]:
        """Discover service instances."""
        all_instances = []
        
        for provider in self.providers:
            try:
                instances = await provider.discover(service_name, version)
                all_instances.extend(instances)
            except Exception as e:
                logger.error(f"Provider discovery failed: {e}")
        
        # Filter by tags if specified
        if tags:
            all_instances = [
                i for i in all_instances
                if i.matches_criteria(version, tags)
            ]
        
        # Remove duplicates
        unique_instances = {}
        for instance in all_instances:
            unique_instances[instance.id] = instance
        
        return list(unique_instances.values())
    
    async def get_endpoint(
        self,
        service_name: str,
        version: Optional[str] = None,
        tags: Optional[Set[str]] = None,
        strategy: LoadBalancingStrategy = LoadBalancingStrategy.ROUND_ROBIN,
        client_ip: Optional[str] = None
    ) -> Optional[ServiceEndpoint]:
        """Get a service endpoint using load balancing."""
        # Get or create load balancer
        lb_key = f"{service_name}:{strategy.value}"
        if lb_key not in self.load_balancers:
            self.load_balancers[lb_key] = LoadBalancer(strategy)
        
        load_balancer = self.load_balancers[lb_key]
        
        # Discover instances
        instances = await self.discover(service_name, version, tags)
        if not instances:
            return None
        
        # Select endpoint
        return load_balancer.select(instances, client_ip)
    
    async def start(self):
        """Start service discovery."""
        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())
    
    async def stop(self):
        """Stop service discovery."""
        self._running = False
        
        # Stop health checkers
        for checker in self.health_checkers.values():
            await checker.stop()
        
        # Cancel health check task
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
    
    async def _health_check_loop(self):
        """Background health check loop."""
        while self._running:
            try:
                # Check all registered services
                tasks = []
                for checker in self.health_checkers.values():
                    tasks.append(checker.check())
                
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                
                await asyncio.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                logger.error(f"Health check loop error: {e}")
                await asyncio.sleep(10)
    
    async def _update_health_callback(self, instance_id: str, health: ServiceHealth):
        """Callback for health updates."""
        for provider in self.providers:
            try:
                await provider.update_health(instance_id, health)
            except Exception as e:
                logger.error(f"Provider health update failed: {e}")


class HealthChecker:
    """Health checker for service instances."""
    
    def __init__(
        self,
        instance: ServiceInstance,
        update_callback: Callable[[str, ServiceHealth], Any],
        timeout: float = 5.0,
        interval: float = 30.0
    ):
        self.instance = instance
        self.update_callback = update_callback
        self.timeout = timeout
        self.interval = interval
        self.health = ServiceHealth(instance_id=instance.id, status=ServiceStatus.UP)
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def check(self) -> ServiceHealth:
        """Perform health check."""
        if not self.instance.health_check_url:
            return self.health
        
        start_time = time.time()
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.instance.health_check_url,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    response_time = time.time() - start_time
                    
                    if 200 <= response.status < 300:
                        # Success
                        self.health.status = ServiceStatus.UP
                        self.health.response_time = response_time
                        self.health.error = None
                        self.health.consecutive_failures = 0
                    else:
                        # HTTP error
                        self.health.status = ServiceStatus.DOWN
                        self.health.error = f"HTTP {response.status}"
                        self.health.consecutive_failures += 1
                        
        except asyncio.TimeoutError:
            self.health.status = ServiceStatus.DOWN
            self.health.error = "Timeout"
            self.health.consecutive_failures += 1
            
        except Exception as e:
            self.health.status = ServiceStatus.DOWN
            self.health.error = str(e)
            self.health.consecutive_failures += 1
        
        # Update statistics
        self.health.total_checks += 1
        if self.health.status != ServiceStatus.UP:
            self.health.failed_checks += 1
        self.health.last_check = datetime.now()
        
        # Update via callback
        await self.update_callback(self.instance.id, self.health)
        
        return self.health
    
    async def start(self):
        """Start health checking."""
        self._running = True
        self._task = asyncio.create_task(self._check_loop())
    
    async def stop(self):
        """Stop health checking."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    
    async def _check_loop(self):
        """Health check loop."""
        while self._running:
            try:
                await self.check()
                await asyncio.sleep(self.interval)
            except Exception as e:
                logger.error(f"Health check error: {e}")
                await asyncio.sleep(self.interval)