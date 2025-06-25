"""
OMS Action Metadata API Routes
ActionType 메타데이터 관리만 담당
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import logging

from core.action.metadata_service import ActionMetadataService
from .models import ActionTypeModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/action-types", tags=["action-types"])


class CreateActionTypeRequest(BaseModel):
    """ActionType 생성 요청"""
    name: str
    displayName: Optional[str] = None
    description: Optional[str] = None
    objectTypeId: str
    inputSchema: Dict[str, Any] = {}
    validationExpression: Optional[str] = None
    webhookUrl: Optional[str] = None
    isBatchable: bool = True
    isAsync: bool = False
    requiresApproval: bool = False
    approvalRoles: List[str] = []
    maxRetries: int = 3
    timeoutSeconds: int = 300
    implementation: str = "webhook"


class UpdateActionTypeRequest(BaseModel):
    """ActionType 업데이트 요청"""
    name: Optional[str] = None
    displayName: Optional[str] = None
    description: Optional[str] = None
    inputSchema: Optional[Dict[str, Any]] = None
    validationExpression: Optional[str] = None
    webhookUrl: Optional[str] = None
    isBatchable: Optional[bool] = None
    isAsync: Optional[bool] = None
    requiresApproval: Optional[bool] = None
    approvalRoles: Optional[List[str]] = None
    maxRetries: Optional[int] = None
    timeoutSeconds: Optional[int] = None
    status: Optional[str] = None


class ValidateActionInputRequest(BaseModel):
    """액션 입력 검증 요청"""
    parameters: Dict[str, Any]


# Action Metadata Service 인스턴스
action_metadata_service = ActionMetadataService()


@router.post("", response_model=ActionTypeModel)
async def create_action_type(request: CreateActionTypeRequest):
    """
    ActionType 정의 생성
    
    OMS의 핵심 기능: 액션 메타데이터 정의
    """
    try:
        action_type = await action_metadata_service.create_action_type(
            request.model_dump()
        )
        return action_type
        
    except Exception as e:
        logger.error(f"Failed to create ActionType: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{action_type_id}", response_model=ActionTypeModel)
async def get_action_type(action_type_id: str):
    """
    ActionType 조회
    
    Actions Service에서 메타데이터 조회 시 사용
    """
    try:
        action_type = await action_metadata_service.get_action_type(action_type_id)
        
        if not action_type:
            raise HTTPException(status_code=404, detail="ActionType not found")
        
        return action_type
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get ActionType: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{action_type_id}", response_model=ActionTypeModel)
async def update_action_type(action_type_id: str, request: UpdateActionTypeRequest):
    """ActionType 업데이트"""
    try:
        # None이 아닌 필드만 업데이트
        updates = {k: v for k, v in request.model_dump().items() if v is not None}
        
        action_type = await action_metadata_service.update_action_type(
            action_type_id, updates
        )
        return action_type
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update ActionType: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{action_type_id}")
async def delete_action_type(action_type_id: str):
    """ActionType 삭제"""
    try:
        success = await action_metadata_service.delete_action_type(action_type_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="ActionType not found")
        
        return {"message": "ActionType deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete ActionType: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=List[ActionTypeModel])
async def list_action_types(
    object_type_id: Optional[str] = None,
    status: Optional[str] = None
):
    """ActionType 목록 조회"""
    try:
        action_types = await action_metadata_service.list_action_types(
            object_type_id=object_type_id,
            status=status
        )
        return action_types
        
    except Exception as e:
        logger.error(f"Failed to list ActionTypes: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{action_type_id}/validate")
async def validate_action_input(
    action_type_id: str, 
    request: ValidateActionInputRequest
):
    """
    액션 입력 검증
    
    Actions Service에서 실행 전 검증 시 사용
    """
    try:
        validation_result = await action_metadata_service.validate_action_input(
            action_type_id, request.parameters
        )
        return validation_result
        
    except Exception as e:
        logger.error(f"Failed to validate action input: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-object/{object_type_id}", response_model=List[ActionTypeModel])
async def get_actions_for_object_type(object_type_id: str):
    """
    특정 ObjectType에 대한 액션 목록 조회
    
    Workshop UI에서 사용 가능한 액션 표시 시 사용
    """
    try:
        action_types = await action_metadata_service.list_action_types(
            object_type_id=object_type_id,
            status="active"
        )
        return action_types
        
    except Exception as e:
        logger.error(f"Failed to get actions for object type: {e}")
        raise HTTPException(status_code=500, detail=str(e))