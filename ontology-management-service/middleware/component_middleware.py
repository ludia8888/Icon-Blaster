"""
Enterprise-grade component middleware system.

Features:
- Middleware pipeline with execution order
- Request/response transformation
- Component lifecycle management
- Cross-cutting concerns (logging, monitoring, security)
- Dependency injection
- Component isolation
- Performance optimization
- Error boundaries
"""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Set, Tuple, Type, TypeVar, Union
from contextvars import ContextVar
import inspect
import logging
import traceback
from collections import defaultdict, OrderedDict
import functools

logger = logging.getLogger(__name__)

T = TypeVar('T')

# Context variables for middleware
middleware_context: ContextVar[Dict[str, Any]] = ContextVar('middleware_context', default={})
component_context: ContextVar[Dict[str, Any]] = ContextVar('component_context', default={})


class MiddlewarePhase(Enum):
    """Middleware execution phases."""
    PRE_INIT = "pre_init"
    POST_INIT = "post_init"
    PRE_PROCESS = "pre_process"
    POST_PROCESS = "post_process"
    PRE_CLEANUP = "pre_cleanup"
    POST_CLEANUP = "post_cleanup"
    ERROR = "error"


class ComponentState(Enum):
    """Component lifecycle states."""
    CREATED = "created"
    INITIALIZING = "initializing"
    INITIALIZED = "initialized"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class MiddlewareContext:
    """Context passed through middleware pipeline."""
    component_name: str
    phase: MiddlewarePhase
    request: Any = None
    response: Any = None
    error: Optional[Exception] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    
    @property
    def elapsed_time(self) -> float:
        """Get elapsed time."""
        return time.time() - self.start_time
    
    def add_metadata(self, key: str, value: Any):
        """Add metadata."""
        self.metadata[key] = value
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """Get metadata."""
        return self.metadata.get(key, default)


@dataclass
class ComponentInfo:
    """Component information."""
    name: str
    component_type: str
    version: str
    dependencies: Set[str] = field(default_factory=set)
    config: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    state: ComponentState = ComponentState.CREATED
    created_at: datetime = field(default_factory=datetime.now)
    
    def __hash__(self):
        return hash(self.name)


class Middleware(ABC):
    """Base middleware class."""
    
    def __init__(self, name: Optional[str] = None, order: int = 0):
        self.name = name or self.__class__.__name__
        self.order = order
        self.enabled = True
    
    @abstractmethod
    async def process(self, context: MiddlewareContext, next_middleware: Callable) -> Any:
        """Process middleware."""
        pass
    
    def supports_phase(self, phase: MiddlewarePhase) -> bool:
        """Check if middleware supports phase."""
        return True


class Component(ABC):
    """Base component class."""
    
    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.config = config or {}
        self.state = ComponentState.CREATED
        self.info = ComponentInfo(
            name=name,
            component_type=self.__class__.__name__,
            version="1.0.0",
            config=self.config
        )
        self._middleware_pipeline: Optional['MiddlewarePipeline'] = None
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize component."""
        pass
    
    @abstractmethod
    async def start(self) -> None:
        """Start component."""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Stop component."""
        pass
    
    @abstractmethod
    async def process(self, request: Any) -> Any:
        """Process request."""
        pass
    
    async def cleanup(self) -> None:
        """Cleanup component resources."""
        pass
    
    def set_middleware_pipeline(self, pipeline: 'MiddlewarePipeline'):
        """Set middleware pipeline."""
        self._middleware_pipeline = pipeline


