"""
Health monitoring component
"""
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging

from .models import HealthCheckResult, HealthStatus, ComponentHealth

logger = logging.getLogger(__name__)


class HealthMonitor:
    """Monitor component health and track history"""
    
    def __init__(self, component_name: str):
        self.component_name = component_name
        self.start_time = time.time()
        self._check_history: List[ComponentHealth] = []
        self._max_history_size = 100
    
    def get_uptime(self) -> float:
        """Get component uptime in seconds"""
        return time.time() - self.start_time
    
    def record_health(self, health: ComponentHealth):
        """Record health check result"""
        self._check_history.append(health)
        
        # Maintain history size limit
        if len(self._check_history) > self._max_history_size:
            self._check_history = self._check_history[-self._max_history_size:]
    
    def get_history(
        self, 
        limit: Optional[int] = None
    ) -> List[ComponentHealth]:
        """Get health check history"""
        if limit:
            return self._check_history[-limit:]
        return self._check_history.copy()
    
    def get_availability(self, period_seconds: float = 3600) -> float:
        """Calculate availability percentage over a period"""
        if not self._check_history:
            return 100.0
        
        cutoff_time = datetime.utcnow().timestamp() - period_seconds
        recent_checks = [
            h for h in self._check_history 
            if h.last_check.timestamp() > cutoff_time
        ]
        
        if not recent_checks:
            return 100.0
        
        healthy_checks = sum(1 for h in recent_checks if h.is_healthy)
        return (healthy_checks / len(recent_checks)) * 100
    
    def get_failure_rate(self, period_seconds: float = 3600) -> float:
        """Calculate failure rate over a period"""
        return 100.0 - self.get_availability(period_seconds)