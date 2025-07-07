import grpc
import asyncio
import json
import logging
from typing import AsyncIterator
from concurrent import futures

from opentelemetry.instrumentation.grpc import server_interceptor

from data_kernel.service.terminus_service import TerminusService, get_service
from data_kernel.proto import data_kernel_pb2_grpc as pb2_grpc
from data_kernel.proto import data_kernel_pb2 as pb2

logger = logging.getLogger(__name__)


class DocumentServicer(pb2_grpc.DocumentServiceServicer):
    """gRPC service implementation for document operations."""
    
    def __init__(self, svc: TerminusService):
        self.svc = svc
    
    async def Get(self, request: pb2.DocumentId, context: grpc.aio.ServicerContext) -> pb2.Document:
        """Get a document by ID."""
        try:
            # Extract metadata
            meta = request.meta
            branch = meta.branch if meta and meta.branch else "main"
            
            # Log context for debugging
            logger.debug(f"Get document: db={request.database}, id={request.id}, branch={branch}")
            
            # Get document
            doc = await self.svc.get_document(
                request.database, 
                request.id,
                branch=branch
            )
            
            if doc is None:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Document {request.id} not found")
                return pb2.Document()
            
            # Return as JSON bytes with metadata
            return pb2.Document(
                json=json.dumps(doc).encode('utf-8'),
                database=request.database,
                meta=meta  # Echo back the metadata
            )
        except Exception as e:
            logger.error(f"Error getting document: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pb2.Document()
    
    async def Put(self, request: pb2.Document, context: grpc.aio.ServicerContext) -> pb2.DocumentId:
        """Create a new document."""
        try:
            # Parse document JSON
            doc_data = json.loads(request.json.decode('utf-8'))
            
            # Extract metadata
            meta = request.meta
            commit_msg = meta.commit_msg if meta else "Create document via gRPC"
            author = meta.author if meta else "system"
            
            # Log context for debugging
            logger.debug(f"Put document: db={request.database}, author={author}, branch={meta.branch if meta else 'default'}")
            
            # Insert document
            result = await self.svc.insert_document(
                request.database,
                doc_data,
                commit_msg=commit_msg,
                author=author
            )
            
            # Extract document ID from result
            doc_id = doc_data.get("@id", "")
            
            return pb2.DocumentId(
                id=doc_id,
                database=request.database
            )
        except Exception as e:
            logger.error(f"Error creating document: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pb2.DocumentId()
    
    async def Patch(self, request: pb2.Document, context: grpc.aio.ServicerContext) -> pb2.DocumentId:
        """Update an existing document."""
        try:
            # Parse update data
            update_data = json.loads(request.json.decode('utf-8'))
            doc_id = update_data.pop("@id", None)
            
            if not doc_id:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("Document must include @id field")
                return pb2.DocumentId()
            
            # Extract metadata
            meta = request.meta
            commit_msg = meta.commit_msg if meta else "Update document via gRPC"
            author = meta.author if meta else "system"
            
            # Update document
            await self.svc.update_document(
                request.database,
                doc_id,
                update_data,
                commit_msg=commit_msg,
                author=author
            )
            
            return pb2.DocumentId(
                id=doc_id,
                database=request.database
            )
        except Exception as e:
            logger.error(f"Error updating document: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pb2.DocumentId()
    
    async def Delete(self, request: pb2.DocumentId, context: grpc.aio.ServicerContext) -> pb2.Empty:
        """Delete a document."""
        try:
            # Extract metadata
            meta = request.meta
            commit_msg = meta.commit_msg if meta else f"Delete document {request.id} via gRPC"
            author = meta.author if meta else "system"
            
            # Delete document
            await self.svc.delete_document(
                request.database,
                request.id,
                commit_msg=commit_msg,
                author=author
            )
            
            return pb2.Empty()
        except Exception as e:
            logger.error(f"Error deleting document: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pb2.Empty()


class QueryServicer(pb2_grpc.QueryServiceServicer):
    """gRPC service implementation for query operations."""
    
    def __init__(self, svc: TerminusService):
        self.svc = svc
    
    async def Execute(self, request: pb2.WOQL, context: grpc.aio.ServicerContext) -> AsyncIterator[pb2.Document]:
        """Execute a WOQL query and stream results."""
        try:
            # Parse query
            query = json.loads(request.query)
            
            # Extract metadata
            meta = request.meta
            commit_msg = meta.commit_msg if meta and hasattr(meta, 'commit_msg') else None
            
            # Execute query
            result = await self.svc.query(request.database, query, commit_msg=commit_msg)
            
            # Stream results (for now, return single result)
            # In a real implementation, we'd chunk large results
            if result:
                yield pb2.Document(
                    json=json.dumps(result).encode('utf-8'),
                    database=request.database
                )
        except Exception as e:
            logger.error(f"Error executing query: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))


class SchemaServicer(pb2_grpc.SchemaServiceServicer):
    """gRPC service implementation for schema operations."""
    
    def __init__(self, svc: TerminusService):
        self.svc = svc
    
    async def Get(self, request: pb2.SchemaRequest, context: grpc.aio.ServicerContext) -> pb2.Schema:
        """Get database schema."""
        try:
            schema = await self.svc.get_schema(request.database)
            
            return pb2.Schema(
                json=json.dumps(schema).encode('utf-8'),
                database=request.database
            )
        except Exception as e:
            logger.error(f"Error getting schema: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pb2.Schema()
    
    async def Update(self, request: pb2.Schema, context: grpc.aio.ServicerContext) -> pb2.Empty:
        """Update database schema."""
        try:
            # Parse schema
            schema = json.loads(request.json.decode('utf-8'))
            
            # Extract metadata
            meta = request.meta
            commit_msg = meta.commit_msg if meta else "Update schema via gRPC"
            author = meta.author if meta else "system"
            
            # Update schema
            await self.svc.update_schema(
                request.database,
                schema,
                commit_msg=commit_msg,
                author=author
            )
            
            return pb2.Empty()
        except Exception as e:
            logger.error(f"Error updating schema: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return pb2.Empty()


class DataKernelServicer(pb2_grpc.DataKernelServiceServicer):
    """Unified gRPC service implementation for all operations."""
    
    def __init__(self, svc: TerminusService):
        self.svc = svc
        # Delegate to specialized servicers
        self.doc_servicer = DocumentServicer(svc)
        self.query_servicer = QueryServicer(svc)
        self.schema_servicer = SchemaServicer(svc)
    
    async def GetDocument(self, request: pb2.GetDocumentRequest, context: grpc.aio.ServicerContext) -> pb2.GetDocumentResponse:
        """Get a document by ID."""
        # Convert to simplified request
        doc_id = pb2.DocumentId(
            id=request.document_id,
            database=request.database,
            meta=pb2.CommitMeta(
                trace_id=request.meta.trace_id if request.meta else "",
                branch=request.branch
            )
        )
        
        # Call simplified service
        doc = await self.doc_servicer.Get(doc_id, context)
        
        return pb2.GetDocumentResponse(
            document_json=doc.json.decode('utf-8') if doc.json else "",
            revision=request.revision or "",
            branch=request.branch
        )
    
    async def CreateDocument(self, request: pb2.CreateDocumentRequest, context: grpc.aio.ServicerContext) -> pb2.CreateDocumentResponse:
        """Create a new document."""
        # Convert to simplified request
        doc = pb2.Document(
            json=request.document_json.encode('utf-8'),
            database=request.database,
            meta=pb2.CommitMeta(
                author=request.meta.user_id if request.meta else "system",
                commit_msg=request.commit_message,
                trace_id=request.meta.trace_id if request.meta else ""
            )
        )
        
        # Call simplified service
        doc_id = await self.doc_servicer.Put(doc, context)
        
        return pb2.CreateDocumentResponse(
            document_id=doc_id.id,
            revision=""  # TODO: Get actual revision from TerminusDB
        )
    
    async def HealthCheck(self, request: pb2.HealthCheckRequest, context: grpc.aio.ServicerContext) -> pb2.HealthCheckResponse:
        """Check service health."""
        try:
            health = await self.svc.health_check()
            return pb2.HealthCheckResponse(
                healthy=True,
                details={"terminus_db": "healthy", "status": str(health)}
            )
        except Exception as e:
            return pb2.HealthCheckResponse(
                healthy=False,
                details={"error": str(e)}
            )


async def serve(port: int = 50051):
    """Start the gRPC server."""
    # Initialize service
    terminus_svc = await get_service()
    
    # Create server with OpenTelemetry interceptor
    server = grpc.aio.server(
        interceptors=[server_interceptor()]
    )
    
    # Add service implementations
    pb2_grpc.add_DocumentServiceServicer_to_server(
        DocumentServicer(terminus_svc), server
    )
    pb2_grpc.add_QueryServiceServicer_to_server(
        QueryServicer(terminus_svc), server
    )
    pb2_grpc.add_SchemaServiceServicer_to_server(
        SchemaServicer(terminus_svc), server
    )
    pb2_grpc.add_DataKernelServiceServicer_to_server(
        DataKernelServicer(terminus_svc), server
    )
    
    # Enable reflection for debugging
    from grpc_reflection.v1alpha import reflection
    SERVICE_NAMES = (
        pb2.DESCRIPTOR.services_by_name['DocumentService'].full_name,
        pb2.DESCRIPTOR.services_by_name['QueryService'].full_name,
        pb2.DESCRIPTOR.services_by_name['SchemaService'].full_name,
        pb2.DESCRIPTOR.services_by_name['DataKernelService'].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)
    
    # Start server
    server.add_insecure_port(f'[::]:{port}')
    await server.start()
    
    logger.info(f"gRPC server started on port {port}")
    
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down gRPC server...")
        await server.stop(5)


if __name__ == "__main__":
    import os
    port = int(os.getenv("GRPC_PORT", "50051"))
    asyncio.run(serve(port))