class MiddlewarePipeline:
    """Manages middleware execution pipeline."""
    
    def __init__(self):
        self.middleware: Dict[MiddlewarePhase, List[Middleware]] = defaultdict(list)
        self._global_middleware: List[Middleware] = []
    
    def add_middleware(
        self,
        middleware: Middleware,
        phases: Optional[List[MiddlewarePhase]] = None
    ):
        """Add middleware to pipeline."""
        if phases:
            for phase in phases:
                self.middleware[phase].append(middleware)
                self.middleware[phase].sort(key=lambda m: m.order)
        else:
            self._global_middleware.append(middleware)
            self._global_middleware.sort(key=lambda m: m.order)
    
    def remove_middleware(self, middleware_name: str):
        """Remove middleware from pipeline."""
        # Remove from phase-specific middleware
        for phase_middleware in self.middleware.values():
            phase_middleware[:] = [m for m in phase_middleware if m.name != middleware_name]
        
        # Remove from global middleware
        self._global_middleware[:] = [m for m in self._global_middleware if m.name != middleware_name]
    
    async def execute(
        self,
        context: MiddlewareContext,
        handler: Callable
    ) -> Any:
        """Execute middleware pipeline."""
        # Get middleware for phase
        phase_middleware = self.middleware.get(context.phase, [])
        all_middleware = self._global_middleware + phase_middleware
        
        # Filter enabled middleware that support the phase
        active_middleware = [
            m for m in all_middleware
            if m.enabled and m.supports_phase(context.phase)
        ]
        
        # Create middleware chain
        async def execute_chain(index: int) -> Any:
            if index >= len(active_middleware):
                # End of chain, execute handler
                return await handler(context)
            
            middleware = active_middleware[index]
            
            async def next_middleware(ctx: MiddlewareContext) -> Any:
                return await execute_chain(index + 1)
            
            return await middleware.process(context, next_middleware)
        
        # Execute chain
        return await execute_chain(0)


# Built-in Middleware Implementations

class LoggingMiddleware(Middleware):
    """Logging middleware."""
    
    def __init__(self, log_level: int = logging.INFO):
        super().__init__("LoggingMiddleware", order=10)
        self.log_level = log_level
    
    async def process(self, context: MiddlewareContext, next_middleware: Callable) -> Any:
        """Log component operations."""
        logger.log(
            self.log_level,
            f"[{context.component_name}] {context.phase.value} started",
            extra={
                'component': context.component_name,
                'phase': context.phase.value,
                'metadata': context.metadata
            }
        )
        
        try:
            result = await next_middleware(context)
            
            logger.log(
                self.log_level,
                f"[{context.component_name}] {context.phase.value} completed in {context.elapsed_time:.3f}s",
                extra={
                    'component': context.component_name,
                    'phase': context.phase.value,
                    'elapsed_time': context.elapsed_time,
                    'metadata': context.metadata
                }
            )
            
            return result
            
        except Exception as e:
            logger.error(
                f"[{context.component_name}] {context.phase.value} failed: {str(e)}",
                extra={
                    'component': context.component_name,
                    'phase': context.phase.value,
                    'error': str(e),
                    'traceback': traceback.format_exc()
                }
            )
            raise


class MetricsMiddleware(Middleware):
    """Metrics collection middleware."""
    
    def __init__(self):
        super().__init__("MetricsMiddleware", order=20)
        self.metrics: Dict[str, Dict[str, Any]] = defaultdict(lambda: defaultdict(int))
    
    async def process(self, context: MiddlewareContext, next_middleware: Callable) -> Any:
        """Collect metrics."""
        component_metrics = self.metrics[context.component_name]
        phase_key = f"{context.phase.value}_count"
        component_metrics[phase_key] += 1
        
        try:
            result = await next_middleware(context)
            component_metrics[f"{context.phase.value}_success"] += 1
            
            # Record timing
            timing_key = f"{context.phase.value}_time"
            if timing_key not in component_metrics:
                component_metrics[timing_key] = []
            component_metrics[timing_key].append(context.elapsed_time)
            
            return result
            
        except Exception as e:
            component_metrics[f"{context.phase.value}_error"] += 1
            raise
    
    def get_metrics(self, component_name: Optional[str] = None) -> Dict[str, Any]:
        """Get collected metrics."""
        if component_name:
            return dict(self.metrics.get(component_name, {}))
        return {k: dict(v) for k, v in self.metrics.items()}


