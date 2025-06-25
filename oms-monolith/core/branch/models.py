"""
Branch Service 도메인 모델
섹션 8.2와 10.1.2의 모델 정의 참조
"""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ProposalStatus(str, Enum):
    """Proposal 상태"""
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    MERGED = "merged"
    REJECTED = "rejected"


class MergeStrategy(str, Enum):
    """머지 전략"""
    MERGE = "merge"
    SQUASH = "squash"
    REBASE = "rebase"


class ConflictType(str, Enum):
    """충돌 타입"""
    MODIFY_MODIFY = "modify-modify"  # 양쪽에서 같은 항목 수정
    MODIFY_DELETE = "modify-delete"  # 한쪽은 수정, 한쪽은 삭제
    ADD_ADD = "add-add"  # 양쪽에서 같은 이름으로 추가
    RENAME_RENAME = "rename-rename"  # 양쪽에서 다르게 이름 변경


class ProtectionRule(BaseModel):
    """브랜치 보호 규칙"""
    id: str
    rule_type: str  # require-review, require-approval, restrict-push
    config: Dict[str, Any]
    created_at: datetime
    created_by: str


class CommitInfo(BaseModel):
    """커밋 정보"""
    hash: str
    message: str
    author: str
    timestamp: datetime
    parent_hashes: List[str]


class ChangeProposal(BaseModel):
    """Change Proposal 모델"""
    id: str
    title: str
    description: Optional[str] = None
    source_branch: str
    target_branch: str
    status: ProposalStatus
    base_hash: str
    source_hash: str
    target_hash: str
    conflicts: List[Dict[str, Any]] = Field(default_factory=list)
    author: str
    reviewers: List[str] = Field(default_factory=list)
    approvals: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    merged_at: Optional[datetime] = None
    merged_by: Optional[str] = None
    diff_summary: Optional[Dict[str, Any]] = None


class ProposalCreate(BaseModel):
    """Proposal 생성 요청"""
    title: str
    description: Optional[str] = None
    target_branch: str = "main"
    reviewers: Optional[List[str]] = None


class ProposalUpdate(BaseModel):
    """Proposal 수정 요청"""
    title: Optional[str] = None
    description: Optional[str] = None
    reviewers: Optional[List[str]] = None
    status: Optional[ProposalStatus] = None


class Conflict(BaseModel):
    """충돌 정보"""
    id: Optional[str] = None
    conflict_type: str  # ConflictType or string
    resource_type: Optional[str] = None  # ObjectType, Property, LinkType
    resource_id: str
    resource_name: Optional[str] = None
    base_value: Optional[Any] = None
    source_value: Optional[Any] = None
    target_value: Optional[Any] = None
    path: Optional[str] = None  # 충돌 위치 경로
    description: Optional[str] = None
    field_conflicts: Optional[List['FieldConflict']] = None


class ConflictResolution(BaseModel):
    """충돌 해결 정보"""
    conflict_id: str
    resolution_type: str  # use-source, use-target, manual
    resolved_value: Optional[Any] = None
    resolved_by: str
    resolved_at: datetime


class DiffEntry(BaseModel):
    """변경사항 항목"""
    operation: str  # add, modify, delete, rename
    resource_type: str  # ObjectType, Property, LinkType
    resource_id: str
    resource_name: str
    path: str
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    metadata: Optional[Dict[str, Any]] = None


class BranchDiff(BaseModel):
    """브랜치 간 차이점"""
    source_branch: str
    target_branch: str
    base_hash: str
    source_hash: str
    target_hash: str
    total_changes: int
    additions: int
    modifications: int
    deletions: int
    renames: int
    entries: List[DiffEntry] = Field(default_factory=list)
    has_conflicts: bool = False
    conflicts: List[Conflict] = Field(default_factory=list)


class MergeResult(BaseModel):
    """머지 결과"""
    merged_schemas: Dict[str, Any] = Field(default_factory=dict)
    conflicts: List[Conflict] = Field(default_factory=list)
    statistics: Optional['MergeStatistics'] = None
    merge_commit: Optional[str] = None
    source_branch: Optional[str] = None
    target_branch: Optional[str] = None
    strategy: Optional[str] = None
    conflicts_resolved: int = 0
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0
    execution_time_ms: int = 0
    merged_by: Optional[str] = None
    merged_at: Optional[datetime] = None


class ThreeWayDiff(BaseModel):
    """3-way diff 결과"""
    base_commit: str
    source_commit: str
    target_commit: str
    common_ancestor: str
    base_to_source: List[DiffEntry]
    base_to_target: List[DiffEntry]
    conflicts: List[Conflict]
    can_auto_merge: bool


class BranchProtection(BaseModel):
    """브랜치 보호 설정"""
    branch_name: str
    is_protected: bool
    rules: List[ProtectionRule] = Field(default_factory=list)
    allow_force_push: bool = False
    allow_deletion: bool = False
    require_pull_request: bool = True
    required_approvals: int = 1
    dismiss_stale_approvals: bool = True
    require_up_to_date: bool = True


class ResourceMergeResult(BaseModel):
    """단일 리소스 머지 결과"""
    merged_value: Optional[Dict[str, Any]] = None
    has_conflict: bool = False
    conflict: Optional[Any] = None  # Conflict 타입


class FieldConflict(BaseModel):
    """필드 레벨 충돌"""
    field: str
    base: Any
    source: Any
    target: Any


class FieldMergeResult(BaseModel):
    """필드 레벨 머지 결과"""
    merged: Dict[str, Any]
    conflicts: List[FieldConflict] = Field(default_factory=list)
    has_conflicts: bool = False


class MergeStatistics(BaseModel):
    """머지 통계"""
    total_resources: int
    added_count: int
    modified_count: int
    deleted_count: int
    conflict_count: int
    merge_duration_ms: int
