"""
Jaeger distributed tracing adapter for OMS graph analysis operations.
Integrates with OpenTelemetry and existing SIEM infrastructure.
"""
import os
import functools
from typing import Dict, Any, Optional, Callable, TypeVar
try:
    from typing import ParamSpec
except ImportError:
    # Python 3.9 compatibility
    from typing_extensions import ParamSpec
from contextlib import asynccontextmanager
import asyncio

from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.asyncio import AsyncIOInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.propagate import inject, extract
from opentelemetry.trace.status import Status, StatusCode

from ...infra.siem.adapter import SIEMAdapter
from common_logging.setup import get_logger

logger = get_logger(__name__)

P = ParamSpec('P')
T = TypeVar('T')


class JaegerConfig:
    """Configuration for Jaeger tracing."""
    
    def __init__(self):
        self.enabled = os.getenv("JAEGER_ENABLED", "false").lower() == "true"
        self.agent_host = os.getenv("JAEGER_AGENT_HOST", "localhost")
        self.agent_port = int(os.getenv("JAEGER_AGENT_PORT", "14268"))
        self.service_name = os.getenv("JAEGER_SERVICE_NAME", "oms-monolith")
        self.service_version = os.getenv("JAEGER_SERVICE_VERSION", "1.0.0")
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.max_tag_value_length = int(os.getenv("JAEGER_MAX_TAG_LENGTH", "1024"))
        self.sampling_rate = float(os.getenv("JAEGER_SAMPLING_RATE", "0.1"))
        
        # SIEM integration
        self.siem_enabled = os.getenv("SIEM_TRACING_ENABLED", "true").lower() == "true"
        
    def get_resource(self) -> Resource:
        """Get OpenTelemetry resource configuration."""
        return Resource.create({
            "service.name": self.service_name,
            "service.version": self.service_version,
            "service.environment": self.environment,
            "service.instance.id": os.getenv("HOSTNAME", "unknown"),
        })


