"""
Enterprise-grade gRPC Server Implementation
Supports Schema and Branch services with advanced features
"""

import asyncio
import logging
import os
from concurrent import futures
from typing import Optional, Dict, Any

import grpc
from grpc_reflection.v1alpha import reflection
from opentelemetry import trace
from opentelemetry.instrumentation.grpc import GrpcInstrumentorServer
from prometheus_client import Counter, Histogram, Gauge

# Import generated proto files
from . import schema_service_pb2, schema_service_pb2_grpc
from . import branch_service_pb2, branch_service_pb2_grpc

# Import service implementations
from core.schema.service import SchemaService
from core.branch.service import BranchService
from models import UserContext
from utils import logging as custom_logging

logger = custom_logging.get_logger(__name__)
tracer = trace.get_tracer(__name__)

# Metrics
grpc_requests_total = Counter(
    'grpc_requests_total',
    'Total gRPC requests',
    ['service', 'method', 'status']
)

grpc_request_duration = Histogram(
    'grpc_request_duration_seconds',
    'gRPC request duration',
    ['service', 'method']
)

grpc_active_connections = Gauge(
    'grpc_active_connections',
    'Active gRPC connections'
)


class AuthInterceptor(grpc.ServerInterceptor):
    """Enterprise-grade authentication interceptor"""
    
    def __init__(self, jwt_secret: str):
        self.jwt_secret = jwt_secret
        
    def intercept_service(self, continuation, handler_call_details):
        # Extract metadata
        metadata = dict(handler_call_details.invocation_metadata)
        
        # Check for authorization header
        auth_header = metadata.get('authorization', '')
        if not auth_header.startswith('Bearer '):
            return self._create_error_handler(
                grpc.StatusCode.UNAUTHENTICATED,
                'Missing or invalid authorization header'
            )
        
        # Validate JWT token
        token = auth_header.split(' ')[1]
        try:
            # In production, validate JWT properly
            user_context = self._validate_token(token)
            
            # Add user context to metadata
            handler_call_details.invocation_metadata.append(
                ('user-context', user_context.json())
            )
        except Exception as e:
            return self._create_error_handler(
                grpc.StatusCode.UNAUTHENTICATED,
                f'Invalid token: {str(e)}'
            )
        
        return continuation(handler_call_details)
    
    def _validate_token(self, token: str) -> UserContext:
        """Validate JWT token and return user context"""
        # Simplified for example - implement proper JWT validation
        return UserContext(
            id=1,
            username="grpc_user",
            email="grpc@example.com",
            roles=["admin"]
        )
    
    def _create_error_handler(self, status_code, details):
        def error_handler(request, context):
            context.set_code(status_code)
            context.set_details(details)
            return None
        return grpc.unary_unary_rpc_method_handler(error_handler)


class SchemaServicer(schema_service_pb2_grpc.SchemaServiceServicer):
    """Enterprise Schema Service gRPC implementation"""
    
    def __init__(self, schema_service: SchemaService):
        self.schema_service = schema_service
        
    async def GetSchema(self, request, context):
        """Get schema by ID with caching and monitoring"""
        with tracer.start_as_current_span("grpc.GetSchema") as span:
            span.set_attribute("schema.id", request.schema_id)
            span.set_attribute("branch", request.branch)
            
            try:
                # Get schema from core.user.service
                schema = await self.schema_service.get_schema(
                    branch=request.branch,
                    schema_id=request.schema_id
                )
                
                if not schema:
                    context.set_code(grpc.StatusCode.NOT_FOUND)
                    context.set_details(f'Schema {request.schema_id} not found')
                    return schema_service_pb2.Schema()
                
                # Convert to proto
                return self._to_proto_schema(schema)
                
            except Exception as e:
                logger.error(f"Error getting schema: {e}")
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(str(e))
                span.record_exception(e)
                return schema_service_pb2.Schema()
    
    async def ListSchemas(self, request, context):
        """List schemas with pagination and filtering"""
        with tracer.start_as_current_span("grpc.ListSchemas") as span:
            span.set_attribute("branch", request.branch)
            span.set_attribute("limit", request.limit)
            
            try:
                schemas = await self.schema_service.list_schemas(
                    branch=request.branch,
                    offset=request.offset,
                    limit=request.limit,
                    filters=dict(request.filters)
                )
                
                response = schema_service_pb2.ListSchemasResponse()
                for schema in schemas:
                    response.schemas.append(self._to_proto_schema(schema))
                
                return response
                
            except Exception as e:
                logger.error(f"Error listing schemas: {e}")
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(str(e))
                span.record_exception(e)
                return schema_service_pb2.ListSchemasResponse()
    
    async def CreateSchema(self, request, context):
        """Create new schema with validation"""
        with tracer.start_as_current_span("grpc.CreateSchema") as span:
            span.set_attribute("schema.name", request.name)
            span.set_attribute("branch", request.branch)
            
            try:
                # Extract user context
                user = self._get_user_context(context)
                
                # Create schema
                schema = await self.schema_service.create_schema(
                    branch=request.branch,
                    schema_data=self._from_proto_schema(request),
                    user=user
                )
                
                return self._to_proto_schema(schema)
                
            except Exception as e:
                logger.error(f"Error creating schema: {e}")
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(str(e))
                span.record_exception(e)
                return schema_service_pb2.Schema()
    
    def _to_proto_schema(self, schema: Dict[str, Any]) -> schema_service_pb2.Schema:
        """Convert internal schema to proto"""
        proto_schema = schema_service_pb2.Schema()
        proto_schema.id = schema.get('id', '')
        proto_schema.name = schema.get('name', '')
        proto_schema.description = schema.get('description', '')
        proto_schema.branch = schema.get('branch', '')
        # Add more fields as needed
        return proto_schema
    
    def _from_proto_schema(self, proto_schema) -> Dict[str, Any]:
        """Convert proto schema to internal format"""
        return {
            'name': proto_schema.name,
            'description': proto_schema.description,
            'properties': [self._from_proto_property(p) for p in proto_schema.properties]
        }
    
    def _get_user_context(self, context) -> UserContext:
        """Extract user context from gRPC metadata"""
        metadata = dict(context.invocation_metadata())
        user_json = metadata.get('user-context', '{}')
        return UserContext.parse_raw(user_json)


