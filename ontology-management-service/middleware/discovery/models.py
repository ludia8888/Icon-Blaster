"""
Service discovery data models
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any


class ServiceStatus(Enum):
    """Service instance status"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    STOPPING = "stopping"
    UNKNOWN = "unknown"


class LoadBalancerStrategy(Enum):
    """Load balancing strategies"""
    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    RANDOM = "random"
    IP_HASH = "ip_hash"
    LEAST_RESPONSE_TIME = "least_response_time"


@dataclass
class ServiceEndpoint:
    """Service endpoint information"""
    host: str
    port: int
    protocol: str = "http"
    path: str = "/"
    
    @property
    def url(self) -> str:
        """Get full URL"""
        return f"{self.protocol}://{self.host}:{self.port}{self.path}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "host": self.host,
            "port": self.port,
            "protocol": self.protocol,
            "path": self.path
        }


@dataclass
class ServiceInstance:
    """Service instance information"""
    id: str
    name: str
    endpoint: ServiceEndpoint
    status: ServiceStatus = ServiceStatus.UNKNOWN
    version: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    registered_at: datetime = field(default_factory=datetime.utcnow)
    last_heartbeat: datetime = field(default_factory=datetime.utcnow)
    
    # Performance metrics
    active_connections: int = 0
    response_time_ms: float = 0.0
    error_rate: float = 0.0
    weight: int = 100  # For weighted load balancing
    
    @property
    def is_healthy(self) -> bool:
        """Check if instance is healthy"""
        return self.status == ServiceStatus.HEALTHY
    
    @property
    def age(self) -> float:
        """Get instance age in seconds"""
        return (datetime.utcnow() - self.registered_at).total_seconds()
    
    @property
    def heartbeat_age(self) -> float:
        """Get heartbeat age in seconds"""
        return (datetime.utcnow() - self.last_heartbeat).total_seconds()
    
    def update_heartbeat(self):
        """Update heartbeat timestamp"""
        self.last_heartbeat = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "id": self.id,
            "name": self.name,
            "endpoint": self.endpoint.to_dict(),
            "status": self.status.value,
            "version": self.version,
            "metadata": self.metadata,
            "registered_at": self.registered_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "active_connections": self.active_connections,
            "response_time_ms": self.response_time_ms,
            "error_rate": self.error_rate,
            "weight": self.weight
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServiceInstance":
        """Create from dictionary"""
        endpoint = ServiceEndpoint(
            host=data["endpoint"]["host"],
            port=data["endpoint"]["port"],
            protocol=data["endpoint"].get("protocol", "http"),
            path=data["endpoint"].get("path", "/")
        )
        
        return cls(
            id=data["id"],
            name=data["name"],
            endpoint=endpoint,
            status=ServiceStatus(data.get("status", "unknown")),
            version=data.get("version"),
            metadata=data.get("metadata", {}),
            registered_at=datetime.fromisoformat(data["registered_at"]),
            last_heartbeat=datetime.fromisoformat(data["last_heartbeat"]),
            active_connections=data.get("active_connections", 0),
            response_time_ms=data.get("response_time_ms", 0.0),
            error_rate=data.get("error_rate", 0.0),
            weight=data.get("weight", 100)
        )


@dataclass
class ServiceRegistration:
    """Service registration request"""
    name: str
    host: str
    port: int
    protocol: str = "http"
    path: str = "/"
    version: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    ttl_seconds: int = 30
    weight: int = 100
    
    def to_instance(self, instance_id: str) -> ServiceInstance:
        """Convert to service instance"""
        endpoint = ServiceEndpoint(
            host=self.host,
            port=self.port,
            protocol=self.protocol,
            path=self.path
        )
        
        return ServiceInstance(
            id=instance_id,
            name=self.name,
            endpoint=endpoint,
            version=self.version,
            metadata=self.metadata,
            status=ServiceStatus.STARTING,
            weight=self.weight
        )


@dataclass
class ServiceDiscoveryConfig:
    """Service discovery configuration"""
    # Health check settings
    health_check_interval: int = 10
    health_check_timeout: int = 5
    unhealthy_threshold: int = 3
    healthy_threshold: int = 2
    
    # Instance management
    deregister_after_seconds: int = 60
    cleanup_interval: int = 30
    
    # Load balancer settings
    default_strategy: LoadBalancerStrategy = LoadBalancerStrategy.ROUND_ROBIN
    sticky_sessions: bool = False
    session_timeout: int = 300
    
    # Provider settings
    provider_type: str = "redis"  # redis, dns, consul, etcd
    provider_config: Dict[str, Any] = field(default_factory=dict)