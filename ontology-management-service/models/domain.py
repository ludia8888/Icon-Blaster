"""
Domain models for OMS
Referenced from Claude.md sections 9.1.1 and 8.1.3

IMPORTANT - Naming Convention Strategy (ADR-005):
1. API/Database Layer: camelCase (TerminusDB/JSON-LD standard)
2. Python Domain Models:
   - ObjectTypeCreate, PropertyCreate: snake_case (명시적으로 표시)
   - 기타 Create/Update 모델: camelCase (API 호환)
   - Domain 모델: camelCase (DB 1:1 매핑)
3. Service Layer: 명시적 변환 수행 (snake_case ↔ camelCase)

이 전략은 TerminusDB 호환성과 Python 관례 사이의 균형을 맞추기 위함입니다.
각 모델 클래스에는 설계 의도가 주석으로 명시되어 있습니다.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator
from .merge_hints import SchemaMergeMetadata


class Status(str, Enum):
    """Entity status enumeration"""
    ACTIVE = "active"
    EXPERIMENTAL = "experimental"
    DEPRECATED = "deprecated"
    EXAMPLE = "example"
    ARCHIVED = "archived"


class TypeClass(str, Enum):
    """Object type classification"""
    OBJECT = "object"
    INTERFACE = "interface"
    LINK = "link"
    EMBEDDED = "embedded"


class MergeStrategy(str, Enum):
    """필드 그룹 병합 전략"""
    PREFER_SOURCE = "prefer_source"  # 소스 브랜치의 값을 우선
    PREFER_TARGET = "prefer_target"  # 타겟 브랜치의 값을 우선
    ATOMIC_UPDATE = "atomic_update"  # 그룹 내 하나라도 변경되면 전체 업데이트
    REQUIRE_CONSENSUS = "require_consensus"  # 양쪽이 동일한 변경만 허용


class Cardinality(str, Enum):
    """Link cardinality types"""
    ONE_TO_ONE = "one-to-one"
    ONE_TO_MANY = "one-to-many"
    MANY_TO_MANY = "many-to-many"


class Directionality(str, Enum):
    """Link directionality types"""
    UNIDIRECTIONAL = "unidirectional"
    BIDIRECTIONAL = "bidirectional"


class Visibility(str, Enum):
    """Property visibility enumeration"""
    VISIBLE = "visible"
    HIDDEN = "hidden"
    ADVANCED = "advanced"


class PropertyType(str, Enum):
    """Property data types"""
    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    REFERENCE = "reference"
    ENUM = "enum"
    TEXT = "text"
    JSON = "json"


class FieldGroup(BaseModel):
    """필드 그룹 정의 - 함께 움직여야 하는 필드들의 집합"""
    name: str = Field(..., description="그룹 이름")
    members: List[str] = Field(..., description="그룹에 속한 필드 이름들")
    merge_strategy: MergeStrategy = Field(
        default=MergeStrategy.ATOMIC_UPDATE,
        description="그룹 단위 병합 전략"
    )
    description: Optional[str] = Field(None, description="그룹 설명")


class StateTransitionRule(BaseModel):
    """상태 전이 규칙 정의"""
    from_states: List[str] = Field(..., description="허용된 이전 상태들")
    required_fields: List[str] = Field(
        default_factory=list,
        description="이 상태가 되기 위해 필요한 필드들"
    )
    validation_expression: Optional[str] = Field(
        None,
        description="추가 검증을 위한 표현식 (예: reviewed_by != created_by)"
    )


class Property(BaseModel):
    """Property domain model - Section 8.1.3 - 설계 의도: snake_case 도메인 모델"""
    id: str
    object_type_id: str
    name: str = Field(..., pattern="^[a-zA-Z][a-zA-Z0-9_]*$")
    display_name: str
    description: Optional[str] = None
    data_type_id: str
    semantic_type_id: Optional[str] = None
    shared_property_id: Optional[str] = None
    is_required: bool = False
    is_primary_key: bool = False
    is_indexed: bool = False
    is_unique: bool = False
    is_searchable: bool = False
    is_array: bool = False
    default_value: Optional[Any] = None
    enum_values: Optional[List[str]] = None
    reference_type: Optional[str] = None
    sort_order: int = 0
    visibility: Visibility = Visibility.VISIBLE
    validation_rules: Optional[Dict[str, Any]] = None
    version_hash: str
    created_at: datetime
    modified_at: datetime

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v[0].isalpha():
            raise ValueError("Name must start with a letter")
        if not all(c.isalnum() or c == "_" for c in v):
            raise ValueError("Name can only contain letters, numbers, and underscores")
        return v

    @classmethod
    def from_document(cls, doc: dict) -> "Property":
        """설계 의도: DB camelCase → 도메인 snake_case 변환 (Doc 8.1.2 참조)"""
        from datetime import datetime

        # Validate required fields per ADR-007 defensive pattern
        required_fields = ["id", "objectTypeId", "name", "displayName", "dataTypeId", "versionHash"]
        missing = [f for f in required_fields if f not in doc or doc[f] is None]
        if missing:
            raise ValueError(f"Property document missing required fields: {missing}")

        # Parse datetime safely with defensive checks
        def parse_datetime(value: Any) -> datetime:
            if not value:
                return datetime.utcnow()
            if isinstance(value, str):
                # TerminusDB returns ISO format with Z suffix
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            return datetime.utcnow()

        return cls(
            id=doc["id"],  # type: ignore[arg-type] # Validated above, TerminusDB returns str
            object_type_id=doc["objectTypeId"],  # type: ignore[arg-type] # Validated above
            name=doc["name"],  # type: ignore[arg-type] # Validated above
            display_name=doc["displayName"],  # type: ignore[arg-type] # Validated above
            description=doc.get("description"),
            data_type_id=doc["dataTypeId"],  # type: ignore[arg-type] # Validated above
            semantic_type_id=doc.get("semanticTypeId"),
            shared_property_id=doc.get("sharedPropertyId"),
            is_required=doc.get("isRequired", False),
            is_primary_key=doc.get("isPrimaryKey", False),
            is_indexed=doc.get("isIndexed", False),
            is_unique=doc.get("isUnique", False),
            is_searchable=doc.get("isSearchable", False),
            is_array=doc.get("isArray", False),
            default_value=doc.get("defaultValue"),
            enum_values=doc.get("enumValues", []),
            reference_type=doc.get("referenceType"),
            sort_order=doc.get("sortOrder", 0),
            visibility=Visibility(doc.get("visibility", "visible")),
            validation_rules=doc.get("validationRules", {}),
            version_hash=doc["versionHash"],  # type: ignore[arg-type] # Validated above
            created_at=parse_datetime(doc.get("createdAt")),
            modified_at=parse_datetime(doc.get("modifiedAt"))
        )


class ObjectType(BaseModel):
    """ObjectType domain model - Section 8.1.3 - 설계 의도: snake_case 도메인 모델"""
    id: str
    name: str = Field(..., pattern="^[a-zA-Z][a-zA-Z0-9_]*$")
    display_name: str
    plural_display_name: Optional[str] = None
    description: Optional[str] = None
    status: Status = Status.ACTIVE
    type_class: TypeClass = TypeClass.OBJECT
    version_hash: str
    created_by: str
    created_at: datetime
    modified_by: str
    modified_at: datetime
    properties: List[Property] = Field(default_factory=list)
    parent_types: List[str] = Field(default_factory=list)
    interfaces: List[str] = Field(default_factory=list)
    is_abstract: bool = False
    icon: Optional[str] = None
    color: Optional[str] = None
    field_groups: List[FieldGroup] = Field(
        default_factory=list,
        description="필드 그룹 정의 - 의미론적으로 연관된 필드들"
    )
    state_transition_rules: Dict[str, StateTransitionRule] = Field(
        default_factory=dict,
        description="상태별 전이 규칙"
    )
    merge_metadata: Optional[SchemaMergeMetadata] = Field(
        default=None,
        description="병합 전략 및 힌트 메타데이터"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v[0].isalpha():
            raise ValueError("Name must start with a letter")
        if not all(c.isalnum() or c == "_" for c in v):
            raise ValueError("Name can only contain letters, numbers, and underscores")
        return v

    @classmethod
    def from_document(cls, doc: dict) -> "ObjectType":
        """설계 의도: DB camelCase → 도메인 snake_case 변환 (Doc 8.1.2 참조)"""
        from datetime import datetime

        # Validate required fields per ADR-007 defensive pattern
        required_fields = ["id", "name", "displayName", "versionHash", "createdBy", "modifiedBy"]
        missing = [f for f in required_fields if f not in doc or doc[f] is None]
        if missing:
            raise ValueError(f"ObjectType document missing required fields: {missing}")

        # Parse datetime safely with defensive checks
        def parse_datetime(value: Any) -> datetime:
            if not value:
                return datetime.utcnow()
            if isinstance(value, str):
                # TerminusDB returns ISO format with Z suffix
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            return datetime.utcnow()

        return cls(
            id=doc["id"],  # type: ignore[arg-type] # Validated above, TerminusDB returns str
            name=doc["name"],  # type: ignore[arg-type] # Validated above
            display_name=doc["displayName"],  # type: ignore[arg-type] # Validated above
            plural_display_name=doc.get("pluralDisplayName"),
            description=doc.get("description"),
            status=Status(doc.get("status", "active")),
            type_class=TypeClass(doc.get("typeClass", "object")),
            version_hash=doc["versionHash"],  # type: ignore[arg-type] # Validated above
            created_by=doc["createdBy"],  # type: ignore[arg-type] # Validated above
            created_at=parse_datetime(doc.get("createdAt")),
            modified_by=doc["modifiedBy"],  # type: ignore[arg-type] # Validated above
            modified_at=parse_datetime(doc.get("modifiedAt")),
            properties=[],  # Properties will be loaded separately if needed
            parent_types=doc.get("parentTypes", []),
            interfaces=doc.get("interfaces", []),
            is_abstract=doc.get("isAbstract", False),
            icon=doc.get("icon"),
            color=doc.get("color")
        )


class ObjectTypeCreate(BaseModel):
    """ObjectType creation request - Section 10.1.1 - 설계 의도: snake_case 도메인 모델"""
    name: str = Field(..., pattern="^[a-zA-Z][a-zA-Z0-9_]*$")
    display_name: str
    plural_display_name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[Status] = None
    type_class: Optional[TypeClass] = None
    parent_types: Optional[List[str]] = None
    interfaces: Optional[List[str]] = None
    is_abstract: Optional[bool] = False
    icon: Optional[str] = None
    color: Optional[str] = None


class ObjectTypeUpdate(BaseModel):
    """ObjectType update request - 설계 의도: snake_case 도메인 모델"""
    display_name: Optional[str] = None
    plural_display_name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[Status] = None
    parent_types: Optional[List[str]] = None
    interfaces: Optional[List[str]] = None
    is_abstract: Optional[bool] = None
    icon: Optional[str] = None
    color: Optional[str] = None


class LinkType(BaseModel):
    """LinkType domain model - Section 8.1.3"""
    id: str
    name: str = Field(..., pattern="^[a-zA-Z][a-zA-Z0-9_]*$")
    displayName: str
    description: Optional[str] = None
    fromTypeId: str
    toTypeId: str
    cardinality: Cardinality
    directionality: Directionality
    properties: List[Property] = Field(default_factory=list)
    cascadeDelete: bool = False
    isRequired: bool = False
    status: Status = Status.ACTIVE
    versionHash: str
    createdBy: str
    createdAt: datetime
    modifiedBy: str
    modifiedAt: datetime
    
    # Graph metadata fields (GF-02, GF-03)
    permissionInheritance: Optional[Dict[str, Any]] = Field(
        None,
        description="Permission propagation rules through this link"
    )
    statePropagation: Optional[Dict[str, Any]] = Field(
        None,
        description="State propagation rules through this link"
    )
    traversalMetadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Metadata for graph traversal optimization"
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v[0].isalpha():
            raise ValueError("Name must start with a letter")
        if not all(c.isalnum() or c == "_" for c in v):
            raise ValueError("Name can only contain letters, numbers, and underscores")
        return v


class LinkTypeCreate(BaseModel):
    """LinkType creation request - 설계 의도: API 호환 camelCase 모델"""
    name: str = Field(..., pattern="^[a-zA-Z][a-zA-Z0-9_]*$")
    displayName: str
    description: Optional[str] = None
    fromTypeId: str
    toTypeId: str
    cardinality: Cardinality
    directionality: Directionality = Directionality.UNIDIRECTIONAL
    cascadeDelete: bool = False
    isRequired: bool = False
    status: Optional[Status] = None


class LinkTypeUpdate(BaseModel):
    """LinkType update request"""
    displayName: Optional[str] = None
    description: Optional[str] = None
    cardinality: Optional[Cardinality] = None
    directionality: Optional[Directionality] = None
    cascadeDelete: Optional[bool] = None
    isRequired: Optional[bool] = None
    status: Optional[Status] = None


class Interface(BaseModel):
    """Interface domain model - defines contracts for ObjectTypes"""
    id: str
    name: str = Field(..., pattern="^[a-zA-Z][a-zA-Z0-9_]*$")
    displayName: str
    description: Optional[str] = None
    properties: List[Property] = Field(default_factory=list)
    extends: List[str] = Field(default_factory=list)  # Parent interfaces
    status: Status = Status.ACTIVE
    versionHash: str
    createdBy: str
    createdAt: datetime
    modifiedBy: str
    modifiedAt: datetime

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v[0].isalpha():
            raise ValueError("Name must start with a letter")
        if not all(c.isalnum() or c == "_" for c in v):
            raise ValueError("Name can only contain letters, numbers, and underscores")
        return v


class InterfaceCreate(BaseModel):
    """Interface creation request - 설계 의도: API 호환 camelCase 모델"""
    name: str = Field(..., pattern="^[a-zA-Z][a-zA-Z0-9_]*$")
    displayName: str
    description: Optional[str] = None
    extends: Optional[List[str]] = None
    status: Optional[Status] = None


class InterfaceUpdate(BaseModel):
    """Interface update request"""
    displayName: Optional[str] = None
    description: Optional[str] = None
    extends: Optional[List[str]] = None
    status: Optional[Status] = None


class SharedProperty(BaseModel):
    """SharedProperty domain model - reusable property definitions"""
    id: str
    name: str = Field(..., pattern="^[a-zA-Z][a-zA-Z0-9_]*$")
    displayName: str
    description: Optional[str] = None
    dataTypeId: str
    semanticTypeId: str
    defaultValue: Optional[Any] = None
    isRequired: bool = False
    isIndexed: bool = False
    isUnique: bool = False
    isSearchable: bool = False
    validationRules: Optional[Dict[str, Any]] = None
    versionHash: str
    createdBy: str
    createdAt: datetime
    modifiedBy: str
    modifiedAt: datetime

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not v or not v[0].isalpha():
            raise ValueError("Name must start with a letter")
        if not all(c.isalnum() or c == "_" for c in v):
            raise ValueError("Name can only contain letters, numbers, and underscores")
        return v


class SharedPropertyCreate(BaseModel):
    """SharedProperty creation request"""
    name: str = Field(..., pattern="^[a-zA-Z][a-zA-Z0-9_]*$")
    displayName: str
    description: Optional[str] = None
    dataTypeId: str
    semanticTypeId: str
    defaultValue: Optional[Any] = None
    isRequired: bool = False
    isIndexed: bool = False
    isUnique: bool = False
    isSearchable: bool = False
    validationRules: Optional[Dict[str, Any]] = None


class SharedPropertyUpdate(BaseModel):
    """SharedProperty update request"""
    displayName: Optional[str] = None
    description: Optional[str] = None
    defaultValue: Optional[Any] = None
    isRequired: Optional[bool] = None
    isIndexed: Optional[bool] = None
    isUnique: Optional[bool] = None
    isSearchable: Optional[bool] = None
    validationRules: Optional[Dict[str, Any]] = None


class PropertyCreate(BaseModel):
    """Property creation request - Section 8.1.3 - 설계 의도: snake_case 도메인 모델"""
    name: str = Field(..., pattern="^[a-zA-Z][a-zA-Z0-9_]*$")
    display_name: Optional[str] = None
    description: Optional[str] = None
    data_type_id: Optional[str] = None  # Optional when using shared_property_id
    semantic_type_id: Optional[str] = None
    shared_property_id: Optional[str] = None
    is_required: bool = False
    is_primary_key: bool = False
    is_indexed: bool = False
    is_unique: bool = False
    is_searchable: bool = False
    is_array: bool = False
    default_value: Optional[Any] = None
    enum_values: Optional[List[str]] = None
    reference_type: Optional[str] = None
    sort_order: Optional[int] = None
    visibility: Optional[Visibility] = None
    validation_rules: Optional[Dict[str, Any]] = None


class PropertyUpdate(BaseModel):
    """Property update request"""
    displayName: Optional[str] = None
    description: Optional[str] = None
    isRequired: Optional[bool] = None
    isPrimaryKey: Optional[bool] = None
    isIndexed: Optional[bool] = None
    isUnique: Optional[bool] = None
    isSearchable: Optional[bool] = None
    isArray: Optional[bool] = None
    defaultValue: Optional[Any] = None
    enumValues: Optional[List[str]] = None
    referenceType: Optional[str] = None
    sortOrder: Optional[int] = None
    visibility: Optional[Visibility] = None
    validationRules: Optional[Dict[str, Any]] = None


class Branch(BaseModel):
    """Branch domain model"""
    id: str
    name: str
    displayName: str
    description: Optional[str] = None
    parentBranch: Optional[str] = None
    isProtected: bool = False
    createdBy: str
    createdAt: datetime
    modifiedBy: str
    modifiedAt: datetime
    versionHash: str
    isActive: bool = True


class BranchCreate(BaseModel):
    """Branch creation request"""
    name: str = Field(..., pattern="^[a-zA-Z][a-zA-Z0-9_-]*$")
    displayName: str
    description: Optional[str] = None
    parentBranch: Optional[str] = "main"
    isProtected: Optional[bool] = False


class ValidationResult(BaseModel):
    """Validation result model"""
    isValid: bool
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    warnings: List[Dict[str, Any]] = Field(default_factory=list)
    info: List[Dict[str, Any]] = Field(default_factory=list)


class ValidationError(BaseModel):
    """Validation error detail"""
    code: str
    message: str
    path: str
    severity: str = "error"
    details: Optional[Dict[str, Any]] = None


class ChangeProposal(BaseModel):
    """Change Proposal model - Git-style merge request for schema changes"""
    id: str
    title: str
    description: Optional[str] = None
    sourceBranch: str
    targetBranch: str
    status: str = "draft"  # draft, review, approved, merged, closed
    createdBy: str
    createdAt: datetime
    mergedBy: Optional[str] = None
    mergedAt: Optional[datetime] = None
    conflicts: List[Dict[str, Any]] = Field(default_factory=list)
    validationResult: Optional[ValidationResult] = None
    reviewers: List[str] = Field(default_factory=list)
    approvals: List[Dict[str, Any]] = Field(default_factory=list)


class ChangeEvent(BaseModel):
    """Change event model for event streaming"""
    id: str
    eventType: str  # created, updated, deleted
    entityType: str  # ObjectType, Property, etc.
    entityId: str
    branch: str
    userId: str
    timestamp: datetime
    changes: Dict[str, Any]
    versionBefore: Optional[str] = None
    versionAfter: Optional[str] = None


class MergeRequest(BaseModel):
    """Merge execution request model - API request to execute merge"""
    proposalId: str
    strategy: Optional[str] = "merge"  # merge, squash, rebase
    conflictResolutions: Optional[Dict[str, Any]] = None
