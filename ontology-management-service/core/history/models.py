"""
OMS History Event Models
OMS 핵심 책임: 스키마 변경 이벤트 발행을 위한 모델
감사 로그 조회/관리는 별도 Audit Service MSA 담당
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class ResourceType(str, Enum):
    """OMS에서 관리하는 리소스 타입"""
    OBJECT_TYPE = "objectType"
    PROPERTY = "property"
    LINK_TYPE = "linkType"
    ACTION_TYPE = "actionType"
    FUNCTION_TYPE = "functionType"
    DATA_TYPE = "dataType"
    SHARED_PROPERTY = "sharedProperty"
    INTERFACE = "interface"
    METRIC_TYPE = "metricType"
    BRANCH = "branch"
    SCHEMA = "schema"
    UNKNOWN = "unknown"


class ChangeOperation(str, Enum):
    """스키마 변경 작업 타입"""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    RENAME = "rename"
    MERGE = "merge"
    REVERT = "revert"


class AuditEvent(BaseModel):
    """감사 이벤트 (OMS에서 발행만, 저장은 Audit Service MSA)"""
    event_id: str = Field(description="이벤트 고유 식별자")
    timestamp: datetime = Field(description="이벤트 발생 시각 (UTC)")
    service: str = Field(default="oms", description="서비스 식별자")
    event_type: str = Field(description="이벤트 타입 (schema.changed, schema.reverted 등)")
    
    # 스키마 변경 정보
    operation: ChangeOperation = Field(description="수행된 작업")
    resource_type: ResourceType = Field(description="변경된 리소스 타입")
    resource_id: str = Field(description="변경된 리소스 ID")
    resource_name: Optional[str] = Field(None, description="리소스 이름")
    branch: Optional[str] = Field(None, description="대상 브랜치")
    commit_hash: Optional[str] = Field(None, description="커밋 해시")
    
    # 사용자 정보
    author: Optional[str] = Field(None, description="작성자 ID")
    author_email: Optional[str] = Field(None, description="작성자 이메일")
    ip_address: Optional[str] = Field(None, description="IP 주소")
    user_agent: Optional[str] = Field(None, description="User Agent")
    session_id: Optional[str] = Field(None, description="세션 ID")
    
    # 변경 상세
    changes: List['ChangeDetail'] = Field(default_factory=list, description="변경 내역")
    result: str = Field(default="success", description="실행 결과")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="추가 메타데이터")
    
    class Config:
        json_schema_extra = {
            "example": {
                "event_id": "audit_abc123def456",
                "timestamp": "2025-06-25T10:30:00Z",
                "service": "oms",
                "event_type": "schema.changed",
                "operation": "update",
                "resource_type": "objectType",
                "resource_id": "Product",
                "branch": "main",
                "author": "user123"
            }
        }


class ChangeDetail(BaseModel):
    """스키마 변경 상세 정보"""
    field: str = Field(description="변경된 필드명")
    operation: ChangeOperation = Field(description="필드 레벨 작업")
    old_value: Optional[Any] = Field(None, description="이전 값")
    new_value: Optional[Any] = Field(None, description="새 값")
    path: str = Field(description="변경된 필드 경로 (예: object_types.Product.properties.price)")
    breaking_change: bool = Field(False, description="Breaking change 여부")
    
    @field_validator('path')
    def validate_path(cls, v):
        if not v or not v.strip():
            raise ValueError("path must not be empty")
        return v


class RevertRequest(BaseModel):
    """스키마 복원 요청"""
    target_commit: str = Field(description="복원할 대상 커밋 해시")
    strategy: str = Field(default="soft", description="복원 전략 (soft/hard)")
    message: str = Field(description="복원 이유/메시지")
    dry_run: bool = Field(default=False, description="시뮬레이션 모드")
    
    @field_validator('strategy')
    def validate_strategy(cls, v):
        if v not in ['soft', 'hard']:
            raise ValueError("strategy must be 'soft' or 'hard'")
        return v


class RevertResult(BaseModel):
    """스키마 복원 결과"""
    success: bool = Field(description="복원 성공 여부")
    new_commit_hash: Optional[str] = Field(None, description="새 커밋 해시 (soft revert)")
    reverted_from: str = Field(description="복원 시작점")
    reverted_to: str = Field(description="복원 목표점")
    message: str = Field(description="결과 메시지")
    reverted_changes: Optional[List[ChangeDetail]] = Field(None, description="복원된 변경사항")
    dry_run: bool = Field(default=False, description="시뮬레이션 여부")
    execution_time_ms: Optional[int] = Field(None, description="실행 시간 (밀리초)")


class AffectedResource(BaseModel):
    """영향받은 리소스"""
    resource_type: ResourceType
    resource_id: str
    resource_name: Optional[str] = None
    impact_type: str = Field(description="영향 타입 (direct/transitive/potential)")
    impact_severity: str = Field("low", description="영향도 (low/medium/high/critical)")
