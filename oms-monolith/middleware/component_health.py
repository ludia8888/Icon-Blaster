"""
Enterprise-grade component health checks with dependency tracking.

Features:
- Component-specific health checks
- Dependency graph and tracking
- Cascading health status
- Health check aggregation
- Configurable check intervals and timeouts
- Health history and trends
- Alert integration
- Health check caching
"""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable, Tuple, Union
import aiohttp
import psutil
import redis.asyncio as redis
from collections import deque, defaultdict
import json
import logging
from functools import lru_cache
import socket

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"
    
    @property
    def severity(self) -> int:
        """Get severity level (higher is worse)."""
        return {
            HealthStatus.HEALTHY: 0,
            HealthStatus.DEGRADED: 1,
            HealthStatus.UNHEALTHY: 2,
            HealthStatus.UNKNOWN: 3
        }[self]
    
    @classmethod
    def worst(cls, statuses: List['HealthStatus']) -> 'HealthStatus':
        """Get worst status from a list."""
        if not statuses:
            return cls.UNKNOWN
        return max(statuses, key=lambda s: s.severity)


class ComponentType(Enum):
    """Component types."""
    DATABASE = "database"
    CACHE = "cache"
    MESSAGE_QUEUE = "message_queue"
    API = "api"
    SERVICE = "service"
    SYSTEM = "system"
    CUSTOM = "custom"


@dataclass
class HealthCheckResult:
    """Health check result."""
    status: HealthStatus
    message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    response_time: Optional[float] = None
    error: Optional[Exception] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'status': self.status.value,
            'message': self.message,
            'details': self.details,
            'response_time': self.response_time,
            'error': str(self.error) if self.error else None,
            'timestamp': self.timestamp.isoformat()
        }


@dataclass
class ComponentHealth:
    """Component health information."""
    component_id: str
    component_type: ComponentType
    status: HealthStatus
    last_check: datetime
    last_healthy: Optional[datetime] = None
    consecutive_failures: int = 0
    total_checks: int = 0
    failed_checks: int = 0
    average_response_time: float = 0
    dependencies: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    history: deque = field(default_factory=lambda: deque(maxlen=100))
    
    @property
    def uptime_percentage(self) -> float:
        """Calculate uptime percentage."""
        if self.total_checks == 0:
            return 100.0
        return ((self.total_checks - self.failed_checks) / self.total_checks) * 100
    
    @property
    def is_critical(self) -> bool:
        """Check if component is in critical state."""
        return self.status in [HealthStatus.UNHEALTHY, HealthStatus.UNKNOWN]
    
    def update(self, result: HealthCheckResult):
        """Update health with new check result."""
        self.last_check = result.timestamp
        self.status = result.status
        self.total_checks += 1
        
        if result.status == HealthStatus.HEALTHY:
            self.last_healthy = result.timestamp
            self.consecutive_failures = 0
        else:
            self.failed_checks += 1
            self.consecutive_failures += 1
        
        # Update average response time
        if result.response_time:
            self.average_response_time = (
                (self.average_response_time * (self.total_checks - 1) + result.response_time) /
                self.total_checks
            )
        
        # Add to history
        self.history.append({
            'timestamp': result.timestamp,
            'status': result.status.value,
            'response_time': result.response_time,
            'message': result.message
        })


class HealthCheck(ABC):
    """Base health check class."""
    
    def __init__(
        self,
        component_id: str,
        component_type: ComponentType,
        interval: float = 30.0,
        timeout: float = 10.0,
        failure_threshold: int = 3,
        recovery_threshold: int = 2
    ):
        self.component_id = component_id
        self.component_type = component_type
        self.interval = interval
        self.timeout = timeout
        self.failure_threshold = failure_threshold
        self.recovery_threshold = recovery_threshold
        self._cache: Optional[Tuple[HealthCheckResult, float]] = None
        self._cache_ttl = min(interval / 2, 15)  # Cache for half the interval or 15s
    
    @abstractmethod
    async def check(self) -> HealthCheckResult:
        """Perform health check."""
        pass
    
    async def check_with_cache(self) -> HealthCheckResult:
        """Check with caching."""
        # Check cache
        if self._cache:
            result, cached_at = self._cache
            if time.time() - cached_at < self._cache_ttl:
                return result
        
        # Perform check
        try:
            result = await asyncio.wait_for(self.check(), timeout=self.timeout)
        except asyncio.TimeoutError:
            result = HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"Health check timed out after {self.timeout}s",
                error=TimeoutError("Health check timeout")
            )
        except Exception as e:
            result = HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"Health check failed: {str(e)}",
                error=e
            )
        
        # Cache result
        self._cache = (result, time.time())
        
        return result


