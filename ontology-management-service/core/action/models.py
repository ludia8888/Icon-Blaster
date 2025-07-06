"""
Action Service 도메인 모델
섹션 8.4의 Action Service 명세 구현
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ActionType(BaseModel):
    """액션 타입 정의"""
    id: str
    objectTypeId: str
    name: str
    displayName: str
    description: Optional[str] = None
    inputSchema: Dict[str, Any]  # JSON Schema
    validationExpression: Optional[str] = None
    webhookUrl: Optional[str] = None
    isBatchable: bool = True
    isAsync: bool = False
    requiresApproval: bool = False
    approvalRoles: List[str] = Field(default_factory=list)
    onSuccessFunction: Optional[str] = None
    onFailureFunction: Optional[str] = None
    maxRetries: int = 3
    timeoutSeconds: int = 300
    batchSize: Optional[int] = 100
    continueOnError: bool = False
    implementation: str  # 플러그인 이름
    status: str = "active"
    versionHash: str
    createdBy: str
    createdAt: datetime
    modifiedBy: str
    modifiedAt: datetime


class ExecutionOptions(BaseModel):
    """액션 실행 옵션"""
    forceAsync: bool = False
    forceSync: bool = False
    priority: str = "normal"  # low, normal, high, critical
    notificationWebhook: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Job(BaseModel):
    """비동기 작업"""
    id: str
    actionTypeId: str
    objectIds: List[str]
    parameters: Dict[str, Any]
    status: str  # pending, running, completed, failed, cancelled
    createdBy: str
    createdAt: datetime
    startedAt: Optional[datetime] = None
    completedAt: Optional[datetime] = None
    totalObjects: int
    processedObjects: int = 0
    successfulObjects: int = 0
    failedObjects: int = 0
    progressPercentage: float = 0.0
    estimatedDuration: float
    actualDuration: Optional[float] = None
    errorMessage: Optional[str] = None
    resultSummary: Optional[Dict[str, Any]] = None
    retryCount: int = 0


class ActionResult(BaseModel):
    """액션 실행 결과"""
    actionTypeId: str
    totalObjects: int
    successful: int
    failed: int
    results: List[Dict[str, Any]]
    errors: List[Dict[str, Any]]
    executedBy: str
    executedAt: datetime
    executionTimeMs: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AsyncJobReference(BaseModel):
    """비동기 작업 참조"""
    jobId: str
    statusUrl: str
    estimatedDuration: float
    asyncFallback: bool = False
    message: Optional[str] = None


class ObjectActionResult(BaseModel):
    """개별 객체 액션 결과"""
    objectId: str
    status: str  # success, failed, skipped
    changes: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    message: Optional[str] = None
    executionTimeMs: Optional[float] = None


class ActionContext(BaseModel):
    """액션 실행 컨텍스트"""
    transaction: Any  # TerminusDB Transaction
    user: Dict[str, Any]
    parameters: Dict[str, Any]
    actionType: ActionType
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True


class ActionValidationResult(BaseModel):
    """액션 입력 검증 결과"""
    isValid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)


class WebhookPayload(BaseModel):
    """웹훅 페이로드"""
    actionTypeId: str
    actionName: str
    totalObjects: int
    successful: int
    failed: int
    results: List[ObjectActionResult]
    parameters: Dict[str, Any]
    executedBy: str
    executedAt: datetime
    webhookType: str  # completion, failure, progress


class ActionDefinition(BaseModel):
    """액션 정의 (생성/수정용)"""
    name: str = Field(..., pattern="^[a-zA-Z][a-zA-Z0-9_]*$")
    displayName: str
    description: Optional[str] = None
    objectTypeId: str
    inputSchema: Dict[str, Any]
    validationExpression: Optional[str] = None
    webhookUrl: Optional[str] = None
    isBatchable: bool = True
    isAsync: bool = False
    requiresApproval: bool = False
    approvalRoles: List[str] = Field(default_factory=list)
    maxRetries: int = 3
    timeoutSeconds: int = 300
    implementation: str


class JobFilter(BaseModel):
    """작업 필터"""
    status: Optional[List[str]] = None
    actionTypeId: Optional[str] = None
    createdBy: Optional[str] = None
    createdAfter: Optional[datetime] = None
    createdBefore: Optional[datetime] = None


class JobUpdate(BaseModel):
    """작업 상태 업데이트"""
    status: Optional[str] = None
    processedObjects: Optional[int] = None
    successfulObjects: Optional[int] = None
    failedObjects: Optional[int] = None
    progressPercentage: Optional[float] = None
    errorMessage: Optional[str] = None
    resultSummary: Optional[Dict[str, Any]] = None


class ActionPlugin(BaseModel):
    """액션 플러그인 인터페이스"""
    name: str
    version: str
    description: str
    supported_types: List[str]
    configuration_schema: Dict[str, Any]

    class Config:
        # 실제 플러그인은 이 인터페이스를 구현해야 함
        pass


# 테스트 호환성을 위한 별칭
ActionTypeModel = ActionType