class JaegerTracingManager:
    """
    Manages Jaeger distributed tracing with SIEM integration.
    """
    
    def __init__(self, config: Optional[JaegerConfig] = None):
        self.config = config or JaegerConfig()
        self.tracer_provider: Optional[TracerProvider] = None
        self.tracer: Optional[trace.Tracer] = None
        self.siem_adapter: Optional[SIEMAdapter] = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize Jaeger tracing."""
        if self._initialized or not self.config.enabled:
            return
        
        try:
            # Create tracer provider
            self.tracer_provider = TracerProvider(
                resource=self.config.get_resource()
            )
            
            # Configure Jaeger exporter
            jaeger_exporter = JaegerExporter(
                agent_host_name=self.config.agent_host,
                agent_port=self.config.agent_port,
            )
            
            # Add batch span processor
            span_processor = BatchSpanProcessor(jaeger_exporter)
            self.tracer_provider.add_span_processor(span_processor)
            
            # Add console exporter for development
            if self.config.environment == "development":
                console_exporter = ConsoleSpanExporter()
                console_processor = BatchSpanProcessor(console_exporter)
                self.tracer_provider.add_span_processor(console_processor)
            
            # Set global tracer provider
            trace.set_tracer_provider(self.tracer_provider)
            
            # Get tracer
            self.tracer = trace.get_tracer(__name__)
            
            # Initialize auto-instrumentation
            self._setup_auto_instrumentation()
            
            # Initialize SIEM integration
            if self.config.siem_enabled:
                await self._initialize_siem_integration()
            
            self._initialized = True
            logger.info(f"Jaeger tracing initialized: {self.config.agent_host}:{self.config.agent_port}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Jaeger tracing: {e}")
            self.config.enabled = False
    
    def _setup_auto_instrumentation(self):
        """Setup automatic instrumentation for common libraries."""
        try:
            # Instrument asyncio
            AsyncIOInstrumentor().instrument()
            
            # Instrument Redis
            RedisInstrumentor().instrument()
            
            # Instrument HTTP requests
            RequestsInstrumentor().instrument()
            
            logger.info("Auto-instrumentation setup complete")
            
        except Exception as e:
            logger.warning(f"Failed to setup auto-instrumentation: {e}")
    
    async def _initialize_siem_integration(self):
        """Initialize SIEM adapter for security event correlation."""
        try:
            self.siem_adapter = SIEMAdapter()
            await self.siem_adapter.initialize()
            logger.info("SIEM tracing integration initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize SIEM integration: {e}")
            self.siem_adapter = None
    
    def create_span(self, name: str, 
                   kind: trace.SpanKind = trace.SpanKind.INTERNAL,
                   attributes: Optional[Dict[str, Any]] = None) -> trace.Span:
        """Create a new tracing span."""
        if not self._initialized or not self.tracer:
            return trace.NoOpSpan()
        
        span = self.tracer.start_span(
            name=name,
            kind=kind,
            attributes=self._sanitize_attributes(attributes or {})
        )
        
        return span
    
    @asynccontextmanager
    async def trace_operation(self, operation_name: str, 
                            operation_type: str = "graph_analysis",
                            **attributes):
        """Context manager for tracing operations."""
        if not self._initialized or not self.tracer:
            yield None
            return
        
        # Add standard attributes
        span_attributes = {
            "operation.type": operation_type,
            "operation.name": operation_name,
            "service.component": "graph_analysis",
            **attributes
        }
        
        with self.tracer.start_as_current_span(
            name=f"{operation_type}.{operation_name}",
            kind=trace.SpanKind.INTERNAL,
            attributes=self._sanitize_attributes(span_attributes)
        ) as span:
            try:
                # Record operation start
                if self.siem_adapter:
                    await self._record_operation_event("start", operation_name, span)
                
                yield span
                
                # Mark span as successful
                span.set_status(Status(StatusCode.OK))
                
                # Record operation success
                if self.siem_adapter:
                    await self._record_operation_event("success", operation_name, span)
                    
            except Exception as e:
                # Record error in span
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                
                # Record operation failure
                if self.siem_adapter:
                    await self._record_operation_event("error", operation_name, span, error=str(e))
                
                raise
    
    def trace_function(self, operation_name: Optional[str] = None,
                      operation_type: str = "function",
                      include_args: bool = False,
                      include_result: bool = False):
        """Decorator for tracing function calls."""
        def decorator(func: Callable[P, T]) -> Callable[P, T]:
            span_name = operation_name or f"{func.__module__}.{func.__name__}"
            
            if asyncio.iscoroutinefunction(func):
                @functools.wraps(func)
                async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                    attributes = {"function.name": func.__name__}
                    
                    if include_args:
                        attributes.update(self._extract_safe_args(args, kwargs))
                    
                    async with self.trace_operation(span_name, operation_type, **attributes) as span:
                        if span:
                            result = await func(*args, **kwargs)
                            
                            if include_result and span:
                                span.set_attribute("function.result_type", type(result).__name__)
                                if hasattr(result, '__len__'):
                                    span.set_attribute("function.result_length", len(result))
                            
                            return result
                        else:
                            return await func(*args, **kwargs)
                
                return async_wrapper
            else:
                @functools.wraps(func)
                def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                    if not self._initialized or not self.tracer:
                        return func(*args, **kwargs)
                    
                    attributes = {"function.name": func.__name__}
                    
                    if include_args:
                        attributes.update(self._extract_safe_args(args, kwargs))
                    
                    with self.tracer.start_as_current_span(
                        name=span_name,
                        attributes=self._sanitize_attributes(attributes)
                    ) as span:
                        try:
                            result = func(*args, **kwargs)
                            
                            if include_result:
                                span.set_attribute("function.result_type", type(result).__name__)
                                if hasattr(result, '__len__'):
                                    span.set_attribute("function.result_length", len(result))
                            
                            span.set_status(Status(StatusCode.OK))
                            return result
                            
                        except Exception as e:
                            span.record_exception(e)
                            span.set_status(Status(StatusCode.ERROR, str(e)))
                            raise
                
                return sync_wrapper
        
        return decorator
    
    def add_span_attributes(self, span: trace.Span, attributes: Dict[str, Any]):
        """Add attributes to an existing span."""
        if span and span.is_recording():
            for key, value in self._sanitize_attributes(attributes).items():
                span.set_attribute(key, value)
    
    def record_graph_query(self, span: trace.Span, 
                          query_type: str,
                          node_count: int = 0,
                          edge_count: int = 0,
                          cache_hit: bool = False,
                          query_duration: float = 0.0):
        """Record graph query specific metrics."""
        if not span or not span.is_recording():
            return
        
        span.set_attributes({
            "graph.query.type": query_type,
            "graph.nodes.count": node_count,
            "graph.edges.count": edge_count,
            "graph.cache.hit": cache_hit,
            "graph.query.duration_ms": query_duration * 1000
        })
    
    def record_path_analysis(self, span: trace.Span,
                           source_node: str,
                           target_node: Optional[str],
                           strategy: str,
                           paths_found: int = 0,
                           max_depth: int = 0):
        """Record path analysis specific metrics."""
        if not span or not span.is_recording():
            return
        
        attributes = {
            "path.analysis.strategy": strategy,
            "path.analysis.paths_found": paths_found,
            "path.analysis.max_depth": max_depth,
            "path.source.node": source_node
        }
        
        if target_node:
            attributes["path.target.node"] = target_node
        
        span.set_attributes(attributes)
    
    def _sanitize_attributes(self, attributes: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize attributes for Jaeger compliance."""
        sanitized = {}
        
        for key, value in attributes.items():
            # Ensure key is string
            str_key = str(key)
            
            # Convert value to appropriate type
            if isinstance(value, (str, int, float, bool)):
                str_value = str(value)
                # Truncate long values
                if len(str_value) > self.config.max_tag_value_length:
                    str_value = str_value[:self.config.max_tag_value_length] + "..."
                sanitized[str_key] = str_value
            elif isinstance(value, (list, dict)):
                # Convert complex types to JSON string
                import json
                try:
                    json_str = json.dumps(value)
                    if len(json_str) > self.config.max_tag_value_length:
                        json_str = json_str[:self.config.max_tag_value_length] + "..."
                    sanitized[str_key] = json_str
                except (TypeError, ValueError):
                    sanitized[str_key] = str(type(value).__name__)
            else:
                sanitized[str_key] = str(type(value).__name__)
        
        return sanitized
    
    def _extract_safe_args(self, args: tuple, kwargs: dict) -> Dict[str, Any]:
        """Extract safe argument information for tracing."""
        safe_args = {}
        
        # Extract basic argument count
        safe_args["function.args_count"] = len(args)
        safe_args["function.kwargs_count"] = len(kwargs)
        
        # Extract safe kwargs (avoid sensitive data)
        safe_kwargs = {}
        for key, value in kwargs.items():
            if not any(sensitive in key.lower() for sensitive in 
                      ['password', 'token', 'key', 'secret', 'auth']):
                if isinstance(value, (str, int, float, bool)):
                    safe_kwargs[key] = value
                elif isinstance(value, list):
                    safe_kwargs[f"{key}_length"] = len(value)
                else:
                    safe_kwargs[f"{key}_type"] = type(value).__name__
        
        if safe_kwargs:
            safe_args["function.safe_kwargs"] = safe_kwargs
        
        return safe_args
    
    async def _record_operation_event(self, event_type: str, operation_name: str, 
                                    span: trace.Span, error: Optional[str] = None):
        """Record operation event in SIEM system."""
        if not self.siem_adapter:
            return
        
        try:
            event_data = {
                "event_type": f"graph_operation_{event_type}",
                "operation_name": operation_name,
                "trace_id": format(span.get_span_context().trace_id, "032x"),
                "span_id": format(span.get_span_context().span_id, "016x"),
                "service_name": self.config.service_name,
                "timestamp": "2025-01-01T00:00:00Z"  # Would be actual timestamp
            }
            
            if error:
                event_data["error"] = error
                event_data["severity"] = "error"
            else:
                event_data["severity"] = "info"
            
            await self.siem_adapter.log_event(event_data)
            
        except Exception as e:
            logger.warning(f"Failed to record SIEM event: {e}")
    
    async def shutdown(self):
        """Shutdown tracing and cleanup resources."""
        if self.tracer_provider:
            # Force flush all spans
            if hasattr(self.tracer_provider, 'force_flush'):
                self.tracer_provider.force_flush(timeout_millis=5000)
            
            # Shutdown span processors
            if hasattr(self.tracer_provider, 'shutdown'):
                self.tracer_provider.shutdown()
        
        if self.siem_adapter:
            await self.siem_adapter.shutdown()
        
        self._initialized = False
        logger.info("Jaeger tracing shutdown complete")


