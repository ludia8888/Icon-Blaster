"""
Health monitoring data models
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any


class HealthStatus(Enum):
    """Health status levels"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class HealthState(Enum):
    """Component operational states"""
    RUNNING = "running"
    STARTING = "starting"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass
class HealthCheckResult:
    """Result of a single health check"""
    name: str
    status: HealthStatus
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration_ms: float = 0.0
    
    @property
    def is_healthy(self) -> bool:
        return self.status == HealthStatus.HEALTHY
    
    @property
    def is_degraded(self) -> bool:
        return self.status == HealthStatus.DEGRADED
    
    @property
    def is_unhealthy(self) -> bool:
        return self.status == HealthStatus.UNHEALTHY


@dataclass
class ComponentHealth:
    """Health status of a component"""
    component_name: str
    status: HealthStatus
    state: HealthState
    checks: List[HealthCheckResult] = field(default_factory=list)
    dependencies: Dict[str, HealthStatus] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    last_check: datetime = field(default_factory=datetime.utcnow)
    uptime_seconds: float = 0.0
    
    @property
    def is_healthy(self) -> bool:
        return self.status == HealthStatus.HEALTHY
    
    @property
    def failed_checks(self) -> List[HealthCheckResult]:
        return [check for check in self.checks if check.is_unhealthy]
    
    @property
    def degraded_checks(self) -> List[HealthCheckResult]:
        return [check for check in self.checks if check.is_degraded]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "component_name": self.component_name,
            "status": self.status.value,
            "state": self.state.value,
            "checks": [
                {
                    "name": check.name,
                    "status": check.status.value,
                    "message": check.message,
                    "details": check.details,
                    "timestamp": check.timestamp.isoformat(),
                    "duration_ms": check.duration_ms
                }
                for check in self.checks
            ],
            "dependencies": {
                name: status.value 
                for name, status in self.dependencies.items()
            },
            "metadata": self.metadata,
            "last_check": self.last_check.isoformat(),
            "uptime_seconds": self.uptime_seconds
        }


@dataclass
class HealthAlert:
    """Health alert notification"""
    component_name: str
    alert_type: str
    severity: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    
    def resolve(self):
        """Mark alert as resolved"""
        self.resolved = True
        self.resolved_at = datetime.utcnow()


@dataclass
class HealthMetrics:
    """Health-related metrics"""
    total_checks: int = 0
    healthy_checks: int = 0
    degraded_checks: int = 0
    unhealthy_checks: int = 0
    average_check_duration_ms: float = 0.0
    last_update: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def health_percentage(self) -> float:
        """Calculate health percentage"""
        if self.total_checks == 0:
            return 100.0
        return (self.healthy_checks / self.total_checks) * 100
    
    def update(self, results: List[HealthCheckResult]):
        """Update metrics from health check results"""
        self.total_checks = len(results)
        self.healthy_checks = sum(1 for r in results if r.is_healthy)
        self.degraded_checks = sum(1 for r in results if r.is_degraded)
        self.unhealthy_checks = sum(1 for r in results if r.is_unhealthy)
        
        if results:
            total_duration = sum(r.duration_ms for r in results)
            self.average_check_duration_ms = total_duration / len(results)
        
        self.last_update = datetime.utcnow()