class TracingMiddleware(Middleware):
    """Distributed tracing middleware."""
    
    def __init__(self):
        super().__init__("TracingMiddleware", order=15)
        self.traces: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    
    async def process(self, context: MiddlewareContext, next_middleware: Callable) -> Any:
        """Add tracing."""
        trace_id = context.get_metadata('trace_id') or self._generate_trace_id()
        span_id = self._generate_span_id()
        
        context.add_metadata('trace_id', trace_id)
        context.add_metadata('span_id', span_id)
        
        span = {
            'trace_id': trace_id,
            'span_id': span_id,
            'component': context.component_name,
            'phase': context.phase.value,
            'start_time': context.start_time,
            'metadata': context.metadata.copy()
        }
        
        try:
            result = await next_middleware(context)
            span['status'] = 'success'
            span['end_time'] = time.time()
            span['duration'] = span['end_time'] - span['start_time']
            
            return result
            
        except Exception as e:
            span['status'] = 'error'
            span['error'] = str(e)
            span['end_time'] = time.time()
            span['duration'] = span['end_time'] - span['start_time']
            raise
        
        finally:
            self.traces[trace_id].append(span)
    
    def _generate_trace_id(self) -> str:
        """Generate trace ID."""
        import uuid
        return str(uuid.uuid4())
    
    def _generate_span_id(self) -> str:
        """Generate span ID."""
        import uuid
        return str(uuid.uuid4())[:8]


class RetryMiddleware(Middleware):
    """Retry middleware for transient failures."""
    
    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        exponential_backoff: bool = True
    ):
        super().__init__("RetryMiddleware", order=30)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.exponential_backoff = exponential_backoff
    
    async def process(self, context: MiddlewareContext, next_middleware: Callable) -> Any:
        """Process with retry logic."""
        retries = 0
        last_error = None
        
        while retries <= self.max_retries:
            try:
                return await next_middleware(context)
            
            except Exception as e:
                last_error = e
                if not self._is_retryable(e) or retries >= self.max_retries:
                    raise
                
                retries += 1
                delay = self._calculate_delay(retries)
                
                logger.warning(
                    f"Retry {retries}/{self.max_retries} for {context.component_name} "
                    f"after {delay:.1f}s delay: {str(e)}"
                )
                
                await asyncio.sleep(delay)
        
        raise last_error
    
    def _is_retryable(self, error: Exception) -> bool:
        """Check if error is retryable."""
        # Customize based on error types
        retryable_errors = (
            ConnectionError,
            TimeoutError,
            asyncio.TimeoutError
        )
        return isinstance(error, retryable_errors)
    
    def _calculate_delay(self, retry_count: int) -> float:
        """Calculate retry delay."""
        if self.exponential_backoff:
            return self.retry_delay * (2 ** (retry_count - 1))
        return self.retry_delay


class CachingMiddleware(Middleware):
    """Caching middleware for component responses."""
    
    def __init__(self, ttl: float = 300.0):
        super().__init__("CachingMiddleware", order=25)
        self.ttl = ttl
        self.cache: Dict[str, Tuple[Any, float]] = {}
    
    async def process(self, context: MiddlewareContext, next_middleware: Callable) -> Any:
        """Process with caching."""
        # Only cache process phase
        if context.phase != MiddlewarePhase.PRE_PROCESS:
            return await next_middleware(context)
        
        # Generate cache key
        cache_key = self._generate_cache_key(context)
        
        # Check cache
        if cache_key in self.cache:
            result, cached_at = self.cache[cache_key]
            if time.time() - cached_at < self.ttl:
                context.add_metadata('cache_hit', True)
                return result
        
        # Process and cache
        result = await next_middleware(context)
        self.cache[cache_key] = (result, time.time())
        context.add_metadata('cache_hit', False)
        
        # Cleanup old entries
        self._cleanup_cache()
        
        return result
    
    def _generate_cache_key(self, context: MiddlewareContext) -> str:
        """Generate cache key."""
        import hashlib
        import json
        
        key_data = {
            'component': context.component_name,
            'request': str(context.request)
        }
        
        return hashlib.md5(json.dumps(key_data, sort_keys=True).encode()).hexdigest()
    
    def _cleanup_cache(self):
        """Cleanup expired cache entries."""
        current_time = time.time()
        expired_keys = [
            key for key, (_, cached_at) in self.cache.items()
            if current_time - cached_at > self.ttl
        ]
        
        for key in expired_keys:
            del self.cache[key]


