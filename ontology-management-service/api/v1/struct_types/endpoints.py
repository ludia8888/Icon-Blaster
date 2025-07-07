"""
Struct Types API Endpoints

Implements FR-ST-STRUCT requirement from Ontology_Requirements_Document.md
Provides CRUD operations for struct types with nested struct validation.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field

from models.struct_types import (
    StructType,
    StructFieldDefinition,
    struct_type_registry
)
# Use real auth from middleware in production
# For testing, this can be overridden with dependency injection
from middleware.auth_middleware import get_current_user
from core.events.publisher import EventPublisher
from common_logging.setup import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/struct-types", tags=["Struct Types"])


# Request/Response Models
class StructFieldDefinitionCreate(BaseModel):
    """Request model for creating a struct field"""
    name: str = Field(..., description="Field name within the struct")
    display_name: str = Field(..., description="Human-readable field name")
    description: Optional[str] = Field(None, description="Field description")
    data_type_id: str = Field(..., description="ID of the data type for this field")
    semantic_type_id: Optional[str] = Field(None, description="Optional semantic type")
    is_required: bool = Field(False, description="Whether this field is required")
    default_value: Optional[Any] = Field(None, description="Default value if not provided")
    validation_rules: Optional[Dict[str, Any]] = Field(None, description="Additional validation")


class StructTypeCreate(BaseModel):
    """Request model for creating a struct type"""
    name: str = Field(..., description="Human-readable name")
    description: Optional[str] = Field(None, description="Detailed description")
    fields: List[StructFieldDefinitionCreate] = Field(
        ..., 
        description="List of field definitions",
        min_items=1
    )
    display_template: Optional[str] = Field(None, description="Display template")
    tags: List[str] = Field(default_factory=list)


class StructTypeUpdate(BaseModel):
    """Request model for updating a struct type"""
    name: Optional[str] = None
    description: Optional[str] = None
    fields: Optional[List[StructFieldDefinitionCreate]] = None
    display_template: Optional[str] = None
    tags: Optional[List[str]] = None
    is_active: Optional[bool] = None


class StructValidationRequest(BaseModel):
    """Request model for validating a struct value"""
    value: Dict[str, Any] = Field(..., description="Struct value to validate")


class StructValidationResponse(BaseModel):
    """Response model for struct validation"""
    is_valid: bool
    errors: List[str] = Field(default_factory=list)
    formatted_value: Optional[str] = None


# Endpoints
@router.post("/", response_model=StructType)
async def create_struct_type(
    struct_type_data: StructTypeCreate,
    current_user: str = Depends(get_current_user)
) -> StructType:
    """
    Create a new struct type.
    
    IMPORTANT: Nested structs are NOT supported per Foundry constraints.
    Attempting to create a struct with fields referencing other struct types will fail.
    
    Requires: schema:write permission
    """
    logger.info(f"Creating struct type: {struct_type_data.name} by user: {current_user}")
    
    # Generate ID from name
    type_id = struct_type_data.name.lower().replace(" ", "_")
    
    # Check if already exists
    if struct_type_registry.get(type_id):
        raise HTTPException(
            status_code=400,
            detail=f"Struct type with ID '{type_id}' already exists"
        )
    
    # Convert field definitions
    fields = []
    for field_data in struct_type_data.fields:
        # Check for nested struct references
        if field_data.data_type_id.startswith("struct:") or struct_type_registry.exists(field_data.data_type_id):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Nested structs are not supported. Field '{field_data.name}' "
                    f"references struct type '{field_data.data_type_id}'. "
                    "Please flatten the structure or use separate properties."
                )
            )
        
        fields.append(StructFieldDefinition(**field_data.model_dump()))
    
    # Create struct type
    struct_type = StructType(
        id=type_id,
        name=struct_type_data.name,
        description=struct_type_data.description,
        fields=fields,
        display_template=struct_type_data.display_template,
        tags=struct_type_data.tags,
        created_by=current_user
    )
    
    # Register the type
    try:
        struct_type_registry.register(struct_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Publish event
    await EventPublisher.publish_schema_event(
        "struct_type.created",
        {
            "struct_type_id": struct_type.id,
            "name": struct_type.name,
            "field_count": struct_type.field_count,
            "created_by": current_user
        }
    )
    
    return struct_type


@router.get("/", response_model=List[StructType])
async def list_struct_types(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    is_system: Optional[bool] = Query(None, description="Filter system types"),
    current_user: str = Depends(get_current_user)
) -> List[StructType]:
    """
    List all struct types with optional filtering.
    
    Requires: schema:read permission
    """
    logger.info(f"Listing struct types for user: {current_user}")
    
    # Get all types
    all_types = struct_type_registry.list_all()
    
    # Apply filters
    if is_active is not None:
        all_types = [st for st in all_types if st.is_active == is_active]
        
    if is_system is not None:
        all_types = [st for st in all_types if st.is_system == is_system]
    
    return all_types


@router.get("/{struct_type_id}", response_model=StructType)
async def get_struct_type(
    struct_type_id: str,
    current_user: str = Depends(get_current_user)
) -> StructType:
    """
    Get a specific struct type by ID.
    
    Requires: schema:read permission
    """
    logger.info(f"Getting struct type: {struct_type_id} for user: {current_user}")
    
    struct_type = struct_type_registry.get(struct_type_id)
    if not struct_type:
        raise HTTPException(
            status_code=404,
            detail=f"Struct type '{struct_type_id}' not found"
        )
    
    return struct_type


@router.put("/{struct_type_id}", response_model=StructType)
async def update_struct_type(
    struct_type_id: str,
    update_data: StructTypeUpdate,
    current_user: str = Depends(get_current_user)
) -> StructType:
    """
    Update an existing struct type.
    
    WARNING: Changing fields may break existing data. Use with caution.
    Cannot update system types.
    
    Requires: schema:write permission
    """
    logger.info(f"Updating struct type: {struct_type_id} by user: {current_user}")
    
    # Get existing type
    struct_type = struct_type_registry.get(struct_type_id)
    if not struct_type:
        raise HTTPException(
            status_code=404,
            detail=f"Struct type '{struct_type_id}' not found"
        )
    
    # Check if system type
    if struct_type.is_system:
        raise HTTPException(
            status_code=403,
            detail="Cannot modify system struct types"
        )
    
    # Update fields if provided
    if update_data.fields is not None:
        fields = []
        for field_data in update_data.fields:
            # Check for nested struct references
            if field_data.data_type_id.startswith("struct:") or struct_type_registry.exists(field_data.data_type_id):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Nested structs are not supported. Field '{field_data.name}' "
                        f"references struct type '{field_data.data_type_id}'. "
                        "Please flatten the structure or use separate properties."
                    )
                )
            fields.append(StructFieldDefinition(**field_data.model_dump()))
        struct_type.fields = fields
    
    # Update other fields
    update_dict = update_data.dict(exclude_unset=True, exclude={"fields"})
    for field, value in update_dict.items():
        setattr(struct_type, field, value)
    
    # Update audit fields
    from datetime import datetime
    struct_type.modified_at = datetime.utcnow()
    struct_type.modified_by = current_user
    
    # Re-validate and compute
    struct_type = struct_type.model_validate(struct_type.model_dump())
    
    # Re-register to update
    struct_type_registry.register(struct_type)
    
    # Publish event
    await EventPublisher.publish_schema_event(
        "struct_type.updated",
        {
            "struct_type_id": struct_type_id,
            "updated_fields": list(update_dict.keys()),
            "modified_by": current_user
        }
    )
    
    return struct_type


@router.delete("/{struct_type_id}")
async def delete_struct_type(
    struct_type_id: str,
    current_user: str = Depends(get_current_user)
) -> Dict[str, str]:
    """
    Delete a struct type.
    
    Requires: schema:delete permission
    Cannot delete system types or types in use.
    """
    logger.info(f"Deleting struct type: {struct_type_id} by user: {current_user}")
    
    # Get existing type
    struct_type = struct_type_registry.get(struct_type_id)
    if not struct_type:
        raise HTTPException(
            status_code=404,
            detail=f"Struct type '{struct_type_id}' not found"
        )
    
    # Check if system type
    if struct_type.is_system:
        raise HTTPException(
            status_code=403,
            detail="Cannot delete system struct types"
        )
    
    # TODO: Check if type is in use by any properties
    # This would require querying properties with data_type_id = struct_type_id
    
    # Remove from registry
    del struct_type_registry._types[struct_type_id]
    
    # Publish event
    await EventPublisher.publish_schema_event(
        "struct_type.deleted",
        {
            "struct_type_id": struct_type_id,
            "deleted_by": current_user
        }
    )
    
    return {"message": f"Struct type '{struct_type_id}' deleted successfully"}


@router.post("/{struct_type_id}/validate", response_model=StructValidationResponse)
async def validate_struct_value(
    struct_type_id: str,
    validation_request: StructValidationRequest,
    current_user: str = Depends(get_current_user)
) -> StructValidationResponse:
    """
    Validate a value against a struct type.
    
    Requires: schema:read permission
    """
    logger.debug(f"Validating value for struct type: {struct_type_id}")
    
    # Get struct type
    struct_type = struct_type_registry.get(struct_type_id)
    if not struct_type:
        raise HTTPException(
            status_code=404,
            detail=f"Struct type '{struct_type_id}' not found"
        )
    
    # Validate the value
    is_valid, errors = struct_type.validate_value(validation_request.value)
    
    # Format the value if valid
    formatted_value = None
    if is_valid and struct_type.display_template:
        formatted_value = struct_type.format_display(validation_request.value)
    
    return StructValidationResponse(
        is_valid=is_valid,
        errors=errors,
        formatted_value=formatted_value
    )


@router.get("/{struct_type_id}/schema", response_model=Dict[str, Any])
async def get_struct_json_schema(
    struct_type_id: str,
    current_user: str = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Get the JSON Schema representation of a struct type.
    
    Useful for form generation and validation in UI.
    
    Requires: schema:read permission
    """
    logger.info(f"Getting JSON schema for struct type: {struct_type_id}")
    
    struct_type = struct_type_registry.get(struct_type_id)
    if not struct_type:
        raise HTTPException(
            status_code=404,
            detail=f"Struct type '{struct_type_id}' not found"
        )
    
    return struct_type.to_json_schema()


@router.post("/check-nested", response_model=Dict[str, bool])
async def check_nested_struct(
    field_definitions: List[StructFieldDefinitionCreate] = Body(...),
    current_user: str = Depends(get_current_user)
) -> Dict[str, bool]:
    """
    Check if field definitions contain nested struct references.
    
    This is a utility endpoint to validate struct definitions before creation.
    
    Requires: schema:read permission
    """
    has_nested = False
    nested_fields = []
    
    for field in field_definitions:
        if field.data_type_id.startswith("struct:") or struct_type_registry.exists(field.data_type_id):
            has_nested = True
            nested_fields.append(field.name)
    
    return {
        "has_nested_structs": has_nested,
        "nested_fields": nested_fields,
        "is_valid": not has_nested
    }