class DatabaseHealthCheck(HealthCheck):
    """Database health check."""
    
    def __init__(
        self,
        component_id: str,
        connection_string: str,
        query: str = "SELECT 1",
        **kwargs
    ):
        super().__init__(component_id, ComponentType.DATABASE, **kwargs)
        self.connection_string = connection_string
        self.query = query
    
    async def check(self) -> HealthCheckResult:
        """Check database health."""
        start_time = time.time()
        
        try:
            # Import database driver dynamically
            import asyncpg
            
            # Connect and execute query
            conn = await asyncpg.connect(self.connection_string)
            try:
                result = await conn.fetchval(self.query)
                response_time = time.time() - start_time
                
                return HealthCheckResult(
                    status=HealthStatus.HEALTHY,
                    message="Database is responsive",
                    response_time=response_time,
                    details={'query_result': result}
                )
            finally:
                await conn.close()
                
        except ImportError:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="Database driver not installed",
                error=ImportError("asyncpg not installed")
            )
        except Exception as e:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"Database check failed: {str(e)}",
                error=e
            )


class RedisHealthCheck(HealthCheck):
    """Redis health check."""
    
    def __init__(
        self,
        component_id: str,
        redis_client: redis.Redis,
        **kwargs
    ):
        super().__init__(component_id, ComponentType.CACHE, **kwargs)
        self.redis_client = redis_client
    
    async def check(self) -> HealthCheckResult:
        """Check Redis health."""
        start_time = time.time()
        
        try:
            # Ping Redis
            await self.redis_client.ping()
            
            # Get info
            info = await self.redis_client.info()
            response_time = time.time() - start_time
            
            # Check memory usage
            used_memory = info.get('used_memory', 0)
            max_memory = info.get('maxmemory', 0)
            memory_usage = (used_memory / max_memory * 100) if max_memory > 0 else 0
            
            # Determine status
            if memory_usage > 90:
                status = HealthStatus.DEGRADED
                message = f"High memory usage: {memory_usage:.1f}%"
            else:
                status = HealthStatus.HEALTHY
                message = "Redis is healthy"
            
            return HealthCheckResult(
                status=status,
                message=message,
                response_time=response_time,
                details={
                    'used_memory': used_memory,
                    'max_memory': max_memory,
                    'memory_usage_percent': memory_usage,
                    'connected_clients': info.get('connected_clients', 0)
                }
            )
            
        except Exception as e:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"Redis check failed: {str(e)}",
                error=e
            )


class HttpHealthCheck(HealthCheck):
    """HTTP endpoint health check."""
    
    def __init__(
        self,
        component_id: str,
        url: str,
        expected_status: Union[int, List[int]] = 200,
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ):
        super().__init__(component_id, ComponentType.API, **kwargs)
        self.url = url
        self.expected_status = expected_status if isinstance(expected_status, list) else [expected_status]
        self.headers = headers or {}
    
    async def check(self) -> HealthCheckResult:
        """Check HTTP endpoint health."""
        start_time = time.time()
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    self.url,
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as response:
                    response_time = time.time() - start_time
                    
                    if response.status in self.expected_status:
                        return HealthCheckResult(
                            status=HealthStatus.HEALTHY,
                            message=f"Endpoint returned {response.status}",
                            response_time=response_time,
                            details={
                                'status_code': response.status,
                                'content_length': response.headers.get('content-length')
                            }
                        )
                    else:
                        return HealthCheckResult(
                            status=HealthStatus.UNHEALTHY,
                            message=f"Unexpected status code: {response.status}",
                            response_time=response_time,
                            details={'status_code': response.status}
                        )
                        
        except asyncio.TimeoutError:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"Request timed out after {self.timeout}s",
                error=TimeoutError("HTTP request timeout")
            )
        except Exception as e:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"HTTP check failed: {str(e)}",
                error=e
            )


