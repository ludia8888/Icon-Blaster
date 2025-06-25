"""
GraphQL Schema Types - 섹션 10.2의 GraphQL API 스키마 정의
"""
from datetime import datetime
from enum import Enum
from typing import List, Optional

import strawberry


# Enums
@strawberry.enum
class StatusEnum(Enum):
    ACTIVE = "active"
    EXPERIMENTAL = "experimental"
    DEPRECATED = "deprecated"
    EXAMPLE = "example"


@strawberry.enum
class TypeClassEnum(Enum):
    OBJECT = "object"
    INTERFACE = "interface"
    LINK = "link"
    EMBEDDED = "embedded"


@strawberry.enum
class VisibilityEnum(Enum):
    VISIBLE = "visible"
    HIDDEN = "hidden"
    ADVANCED = "advanced"


@strawberry.enum
class CardinalityEnum(Enum):
    ONE = "one"
    MANY = "many"
    ZERO_OR_ONE = "zero_or_one"
    ONE_OR_MANY = "one_or_many"


@strawberry.enum
class DirectionalityEnum(Enum):
    DIRECTIONAL = "directional"
    BIDIRECTIONAL = "bidirectional"


@strawberry.enum
class FunctionCategoryEnum(Enum):
    TRANSFORMATION = "transformation"
    AGGREGATION = "aggregation"
    VALIDATION = "validation"
    CALCULATION = "calculation"
    EXTRACTION = "extraction"
    ENRICHMENT = "enrichment"
    FILTERING = "filtering"
    INTEGRATION = "integration"
    TEMPORAL = "temporal"
    SPATIAL = "spatial"
    ML_INFERENCE = "ml_inference"
    CUSTOM = "custom"


