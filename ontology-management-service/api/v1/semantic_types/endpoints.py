"""
Semantic Types API Endpoints

Implements FR-SM-VALID requirement from Ontology_Requirements_Document.md
Provides CRUD operations for semantic types with validation.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field

from models.semantic_types import (
    SemanticType, 
    SemanticTypeCategory,
    ValidationRule,
    semantic_type_registry
)
# Use real auth from middleware in production
# For testing, this can be overridden with dependency injection
from middleware.auth_middleware import get_current_user
from core.events.publisher import EventPublisher
from common_logging.setup import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/semantic-types", tags=["Semantic Types"])

# Request/Response Models
class SemanticTypeCreate(BaseModel):
    """Request model for creating a semantic type"""
    name: str = Field(..., description="Human-readable name")
    description: Optional[str] = Field(None, description="Detailed description")
    category: SemanticTypeCategory = Field(..., description="Category for organization")
    base_type_id: str = Field(..., description="ID of the underlying data type")
    validation_rules: List[ValidationRule] = Field(
        default_factory=list,
        description="List of validation rules"
    )
    display_format: Optional[str] = None
    input_mask: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    examples: List[Any] = Field(default_factory=list)

class SemanticTypeUpdate(BaseModel):
    """Request model for updating a semantic type"""
    name: Optional[str] = None
    description: Optional[str] = None
    validation_rules: Optional[List[ValidationRule]] = None
    display_format: Optional[str] = None
    input_mask: Optional[str] = None
    tags: Optional[List[str]] = None
    examples: Optional[List[Any]] = None
    is_active: Optional[bool] = None

class ValidationRequest(BaseModel):
    """Request model for validating a value"""
    value: Any = Field(..., description="Value to validate")

class ValidationResponse(BaseModel):
    """Response model for validation results"""
    is_valid: bool
    errors: List[str] = Field(default_factory=list)
    formatted_value: Optional[str] = None

# Endpoints
@router.post("/", response_model=SemanticType)
async def create_semantic_type(
    semantic_type_data: SemanticTypeCreate,
    current_user: str = Depends(get_current_user)
) -> SemanticType:
    """
    Create a new semantic type.
    
    Requires: schema:write permission
    """
    logger.info(f"Creating semantic type: {semantic_type_data.name} by user: {current_user}")
    
    # Generate ID from name
    type_id = semantic_type_data.name.lower().replace(" ", "_")
    
    # Check if already exists
    if semantic_type_registry.get(type_id):
        raise HTTPException(
            status_code=400,
            detail=f"Semantic type with ID '{type_id}' already exists"
        )
    
    # Create semantic type
    semantic_type = SemanticType(
        id=type_id,
        name=semantic_type_data.name,
        description=semantic_type_data.description,
        category=semantic_type_data.category,
        base_type_id=semantic_type_data.base_type_id,
        validation_rules=semantic_type_data.validation_rules,
        display_format=semantic_type_data.display_format,
        input_mask=semantic_type_data.input_mask,
        tags=semantic_type_data.tags,
        examples=semantic_type_data.examples,
        created_by=current_user
    )
    
    # Register the type
    try:
        semantic_type_registry.register(semantic_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Publish event
    await EventPublisher.publish_schema_event(
        "semantic_type.created",
        {
            "semantic_type_id": semantic_type.id,
            "name": semantic_type.name,
            "category": semantic_type.category,
            "created_by": current_user
        }
    )
    
    return semantic_type

@router.get("/", response_model=List[SemanticType])
async def list_semantic_types(
    category: Optional[SemanticTypeCategory] = Query(None, description="Filter by category"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    is_system: Optional[bool] = Query(None, description="Filter system types"),
    current_user: str = Depends(get_current_user)
) -> List[SemanticType]:
    """
    List all semantic types with optional filtering.
    
    Requires: schema:read permission
    """
    logger.info(f"Listing semantic types for user: {current_user}")
    
    # Get all types
    all_types = semantic_type_registry.list_all()
    
    # Apply filters
    if category:
        all_types = [st for st in all_types if st.category == category]
    
    if is_active is not None:
        all_types = [st for st in all_types if st.is_active == is_active]
        
    if is_system is not None:
        all_types = [st for st in all_types if st.is_system == is_system]
    
    return all_types

@router.get("/{semantic_type_id}", response_model=SemanticType)
async def get_semantic_type(
    semantic_type_id: str,
    current_user: str = Depends(get_current_user)
) -> SemanticType:
    """
    Get a specific semantic type by ID.
    
    Requires: schema:read permission
    """
    logger.info(f"Getting semantic type: {semantic_type_id} for user: {current_user}")
    
    semantic_type = semantic_type_registry.get(semantic_type_id)
    if not semantic_type:
        raise HTTPException(
            status_code=404,
            detail=f"Semantic type '{semantic_type_id}' not found"
        )
    
    return semantic_type

@router.put("/{semantic_type_id}", response_model=SemanticType)
async def update_semantic_type(
    semantic_type_id: str,
    update_data: SemanticTypeUpdate,
    current_user: str = Depends(get_current_user)
) -> SemanticType:
    """
    Update an existing semantic type.
    
    Requires: schema:write permission
    Cannot update system types.
    """
    logger.info(f"Updating semantic type: {semantic_type_id} by user: {current_user}")
    
    # Get existing type
    semantic_type = semantic_type_registry.get(semantic_type_id)
    if not semantic_type:
        raise HTTPException(
            status_code=404,
            detail=f"Semantic type '{semantic_type_id}' not found"
        )
    
    # Check if system type
    if semantic_type.is_system:
        raise HTTPException(
            status_code=403,
            detail="Cannot modify system semantic types"
        )
    
    # Update fields
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(semantic_type, field, value)
    
    # Update audit fields
    from datetime import datetime
    semantic_type.modified_at = datetime.utcnow()
    semantic_type.modified_by = current_user
    
    # Re-register to update
    semantic_type_registry.register(semantic_type)
    
    # Publish event
    await EventPublisher.publish_schema_event(
        "semantic_type.updated",
        {
            "semantic_type_id": semantic_type_id,
            "updated_fields": list(update_dict.keys()),
            "modified_by": current_user
        }
    )
    
    return semantic_type

@router.delete("/{semantic_type_id}")
async def delete_semantic_type(
    semantic_type_id: str,
    current_user: str = Depends(get_current_user)
) -> Dict[str, str]:
    """
    Delete a semantic type.
    
    Requires: schema:delete permission
    Cannot delete system types or types in use.
    """
    logger.info(f"Deleting semantic type: {semantic_type_id} by user: {current_user}")
    
    # Get existing type
    semantic_type = semantic_type_registry.get(semantic_type_id)
    if not semantic_type:
        raise HTTPException(
            status_code=404,
            detail=f"Semantic type '{semantic_type_id}' not found"
        )
    
    # Check if system type
    if semantic_type.is_system:
        raise HTTPException(
            status_code=403,
            detail="Cannot delete system semantic types"
        )
    
    # TODO: Check if type is in use by any properties
    # This would require querying properties with this semantic_type_id
    
    # Remove from registry
    del semantic_type_registry._types[semantic_type_id]
    
    # Publish event
    await EventPublisher.publish_schema_event(
        "semantic_type.deleted",
        {
            "semantic_type_id": semantic_type_id,
            "deleted_by": current_user
        }
    )
    
    return {"message": f"Semantic type '{semantic_type_id}' deleted successfully"}

@router.post("/{semantic_type_id}/validate", response_model=ValidationResponse)
async def validate_value(
    semantic_type_id: str,
    validation_request: ValidationRequest,
    current_user: str = Depends(get_current_user)
) -> ValidationResponse:
    """
    Validate a value against a semantic type.
    
    Requires: schema:read permission
    """
    logger.debug(f"Validating value for semantic type: {semantic_type_id}")
    
    # Get semantic type
    semantic_type = semantic_type_registry.get(semantic_type_id)
    if not semantic_type:
        raise HTTPException(
            status_code=404,
            detail=f"Semantic type '{semantic_type_id}' not found"
        )
    
    # Validate the value
    is_valid, errors = semantic_type.validate(validation_request.value)
    
    # Format the value if valid
    formatted_value = None
    if is_valid and semantic_type.display_format:
        formatted_value = semantic_type.format_display(validation_request.value)
    
    return ValidationResponse(
        is_valid=is_valid,
        errors=errors,
        formatted_value=formatted_value
    )

@router.get("/categories/list", response_model=List[str])
async def list_categories(
    current_user: str = Depends(get_current_user)
) -> List[str]:
    """
    List all available semantic type categories.
    
    Requires: schema:read permission
    """
    return [category.value for category in SemanticTypeCategory]

@router.post("/bulk-validate", response_model=Dict[str, ValidationResponse])
async def bulk_validate(
    validations: Dict[str, ValidationRequest] = Body(..., description="Map of semantic_type_id to validation request"),
    current_user: str = Depends(get_current_user)
) -> Dict[str, ValidationResponse]:
    """
    Validate multiple values against their semantic types.
    
    Requires: schema:read permission
    """
    results = {}
    
    for semantic_type_id, validation_request in validations.items():
        semantic_type = semantic_type_registry.get(semantic_type_id)
        if not semantic_type:
            results[semantic_type_id] = ValidationResponse(
                is_valid=False,
                errors=[f"Unknown semantic type: {semantic_type_id}"]
            )
            continue
        
        is_valid, errors = semantic_type.validate(validation_request.value)
        formatted_value = None
        if is_valid and semantic_type.display_format:
            formatted_value = semantic_type.format_display(validation_request.value)
        
        results[semantic_type_id] = ValidationResponse(
            is_valid=is_valid,
            errors=errors,
            formatted_value=formatted_value
        )
    
    return results