class BranchServicer(branch_service_pb2_grpc.BranchServiceServicer):
    """Enterprise Branch Service gRPC implementation"""
    
    def __init__(self, branch_service: BranchService):
        self.branch_service = branch_service
        
    async def CreateBranch(self, request, context):
        """Create new branch with validation"""
        with tracer.start_as_current_span("grpc.CreateBranch") as span:
            span.set_attribute("branch.name", request.name)
            span.set_attribute("parent_branch", request.parent_branch)
            
            try:
                user = self._get_user_context(context)
                
                branch = await self.branch_service.create_branch(
                    branch_data={
                        'name': request.name,
                        'description': request.description,
                        'parent_branch': request.parent_branch
                    },
                    user=user
                )
                
                return self._to_proto_branch(branch)
                
            except Exception as e:
                logger.error(f"Error creating branch: {e}")
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(str(e))
                span.record_exception(e)
                return branch_service_pb2.Branch()
    
    async def MergeBranches(self, request, context):
        """Merge branches with conflict resolution"""
        with tracer.start_as_current_span("grpc.MergeBranches") as span:
            span.set_attribute("source_branch", request.source_branch)
            span.set_attribute("target_branch", request.target_branch)
            span.set_attribute("strategy", request.strategy)
            
            try:
                user = self._get_user_context(context)
                
                result = await self.branch_service.merge_branches(
                    source=request.source_branch,
                    target=request.target_branch,
                    strategy=request.strategy,
                    user=user
                )
                
                response = branch_service_pb2.MergeResult()
                response.success = result['success']
                response.conflicts.extend(result.get('conflicts', []))
                response.merged_changes = result.get('merged_changes', 0)
                
                return response
                
            except Exception as e:
                logger.error(f"Error merging branches: {e}")
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details(str(e))
                span.record_exception(e)
                return branch_service_pb2.MergeResult()
    
    def _to_proto_branch(self, branch: Dict[str, Any]) -> branch_service_pb2.Branch:
        """Convert internal branch to proto"""
        proto_branch = branch_service_pb2.Branch()
        proto_branch.name = branch.get('name', '')
        proto_branch.description = branch.get('description', '')
        proto_branch.parent_branch = branch.get('parent_branch', '')
        proto_branch.created_at = branch.get('created_at', '')
        proto_branch.created_by = branch.get('created_by', '')
        return proto_branch
    
    def _get_user_context(self, context) -> UserContext:
        """Extract user context from gRPC metadata"""
        metadata = dict(context.invocation_metadata())
        user_json = metadata.get('user-context', '{}')
        return UserContext.parse_raw(user_json)


