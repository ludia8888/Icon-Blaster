"""
History Models (Migrated from OMS)
OMS core/history/models.py에서 이관된 히스토리 관련 모델들
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


class AffectedResource(BaseModel):
    """영향받은 리소스"""
    resource_type: ResourceType
    resource_id: str
    resource_name: Optional[str] = None
    impact_type: str = Field(description="영향 타입 (direct/transitive/potential)")
    impact_severity: str = Field("low", description="영향도 (low/medium/high/critical)")


class HistoryEntry(BaseModel):
    """
    히스토리 엔트리 (OMS에서 이관)
    단일 스키마 변경 기록
    """
    # 기본 식별 정보
    commit_hash: str = Field(description="커밋 해시")
    branch: str = Field(description="브랜치명")
    timestamp: datetime = Field(description="변경 시각 (UTC)")
    author: str = Field(description="작성자 ID")
    author_email: Optional[str] = Field(None, description="작성자 이메일")
    message: str = Field(description="커밋 메시지")
    
    # 변경 정보
    operation: ChangeOperation = Field(description="수행된 작업")
    resource_type: ResourceType = Field(description="변경된 리소스 타입")
    resource_id: str = Field(description="변경된 리소스 ID")
    resource_name: Optional[str] = Field(None, description="리소스 이름")
    
    # 상세 변경 내역
    changes: List[ChangeDetail] = Field(default_factory=list, description="변경 상세 내역")
    total_changes: int = Field(description="총 변경 개수")
    
    # 영향 분석
    affected_resources: List[AffectedResource] = Field(
        default_factory=list, 
        description="영향받은 리소스들"
    )
    breaking_changes: int = Field(0, description="Breaking change 개수")
    
    # 메타데이터
    metadata: Dict[str, Any] = Field(default_factory=dict, description="추가 메타데이터")
    
    class Config:
        json_schema_extra = {
            "example": {
                "commit_hash": "abc123def456",
                "branch": "main",
                "timestamp": "2025-06-25T10:30:00Z",
                "author": "user123",
                "message": "Update Product object type",
                "operation": "update",
                "resource_type": "objectType",
                "resource_id": "Product",
                "total_changes": 3,
                "breaking_changes": 0
            }
        }


class HistoryQuery(BaseModel):
    """
    히스토리 조회 파라미터 (OMS에서 이관)
    """
    # 필터링 옵션
    branch: Optional[str] = Field("main", description="브랜치 필터")
    resource_type: Optional[ResourceType] = Field(None, description="리소스 타입 필터")
    resource_id: Optional[str] = Field(None, description="특정 리소스 ID")
    author: Optional[str] = Field(None, description="작성자 필터")
    operation: Optional[ChangeOperation] = Field(None, description="작업 타입 필터")
    
    # 시간 범위
    from_date: Optional[datetime] = Field(None, description="시작 날짜")
    to_date: Optional[datetime] = Field(None, description="종료 날짜")
    
    # 포함 옵션
    include_changes: bool = Field(True, description="상세 변경 내역 포함 여부")
    include_affected: bool = Field(False, description="영향받은 리소스 포함 여부")
    include_metadata: bool = Field(False, description="메타데이터 포함 여부")
    
    # 페이지네이션
    limit: int = Field(50, ge=1, le=1000, description="결과 제한")
    cursor: Optional[str] = Field(None, description="페이지네이션 커서")
    
    # 정렬
    sort_by: str = Field("timestamp", description="정렬 기준 (timestamp/author/resource_id)")
    sort_order: str = Field("desc", description="정렬 순서 (asc/desc)")
    
    @field_validator('sort_by')
    def validate_sort_by(cls, v):
        allowed = ['timestamp', 'author', 'resource_id', 'operation', 'branch']
        if v not in allowed:
            raise ValueError(f"sort_by must be one of {allowed}")
        return v
    
    @field_validator('sort_order')
    def validate_sort_order(cls, v):
        if v not in ['asc', 'desc']:
            raise ValueError("sort_order must be 'asc' or 'desc'")
        return v


class HistoryListResponse(BaseModel):
    """
    히스토리 목록 응답 (OMS에서 이관)
    """
    # 결과 데이터
    entries: List[HistoryEntry] = Field(description="히스토리 엔트리 목록")
    
    # 페이지네이션 정보
    total_count: int = Field(description="전체 결과 개수")
    has_more: bool = Field(description="추가 결과 여부")
    next_cursor: Optional[str] = Field(None, description="다음 페이지 커서")
    
    # 쿼리 정보
    query_time_ms: int = Field(description="쿼리 실행 시간 (밀리초)")
    applied_filters: Dict[str, Any] = Field(
        default_factory=dict, 
        description="적용된 필터 정보"
    )
    
    # 통계 정보
    summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="결과 요약 통계"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "entries": [],
                "total_count": 150,
                "has_more": True,
                "next_cursor": "eyJpZCI6MTIzfQ==",
                "query_time_ms": 45,
                "summary": {
                    "operations": {"create": 10, "update": 30, "delete": 5},
                    "resource_types": {"objectType": 25, "property": 20},
                    "breaking_changes": 2
                }
            }
        }


class CommitDetail(BaseModel):
    """
    커밋 상세 정보 (OMS에서 이관)
    특정 시점의 전체 스냅샷과 상세 정보
    """
    # 커밋 기본 정보
    commit_hash: str = Field(description="커밋 해시")
    branch: str = Field(description="브랜치명")
    timestamp: datetime = Field(description="커밋 시각 (UTC)")
    author: str = Field(description="작성자 ID")
    author_email: Optional[str] = Field(None, description="작성자 이메일")
    message: str = Field(description="커밋 메시지")
    parent_hashes: List[str] = Field(default_factory=list, description="부모 커밋 해시들")
    
    # 변경 통계
    total_changes: int = Field(description="총 변경 개수")
    additions: int = Field(description="추가된 항목 수")
    modifications: int = Field(description="수정된 항목 수")
    deletions: int = Field(description="삭제된 항목 수")
    breaking_changes: int = Field(0, description="Breaking change 개수")
    
    # 리소스별 변경 요약
    changed_resources: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="리소스 타입별 변경된 ID 목록"
    )
    
    # 상세 변경 내역
    detailed_changes: List[ChangeDetail] = Field(
        default_factory=list,
        description="상세 변경 내역"
    )
    
    # 영향 분석
    affected_resources: List[AffectedResource] = Field(
        default_factory=list,
        description="영향받은 리소스들"
    )
    impact_analysis: Dict[str, Any] = Field(
        default_factory=dict,
        description="영향 분석 결과"
    )
    
    # 스냅샷 데이터 (선택적)
    snapshot: Optional[Dict[str, Any]] = Field(
        None, 
        description="해당 시점의 전체 스키마 스냅샷"
    )
    
    # 메타데이터
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="추가 메타데이터"
    )
    
    # 성능 정보
    snapshot_size_bytes: Optional[int] = Field(None, description="스냅샷 크기 (바이트)")
    generation_time_ms: Optional[int] = Field(None, description="생성 시간 (밀리초)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "commit_hash": "abc123def456",
                "branch": "main",
                "timestamp": "2025-06-25T10:30:00Z",
                "author": "user123",
                "message": "Major schema update for Product object",
                "total_changes": 15,
                "additions": 5,
                "modifications": 8,
                "deletions": 2,
                "breaking_changes": 1,
                "changed_resources": {
                    "objectType": ["Product", "Order"],
                    "property": ["Product.price", "Order.status"]
                }
            }
        }