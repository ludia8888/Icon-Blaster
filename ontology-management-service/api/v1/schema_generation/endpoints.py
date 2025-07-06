"""
API Endpoints for Schema Generation - Refactored with DI

Implements Phase 5 requirements: GraphQL and OpenAPI schema generation
with automatic link field generation.
"""

from typing import Dict, Any, Optional, Annotated
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from pydantic import BaseModel, Field

from bootstrap.dependencies import get_schema_service
from core.interfaces import SchemaServiceProtocol
from core.api.schema_generator import (
    graphql_generator, 
    openapi_generator
)
from core.schema.registry import schema_registry
from middleware.auth_middleware import get_current_user
from common_logging.setup import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/schema-generation", tags=["Schema Generation"])


class GraphQLGenerateRequest(BaseModel):
    """Request model for GraphQL schema generation"""
    object_type_ids: Optional[list[str]] = Field(
        None, 
        description="Specific object types to include. If empty, includes all active types."
    )
    include_inactive: bool = Field(
        False,
        description="Include inactive object types"
    )
    export_metadata: bool = Field(
        True,
        description="Include link field metadata in response"
    )


class OpenAPIGenerateRequest(BaseModel):
    """Request model for OpenAPI schema generation"""
    object_type_ids: Optional[list[str]] = Field(
        None,
        description="Specific object types to include. If empty, includes all active types."
    )
    include_inactive: bool = Field(
        False,
        description="Include inactive object types"
    )
    api_info: Dict[str, Any] = Field(
        default_factory=lambda: {
            "title": "OMS API",
            "version": "1.0.0",
            "description": "Ontology Management Service API"
        },
        description="OpenAPI info section"
    )


class SchemaGenerationResponse(BaseModel):
    """Response model for schema generation"""
    format: str
    schema: str
    metadata: Optional[Dict[str, Any]] = None
    generated_at: str
    object_types_included: list[str]
    link_types_included: list[str]


@router.post("/graphql", response_model=SchemaGenerationResponse)
async def generate_graphql_schema(
    request: GraphQLGenerateRequest,
    schema_service: Annotated[SchemaServiceProtocol, Depends(get_schema_service)],
    current_user: str = Depends(get_current_user)
) -> SchemaGenerationResponse:
    """
    Generate GraphQL schema for object types with automatic link fields.
    
    This generates the GraphQL SDL (Schema Definition Language) that includes:
    - Object type definitions
    - Automatic SingleLink/LinkSet fields for relationships
    - Input types for mutations
    - Query and mutation operations
    - Connection types for pagination
    
    Requires: schema:read permission
    """
    logger.info(f"Generating GraphQL schema for user: {current_user}")
    
    try:
        # Get object types
        if request.object_type_ids:
            object_types = []
            for type_id in request.object_type_ids:
                obj_type = await schema_registry.get_object_type(type_id)
                if not obj_type:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Object type '{type_id}' not found"
                    )
                object_types.append(obj_type)
        else:
            # Get all active object types
            all_types = await schema_registry.list_object_types()
            object_types = [
                t for t in all_types 
                if request.include_inactive or t.status.value == "ACTIVE"
            ]
        
        # Get all link types
        all_link_types = await schema_registry.list_link_types()
        
        # Filter link types relevant to selected object types
        object_type_ids = {t.id for t in object_types}
        relevant_link_types = [
            lt for lt in all_link_types
            if lt.fromTypeId in object_type_ids or lt.toTypeId in object_type_ids
        ]
        
        # Generate schema
        sdl = graphql_generator.generate_complete_schema(
            object_types,
            relevant_link_types
        )
        
        # Prepare response
        from datetime import datetime
        response = SchemaGenerationResponse(
            format="graphql",
            schema=sdl,
            metadata=graphql_generator.export_schema_metadata() if request.export_metadata else None,
            generated_at=datetime.utcnow().isoformat(),
            object_types_included=[t.id for t in object_types],
            link_types_included=[lt.id for lt in relevant_link_types]
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error generating GraphQL schema: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate GraphQL schema: {str(e)}"
        )


