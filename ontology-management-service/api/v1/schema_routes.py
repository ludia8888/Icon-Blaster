"""Schema management routes"""

from typing import Dict, Any, List, Annotated
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Path, Body, Request

from bootstrap.dependencies import get_schema_service_from_container
from core.interfaces import SchemaServiceProtocol
from middleware.auth_middleware import get_current_user
from database.dependencies import get_secure_database
from database.clients.secure_database_adapter import SecureDatabaseAdapter
from core.auth_utils import UserContext
from middleware.etag_middleware import enable_etag
from core.iam.dependencies import require_scope
from core.iam.iam_integration import IAMScope

router = APIRouter(
    prefix="/schemas", 
    tags=["Schema Management"]
)

@router.get(
    "/{branch}/object-types",
    dependencies=[Depends(require_scope([IAMScope.ONTOLOGIES_READ]))]
)
@enable_etag(
    resource_type_func=lambda params: "object_types_collection",
    resource_id_func=lambda params: f"{params['branch']}_object_types",
    branch_func=lambda params: params['branch']
)
async def list_object_types(
    branch: str,
    schema_service: Annotated[SchemaServiceProtocol, Depends(get_schema_service_from_container)],
    current_user: Annotated[UserContext, Depends(get_current_user)],
    request: Request
) -> List[Dict[str, Any]]:
    """List all object types in a branch"""
    result = await schema_service.list_schemas(
        filters={"branch": branch, "type": "object"}
    )
    return result.get("items", [])

@router.get(
    "/{branch}/object-types/{type_name}",
    dependencies=[Depends(require_scope([IAMScope.ONTOLOGIES_READ]))]
)
@enable_etag(
    resource_type_func=lambda params: "object_type",
    resource_id_func=lambda params: params['type_name'],
    branch_func=lambda params: params['branch']
)
async def get_object_type(
    branch: str,
    type_name: str,
    schema_service: Annotated[SchemaServiceProtocol, Depends(get_schema_service_from_container)],
    current_user: Annotated[UserContext, Depends(get_current_user)],
    request: Request
) -> Dict[str, Any]:
    """Get a specific object type by name."""
    schema = await schema_service.get_schema_by_name(name=type_name, branch=branch)
    if not schema:
        raise HTTPException(status_code=404, detail=f"Object type '{type_name}' not found in branch '{branch}'")
    return schema

@router.post(
    "/{branch}/object-types",
    dependencies=[Depends(require_scope([IAMScope.ONTOLOGIES_WRITE]))]
)
async def create_object_type(
    branch: str,
    object_type: Dict[str, Any],
    schema_service: Annotated[SchemaServiceProtocol, Depends(get_schema_service_from_container)],
    current_user: Annotated[UserContext, Depends(get_current_user)],
    request: Request
) -> Dict[str, Any]:
    """Create a new object type in a branch"""
    
    # 입력 데이터 검증
    if not object_type.get("name"):
        raise HTTPException(
            status_code=400,
            detail="Object type name is required"
        )
    
    try:
        # 스키마 유효성 검증
        validation_result = await schema_service.validate_schema(object_type)
        if not validation_result.get("valid"):
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Schema validation failed",
                    "errors": validation_result.get("errors", []),
                    "warnings": validation_result.get("warnings", [])
                }
            )
        
        # 스키마 생성
        created_schema = await schema_service.create_schema(
            name=object_type.get("name", ""),
            schema_def={**object_type, "branch": branch},
            created_by=current_user.user_id
        )
        
        return {
            "message": "Object type created successfully",
            "object_type": created_schema,
            "created_at": datetime.utcnow().isoformat()
        }
        
    except PermissionError as e:
        raise HTTPException(
            status_code=403,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        import traceback
        error_detail = f"Failed to create object type: {str(e)}"
        tb = traceback.format_exc()
        print(f"ERROR in create_object_type: {error_detail}")
        print(f"Traceback:\n{tb}")
        raise HTTPException(
            status_code=500,
            detail=error_detail
        )