class SystemHealthCheck(HealthCheck):
    """System resource health check."""
    
    def __init__(
        self,
        component_id: str,
        cpu_threshold: float = 80.0,
        memory_threshold: float = 85.0,
        disk_threshold: float = 90.0,
        **kwargs
    ):
        super().__init__(component_id, ComponentType.SYSTEM, **kwargs)
        self.cpu_threshold = cpu_threshold
        self.memory_threshold = memory_threshold
        self.disk_threshold = disk_threshold
    
    async def check(self) -> HealthCheckResult:
        """Check system resources."""
        start_time = time.time()
        
        try:
            # Get system metrics
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            response_time = time.time() - start_time
            
            # Check thresholds
            issues = []
            if cpu_percent > self.cpu_threshold:
                issues.append(f"High CPU usage: {cpu_percent:.1f}%")
            if memory.percent > self.memory_threshold:
                issues.append(f"High memory usage: {memory.percent:.1f}%")
            if disk.percent > self.disk_threshold:
                issues.append(f"High disk usage: {disk.percent:.1f}%")
            
            # Determine status
            if not issues:
                status = HealthStatus.HEALTHY
                message = "System resources are healthy"
            elif len(issues) == 1:
                status = HealthStatus.DEGRADED
                message = issues[0]
            else:
                status = HealthStatus.UNHEALTHY
                message = "; ".join(issues)
            
            return HealthCheckResult(
                status=status,
                message=message,
                response_time=response_time,
                details={
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory.percent,
                    'memory_available_gb': memory.available / (1024 ** 3),
                    'disk_percent': disk.percent,
                    'disk_free_gb': disk.free / (1024 ** 3)
                }
            )
            
        except Exception as e:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"System check failed: {str(e)}",
                error=e
            )


class CustomHealthCheck(HealthCheck):
    """Custom health check with user-defined function."""
    
    def __init__(
        self,
        component_id: str,
        check_function: Callable[[], Union[HealthCheckResult, Callable]],
        **kwargs
    ):
        super().__init__(component_id, ComponentType.CUSTOM, **kwargs)
        self.check_function = check_function
    
    async def check(self) -> HealthCheckResult:
        """Perform custom health check."""
        try:
            if asyncio.iscoroutinefunction(self.check_function):
                result = await self.check_function()
            else:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, self.check_function
                )
            
            if isinstance(result, HealthCheckResult):
                return result
            else:
                # Assume boolean result
                return HealthCheckResult(
                    status=HealthStatus.HEALTHY if result else HealthStatus.UNHEALTHY,
                    message="Custom check " + ("passed" if result else "failed")
                )
                
        except Exception as e:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"Custom check failed: {str(e)}",
                error=e
            )


class DependencyGraph:
    """Manages component dependencies."""
    
    def __init__(self):
        self.dependencies: Dict[str, Set[str]] = defaultdict(set)
        self.dependents: Dict[str, Set[str]] = defaultdict(set)
    
    def add_dependency(self, component: str, depends_on: str):
        """Add a dependency relationship."""
        self.dependencies[component].add(depends_on)
        self.dependents[depends_on].add(component)
    
    def remove_dependency(self, component: str, depends_on: str):
        """Remove a dependency relationship."""
        self.dependencies[component].discard(depends_on)
        self.dependents[depends_on].discard(component)
    
    def get_dependencies(self, component: str) -> Set[str]:
        """Get all dependencies of a component."""
        return self.dependencies.get(component, set())
    
    def get_dependents(self, component: str) -> Set[str]:
        """Get all components that depend on this one."""
        return self.dependents.get(component, set())
    
    def get_all_dependencies(self, component: str) -> Set[str]:
        """Get all transitive dependencies."""
        visited = set()
        to_visit = [component]
        
        while to_visit:
            current = to_visit.pop()
            if current in visited:
                continue
            
            visited.add(current)
            to_visit.extend(self.dependencies.get(current, set()))
        
        visited.discard(component)
        return visited
    
    def has_circular_dependency(self) -> bool:
        """Check for circular dependencies."""
        visited = set()
        rec_stack = set()
        
        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in self.dependencies.get(node, set()):
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(node)
            return False
        
        for node in self.dependencies:
            if node not in visited:
                if has_cycle(node):
                    return True
        
        return False
    
    def topological_sort(self) -> List[str]:
        """Get components in dependency order."""
        in_degree = defaultdict(int)
        for deps in self.dependencies.values():
            for dep in deps:
                in_degree[dep] += 1
        
        # Add all nodes
        all_nodes = set(self.dependencies.keys()) | set(self.dependents.keys())
        queue = [node for node in all_nodes if in_degree[node] == 0]
        result = []
        
        while queue:
            node = queue.pop(0)
            result.append(node)
            
            for dependent in self.dependents.get(node, set()):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        
        return result if len(result) == len(all_nodes) else []


