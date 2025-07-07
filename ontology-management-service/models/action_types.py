# Action types for schema service
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ActionCategory(str, Enum):
    """Action category enumeration"""
    TRANSFORMATION = "transformation"
    VALIDATION = "validation"
    NOTIFICATION = "notification"
    INTEGRATION = "integration"
    CUSTOM = "custom"

class TransformationType(str, Enum):
    """Transformation type enumeration"""
    MAPPING = "mapping"
    ENRICHMENT = "enrichment"
    AGGREGATION = "aggregation"
    FILTERING = "filtering"
    CUSTOM = "custom"

class ApplicableObjectType(BaseModel):
    """Applicable object type model"""
    object_type_id: str
    object_type_name: str
    version: Optional[str] = None

class ActionType(BaseModel):
    """Base action type model"""
    id: str
    name: str
    description: Optional[str] = None
    category: ActionCategory
    is_async: bool = False
    timeout_seconds: Optional[int] = None
    retry_config: Optional[Dict[str, Any]] = None
    applicable_object_types: List[ApplicableObjectType] = Field(default_factory=list)
    required_permissions: List[str] = Field(default_factory=list)
    configuration_schema: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ActionTypeCreate(BaseModel):
    """Create action type request model"""
    name: str
    description: Optional[str] = None
    category: ActionCategory
    is_async: bool = False
    timeout_seconds: Optional[int] = None
    retry_config: Optional[Dict[str, Any]] = None
    applicable_object_types: List[ApplicableObjectType] = Field(default_factory=list)
    required_permissions: List[str] = Field(default_factory=list)
    configuration_schema: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ActionTypeUpdate(BaseModel):
    """Update action type request model"""
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[ActionCategory] = None
    is_async: Optional[bool] = None
    timeout_seconds: Optional[int] = None
    retry_config: Optional[Dict[str, Any]] = None
    applicable_object_types: Optional[List[ApplicableObjectType]] = None
    required_permissions: Optional[List[str]] = None
    configuration_schema: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

class CreateAction(ActionType):
    """Create action type"""
    action_type: str = "create"
    target_type: str
    target_id: str

class UpdateAction(ActionType):
    """Update action type"""
    action_type: str = "update"
    target_type: str
    target_id: str
    changes: Dict[str, Any]

class DeleteAction(ActionType):
    """Delete action type"""
    action_type: str = "delete"
    target_type: str
    target_id: str

class EventAction(ActionType):
    """Event-based action type"""
    action_type: str = "event"
    event_name: str
    payload: Dict[str, Any]

class ParameterSchema(BaseModel):
    """Parameter schema for action types"""
    name: str
    type: str
    description: Optional[str] = None
    required: bool = True
    default: Any = None
    validation: Optional[Dict[str, Any]] = None

class ActionTypeReference(BaseModel):
    """Reference to an action type"""
    action_type_id: str
    action_type_name: str
    version: Optional[str] = None

class ActionTypeValidator(BaseModel):
    """Validator for action types"""
    name: str
    type: str
    config: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
