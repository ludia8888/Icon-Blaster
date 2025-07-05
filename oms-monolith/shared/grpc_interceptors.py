"""
gRPC interceptors for authentication, tracing, and metadata propagation
"""
import grpc
import logging
from typing import Callable, Any
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class ClientAuthInterceptor(grpc.aio.UnaryUnaryClientInterceptor, grpc.aio.UnaryStreamClientInterceptor):
    """Client interceptor that adds authentication and tracing metadata."""
    
    def __init__(self, get_auth_token: Callable[[], str] = None, get_user_context: Callable[[], Any] = None):
        self.get_auth_token = get_auth_token
        self.get_user_context = get_user_context
    
    async def intercept_unary_unary(self, continuation, client_call_details, request):
        """Intercept unary-unary calls."""
        metadata = self._inject_metadata(client_call_details.metadata)
        new_details = client_call_details._replace(metadata=metadata)
        return await continuation(new_details, request)
    
    async def intercept_unary_stream(self, continuation, client_call_details, request):
        """Intercept unary-stream calls."""
        metadata = self._inject_metadata(client_call_details.metadata)
        new_details = client_call_details._replace(metadata=metadata)
        return await continuation(new_details, request)
    
    def _inject_metadata(self, metadata):
        """Inject auth and tracing metadata."""
        metadata = list(metadata) if metadata else []
        
        # Add authentication token if available
        if self.get_auth_token:
            try:
                token = self.get_auth_token()
                if token:
                    metadata.append(('authorization', f'Bearer {token}'))
            except Exception as e:
                logger.warning(f"Failed to get auth token: {e}")
        
        # Add user context if available
        if self.get_user_context:
            try:
                user_context = self.get_user_context()
                if user_context:
                    metadata.append(('x-user-id', str(user_context.user_id)))
                    metadata.append(('x-username', user_context.username))
                    if hasattr(user_context, 'tenant_id') and user_context.tenant_id:
                        metadata.append(('x-tenant-id', user_context.tenant_id))
            except Exception as e:
                logger.warning(f"Failed to get user context: {e}")
        
        # Add OpenTelemetry trace context
        span = trace.get_current_span()
        if span and span.is_recording():
            ctx = span.get_span_context()
            traceparent = f"00-{format(ctx.trace_id, '032x')}-{format(ctx.span_id, '016x')}-01"
            metadata.append(('traceparent', traceparent))
        
        return metadata


def get_client_interceptor(auth_token_func=None, user_context_func=None):
    """Factory function to create client interceptor with auth callbacks."""
    return ClientAuthInterceptor(auth_token_func, user_context_func)


class ServerAuthInterceptor(grpc.aio.ServerInterceptor):
    """Server interceptor that extracts auth and tracing metadata."""
    
    async def intercept_service(self, continuation, handler_call_details):
        """Intercept incoming requests to extract metadata."""
        # Extract metadata
        metadata = dict(handler_call_details.invocation_metadata or [])
        
        # Extract trace context and create span
        traceparent = metadata.get('traceparent')
        if traceparent:
            # Parse traceparent and set up OpenTelemetry context
            # Format: version-trace_id-span_id-flags
            parts = traceparent.split('-')
            if len(parts) >= 4:
                trace_id = int(parts[1], 16)
                parent_span_id = int(parts[2], 16)
                # Create a new span with the parent context
                # This would be done properly with OpenTelemetry SDK
        
        # Extract user information
        user_info = {
            'user_id': metadata.get('x-user-id', 'anonymous'),
            'username': metadata.get('x-username', 'anonymous'),
            'tenant_id': metadata.get('x-tenant-id'),
            'authorization': metadata.get('authorization')
        }
        
        # Store in context (would be properly done with contextvars)
        # For now, we'll log it
        logger.debug(f"Request metadata: user={user_info['username']}, trace={traceparent}")
        
        # Continue with the request
        return await continuation(handler_call_details)


def get_server_interceptor():
    """Factory function to create server interceptor."""
    return ServerAuthInterceptor()


# Convenience function to create client with all interceptors
def create_instrumented_channel(target: str, auth_token_func=None, user_context_func=None):
    """Create a gRPC channel with all necessary interceptors."""
    from opentelemetry.instrumentation.grpc import client_interceptor as otel_client_interceptor
    
    interceptors = [
        otel_client_interceptor(),  # OpenTelemetry auto-instrumentation
        get_client_interceptor(auth_token_func, user_context_func)  # Our custom interceptor
    ]
    
    return grpc.aio.insecure_channel(target, interceptors=interceptors)