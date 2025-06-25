"""
GraphQL Schema for History API
히스토리 조회 및 복원 기능을 위한 GraphQL 타입 정의
"""
from datetime import datetime
from typing import List, Optional
import strawberry
from strawberry.types import Info

from core.history.models import (
    ChangeOperation, ResourceType as ModelResourceType,
    HistoryEntry as ModelHistoryEntry,
    CommitDetail as ModelCommitDetail,
    RevertRequest as ModelRevertRequest,
    RevertResult as ModelRevertResult,
    AffectedResource as ModelAffectedResource,
    ChangeDetail as ModelChangeDetail
)


@strawberry.enum
class ResourceTypeEnum:
    """추적 가능한 리소스 타입"""
    OBJECT_TYPE = "ObjectType"
    PROPERTY = "Property"
    LINK_TYPE = "LinkType"
    ACTION_TYPE = "ActionType"
    FUNCTION_TYPE = "FunctionType"
    DATA_TYPE = "DataType"
    SHARED_PROPERTY = "SharedProperty"
    INTERFACE = "Interface"
    METRIC_TYPE = "MetricType"
    BRANCH = "Branch"
    PROPOSAL = "Proposal"


@strawberry.enum
class ChangeOperationEnum:
    """변경 작업 타입"""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    RENAME = "rename"
    MERGE = "merge"
    REVERT = "revert"
    BRANCH_CREATE = "branch_create"
    BRANCH_DELETE = "branch_delete"
    PROPOSAL_CREATE = "proposal_create"
    PROPOSAL_MERGE = "proposal_merge"


@strawberry.type
class ChangeDetail:
    """필드 레벨 변경 상세"""
    field_path: str
    operation: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    breaking_change: bool = False


@strawberry.type
class AffectedResource:
    """영향받은 리소스"""
    resource_type: ResourceTypeEnum
    resource_id: str
    resource_name: Optional[str] = None
    impact_type: str
    impact_severity: str = "low"


@strawberry.type
class HistoryEntry:
    """히스토리 엔트리"""
    id: str
    commit_hash: str
    parent_hash: Optional[str]
    branch: str
    timestamp: datetime
    author: str
    author_email: Optional[str]
    message: str
    operation: ChangeOperationEnum
    resource_type: ResourceTypeEnum
    resource_id: str
    resource_name: Optional[str]
    
    # 선택적 필드
    changes: List[ChangeDetail] = strawberry.field(default_factory=list)
    affected_resources: List[AffectedResource] = strawberry.field(default_factory=list)
    
    # 메타데이터
    proposal_id: Optional[str] = None
    approval_status: Optional[str] = None
    approvers: List[str] = strawberry.field(default_factory=list)
    tags: List[str] = strawberry.field(default_factory=list)


@strawberry.type
class HistoryConnection:
    """히스토리 페이지네이션"""
    entries: List[HistoryEntry]
    total_count: int
    has_more: bool
    next_cursor: Optional[str] = None
    query_time_ms: int


@strawberry.type
class CommitDetail:
    """커밋 상세 정보"""
    commit_hash: str
    branch: str
    timestamp: datetime
    author: str
    message: str
    parent_hashes: List[str]
    
    # 변경 통계
    total_changes: int
    additions: int
    modifications: int
    deletions: int
    
    # 스냅샷 (선택적)
    snapshot: Optional[str] = None  # JSON string


@strawberry.input
class RevertInput:
    """복원 요청 입력"""
    target_commit: str
    message: str
    strategy: str = "soft"
    dry_run: bool = False


@strawberry.type
class RevertResult:
    """복원 결과"""
    success: bool
    new_commit_hash: Optional[str]
    reverted_from: str
    reverted_to: str
    message: str
    warnings: List[str]
    affected_resources: List[AffectedResource]
    dry_run: bool
    execution_time_ms: int


# Query extensions
@strawberry.type
class HistoryQueries:
    """히스토리 관련 쿼리"""
    
    @strawberry.field
    async def history(
        self,
        info: Info,
        branch: str = "main",
        resource_type: Optional[ResourceTypeEnum] = None,
        resource_id: Optional[str] = None,
        author: Optional[str] = None,
        operation: Optional[ChangeOperationEnum] = None,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
        include_changes: bool = True,
        include_affected: bool = False,
        limit: int = 50,
        cursor: Optional[str] = None
    ) -> HistoryConnection:
        """스키마 변경 이력 조회"""
        # TODO: Resolver 구현
        pass
    
    @strawberry.field
    async def commit_detail(
        self,
        info: Info,
        commit_hash: str,
        branch: str = "main",
        include_snapshot: bool = False
    ) -> CommitDetail:
        """특정 커밋 상세 조회"""
        # TODO: Resolver 구현
        pass


# Mutation extensions
@strawberry.type
class HistoryMutations:
    """히스토리 관련 뮤테이션"""
    
    @strawberry.mutation
    async def revert_to_commit(
        self,
        info: Info,
        branch: str,
        input: RevertInput
    ) -> RevertResult:
        """특정 커밋으로 복원"""
        # TODO: Resolver 구현
        pass


# Subscription extensions
@strawberry.type
class HistorySubscriptions:
    """히스토리 관련 구독"""
    
    @strawberry.subscription
    async def schema_changes(
        self,
        info: Info,
        branch: str = "main",
        resource_types: Optional[List[ResourceTypeEnum]] = None
    ) -> HistoryEntry:
        """실시간 스키마 변경 알림"""
        # TODO: Resolver 구현
        pass