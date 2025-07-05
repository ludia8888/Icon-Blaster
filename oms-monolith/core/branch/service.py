"""
REQ-OMS-F2: 브랜치 관리 핵심 서비스 - TerminusDB 내부 캐싱 활용
버전 제어 (Branching & Merge) 시스템 구현
섹션 8.2.2의 BranchService 클래스 구현 - TERMINUSDB_LRU_CACHE_SIZE 최적화
"""
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from shared.terminus_context import get_author, get_branch

from core.branch.conflict_resolver import ConflictResolver
from core.branch.diff_engine import DiffEngine
from core.branch.merge_strategies import MergeStrategyImplementor
from core.branch.models import (
    BranchDiff,
    ChangeProposal,
    MergeResult,
    MergeStrategy,
    ProposalStatus,
    ProposalUpdate,
)
from core.branch.three_way_merge import ThreeWayMergeAlgorithm
from shared.cache.smart_cache import SmartCacheManager
from database.clients.terminus_db import TerminusDBClient
from models.domain import Branch

logger = logging.getLogger(__name__)


class BranchService:
    """
    REQ-OMS-F2: 브랜치 관리 핵심 서비스 - TerminusDB 내부 캐싱 활용
    Git-style 브랜치 생성, 머지, Proposal 워크플로 지원
    """

    def __init__(
        self,
        tdb_endpoint: str,
        diff_engine: DiffEngine,
        conflict_resolver: ConflictResolver,
        event_publisher: Optional[Any] = None
    ):
        self.tdb_endpoint = tdb_endpoint
        self.tdb = TerminusDBClient(tdb_endpoint)
        self.cache = SmartCacheManager(self.tdb)  # TerminusDB 내부 캐싱 활용
        self.diff_engine = diff_engine
        self.conflict_resolver = conflict_resolver
        self.event_publisher = event_publisher
        self.db_name = os.getenv("TERMINUSDB_DB", "oms")
        self.three_way_merge = None  # Will be initialized in initialize()
        self.merge_strategies = MergeStrategyImplementor(self.tdb)  # 고급 머지 전략

    async def initialize(self):
        """서비스 초기화 - TerminusDB 내부 캐싱 활성화"""
        # 시스템 브랜치 생성 (_system, _proposals)
        try:
            await self.tdb.create_database(self.db_name)
            logger.info(f"Database {self.db_name} initialized with TerminusDB internal caching")

            # 브랜치 관련 문서 타입들을 캐시에 워밍
            await self.cache.warm_cache_for_branch(
                self.db_name,
                "main",
                ["Branch", "ChangeProposal", "MergeCommit"]
            )

        except Exception as e:
            logger.warning(f"Database initialization: {e}")

            # 3-way merge 알고리즘 초기화
            self.three_way_merge = ThreeWayMergeAlgorithm(self.tdb)

    def _generate_id(self) -> str:
        """고유 ID 생성"""
        return str(uuid.uuid4())

    def _generate_proposal_id(self) -> str:
        """Proposal ID 생성"""
        return f"proposal_{self._generate_id()}"

    def _validate_branch_name(self, name: str) -> bool:
        """브랜치 이름 검증"""
        import re
        # 브랜치 이름 패턴: 소문자, 숫자, 하이픈, 슬래시
        pattern = r'^[a-z][a-z0-9\-/]*$'
        return bool(re.match(pattern, name))

    async def _branch_exists(self, name: str) -> bool:
        """브랜치 존재 여부 확인 - TerminusDB 내부 캐싱 활용"""
        cache_key = f"branch_exists:{name}"

        return await self.cache.get_with_optimization(
            key=cache_key,
            db=self.db_name,
            branch="_system",
            query_factory=lambda: self._check_branch_exists_from_db(name),
            doc_type="Branch"
        )

    async def _check_branch_exists_from_db(self, name: str) -> bool:
        """DB에서 브랜치 존재 여부 직접 확인"""
        try:
            info = await self.tdb.get_branch_info(self.db_name, name)
            return info is not None
        except Exception as e:
            logger.debug(f"Branch existence check failed for {name}: {e}")
            return False

    async def _get_branch_info(self, branch_name: str) -> Optional[Dict[str, Any]]:
        """브랜치 정보 조회 - TerminusDB 내부 캐싱 활용"""
        cache_key = f"branch_info:{branch_name}"

        return await self.cache.get_with_optimization(
            key=cache_key,
            db=self.db_name,
            branch="_system",
            query_factory=lambda: self._get_branch_info_from_db(branch_name),
            doc_type="Branch"
        )

    async def _get_branch_info_from_db(self, branch_name: str) -> Optional[Dict[str, Any]]:
        """DB에서 브랜치 정보 직접 조회"""
        try:
            return await self.tdb.get_branch_info(self.db_name, branch_name)
        except Exception as e:
            logger.debug(f"Failed to get branch info for {branch_name}: {e}")
            return None

    async def _get_branch_head(self, branch_name: str) -> Optional[str]:
        """브랜치 HEAD 커밋 조회"""
        info = await self._get_branch_info(branch_name)
        return info.get("head") if info else None

    async def _is_protected_branch(self, branch_name: str) -> bool:
        """보호된 브랜치 여부 확인 - TerminusDB 내부 캐싱 활용"""
        if branch_name in ["main", "master", "_system", "_proposals"]:
            return True

        # 브랜치 메타데이터에서 보호 설정 확인
        cache_key = f"branch_protected:{branch_name}"

        return await self.cache.get_with_optimization(
            key=cache_key,
            db=self.db_name,
            branch="_system",
            query_factory=lambda: self._check_protected_branch_from_db(branch_name),
            doc_type="Branch"
        )

    async def _check_protected_branch_from_db(self, branch_name: str) -> bool:
        """DB에서 보호된 브랜치 여부 직접 확인"""
        doc = await self.tdb.get_document(
            f"Branch_{branch_name}",
            db=self.db_name,
            branch="_system"
        )
        return doc.get("isProtected", False) if doc else False

    async def create_branch(
        self,
        name: str,
        from_branch: str = "main",
        description: Optional[str] = None,
        user_id: str = "system"
    ) -> Branch:
        """
        REQ-OMS-F2-AC1: Virtual Branch 생성
        새 브랜치를 생성하고 메타데이터를 관리합니다.
        """

        # 1. 브랜치 이름 검증
        if not self._validate_branch_name(name):
            raise ValueError(f"Invalid branch name: {name}")

        if await self._branch_exists(name):
            raise ValueError(f"Branch {name} already exists")

        # 2. 소스 브랜치 확인
        source_info = await self._get_branch_info(from_branch)
        if not source_info:
            raise ValueError(f"Source branch {from_branch} not found")

        # 3. Terminus DB 네이티브 브랜치 생성
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            await tdb.create_branch(
                db=self.db_name,
                branch_name=name,
                from_branch=from_branch
            )

        # 4. 브랜치 메타데이터
        branch_meta = {
            "@type": "Branch",
            "@id": f"Branch_{name}",
            "id": self._generate_id(),
            "name": name,
            "displayName": name.replace("-", " ").title(),
            "description": description,
            "parentBranch": from_branch,
            "headHash": source_info.get("head", ""),
            "isProtected": False,
            "createdBy": user_id,
            "createdAt": datetime.utcnow().isoformat(),
            "modifiedBy": user_id,
            "modifiedAt": datetime.utcnow().isoformat(),
            "versionHash": "",
            "isActive": True
        }

        # 메타데이터는 _system 브랜치에 저장
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            await tdb.insert_document(
                branch_meta,
                db=self.db_name,
                branch="_system",
                message=f"Create branch metadata for {name}"
            )

        # 5. 이벤트 발행
        if self.event_publisher:
            try:
                await self.event_publisher.publish_branch_created(
                    branch_name=name,
                    parent_branch=from_branch,
                    author=user_id,
                    description=description
                )
            except Exception as e:
                logger.warning(f"Failed to publish branch created event: {e}")

        return self._doc_to_branch(branch_meta)

    async def get_branch(self, branch_name: str) -> Optional[Branch]:
        """
        REQ-OMS-F2-AC5: 브랜치별 독립 조회
        브랜치 메타데이터와 상태 정보를 조회합니다.
        """
        # 시스템 브랜치 정보
        branch_info = await self._get_branch_info(branch_name)
        if not branch_info:
            return None

        # 메타데이터 조회
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            doc = await tdb.get_document(
                f"Branch_{branch_name}",
                db=self.db_name,
                branch="_system"
            )

        if doc:
            # 최신 정보 업데이트
            doc["head_hash"] = branch_info.get("head", "")
            return self._doc_to_branch(doc)
        else:
            # 기본 브랜치는 메타데이터가 없을 수 있음
            if branch_name in ["main", "master"]:
                return Branch(
                    id=branch_name,
                    name=branch_name,
                    display_name=branch_name.title(),
                    parent_branch=None,
                    is_protected=True,
                    created_by=get_author(),
                    created_at=datetime.utcnow(),
                    modified_by=get_author(),
                    modified_at=datetime.utcnow(),
                    version_hash="",
                    is_active=True
                )
            return None

    async def list_branches(
        self,
        include_system: bool = False,
        status: Optional[str] = None
    ) -> List[Branch]:
        """브랜치 목록 조회"""
        branches = []

        # Terminus DB에서 모든 브랜치 조회
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # 브랜치 메타데이터 조회
            docs = await tdb.get_all_documents(
                doc_type="Branch",
                db=self.db_name,
                branch="_system"
            )

            for doc in docs:
                branch = self._doc_to_branch(doc)

                # 시스템 브랜치 필터링
                if not include_system and branch.name.startswith("_"):
                    continue

                # 상태 필터링
                if status and branch.is_active != (status == "active"):
                    continue

                branches.append(branch)

        # 기본 브랜치 추가 (메타데이터가 없을 수 있음)
        if "main" not in [b.name for b in branches]:
            main_branch = await self.get_branch("main")
            if main_branch:
                branches.insert(0, main_branch)

        return branches

    async def delete_branch(
        self,
        branch_name: str,
        force: bool = False,
        user_id: str = "system"
    ) -> bool:
        """브랜치 삭제"""
        # 보호된 브랜치 확인
        if await self._is_protected_branch(branch_name) and not force:
            raise ValueError(f"Cannot delete protected branch {branch_name}")

        # 브랜치 존재 확인
        if not await self._branch_exists(branch_name):
            return False

        # Terminus DB 브랜치 삭제
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # 메타데이터 삭제
            await tdb.delete_document(
                f"Branch_{branch_name}",
                db=self.db_name,
                branch="_system",
                message=f"Delete branch metadata for {branch_name}"
            )

            # 실제 브랜치 삭제는 지원하지 않음 (데이터 보존)
            # 대신 is_active를 false로 설정

        # 이벤트 발행
        if self.event_publisher:
            await self._publish_event(
                "branch.deleted",
                {
                    "name": branch_name,
                    "deleted_by": user_id
                }
            )

        return True

    async def create_proposal(
        self,
        source_branch: str,
        target_branch: str,
        title: str,
        description: Optional[str] = None,
        user_id: str = "system"
    ) -> ChangeProposal:
        """
        REQ-OMS-F2-AC2: Proposal 생성/리뷰
        REQ-OMS-F2-AC3: 3-way diff 충돌 감지 포함
        Change Proposal을 생성하고 초기 충돌을 감지합니다.
        """

        # 1. 브랜치 정보 조회
        source_info = await self._get_branch_info(source_branch)
        target_info = await self._get_branch_info(target_branch)

        if not source_info or not target_info:
            raise ValueError("Branch not found")

        # 2. 보호된 브랜치 확인
        if await self._is_protected_branch(target_branch):
            # 보호된 브랜치는 proposal 필수
            logger.info(f"Creating proposal for protected branch {target_branch}")

        # 3. 공통 조상 찾기
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # 간단한 구현: target branch의 현재 HEAD를 base로 사용
            base_commit = target_info.get("head", "")

        # 4. 3-way diff 계산
        diff_result = await self.diff_engine.calculate_three_way_diff(
            base=base_commit,
            source=source_info.get("head", ""),
            target=target_info.get("head", "")
        )

        # 5. 초기 충돌 감지
        conflicts = await self.conflict_resolver.detect_conflicts(diff_result)

        # 6. Proposal 문서 생성
        proposal_id = self._generate_proposal_id()
        proposal = {
            "@type": "ChangeProposal",
            "@id": proposal_id,
            "id": proposal_id,
            "title": title,
            "description": description or "",
            "source_branch": source_branch,
            "target_branch": target_branch,
            "base_hash": base_commit,
            "source_hash": source_info.get("head", ""),
            "target_hash": target_info.get("head", ""),
            "status": ProposalStatus.DRAFT.value,
            "diff": diff_result.model_dump() if hasattr(diff_result, 'model_dump') else {},
            "conflicts": [c.model_dump() if hasattr(c, 'model_dump') else c for c in conflicts],
            "author": user_id,
            "reviewers": [],
            "approvals": [],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        # 7. 저장
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            await tdb.insert_document(
                proposal,
                db=self.db_name,
                branch="_proposals",
                message=f"Create proposal: {title}"
            )

        # 8. 이벤트 발행
        if self.event_publisher:
            try:
                await self.event_publisher.publish_proposal_status_changed(
                    proposal_id=proposal_id,
                    status="created",
                    author=user_id,
                    comment=f"Created proposal from {source_branch} to {target_branch}"
                )
            except Exception as e:
                logger.warning(f"Failed to publish proposal created event: {e}")

        return self._doc_to_proposal(proposal)

    async def merge_branch(
        self,
        proposal_id: str,
        strategy: MergeStrategy,
        user_id: str = "system",
        conflict_resolutions: Optional[Dict[str, Any]] = None
    ) -> MergeResult:
        """브랜치 머지 실행"""

        # 1. Proposal 조회 및 검증
        proposal = await self.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        if proposal.status != ProposalStatus.APPROVED:
            raise ValueError("Proposal must be approved before merge")

        # 2. 최신 상태 확인
        current_source = await self._get_branch_info(proposal.source_branch)
        # TODO: 타겟 브랜치 변경 검증 추가 필요
        # current_target = await self._get_branch_info(proposal.target_branch)

        if current_source.get("head") != proposal.source_hash:
            # 소스 브랜치가 변경됨
            raise ValueError(
                "Source branch has changed since proposal creation"
            )

        # 3. 머지 전략별 처리
        if strategy == MergeStrategy.MERGE:
            result = await self._perform_merge(
                proposal, conflict_resolutions, user_id
            )
        elif strategy == MergeStrategy.SQUASH:
            result = await self._perform_squash_merge(
                proposal, user_id
            )
        elif strategy == MergeStrategy.REBASE:
            result = await self._perform_rebase_merge(
                proposal, user_id
            )
        else:
            raise ValueError(f"Unknown merge strategy: {strategy}")

        # 4. Proposal 상태 업데이트
        await self._update_proposal_status(
            proposal_id,
            ProposalStatus.MERGED,
            user_id
        )

        # 5. 이벤트 발행
        if self.event_publisher:
            try:
                await self.event_publisher.publish_branch_merged(
                    source_branch=proposal.source_branch,
                    target_branch=proposal.target_branch,
                    proposal_id=proposal_id,
                    author=user_id,
                    merge_commit=result.merge_commit
                )
            except Exception as e:
                logger.warning(f"Failed to publish branch merged event: {e}")

        return result

    async def _perform_merge(
        self,
        proposal: ChangeProposal,
        conflict_resolutions: Optional[Dict[str, Any]],
        user_id: str
    ) -> MergeResult:
        """일반 머지 수행"""

        import time
        start_time = time.time()

        # 1. 3-way merge 알고리즘 실행
        target_head = await self._get_branch_head(proposal.target_branch)

        merge_result = await self.three_way_merge.merge(
            base_version=proposal.base_hash,
            source_version=proposal.source_hash,
            target_version=target_head
        )

        # 2. 충돌 처리
        if merge_result.conflicts:
            if not conflict_resolutions:
                raise ValueError("Conflict resolutions required")

            # 충돌 해결 적용
            for conflict in merge_result.conflicts:
                resolution = conflict_resolutions.get(conflict.resource_id)
                if not resolution:
                    raise ValueError(f"No resolution provided for conflict: {conflict.resource_id}")

                # 해결된 값으로 머지 결과 업데이트
                merge_result.merged_schemas[conflict.resource_id] = resolution

        # 3. Terminus DB에 머지된 스키마 적용
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            # 실제 TerminusDB는 자동 트랜잭션 지원, 수동 커밋 구현
            try:
                merge_changes = []
                for resource_id, schema in merge_result.merged_schemas.items():
                    if schema is None:
                        # 삭제된 리소스
                        await tdb.delete_document(
                            resource_id,
                            db=self.db_name,
                            branch=proposal.target_branch
                        )
                        merge_changes.append(f"Deleted {resource_id}")
                    else:
                        # 추가 또는 수정된 리소스
                        existing = await tdb.get_document(
                            resource_id,
                            db=self.db_name,
                            branch=proposal.target_branch
                        )
                        if existing:
                            await tdb.update_document(
                                schema,
                                db=self.db_name,
                                branch=proposal.target_branch,
                                message=f"Update {resource_id} during merge"
                            )
                            merge_changes.append(f"Updated {resource_id}")
                        else:
                            await tdb.insert_document(
                                schema,
                                db=self.db_name,
                                branch=proposal.target_branch,
                                message=f"Insert {resource_id} during merge"
                            )
                            merge_changes.append(f"Inserted {resource_id}")

                # 머지 완료 기록
                merge_commit = f"merge_{proposal.id}_{int(time.time())}"
                logger.info(f"Merge completed: {', '.join(merge_changes)}")

            except Exception as e:
                logger.error(f"Merge operation failed: {e}")
                raise

        # 4. 통계 업데이트
        end_time = time.time()
        execution_time_ms = int((end_time - start_time) * 1000)

        if merge_result.statistics:
            merge_result.statistics.merge_duration_ms = execution_time_ms
            merge_result.statistics.conflict_count = len(merge_result.conflicts)

        # 5. 결과 반환
        return MergeResult(
            merged_schemas=merge_result.merged_schemas,
            conflicts=merge_result.conflicts,
            statistics=merge_result.statistics,
            merge_commit=merge_commit,
            source_branch=proposal.source_branch,
            target_branch=proposal.target_branch,
            strategy="merge",
            conflicts_resolved=len(conflict_resolutions) if conflict_resolutions else 0,
            files_changed=len(merge_result.merged_schemas),
            execution_time_ms=execution_time_ms,
            merged_by=user_id,
            merged_at=datetime.utcnow()
        )

    async def _perform_squash_merge(
        self,
        proposal: ChangeProposal,
        user_id: str
    ) -> MergeResult:
        """Squash 머지 수행 - 문서 근거: 섹션 8.2"""

        user = {"id": user_id}
        return await self.merge_strategies.perform_squash_merge(proposal, user)

    async def _perform_rebase_merge(
        self,
        proposal: ChangeProposal,
        user_id: str
    ) -> MergeResult:
        """Rebase 머지 수행 - 문서 근거: 섹션 8.2"""

        user = {"id": user_id}
        return await self.merge_strategies.perform_rebase_merge(proposal, user)

    async def get_proposal(self, proposal_id: str) -> Optional[ChangeProposal]:
        """Proposal 조회"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            doc = await tdb.get_document(
                proposal_id,
                db=self.db_name,
                branch="_proposals"
            )

        return self._doc_to_proposal(doc) if doc else None

    async def list_proposals(
        self,
        branch: Optional[str] = None,
        status: Optional[ProposalStatus] = None,
        author: Optional[str] = None
    ) -> List[ChangeProposal]:
        """Proposal 목록 조회"""
        proposals = []

        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            docs = await tdb.get_all_documents(
                doc_type="ChangeProposal",
                db=self.db_name,
                branch="_proposals"
            )

        for doc in docs:
            proposal = self._doc_to_proposal(doc)

            # 필터링
            if branch and proposal.source_branch != branch and proposal.target_branch != branch:
                continue
            if status and proposal.status != status:
                continue
            if author and proposal.author != author:
                continue

            proposals.append(proposal)

        return proposals

    async def update_proposal(
        self,
        proposal_id: str,
        update: ProposalUpdate,
        user_id: str
    ) -> ChangeProposal:
        """Proposal 수정"""
        proposal = await self.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        # 업데이트 적용
        update_data = update.model_dump(exclude_unset=True)

        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            doc = await tdb.get_document(
                proposal_id,
                db=self.db_name,
                branch="_proposals"
            )

            for field, value in update_data.items():
                if value is not None:
                    doc[field] = value

            doc["updated_at"] = datetime.utcnow().isoformat()

            await tdb.update_document(
                doc,
                db=self.db_name,
                branch="_proposals",
                message=f"Update proposal {proposal_id}"
            )

        return self._doc_to_proposal(doc)

    async def approve_proposal(
        self,
        proposal_id: str,
        user_id: str,
        comment: Optional[str] = None
    ) -> ChangeProposal:
        """
        REQ-OMS-F2-AC6: Proposal 승인
        머지 승인 워크플로 - 보호된 브랜치 요구사항
        """
        proposal = await self.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        if proposal.status != ProposalStatus.REVIEW:
            raise ValueError("Proposal must be in review status")

        # 승인 추가
        approval = {
            "user_id": user_id,
            "approved_at": datetime.utcnow().isoformat(),
            "comment": comment
        }

        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            doc = await tdb.get_document(
                proposal_id,
                db=self.db_name,
                branch="_proposals"
            )

            doc["approvals"].append(approval)
            doc["status"] = ProposalStatus.APPROVED.value
            doc["updated_at"] = datetime.utcnow().isoformat()

            await tdb.update_document(
                doc,
                db=self.db_name,
                branch="_proposals",
                message=f"Approve proposal {proposal_id}"
            )

        # 이벤트 발행
        if self.event_publisher:
            try:
                await self.event_publisher.publish_proposal_status_changed(
                    proposal_id=proposal_id,
                    status="approved",
                    author=user_id,
                    comment=comment
                )
            except Exception as e:
                logger.warning(f"Failed to publish proposal approved event: {e}")

        return self._doc_to_proposal(doc)

    async def reject_proposal(
        self,
        proposal_id: str,
        user_id: str,
        reason: str
    ) -> ChangeProposal:
        """Proposal 거부"""
        proposal = await self.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        await self._update_proposal_status(
            proposal_id,
            ProposalStatus.REJECTED,
            user_id,
            comment=reason
        )

        # 이벤트 발행
        if self.event_publisher:
            try:
                await self.event_publisher.publish_proposal_status_changed(
                    proposal_id=proposal_id,
                    status="rejected",
                    author=user_id,
                    comment=reason
                )
            except Exception as e:
                logger.warning(f"Failed to publish proposal rejected event: {e}")

        return await self.get_proposal(proposal_id)

    async def get_branch_diff(
        self,
        source_branch: str,
        target_branch: str,
        format: str = "summary"
    ) -> BranchDiff:
        """
        REQ-OMS-F2-AC4: 브랜치 간 차이점 조회 - Preview 기능
        머지 전 미리보기를 위한 Diff 계산
        """
        # 브랜치 정보 조회
        source_info = await self._get_branch_info(source_branch)
        target_info = await self._get_branch_info(target_branch)

        if not source_info or not target_info:
            raise ValueError("Branch not found")

        # Diff 계산
        diff_result = await self.diff_engine.calculate_branch_diff(
            source_branch=source_branch,
            target_branch=target_branch,
            format=format
        )

        return diff_result

    async def _update_proposal_status(
        self,
        proposal_id: str,
        status: ProposalStatus,
        user_id: str,
        comment: Optional[str] = None
    ):
        """Proposal 상태 업데이트"""
        async with TerminusDBClient(self.tdb_endpoint) as tdb:
            doc = await tdb.get_document(
                proposal_id,
                db=self.db_name,
                branch="_proposals"
            )

            doc["status"] = status.value
            doc["updated_at"] = datetime.utcnow().isoformat()

            if status == ProposalStatus.MERGED:
                doc["merged_at"] = datetime.utcnow().isoformat()
                doc["merged_by"] = user_id

            await tdb.update_document(
                doc,
                db=self.db_name,
                branch="_proposals",
                message=f"Update proposal status to {status.value}"
            )

    async def _publish_event(self, event_type: str, data: Dict[str, Any]):
        """이벤트 발행"""
        if self.event_publisher:
            try:
                await self.event_publisher.publish(event_type, data)
            except Exception as e:
                logger.error(f"Failed to publish event {event_type}: {e}")

    def _doc_to_branch(self, doc: Dict[str, Any]) -> Branch:
        """문서를 Branch 모델로 변환"""
        return Branch(
            id=doc.get("id", doc.get("name")),
            name=doc["name"],
            display_name=doc.get("display_name", doc["name"]),
            description=doc.get("description"),
            parent_branch=doc.get("parent_branch"),
            is_protected=doc.get("is_protected", False),
            created_by=doc["created_by"],
            created_at=datetime.fromisoformat(doc["created_at"]) if isinstance(doc["created_at"], str) else doc["created_at"],
            modified_by=doc["modified_by"],
            modified_at=datetime.fromisoformat(doc["modified_at"]) if isinstance(doc["modified_at"], str) else doc["modified_at"],
            version_hash=doc.get("version_hash", ""),
            is_active=doc.get("is_active", True)
        )

    def _doc_to_proposal(self, doc: Dict[str, Any]) -> ChangeProposal:
        """문서를 ChangeProposal 모델로 변환"""
        return ChangeProposal(
            id=doc["id"],
            title=doc["title"],
            description=doc.get("description"),
            source_branch=doc["source_branch"],
            target_branch=doc["target_branch"],
            status=ProposalStatus(doc["status"]),
            base_hash=doc["base_hash"],
            source_hash=doc["source_hash"],
            target_hash=doc["target_hash"],
            conflicts=doc.get("conflicts", []),
            author=doc["author"],
            reviewers=doc.get("reviewers", []),
            approvals=doc.get("approvals", []),
            created_at=datetime.fromisoformat(doc["created_at"]) if isinstance(doc["created_at"], str) else doc["created_at"],
            updated_at=datetime.fromisoformat(doc["updated_at"]) if isinstance(doc["updated_at"], str) else doc["updated_at"],
            merged_at=datetime.fromisoformat(doc["merged_at"]) if doc.get("merged_at") and isinstance(doc["merged_at"], str) else doc.get("merged_at"),
            merged_by=doc.get("merged_by")
        )

    async def _is_protected_branch(self, branch_name: str) -> bool:
        """브랜치 보호 여부 확인"""
        # TODO: 브랜치 보호 규칙 구현
        return branch_name in ["main", "master", "production"]

    async def _get_branch_head(self, branch_name: str) -> str:
        """브랜치의 현재 HEAD 조회"""
        branch_info = await self._get_branch_info(branch_name)
        if not branch_info:
            raise ValueError(f"Branch {branch_name} not found")
        return branch_info.get("head", "")
