"""
도메인 모델 정의
브랜치 병합과 충돌 처리를 위한 도메인 엔티티
"""

from enum import Enum
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from datetime import datetime


class MergeStrategy(Enum):
    """브랜치 병합 전략"""
    MERGE = "merge"
    REBASE = "rebase"
    SQUASH = "squash"
    FAST_FORWARD = "fast_forward"


class ConflictType(Enum):
    """충돌 타입"""
    CONTENT = "content"          # 내용 충돌
    SCHEMA = "schema"            # 스키마 충돌
    PROPERTY = "property"        # 속성 충돌
    RELATIONSHIP = "relationship"# 관계 충돌
    DELETION = "deletion"        # 삭제 충돌
    STRUCTURE = "structure"      # 구조 충돌
    NAMING = "naming"           # 이름 충돌


class ConflictResolution(Enum):
    """충돌 해결 방식"""
    MANUAL = "manual"           # 수동 해결
    ACCEPT_SOURCE = "accept_source"     # 소스 브랜치 내용 선택
    ACCEPT_TARGET = "accept_target"     # 타겟 브랜치 내용 선택
    ACCEPT_BOTH = "accept_both"         # 양쪽 모두 유지
    CUSTOM = "custom"           # 사용자 정의 해결


@dataclass
class MergeConflict:
    """
    3-way merge 충돌 정보
    Foundry-style 충돌 처리를 위한 도메인 모델
    """
    
    # 기본 정보
    id: str
    type: ConflictType
    resource_id: str
    resource_type: str
    description: str
    
    # 3-way merge 정보
    base_value: Optional[Any] = None        # 공통 조상에서의 값
    source_value: Optional[Any] = None      # 소스 브랜치에서의 값
    target_value: Optional[Any] = None      # 타겟 브랜치에서의 값
    
    # 충돌 세부사항
    field_path: Optional[str] = None        # 충돌이 발생한 필드 경로
    line_number: Optional[int] = None       # 충돌 라인 번호 (해당하는 경우)
    
    # 해결 정보
    resolution: Optional[ConflictResolution] = None
    resolved_value: Optional[Any] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    
    # 메타데이터
    created_at: datetime = field(default_factory=datetime.utcnow)
    severity: str = "medium"                # low, medium, high, critical
    auto_resolvable: bool = False           # 자동 해결 가능 여부
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "id": self.id,
            "type": self.type.value,
            "resource_id": self.resource_id,
            "resource_type": self.resource_type,
            "description": self.description,
            "base_value": self.base_value,
            "source_value": self.source_value,
            "target_value": self.target_value,
            "field_path": self.field_path,
            "line_number": self.line_number,
            "resolution": self.resolution.value if self.resolution else None,
            "resolved_value": self.resolved_value,
            "resolved_by": self.resolved_by,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "created_at": self.created_at.isoformat(),
            "severity": self.severity,
            "auto_resolvable": self.auto_resolvable
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MergeConflict':
        """딕셔너리에서 생성"""
        return cls(
            id=data["id"],
            type=ConflictType(data["type"]),
            resource_id=data["resource_id"],
            resource_type=data["resource_type"],
            description=data["description"],
            base_value=data.get("base_value"),
            source_value=data.get("source_value"),
            target_value=data.get("target_value"),
            field_path=data.get("field_path"),
            line_number=data.get("line_number"),
            resolution=ConflictResolution(data["resolution"]) if data.get("resolution") else None,
            resolved_value=data.get("resolved_value"),
            resolved_by=data.get("resolved_by"),
            resolved_at=datetime.fromisoformat(data["resolved_at"]) if data.get("resolved_at") else None,
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.utcnow(),
            severity=data.get("severity", "medium"),
            auto_resolvable=data.get("auto_resolvable", False)
        )
    
    def is_resolved(self) -> bool:
        """해결 여부 확인"""
        return self.resolution is not None and self.resolved_value is not None
    
    def can_auto_resolve(self) -> bool:
        """자동 해결 가능 여부 확인"""
        return self.auto_resolvable and not self.is_resolved()


@dataclass
class MergeResult:
    """병합 결과"""
    
    # 기본 정보
    source_branch: str
    target_branch: str
    strategy: MergeStrategy
    
    # 결과 상태
    success: bool
    merge_commit: Optional[str] = None
    
    # 충돌 정보
    conflicts: List[MergeConflict] = field(default_factory=list)
    total_conflicts: int = 0
    resolved_conflicts: int = 0
    
    # 변경 통계
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0
    
    # 메타데이터
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    
    # 메시지
    message: Optional[str] = None
    author: Optional[str] = None
    
    @property
    def has_conflicts(self) -> bool:
        """충돌 존재 여부"""
        return len(self.conflicts) > 0
    
    @property
    def all_conflicts_resolved(self) -> bool:
        """모든 충돌 해결 여부"""
        return self.has_conflicts and all(c.is_resolved() for c in self.conflicts)
    
    @property
    def can_complete_merge(self) -> bool:
        """병합 완료 가능 여부"""
        return not self.has_conflicts or self.all_conflicts_resolved
    
    def add_conflict(self, conflict: MergeConflict) -> None:
        """충돌 추가"""
        self.conflicts.append(conflict)
        self.total_conflicts = len(self.conflicts)
        self.resolved_conflicts = sum(1 for c in self.conflicts if c.is_resolved())
    
    def resolve_conflict(self, conflict_id: str, resolution: ConflictResolution, 
                        resolved_value: Any, resolved_by: str) -> bool:
        """충돌 해결"""
        for conflict in self.conflicts:
            if conflict.id == conflict_id:
                conflict.resolution = resolution
                conflict.resolved_value = resolved_value
                conflict.resolved_by = resolved_by
                conflict.resolved_at = datetime.utcnow()
                self.resolved_conflicts = sum(1 for c in self.conflicts if c.is_resolved())
                return True
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "source_branch": self.source_branch,
            "target_branch": self.target_branch,
            "strategy": self.strategy.value,
            "success": self.success,
            "merge_commit": self.merge_commit,
            "conflicts": [c.to_dict() for c in self.conflicts],
            "total_conflicts": self.total_conflicts,
            "resolved_conflicts": self.resolved_conflicts,
            "files_changed": self.files_changed,
            "insertions": self.insertions,
            "deletions": self.deletions,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "message": self.message,
            "author": self.author,
            "has_conflicts": self.has_conflicts,
            "all_conflicts_resolved": self.all_conflicts_resolved,
            "can_complete_merge": self.can_complete_merge
        }


@dataclass
class BranchInfo:
    """브랜치 정보"""
    name: str
    current: bool = False
    protected: bool = False
    head_commit: Optional[str] = None
    created_at: Optional[datetime] = None
    last_modified: Optional[datetime] = None
    commit_count: int = 0
    author: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "name": self.name,
            "current": self.current,
            "protected": self.protected,
            "head_commit": self.head_commit,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_modified": self.last_modified.isoformat() if self.last_modified else None,
            "commit_count": self.commit_count,
            "author": self.author
        }


@dataclass
class MergePreview:
    """병합 미리보기"""
    source_branch: str
    target_branch: str
    can_merge: bool
    conflicts: List[MergeConflict] = field(default_factory=list)
    changes: List[Dict[str, Any]] = field(default_factory=list)
    stats: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """딕셔너리로 변환"""
        return {
            "source_branch": self.source_branch,
            "target_branch": self.target_branch,
            "can_merge": self.can_merge,
            "conflicts": [c.to_dict() for c in self.conflicts],
            "changes": self.changes,
            "stats": self.stats
        }