# Global tracing manager instance
_tracing_manager: Optional[JaegerTracingManager] = None

async def get_tracing_manager() -> JaegerTracingManager:
    """Get global tracing manager instance."""
    global _tracing_manager
    
    if _tracing_manager is None:
        _tracing_manager = JaegerTracingManager()
        await _tracing_manager.initialize()
    
    return _tracing_manager

async def shutdown_tracing():
    """Shutdown global tracing manager."""
    global _tracing_manager
    
    if _tracing_manager:
        await _tracing_manager.shutdown()
        _tracing_manager = None

# Convenience decorators
def trace_graph_operation(operation_name: Optional[str] = None,
                         include_args: bool = False,
                         include_result: bool = False):
    """Decorator for tracing graph operations."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            tracing_manager = await get_tracing_manager()
            
            if not tracing_manager._initialized:
                return await func(*args, **kwargs)
            
            decorated_func = tracing_manager.trace_function(
                operation_name=operation_name,
                operation_type="graph_operation",
                include_args=include_args,
                include_result=include_result
            )(func)
            
            return await decorated_func(*args, **kwargs)
        
        return wrapper
    return decorator

def trace_path_analysis(operation_name: Optional[str] = None):
    """Decorator for tracing path analysis operations."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            tracing_manager = await get_tracing_manager()
            
            if not tracing_manager._initialized:
                return await func(*args, **kwargs)
            
            decorated_func = tracing_manager.trace_function(
                operation_name=operation_name,
                operation_type="path_analysis",
                include_args=True,
                include_result=True
            )(func)
            
            return await decorated_func(*args, **kwargs)
        
        return wrapper
    return decorator