class ValidationMiddleware(Middleware):
    """Request/response validation middleware."""
    
    def __init__(self):
        super().__init__("ValidationMiddleware", order=40)
        self.validators: Dict[str, Dict[str, Callable]] = defaultdict(dict)
    
    def register_validator(
        self,
        component_name: str,
        phase: MiddlewarePhase,
        validator: Callable[[Any], bool]
    ):
        """Register validator for component."""
        key = f"{component_name}:{phase.value}"
        self.validators[key]['validator'] = validator
    
    async def process(self, context: MiddlewareContext, next_middleware: Callable) -> Any:
        """Validate request/response."""
        # Validate request
        if context.phase == MiddlewarePhase.PRE_PROCESS:
            key = f"{context.component_name}:{context.phase.value}"
            if key in self.validators:
                validator = self.validators[key]['validator']
                if not validator(context.request):
                    raise ValueError(f"Request validation failed for {context.component_name}")
        
        result = await next_middleware(context)
        
        # Validate response
        if context.phase == MiddlewarePhase.POST_PROCESS:
            key = f"{context.component_name}:{context.phase.value}"
            if key in self.validators:
                validator = self.validators[key]['validator']
                if not validator(result):
                    raise ValueError(f"Response validation failed for {context.component_name}")
        
        return result


class SecurityMiddleware(Middleware):
    """Security middleware for authentication and authorization."""
    
    def __init__(self):
        super().__init__("SecurityMiddleware", order=5)
        self.permissions: Dict[str, Set[str]] = defaultdict(set)
    
    def set_permissions(self, component_name: str, required_permissions: Set[str]):
        """Set required permissions for component."""
        self.permissions[component_name] = required_permissions
    
    async def process(self, context: MiddlewareContext, next_middleware: Callable) -> Any:
        """Check security permissions."""
        # Only check on process phase
        if context.phase != MiddlewarePhase.PRE_PROCESS:
            return await next_middleware(context)
        
        # Get user permissions from context
        user_permissions = context.get_metadata('user_permissions', set())
        required_permissions = self.permissions.get(context.component_name, set())
        
        # Check permissions
        if required_permissions and not required_permissions.issubset(user_permissions):
            missing = required_permissions - user_permissions
            raise PermissionError(
                f"Missing permissions for {context.component_name}: {missing}"
            )
        
        return await next_middleware(context)