class ComponentHealthMonitor:
    """Monitors health of all components with dependency tracking."""
    
    def __init__(self, alert_callback: Optional[Callable] = None):
        self.health_checks: Dict[str, HealthCheck] = {}
        self.component_health: Dict[str, ComponentHealth] = {}
        self.dependency_graph = DependencyGraph()
        self.alert_callback = alert_callback
        self._running = False
        self._tasks: Dict[str, asyncio.Task] = {}
        self._aggregate_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}
        self._aggregate_cache_ttl = 5.0
    
    def register_component(
        self,
        component_id: str,
        health_check: HealthCheck,
        dependencies: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """Register a component with its health check."""
        self.health_checks[component_id] = health_check
        
        # Initialize component health
        self.component_health[component_id] = ComponentHealth(
            component_id=component_id,
            component_type=health_check.component_type,
            status=HealthStatus.UNKNOWN,
            last_check=datetime.now(),
            dependencies=set(dependencies or []),
            metadata=metadata or {}
        )
        
        # Update dependency graph
        for dep in dependencies or []:
            self.dependency_graph.add_dependency(component_id, dep)
    
    def unregister_component(self, component_id: str):
        """Unregister a component."""
        # Stop monitoring
        if component_id in self._tasks:
            self._tasks[component_id].cancel()
            del self._tasks[component_id]
        
        # Remove from tracking
        self.health_checks.pop(component_id, None)
        self.component_health.pop(component_id, None)
        
        # Update dependency graph
        for dep in self.dependency_graph.get_dependencies(component_id):
            self.dependency_graph.remove_dependency(component_id, dep)
        for dependent in self.dependency_graph.get_dependents(component_id):
            self.dependency_graph.remove_dependency(dependent, component_id)
    
    async def check_component(self, component_id: str) -> HealthCheckResult:
        """Check health of a specific component."""
        if component_id not in self.health_checks:
            return HealthCheckResult(
                status=HealthStatus.UNKNOWN,
                message=f"Component {component_id} not registered"
            )
        
        health_check = self.health_checks[component_id]
        result = await health_check.check_with_cache()
        
        # Update component health
        component = self.component_health[component_id]
        old_status = component.status
        component.update(result)
        
        # Check dependency health
        dep_statuses = []
        for dep_id in component.dependencies:
            if dep_id in self.component_health:
                dep_statuses.append(self.component_health[dep_id].status)
        
        if dep_statuses:
            worst_dep_status = HealthStatus.worst(dep_statuses)
            if worst_dep_status.severity > result.status.severity:
                result.status = HealthStatus.DEGRADED
                result.message = f"{result.message}; degraded due to dependency issues"
        
        # Send alert if status changed
        if old_status != result.status and self.alert_callback:
            await self._send_alert(component_id, old_status, result.status)
        
        return result
    
    async def check_all(self) -> Dict[str, HealthCheckResult]:
        """Check health of all components."""
        # Check in dependency order
        order = self.dependency_graph.topological_sort()
        ordered_components = [c for c in order if c in self.health_checks]
        
        # Add any components not in the dependency graph
        for component_id in self.health_checks:
            if component_id not in ordered_components:
                ordered_components.append(component_id)
        
        # Check components
        results = {}
        for component_id in ordered_components:
            results[component_id] = await self.check_component(component_id)
        
        return results
    
    async def get_aggregate_health(self, use_cache: bool = True) -> Dict[str, Any]:
        """Get aggregated health status."""
        # Check cache
        if use_cache and self._aggregate_cache:
            cached_result, cached_at = list(self._aggregate_cache.values())[0]
            if time.time() - cached_at < self._aggregate_cache_ttl:
                return cached_result
        
        # Check all components
        results = await self.check_all()
        
        # Aggregate results
        total_components = len(self.component_health)
        healthy_components = sum(
            1 for c in self.component_health.values()
            if c.status == HealthStatus.HEALTHY
        )
        degraded_components = sum(
            1 for c in self.component_health.values()
            if c.status == HealthStatus.DEGRADED
        )
        unhealthy_components = sum(
            1 for c in self.component_health.values()
            if c.status == HealthStatus.UNHEALTHY
        )
        
        # Overall status
        if unhealthy_components > 0:
            overall_status = HealthStatus.UNHEALTHY
        elif degraded_components > 0:
            overall_status = HealthStatus.DEGRADED
        elif healthy_components == total_components:
            overall_status = HealthStatus.HEALTHY
        else:
            overall_status = HealthStatus.UNKNOWN
        
        # Calculate average uptime
        total_uptime = sum(c.uptime_percentage for c in self.component_health.values())
        average_uptime = total_uptime / total_components if total_components > 0 else 0
        
        aggregate = {
            'overall_status': overall_status.value,
            'total_components': total_components,
            'healthy_components': healthy_components,
            'degraded_components': degraded_components,
            'unhealthy_components': unhealthy_components,
            'average_uptime': average_uptime,
            'components': {
                component_id: {
                    'status': health.status.value,
                    'uptime_percentage': health.uptime_percentage,
                    'last_check': health.last_check.isoformat(),
                    'consecutive_failures': health.consecutive_failures,
                    'dependencies': list(health.dependencies)
                }
                for component_id, health in self.component_health.items()
            },
            'timestamp': datetime.now().isoformat()
        }
        
        # Cache result
        self._aggregate_cache = {overall_status.value: (aggregate, time.time())}
        
        return aggregate
    
    async def start(self):
        """Start health monitoring."""
        self._running = True
        
        # Start monitoring tasks for each component
        for component_id, health_check in self.health_checks.items():
            self._tasks[component_id] = asyncio.create_task(
                self._monitor_component(component_id, health_check)
            )
    
    async def stop(self):
        """Stop health monitoring."""
        self._running = False
        
        # Cancel all monitoring tasks
        for task in self._tasks.values():
            task.cancel()
        
        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        
        self._tasks.clear()
    
    async def _monitor_component(self, component_id: str, health_check: HealthCheck):
        """Monitor a component continuously."""
        while self._running:
            try:
                await self.check_component(component_id)
                await asyncio.sleep(health_check.interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error monitoring component {component_id}: {e}")
                await asyncio.sleep(health_check.interval)
    
    async def _send_alert(self, component_id: str, old_status: HealthStatus, new_status: HealthStatus):
        """Send alert for status change."""
        try:
            alert_data = {
                'component_id': component_id,
                'old_status': old_status.value,
                'new_status': new_status.value,
                'timestamp': datetime.now().isoformat(),
                'component_info': {
                    'type': self.component_health[component_id].component_type.value,
                    'uptime_percentage': self.component_health[component_id].uptime_percentage,
                    'consecutive_failures': self.component_health[component_id].consecutive_failures
                }
            }
            
            if asyncio.iscoroutinefunction(self.alert_callback):
                await self.alert_callback(alert_data)
            else:
                await asyncio.get_event_loop().run_in_executor(
                    None, self.alert_callback, alert_data
                )
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
    
    def get_component_history(self, component_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get health check history for a component."""
        if component_id not in self.component_health:
            return []
        
        history = list(self.component_health[component_id].history)
        if limit:
            history = history[-limit:]
        
        return history
    
    def get_dependency_tree(self, component_id: str) -> Dict[str, Any]:
        """Get dependency tree for a component."""
        def build_tree(comp_id: str, visited: Set[str]) -> Dict[str, Any]:
            if comp_id in visited:
                return {'id': comp_id, 'circular': True}
            
            visited.add(comp_id)
            
            component = self.component_health.get(comp_id)
            if not component:
                return {'id': comp_id, 'status': 'unknown'}
            
            tree = {
                'id': comp_id,
                'status': component.status.value,
                'type': component.component_type.value,
                'dependencies': []
            }
            
            for dep_id in self.dependency_graph.get_dependencies(comp_id):
                tree['dependencies'].append(build_tree(dep_id, visited.copy()))
            
            return tree
        
        return build_tree(component_id, set())