@router.post("/openapi", response_model=SchemaGenerationResponse)
async def generate_openapi_schema(
    request: OpenAPIGenerateRequest,
    schema_service: Annotated[SchemaServiceProtocol, Depends(get_schema_service)],
    current_user: str = Depends(get_current_user)
) -> SchemaGenerationResponse:
    """
    Generate OpenAPI 3.0 specification for object types with HAL-style links.
    
    This generates an OpenAPI spec that includes:
    - Object schemas with _links and _embedded for relationships
    - CRUD operation paths
    - Link navigation endpoints
    - Common parameters and responses
    
    Requires: schema:read permission
    """
    logger.info(f"Generating OpenAPI schema for user: {current_user}")
    
    try:
        # Get object types (similar to GraphQL)
        if request.object_type_ids:
            object_types = []
            for type_id in request.object_type_ids:
                obj_type = await schema_registry.get_object_type(type_id)
                if not obj_type:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Object type '{type_id}' not found"
                    )
                object_types.append(obj_type)
        else:
            all_types = await schema_registry.list_object_types()
            object_types = [
                t for t in all_types
                if request.include_inactive or t.status.value == "ACTIVE"
            ]
        
        # Get relevant link types
        all_link_types = await schema_registry.list_link_types()
        object_type_ids = {t.id for t in object_types}
        relevant_link_types = [
            lt for lt in all_link_types
            if lt.fromTypeId in object_type_ids or lt.toTypeId in object_type_ids
        ]
        
        # Generate OpenAPI spec
        spec = openapi_generator.generate_complete_spec(
            object_types,
            relevant_link_types,
            request.api_info
        )
        
        # Convert spec to JSON string
        import json
        spec_json = json.dumps(spec, indent=2)
        
        # Prepare response
        from datetime import datetime
        response = SchemaGenerationResponse(
            format="openapi",
            schema=spec_json,
            metadata=None,  # OpenAPI spec is self-contained
            generated_at=datetime.utcnow().isoformat(),
            object_types_included=[t.id for t in object_types],
            link_types_included=[lt.id for lt in relevant_link_types]
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Error generating OpenAPI schema: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate OpenAPI schema: {str(e)}"
        )


@router.get("/link-metadata/{object_type_id}")
async def get_link_metadata(
    object_type_id: str,
    schema_service: Annotated[SchemaServiceProtocol, Depends(get_schema_service)],
    current_user: str = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get link field metadata for a specific object type.
    
    This returns information about all the link fields that would be
    generated for an object type, including:
    - Field names and types (SingleLink vs LinkSet)
    - Target object types
    - Directionality and cardinality
    - Resolver hints
    
    Requires: schema:read permission
    """
    logger.info(f"Getting link metadata for {object_type_id} for user: {current_user}")
    
    # Check if object type exists
    obj_type = await schema_registry.get_object_type(object_type_id)
    if not obj_type:
        raise HTTPException(
            status_code=404,
            detail=f"Object type '{object_type_id}' not found"
        )
    
    # Get all link types
    all_link_types = await schema_registry.list_link_types()
    
    # Generate metadata for this type
    graphql_generator.generate_object_type_schema(obj_type, all_link_types)
    
    # Get link fields
    link_fields = graphql_generator.link_fields.get(object_type_id, [])
    
    return {
        "object_type_id": object_type_id,
        "object_type_name": obj_type.name,
        "link_fields": [field.dict() for field in link_fields],
        "total_fields": len(link_fields)
    }


@router.post("/export/{format}")
async def export_schema(
    format: str,
    schema_service: Annotated[SchemaServiceProtocol, Depends(get_schema_service)],
    current_user: str = Depends(get_current_user),
    filename: Optional[str] = Query(None, description="Custom filename for export")
) -> Dict[str, str]:
    """
    Export generated schema to a file.
    
    Formats:
    - graphql: Exports as .graphql SDL file
    - openapi: Exports as .json OpenAPI spec file
    
    Requires: schema:read permission
    """
    logger.info(f"Exporting {format} schema for user: {current_user}")
    
    try:
        # Get all active types
        all_object_types = await schema_registry.list_object_types()
        active_types = [t for t in all_object_types if t.status.value == "ACTIVE"]
        all_link_types = await schema_registry.list_link_types()
        
        # Generate schema based on format
        from datetime import datetime
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        if format == "graphql":
            schema_content = graphql_generator.generate_complete_schema(
                active_types,
                all_link_types
            )
            default_filename = f"oms_schema_{timestamp}.graphql"
            content_type = "text/plain"
        else:  # openapi
            spec = openapi_generator.generate_complete_spec(
                active_types,
                all_link_types,
                {
                    "title": "OMS API",
                    "version": "1.0.0",
                    "description": "Auto-generated OpenAPI specification"
                }
            )
            import json
            schema_content = json.dumps(spec, indent=2)
            default_filename = f"oms_openapi_{timestamp}.json"
            content_type = "application/json"
        
        # Use custom filename if provided
        export_filename = filename or default_filename
        
        # Save to exports directory
        import os
        export_dir = "exports/schemas"
        os.makedirs(export_dir, exist_ok=True)
        
        export_path = os.path.join(export_dir, export_filename)
        with open(export_path, "w") as f:
            f.write(schema_content)
        
        return {
            "filename": export_filename,
            "path": export_path,
            "format": format,
            "content_type": content_type,
            "size_bytes": str(len(schema_content)),
            "exported_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error exporting {format} schema: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to export schema: {str(e)}"
        )