class ComponentManager:
    """Manages components with middleware support."""
    
    def __init__(self):
        self.components: Dict[str, Component] = {}
        self.middleware_pipeline = MiddlewarePipeline()
        self.dependency_graph: Dict[str, Set[str]] = defaultdict(set)
        self._running = False
        
        # Add default middleware
        self.middleware_pipeline.add_middleware(LoggingMiddleware())
        self.middleware_pipeline.add_middleware(MetricsMiddleware())
        self.middleware_pipeline.add_middleware(TracingMiddleware())
    
    def register_component(self, component: Component, dependencies: Optional[List[str]] = None):
        """Register a component."""
        self.components[component.name] = component
        component.set_middleware_pipeline(self.middleware_pipeline)
        
        if dependencies:
            self.dependency_graph[component.name].update(dependencies)
            component.info.dependencies.update(dependencies)
    
    def add_middleware(self, middleware: Middleware, phases: Optional[List[MiddlewarePhase]] = None):
        """Add middleware to all components."""
        self.middleware_pipeline.add_middleware(middleware, phases)
    
    async def initialize_component(self, component_name: str):
        """Initialize a component."""
        component = self.components.get(component_name)
        if not component:
            raise ValueError(f"Component {component_name} not found")
        
        # Check dependencies
        for dep in self.dependency_graph.get(component_name, []):
            dep_component = self.components.get(dep)
            if not dep_component or dep_component.state != ComponentState.RUNNING:
                raise RuntimeError(f"Dependency {dep} not running for {component_name}")
        
        # Create context
        context = MiddlewareContext(
            component_name=component_name,
            phase=MiddlewarePhase.PRE_INIT
        )
        
        # Execute through middleware
        async def init_handler(ctx: MiddlewareContext):
            component.state = ComponentState.INITIALIZING
            await component.initialize()
            component.state = ComponentState.INITIALIZED
        
        await self.middleware_pipeline.execute(context, init_handler)
    
    async def start_component(self, component_name: str):
        """Start a component."""
        component = self.components.get(component_name)
        if not component:
            raise ValueError(f"Component {component_name} not found")
        
        if component.state != ComponentState.INITIALIZED:
            await self.initialize_component(component_name)
        
        # Create context
        context = MiddlewareContext(
            component_name=component_name,
            phase=MiddlewarePhase.PRE_PROCESS
        )
        
        # Execute through middleware
        async def start_handler(ctx: MiddlewareContext):
            component.state = ComponentState.STARTING
            await component.start()
            component.state = ComponentState.RUNNING
        
        await self.middleware_pipeline.execute(context, start_handler)
    
    async def stop_component(self, component_name: str):
        """Stop a component."""
        component = self.components.get(component_name)
        if not component:
            raise ValueError(f"Component {component_name} not found")
        
        # Check dependents
        dependents = [
            name for name, deps in self.dependency_graph.items()
            if component_name in deps and self.components[name].state == ComponentState.RUNNING
        ]
        
        if dependents:
            raise RuntimeError(f"Cannot stop {component_name}, required by: {dependents}")
        
        # Create context
        context = MiddlewareContext(
            component_name=component_name,
            phase=MiddlewarePhase.PRE_CLEANUP
        )
        
        # Execute through middleware
        async def stop_handler(ctx: MiddlewareContext):
            component.state = ComponentState.STOPPING
            await component.stop()
            await component.cleanup()
            component.state = ComponentState.STOPPED
        
        await self.middleware_pipeline.execute(context, stop_handler)
    
    async def process_request(self, component_name: str, request: Any) -> Any:
        """Process request through component."""
        component = self.components.get(component_name)
        if not component:
            raise ValueError(f"Component {component_name} not found")
        
        if component.state != ComponentState.RUNNING:
            raise RuntimeError(f"Component {component_name} not running")
        
        # Create context
        context = MiddlewareContext(
            component_name=component_name,
            phase=MiddlewarePhase.PRE_PROCESS,
            request=request
        )
        
        # Execute through middleware
        async def process_handler(ctx: MiddlewareContext):
            return await component.process(ctx.request)
        
        result = await self.middleware_pipeline.execute(context, process_handler)
        
        # Post-process phase
        context.phase = MiddlewarePhase.POST_PROCESS
        context.response = result
        
        async def post_handler(ctx: MiddlewareContext):
            return ctx.response
        
        return await self.middleware_pipeline.execute(context, post_handler)
    
    async def start_all(self):
        """Start all components in dependency order."""
        self._running = True
        
        # Topological sort for startup order
        started = set()
        
        async def start_with_deps(component_name: str):
            if component_name in started:
                return
            
            # Start dependencies first
            for dep in self.dependency_graph.get(component_name, []):
                await start_with_deps(dep)
            
            # Start component
            await self.start_component(component_name)
            started.add(component_name)
        
        for component_name in self.components:
            await start_with_deps(component_name)
    
    async def stop_all(self):
        """Stop all components in reverse dependency order."""
        self._running = False
        
        # Stop in reverse order
        running_components = [
            name for name, comp in self.components.items()
            if comp.state == ComponentState.RUNNING
        ]
        
        while running_components:
            # Find components with no running dependents
            stoppable = []
            for name in running_components:
                dependents = [
                    dep_name for dep_name, deps in self.dependency_graph.items()
                    if name in deps and dep_name in running_components
                ]
                if not dependents:
                    stoppable.append(name)
            
            # Stop them
            for name in stoppable:
                await self.stop_component(name)
                running_components.remove(name)
    
    def get_component_info(self, component_name: str) -> Optional[ComponentInfo]:
        """Get component information."""
        component = self.components.get(component_name)
        return component.info if component else None
    
    def get_all_components_info(self) -> Dict[str, ComponentInfo]:
        """Get information for all components."""
        return {name: comp.info for name, comp in self.components.items()}
    
    def get_middleware_metrics(self) -> Dict[str, Any]:
        """Get metrics from metrics middleware."""
        for middleware in self.middleware_pipeline._global_middleware:
            if isinstance(middleware, MetricsMiddleware):
                return middleware.get_metrics()
        return {}