@strawberry.enum
class FunctionRuntimeEnum(Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    SQL = "sql"
    SPARK = "spark"
    CUSTOM = "custom"


@strawberry.enum
class ParameterDirectionEnum(Enum):
    INPUT = "input"
    OUTPUT = "output"
    INOUT = "inout"


@strawberry.enum
class DataTypeCategoryEnum(Enum):
    PRIMITIVE = "primitive"
    COMPLEX = "complex"
    TEMPORAL = "temporal"
    SPATIAL = "spatial"
    BINARY = "binary"
    SPECIAL = "special"


@strawberry.enum
class DataTypeFormatEnum(Enum):
    BOOLEAN = "xsd:boolean"
    STRING = "xsd:string"
    INTEGER = "xsd:integer"
    LONG = "xsd:long"
    FLOAT = "xsd:float"
    DOUBLE = "xsd:double"
    DECIMAL = "xsd:decimal"
    DATE = "xsd:date"
    TIME = "xsd:time"
    DATETIME = "xsd:dateTime"
    TIMESTAMP = "xsd:dateTimeStamp"
    DURATION = "xsd:duration"
    BINARY = "xsd:base64Binary"
    HEX_BINARY = "xsd:hexBinary"
    JSON = "xsd:json"
    XML = "xsd:xml"
    ANY = "xsd:any"


@strawberry.enum
class BranchStatusEnum(Enum):
    ACTIVE = "active"
    MERGED = "merged"
    ARCHIVED = "archived"


@strawberry.enum
class ResourceTypeEnum(Enum):
    OBJECT_TYPE = "object_type"
    PROPERTY = "property"
    LINK_TYPE = "link_type"
    INTERFACE = "interface"
    SHARED_PROPERTY = "shared_property"
    ACTION_TYPE = "action_type"


# Core Types
@strawberry.type
class Property:
    id: str
    objectTypeId: str
    name: str
    displayName: str
    dataType: str
    isRequired: bool = False
    isUnique: bool = False
    isPrimaryKey: bool = False
    isSearchable: bool = False
    isIndexed: bool = False
    defaultValue: Optional[str] = None
    description: Optional[str] = None
    enumValues: List[str] = strawberry.field(default_factory=list)
    linkedObjectType: Optional[str] = None
    status: StatusEnum = StatusEnum.ACTIVE
    visibility: VisibilityEnum = VisibilityEnum.VISIBLE
    isMutable: bool = True
    versionHash: str
    createdBy: str
    createdAt: Optional[datetime] = None
    modifiedBy: str
    modifiedAt: Optional[datetime] = None


@strawberry.type
class ObjectType:
    id: str
    name: str
    displayName: str
    pluralDisplayName: Optional[str] = None
    description: Optional[str] = None
    status: StatusEnum = StatusEnum.ACTIVE
    typeClass: TypeClassEnum = TypeClassEnum.OBJECT
    visibility: VisibilityEnum = VisibilityEnum.VISIBLE
    isMutable: bool = True
    isAbstract: bool = False
    extends: Optional[str] = None
    implements: List[str] = strawberry.field(default_factory=list)
    properties: List[Property] = strawberry.field(default_factory=list)
    tags: List[str] = strawberry.field(default_factory=list)
    icon: Optional[str] = None
    color: Optional[str] = None
    versionHash: str
    createdBy: str
    createdAt: Optional[datetime] = None
    modifiedBy: str
    modifiedAt: Optional[datetime] = None
    parentTypes: List[str] = strawberry.field(default_factory=list)
    interfaces: List[str] = strawberry.field(default_factory=list)


@strawberry.type
class LinkType:
    id: str
    name: str
    displayName: str
    description: Optional[str] = None
    fromObjectType: str
    toObjectType: str
    directionality: DirectionalityEnum = DirectionalityEnum.DIRECTIONAL
    fromCardinality: CardinalityEnum = CardinalityEnum.MANY
    toCardinality: CardinalityEnum = CardinalityEnum.MANY
    isInheritable: bool = True
    status: StatusEnum = StatusEnum.ACTIVE
    versionHash: str
    createdBy: str
    createdAt: Optional[datetime] = None
    modifiedBy: str
    modifiedAt: Optional[datetime] = None


@strawberry.type
class Interface:
    id: str
    name: str
    displayName: str
    description: Optional[str] = None
    properties: List[Property] = strawberry.field(default_factory=list)
    status: StatusEnum = StatusEnum.ACTIVE
    versionHash: str
    createdBy: str
    createdAt: Optional[datetime] = None
    modifiedBy: str
    modifiedAt: Optional[datetime] = None


@strawberry.type
class SharedProperty:
    id: str
    name: str
    displayName: str
    description: Optional[str] = None
    dataType: str
    semanticType: Optional[str] = None
    defaultValue: Optional[str] = None
    enumValues: List[str] = strawberry.field(default_factory=list)
    status: StatusEnum = StatusEnum.ACTIVE
    versionHash: str
    createdBy: str
    createdAt: Optional[datetime] = None
    modifiedBy: str
    modifiedAt: Optional[datetime] = None


@strawberry.type
class Branch:
    name: str
    fromBranch: Optional[str] = None
    headHash: str
    description: Optional[str] = None
    status: BranchStatusEnum = BranchStatusEnum.ACTIVE
    isProtected: bool = False
    createdBy: str
    createdAt: Optional[datetime] = None
    lastModified: Optional[datetime] = None
    commitsAhead: int = 0
    commitsBehind: int = 0
    hasPendingChanges: bool = False


@strawberry.type
class HistoryEntry:
    id: str
    hash: str
    message: str
    author: str
    timestamp: Optional[datetime] = None
    resourceType: ResourceTypeEnum
    resourceId: Optional[str] = None
    operation: str
    changes: strawberry.scalars.JSON = strawberry.field(default_factory=dict)


# Validation Types
@strawberry.type
class BreakingChange:
    type: str
    description: str
    resourceType: ResourceTypeEnum
    resourceId: str
    severity: str = "high"
    mitigation: Optional[str] = None


@strawberry.type
class ValidationWarning:
    type: str
    message: str
    resourceType: ResourceTypeEnum
    resourceId: str
    recommendation: Optional[str] = None


@strawberry.type
class ImpactAnalysis:
    affectedObjectTypes: List[str] = strawberry.field(default_factory=list)
    affectedProperties: List[str] = strawberry.field(default_factory=list)
    affectedLinkTypes: List[str] = strawberry.field(default_factory=list)
    estimatedDowntime: Optional[str] = None
    migrationComplexity: str = "low"
    riskLevel: str = "low"


@strawberry.type
class SuggestedMigration:
    type: str
    description: str
    script: str
    reversible: bool = False
    estimatedTime: Optional[str] = None


@strawberry.type
class ValidationResult:
    isValid: bool
    breakingChanges: List[BreakingChange] = strawberry.field(default_factory=list)
    warnings: List[ValidationWarning] = strawberry.field(default_factory=list)
    impactAnalysis: Optional[ImpactAnalysis] = None
    suggestedMigrations: List[SuggestedMigration] = strawberry.field(default_factory=list)
    validationTime: Optional[datetime] = None


# Search Types
@strawberry.type
class SearchItem:
    id: str
    type: ResourceTypeEnum
    name: str
    displayName: str
    description: Optional[str] = None
    score: float = 0.0
    branch: str
    path: str
    highlights: strawberry.scalars.JSON = strawberry.field(default_factory=dict)


@strawberry.type
class SearchResult:
    items: List[SearchItem] = strawberry.field(default_factory=list)
    totalCount: int = 0
    facets: strawberry.scalars.JSON = strawberry.field(default_factory=dict)


# Connection Types
@strawberry.type
class ObjectTypeConnection:
    data: List[ObjectType] = strawberry.field(default_factory=list)
    totalCount: int = 0
    hasNextPage: bool = False
    hasPreviousPage: bool = False


# Real-time Event Types
@strawberry.type
class SchemaChangeEvent:
    """스키마 변경 이벤트 (Foundry OMS Real-time)"""
    event_id: str
    event_type: str  # created, updated, deleted
    resource_type: ResourceTypeEnum
    resource_id: str
    resource_name: str
    branch: str
    changes: strawberry.scalars.JSON = strawberry.field(default_factory=dict)
    timestamp: Optional[datetime] = None
    user_id: str
    version_hash: str


@strawberry.type
class BranchChangeEvent:
    """브랜치 변경 이벤트"""
    event_id: str
    branch_name: str
    event_type: str  # commit, merge, create, delete
    commit_hash: Optional[str] = None
    commit_message: Optional[str] = None
    author: str
    timestamp: Optional[datetime] = None
    affected_resources: List[str] = strawberry.field(default_factory=list)


@strawberry.type
class ProposalUpdateEvent:
    """제안(PR) 업데이트 이벤트"""
    event_id: str
    proposal_id: str
    event_type: str  # created, updated, reviewed, approved, merged, closed
    title: str
    status: str
    reviewer: Optional[str] = None
    comment: Optional[str] = None
    timestamp: Optional[datetime] = None


@strawberry.type
class ActionProgressEvent:
    """액션 진행 상황 이벤트"""
    event_id: str
    job_id: str
    status: str  # queued, running, completed, failed
    progress_percentage: int
    current_step: str
    total_steps: int
    message: Optional[str] = None
    estimated_completion: Optional[datetime] = None
    timestamp: Optional[datetime] = None


# Input Types
@strawberry.input
class ObjectTypeInput:
    name: str
    displayName: str
    pluralDisplayName: Optional[str] = None
    description: Optional[str] = None
    status: Optional[StatusEnum] = None
    typeClass: Optional[TypeClassEnum] = None
    parentTypes: List[str] = strawberry.field(default_factory=list)
    interfaces: List[str] = strawberry.field(default_factory=list)
    isAbstract: bool = False
    icon: Optional[str] = None
    color: Optional[str] = None


@strawberry.input
class ObjectTypeUpdateInput:
    displayName: Optional[str] = None
    pluralDisplayName: Optional[str] = None
    description: Optional[str] = None
    status: Optional[StatusEnum] = None
    parentTypes: Optional[List[str]] = None
    interfaces: Optional[List[str]] = None
    isAbstract: Optional[bool] = None
    icon: Optional[str] = None
    color: Optional[str] = None


@strawberry.input
class PropertyInput:
    name: str
    displayName: str
    dataType: str
    isRequired: bool = False
    isUnique: bool = False
    isPrimaryKey: bool = False
    isSearchable: bool = False
    isIndexed: bool = False
    defaultValue: Optional[str] = None
    description: Optional[str] = None
    enumValues: List[str] = strawberry.field(default_factory=list)
    linkedObjectType: Optional[str] = None
    status: StatusEnum = StatusEnum.ACTIVE
    visibility: VisibilityEnum = VisibilityEnum.VISIBLE
    isMutable: bool = True


@strawberry.input
class PropertyUpdateInput:
    displayName: Optional[str] = None
    isRequired: Optional[bool] = None
    isUnique: Optional[bool] = None
    isPrimaryKey: Optional[bool] = None
    isSearchable: Optional[bool] = None
    isIndexed: Optional[bool] = None
    defaultValue: Optional[str] = None
    description: Optional[str] = None
    enumValues: Optional[List[str]] = None
    linkedObjectType: Optional[str] = None
    status: Optional[StatusEnum] = None
    visibility: Optional[VisibilityEnum] = None
    isMutable: Optional[bool] = None


@strawberry.input
class LinkTypeInput:
    name: str
    displayName: str
    description: Optional[str] = None
    fromObjectType: str
    toObjectType: str
    directionality: DirectionalityEnum = DirectionalityEnum.DIRECTIONAL
    fromCardinality: CardinalityEnum = CardinalityEnum.MANY
    toCardinality: CardinalityEnum = CardinalityEnum.MANY
    isInheritable: bool = True
    status: StatusEnum = StatusEnum.ACTIVE


@strawberry.input
class LinkTypeUpdateInput:
    displayName: Optional[str] = None
    description: Optional[str] = None
    directionality: Optional[DirectionalityEnum] = None
    fromCardinality: Optional[CardinalityEnum] = None
    toCardinality: Optional[CardinalityEnum] = None
    isInheritable: Optional[bool] = None
    status: Optional[StatusEnum] = None


@strawberry.input
class InterfaceInput:
    name: str
    displayName: str
    description: Optional[str] = None
    status: StatusEnum = StatusEnum.ACTIVE


@strawberry.input
class InterfaceUpdateInput:
    displayName: Optional[str] = None
    description: Optional[str] = None
    status: Optional[StatusEnum] = None


@strawberry.input
class SharedPropertyInput:
    name: str
    displayName: str
    description: Optional[str] = None
    dataType: str
    semanticType: Optional[str] = None
    defaultValue: Optional[str] = None
    enumValues: List[str] = strawberry.field(default_factory=list)
    status: StatusEnum = StatusEnum.ACTIVE


@strawberry.input
class SharedPropertyUpdateInput:
    displayName: Optional[str] = None
    description: Optional[str] = None
    semanticType: Optional[str] = None
    defaultValue: Optional[str] = None
    enumValues: Optional[List[str]] = None
    status: Optional[StatusEnum] = None


@strawberry.input
class CreateBranchInput:
    name: str
    fromBranch: str = "main"
    description: Optional[str] = None


@strawberry.input
class ProposalInput:
    title: str
    description: Optional[str] = None
    sourceBranch: str
    targetBranch: str = "main"
    reviewers: List[str] = strawberry.field(default_factory=list)


@strawberry.input
class ProposalUpdateInput:
    title: Optional[str] = None
    description: Optional[str] = None
    reviewers: Optional[List[str]] = None


# Action Type Enums
@strawberry.enum
class ActionCategoryEnum(Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    LINK = "link"
    UNLINK = "unlink"
    BULK = "bulk"
    WORKFLOW = "workflow"
    VALIDATION = "validation"
    CUSTOM = "custom"


@strawberry.enum
class TransformationTypeEnum(Enum):
    PROPERTY_UPDATE = "property_update"
    LINK_CREATE = "link_create"
    LINK_DELETE = "link_delete"
    OBJECT_CREATE = "object_create"
    OBJECT_DELETE = "object_delete"
    BULK_UPDATE = "bulk_update"
    EXTERNAL_TRIGGER = "external_trigger"
    WORKFLOW_TRANSITION = "workflow_transition"
    CUSTOM = "custom"


# Action Type Types
@strawberry.type
class ApplicableObjectType:
    objectTypeId: str
    role: str = "primary"  # primary, secondary, related
    required: bool = True
    description: Optional[str] = None


@strawberry.type
class ParameterSchema:
    schema: strawberry.scalars.JSON
    examples: List[strawberry.scalars.JSON] = strawberry.field(default_factory=list)
    uiHints: Optional[strawberry.scalars.JSON] = None


@strawberry.type
class ActionTypeReference:
    actionTypeId: str
    version: Optional[int] = None
    description: Optional[str] = None


@strawberry.type
class ActionType:
    id: str
    name: str
    displayName: str
    description: Optional[str] = None
    category: ActionCategoryEnum
    transformationType: TransformationTypeEnum
    transformationTypeRef: Optional[str] = None
    applicableObjectTypes: List[ApplicableObjectType] = strawberry.field(default_factory=list)
    parameterSchema: Optional[ParameterSchema] = None
    configuration: strawberry.scalars.JSON = strawberry.field(default_factory=dict)
    referencedActions: List[ActionTypeReference] = strawberry.field(default_factory=list)
    requiredPermissions: List[str] = strawberry.field(default_factory=list)
    tags: List[str] = strawberry.field(default_factory=list)
    metadata: strawberry.scalars.JSON = strawberry.field(default_factory=dict)
    isSystem: bool = False
    isDeprecated: bool = False
    version: int = 1
    versionHash: str
    createdBy: str
    createdAt: Optional[datetime] = None
    modifiedBy: str
    modifiedAt: Optional[datetime] = None


# Action Type Input Types
@strawberry.input
class ApplicableObjectTypeInput:
    objectTypeId: str
    role: str = "primary"
    required: bool = True
    description: Optional[str] = None


@strawberry.input
class ParameterSchemaInput:
    schema: strawberry.scalars.JSON
    examples: List[strawberry.scalars.JSON] = strawberry.field(default_factory=list)
    uiHints: Optional[strawberry.scalars.JSON] = None


@strawberry.input
class ActionTypeReferenceInput:
    actionTypeId: str
    version: Optional[int] = None
    description: Optional[str] = None


@strawberry.input
class ActionTypeInput:
    name: str
    displayName: str
    description: Optional[str] = None
    category: ActionCategoryEnum
    transformationType: TransformationTypeEnum
    transformationTypeRef: Optional[str] = None
    applicableObjectTypes: List[ApplicableObjectTypeInput]
    parameterSchema: Optional[ParameterSchemaInput] = None
    configuration: Optional[strawberry.scalars.JSON] = None
    referencedActions: Optional[List[ActionTypeReferenceInput]] = None
    requiredPermissions: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    metadata: Optional[strawberry.scalars.JSON] = None


@strawberry.input
class ActionTypeUpdateInput:
    displayName: Optional[str] = None
    description: Optional[str] = None
    transformationType: Optional[TransformationTypeEnum] = None
    transformationTypeRef: Optional[str] = None
    applicableObjectTypes: Optional[List[ApplicableObjectTypeInput]] = None
    parameterSchema: Optional[ParameterSchemaInput] = None
    configuration: Optional[strawberry.scalars.JSON] = None
    referencedActions: Optional[List[ActionTypeReferenceInput]] = None
    requiredPermissions: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    metadata: Optional[strawberry.scalars.JSON] = None
    isDeprecated: Optional[bool] = None


# ===== Function Type GraphQL Types =====

@strawberry.type
class FunctionParameter:
    name: str
    displayName: str
    description: Optional[str] = None
    direction: ParameterDirectionEnum = ParameterDirectionEnum.INPUT
    dataTypeId: str
    semanticTypeId: Optional[str] = None
    structTypeId: Optional[str] = None
    isRequired: bool = True
    isArray: bool = False
    defaultValue: Optional[strawberry.scalars.JSON] = None
    validationRules: Optional[strawberry.scalars.JSON] = None
    metadata: Optional[strawberry.scalars.JSON] = None
    sortOrder: int = 0


@strawberry.type
class ReturnType:
    dataTypeId: str
    semanticTypeId: Optional[str] = None
    structTypeId: Optional[str] = None
    isArray: bool = False
    isNullable: bool = True
    description: Optional[str] = None
    metadata: Optional[strawberry.scalars.JSON] = None


@strawberry.type
class RuntimeConfig:
    runtime: FunctionRuntimeEnum
    version: Optional[str] = None
    timeoutMs: int = 30000
    memoryMb: int = 512
    cpuCores: float = 1.0
    maxRetries: int = 3
    retryDelayMs: int = 1000
    environmentVars: Optional[strawberry.scalars.JSON] = None
    dependencies: Optional[List[str]] = None
    resourceLimits: Optional[strawberry.scalars.JSON] = None


@strawberry.type
class FunctionBehavior:
    isDeterministic: bool = True
    isStateless: bool = True
    isCacheable: bool = True
    isParallelizable: bool = True
    hasSideEffects: bool = False
    isExpensive: bool = False
    cacheTtlSeconds: Optional[int] = None


@strawberry.type
class FunctionExample:
    name: str
    description: Optional[str] = None
    inputValues: strawberry.scalars.JSON
    expectedOutput: strawberry.scalars.JSON
    explanation: Optional[str] = None


@strawberry.type
class FunctionType:
    id: str
    name: str
    displayName: str
    description: Optional[str] = None
    category: FunctionCategoryEnum
    parameters: List[FunctionParameter]
    returnType: ReturnType
    runtimeConfig: RuntimeConfig
    behavior: FunctionBehavior
    implementationRef: Optional[str] = None
    functionBody: Optional[str] = None
    examples: List[FunctionExample]
    tags: List[str]
    isPublic: bool = True
    allowedRoles: List[str]
    allowedUsers: List[str]
    metadata: Optional[strawberry.scalars.JSON] = None
    isSystem: bool = False
    isDeprecated: bool = False
    version: str = "1.0.0"
    versionHash: str
    previousVersionId: Optional[str] = None
    createdBy: str
    createdAt: datetime
    modifiedBy: str
    modifiedAt: datetime
    branchId: Optional[str] = None
    isBranchSpecific: bool = False


@strawberry.input
class FunctionParameterInput:
    name: str
    displayName: str
    description: Optional[str] = None
    direction: ParameterDirectionEnum = ParameterDirectionEnum.INPUT
    dataTypeId: str
    semanticTypeId: Optional[str] = None
    structTypeId: Optional[str] = None
    isRequired: bool = True
    isArray: bool = False
    defaultValue: Optional[strawberry.scalars.JSON] = None
    validationRules: Optional[strawberry.scalars.JSON] = None
    metadata: Optional[strawberry.scalars.JSON] = None
    sortOrder: int = 0


@strawberry.input
class ReturnTypeInput:
    dataTypeId: str
    semanticTypeId: Optional[str] = None
    structTypeId: Optional[str] = None
    isArray: bool = False
    isNullable: bool = True
    description: Optional[str] = None
    metadata: Optional[strawberry.scalars.JSON] = None


@strawberry.input
class RuntimeConfigInput:
    runtime: FunctionRuntimeEnum
    version: Optional[str] = None
    timeoutMs: int = 30000
    memoryMb: int = 512
    cpuCores: float = 1.0
    maxRetries: int = 3
    retryDelayMs: int = 1000
    environmentVars: Optional[strawberry.scalars.JSON] = None
    dependencies: Optional[List[str]] = None
    resourceLimits: Optional[strawberry.scalars.JSON] = None


@strawberry.input
class FunctionBehaviorInput:
    isDeterministic: bool = True
    isStateless: bool = True
    isCacheable: bool = True
    isParallelizable: bool = True
    hasSideEffects: bool = False
    isExpensive: bool = False
    cacheTtlSeconds: Optional[int] = None


@strawberry.input
class FunctionExampleInput:
    name: str
    description: Optional[str] = None
    inputValues: strawberry.scalars.JSON
    expectedOutput: strawberry.scalars.JSON
    explanation: Optional[str] = None


@strawberry.input
class FunctionTypeInput:
    name: str
    displayName: str
    description: Optional[str] = None
    category: FunctionCategoryEnum
    parameters: List[FunctionParameterInput]
    returnType: ReturnTypeInput
    runtimeConfig: RuntimeConfigInput
    behavior: Optional[FunctionBehaviorInput] = None
    implementationRef: Optional[str] = None
    functionBody: Optional[str] = None
    examples: Optional[List[FunctionExampleInput]] = None
    tags: Optional[List[str]] = None
    isPublic: Optional[bool] = True
    allowedRoles: Optional[List[str]] = None
    allowedUsers: Optional[List[str]] = None
    metadata: Optional[strawberry.scalars.JSON] = None


@strawberry.input
class FunctionTypeUpdateInput:
    displayName: Optional[str] = None
    description: Optional[str] = None
    parameters: Optional[List[FunctionParameterInput]] = None
    returnType: Optional[ReturnTypeInput] = None
    runtimeConfig: Optional[RuntimeConfigInput] = None
    behavior: Optional[FunctionBehaviorInput] = None
    implementationRef: Optional[str] = None
    functionBody: Optional[str] = None
    examples: Optional[List[FunctionExampleInput]] = None
    tags: Optional[List[str]] = None
    isPublic: Optional[bool] = None
    allowedRoles: Optional[List[str]] = None
    allowedUsers: Optional[List[str]] = None
    metadata: Optional[strawberry.scalars.JSON] = None
    isDeprecated: Optional[bool] = None


# ===== Data Type GraphQL Types =====

@strawberry.type
class TypeConstraint:
    constraintType: str
    value: strawberry.scalars.JSON
    message: Optional[str] = None


@strawberry.type
class DataType:
    id: str
    name: str
    displayName: str
    description: Optional[str] = None
    category: DataTypeCategoryEnum
    format: DataTypeFormatEnum
    constraints: List[TypeConstraint]
    defaultValue: Optional[strawberry.scalars.JSON] = None
    isNullable: bool = True
    isArrayType: bool = False
    arrayItemType: Optional[str] = None
    mapKeyType: Optional[str] = None
    mapValueType: Optional[str] = None
    metadata: Optional[strawberry.scalars.JSON] = None
    supportedOperations: List[str]
    compatibleTypes: List[str]
    isSystem: bool = False
    isDeprecated: bool = False
    deprecationMessage: Optional[str] = None
    tags: List[str]
    version: str = "1.0.0"
    versionHash: str
    previousVersionId: Optional[str] = None
    createdBy: str
    createdAt: datetime
    modifiedBy: str
    modifiedAt: datetime
    branchId: Optional[str] = None
    isBranchSpecific: bool = False
    isPublic: bool = True
    allowedRoles: List[str]
    allowedUsers: List[str]


@strawberry.input
class TypeConstraintInput:
    constraintType: str
    value: strawberry.scalars.JSON
    message: Optional[str] = None


@strawberry.input
class DataTypeInput:
    name: str
    displayName: str
    description: Optional[str] = None
    category: DataTypeCategoryEnum
    format: DataTypeFormatEnum
    constraints: Optional[List[TypeConstraintInput]] = None
    defaultValue: Optional[strawberry.scalars.JSON] = None
    isNullable: Optional[bool] = True
    isArrayType: Optional[bool] = False
    arrayItemType: Optional[str] = None
    mapKeyType: Optional[str] = None
    mapValueType: Optional[str] = None
    metadata: Optional[strawberry.scalars.JSON] = None
    supportedOperations: Optional[List[str]] = None
    compatibleTypes: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    isPublic: Optional[bool] = True
    allowedRoles: Optional[List[str]] = None
    allowedUsers: Optional[List[str]] = None


@strawberry.input
class DataTypeUpdateInput:
    displayName: Optional[str] = None
    description: Optional[str] = None
    constraints: Optional[List[TypeConstraintInput]] = None
    defaultValue: Optional[strawberry.scalars.JSON] = None
    isNullable: Optional[bool] = None
    isArrayType: Optional[bool] = None
    arrayItemType: Optional[str] = None
    mapKeyType: Optional[str] = None
    mapValueType: Optional[str] = None
    metadata: Optional[strawberry.scalars.JSON] = None
    supportedOperations: Optional[List[str]] = None
    compatibleTypes: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    isPublic: Optional[bool] = None
    allowedRoles: Optional[List[str]] = None
    allowedUsers: Optional[List[str]] = None
    isDeprecated: Optional[bool] = None
    deprecationMessage: Optional[str] = None