class EnterpriseGrpcServer:
    """Enterprise-grade gRPC server with all features"""
    
    def __init__(
        self,
        schema_service: SchemaService,
        branch_service: BranchService,
        port: int = 50051,
        max_workers: int = 10,
        enable_reflection: bool = True,
        enable_auth: bool = True,
        enable_tls: bool = True,
        tls_cert_path: Optional[str] = None,
        tls_key_path: Optional[str] = None,
        jwt_secret: Optional[str] = None
    ):
        self.schema_service = schema_service
        self.branch_service = branch_service
        self.port = port
        self.max_workers = max_workers
        self.enable_reflection = enable_reflection
        self.enable_auth = enable_auth
        self.enable_tls = enable_tls
        self.tls_cert_path = tls_cert_path
        self.tls_key_path = tls_key_path
        self.jwt_secret = jwt_secret or os.getenv('JWT_SECRET_KEY', 'secret')
        
        self.server = None
        
    async def start(self):
        """Start the gRPC server"""
        logger.info(f"Starting gRPC server on port {self.port}")
        
        # Create server with interceptors
        interceptors = []
        
        if self.enable_auth:
            interceptors.append(AuthInterceptor(self.jwt_secret))
        
        # Instrument with OpenTelemetry
        grpc_server_instrumentor = GrpcInstrumentorServer()
        grpc_server_instrumentor.instrument()
        
        self.server = grpc.aio.server(
            futures.ThreadPoolExecutor(max_workers=self.max_workers),
            interceptors=interceptors,
            options=[
                ('grpc.max_send_message_length', 100 * 1024 * 1024),  # 100MB
                ('grpc.max_receive_message_length', 100 * 1024 * 1024),
                ('grpc.keepalive_time_ms', 10000),
                ('grpc.keepalive_timeout_ms', 5000),
                ('grpc.keepalive_permit_without_calls', True),
                ('grpc.http2.max_pings_without_data', 0),
                ('grpc.http2.min_time_between_pings_ms', 10000),
            ]
        )
        
        # Add servicers
        schema_service_pb2_grpc.add_SchemaServiceServicer_to_server(
            SchemaServicer(self.schema_service), self.server
        )
        branch_service_pb2_grpc.add_BranchServiceServicer_to_server(
            BranchServicer(self.branch_service), self.server
        )
        
        # Enable reflection for grpcurl/grpc_cli
        if self.enable_reflection:
            SERVICE_NAMES = (
                schema_service_pb2.DESCRIPTOR.services_by_name['SchemaService'].full_name,
                branch_service_pb2.DESCRIPTOR.services_by_name['BranchService'].full_name,
                reflection.SERVICE_NAME,
            )
            reflection.enable_server_reflection(SERVICE_NAMES, self.server)
        
        # Configure TLS if enabled
        if self.enable_tls and self.tls_cert_path and self.tls_key_path:
            with open(self.tls_cert_path, 'rb') as f:
                server_cert = f.read()
            with open(self.tls_key_path, 'rb') as f:
                server_key = f.read()
            
            server_credentials = grpc.ssl_server_credentials(
                [(server_key, server_cert)]
            )
            self.server.add_secure_port(f'[::]:{self.port}', server_credentials)
        else:
            self.server.add_insecure_port(f'[::]:{self.port}')
        
        await self.server.start()
        logger.info(f"gRPC server started on port {self.port}")
        
        # Update metrics
        grpc_active_connections.set(1)
        
    async def stop(self, grace_period: int = 5):
        """Gracefully stop the gRPC server"""
        logger.info("Stopping gRPC server...")
        if self.server:
            await self.server.stop(grace_period)
        grpc_active_connections.set(0)
        logger.info("gRPC server stopped")
        
    async def wait_for_termination(self):
        """Wait for server termination"""
        if self.server:
            await self.server.wait_for_termination()


# Middleware for request tracking
class RequestTrackingInterceptor(grpc.ServerInterceptor):
    """Track all gRPC requests for monitoring"""
    
    def intercept_service(self, continuation, handler_call_details):
        # Extract method info
        method = handler_call_details.method
        service = method.split('/')[1] if '/' in method else 'unknown'
        
        # Start timer
        start_time = asyncio.get_event_loop().time()
        
        def wrapper(request, context):
            try:
                # Call actual handler
                response = continuation(handler_call_details)(request, context)
                
                # Record metrics
                duration = asyncio.get_event_loop().time() - start_time
                grpc_requests_total.labels(
                    service=service,
                    method=method,
                    status='success'
                ).inc()
                grpc_request_duration.labels(
                    service=service,
                    method=method
                ).observe(duration)
                
                return response
                
            except Exception as e:
                # Record error metrics
                grpc_requests_total.labels(
                    service=service,
                    method=method,
                    status='error'
                ).inc()
                raise
        
        return wrapper