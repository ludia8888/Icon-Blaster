"""
Advanced Merge Strategies
섹션 8.2의 Squash/Rebase 머지 전략 구현
"""
import logging
from datetime import datetime
from typing import Dict, List

from core.branch.models import (
    ChangeProposal,
    MergeResult,
)
from database.clients.terminus_db import TerminusDBClient

logger = logging.getLogger(__name__)


class MergeStrategyImplementor:
    """고급 머지 전략 구현체"""

    def __init__(self, tdb_client: TerminusDBClient):
        self.tdb = tdb_client

    async def perform_squash_merge(
        self,
        proposal: ChangeProposal,
        user: Dict[str, str]
    ) -> MergeResult:
        """
        Squash 머지 수행

        문서 근거: 섹션 8.2의 MergeStrategy.SQUASH
        - 소스 브랜치의 모든 커밋을 하나로 합쳐서 타겟 브랜치에 적용
        - 커밋 히스토리가 깔끔하게 유지됨
        """

        logger.info(f"Performing squash merge for proposal {proposal.id}")

        try:
            # 1. 소스 브랜치의 모든 변경사항을 하나의 커밋으로 수집
            source_changes = await self._collect_branch_changes(
                base_branch=proposal.targetBranch,
                source_branch=proposal.sourceBranch
            )

            if not source_changes:
                raise ValueError("No changes to squash merge")

            # 2. 타겟 브랜치에서 새 브랜치 생성 (임시)
            temp_branch = f"temp_squash_{proposal.id}_{int(datetime.utcnow().timestamp())}"

            await self.tdb.create_branch(
                branch_name=temp_branch,
                origin_branch=proposal.targetBranch
            )

            # 3. 모든 변경사항을 하나의 트랜잭션으로 적용
            async with self.tdb.transaction(branch=temp_branch) as tx:

                # 모든 변경사항 적용
                for change in source_changes:
                    if change["operation"] == "create":
                        await tx.insert_document(change["document"])
                    elif change["operation"] == "update":
                        await tx.update_document(change["document_id"], change["document"])
                    elif change["operation"] == "delete":
                        await tx.delete_document(change["document_id"])

                # 단일 커밋으로 생성
                squash_commit_id = await tx.commit(
                    author=user.get("id", "system"),
                    message=self._generate_squash_commit_message(proposal, source_changes)
                )

            # 4. 타겟 브랜치를 임시 브랜치 상태로 업데이트
            await self.tdb.fast_forward_merge(
                source_branch=temp_branch,
                target_branch=proposal.targetBranch
            )

            # 5. 임시 브랜치 삭제
            await self.tdb.delete_branch(temp_branch)

            logger.info(f"Squash merge completed: {squash_commit_id}")

            return MergeResult(
                merge_commit=squash_commit_id,
                source_branch=proposal.sourceBranch,
                target_branch=proposal.targetBranch,
                conflicts_resolved=0,  # Squash merge는 충돌이 미리 해결됨
                strategy="squash",
                commits_squashed=len(source_changes)
            )

        except Exception as e:
            logger.error(f"Squash merge failed for proposal {proposal.id}: {e}")
            raise

    async def perform_rebase_merge(
        self,
        proposal: ChangeProposal,
        user: Dict[str, str]
    ) -> MergeResult:
        """
        Rebase 머지 수행

        문서 근거: 섹션 8.2의 MergeStrategy.REBASE
        - 소스 브랜치의 커밋들을 타겟 브랜치 최신 상태 위로 재적용
        - 선형적인 히스토리 유지
        """

        logger.info(f"Performing rebase merge for proposal {proposal.id}")

        try:
            # 1. 타겟 브랜치의 최신 상태 확인
            target_head = await self.tdb.get_branch_head(proposal.targetBranch)

            # 2. 소스 브랜치의 커밋 목록 조회 (베이스 이후)
            source_commits = await self._get_commits_since_base(
                branch=proposal.sourceBranch,
                base_commit=proposal.baseHash
            )

            if not source_commits:
                raise ValueError("No commits to rebase")

            # 3. 임시 rebase 브랜치 생성
            rebase_branch = f"temp_rebase_{proposal.id}_{int(datetime.utcnow().timestamp())}"

            await self.tdb.create_branch(
                branch_name=rebase_branch,
                origin_branch=proposal.targetBranch
            )

            # 4. 각 커밋을 순서대로 재적용
            rebased_commits = []

            for commit in source_commits:
                try:
                    # 커밋의 변경사항을 현재 rebase 브랜치에 적용
                    rebased_commit = await self._apply_commit_to_branch(
                        commit=commit,
                        target_branch=rebase_branch,
                        author=user.get("id", "system")
                    )

                    rebased_commits.append(rebased_commit)

                except Exception as conflict_error:
                    # Rebase 중 충돌 발생 시 중단
                    await self.tdb.delete_branch(rebase_branch)
                    raise ValueError(
                        f"Rebase conflict at commit {commit['id']}: {conflict_error}"
                    )

            # 5. 타겟 브랜치를 rebase된 상태로 업데이트
            final_commit = rebased_commits[-1] if rebased_commits else target_head

            await self.tdb.fast_forward_merge(
                source_branch=rebase_branch,
                target_branch=proposal.targetBranch
            )

            # 6. 임시 브랜치 정리
            await self.tdb.delete_branch(rebase_branch)

            logger.info(f"Rebase merge completed: {final_commit}")

            return MergeResult(
                merge_commit=final_commit,
                source_branch=proposal.sourceBranch,
                target_branch=proposal.targetBranch,
                conflicts_resolved=0,  # Rebase는 충돌 시 실패
                strategy="rebase",
                commits_rebased=len(rebased_commits)
            )

        except Exception as e:
            logger.error(f"Rebase merge failed for proposal {proposal.id}: {e}")
            raise

    async def _collect_branch_changes(
        self,
        base_branch: str,
        source_branch: str
    ) -> List[Dict]:
        """브랜치 간 모든 변경사항 수집"""

        # 베이스 브랜치와 소스 브랜치 간의 diff 계산
        diff_result = await self.tdb.compare_branches(
            base_branch=base_branch,
            compare_branch=source_branch
        )

        changes = []

        for change in diff_result.get("changes", []):
            if change["type"] == "added":
                changes.append({
                    "operation": "create",
                    "document": change["new_value"],
                    "document_id": change["id"]
                })
            elif change["type"] == "modified":
                changes.append({
                    "operation": "update",
                    "document": change["new_value"],
                    "document_id": change["id"]
                })
            elif change["type"] == "deleted":
                changes.append({
                    "operation": "delete",
                    "document_id": change["id"]
                })

        return changes

    async def _get_commits_since_base(
        self,
        branch: str,
        base_commit: str
    ) -> List[Dict]:
        """베이스 커밋 이후의 모든 커밋 조회"""

        commit_history = await self.tdb.get_commit_history(
            branch=branch,
            since=base_commit,
            limit=1000  # 합리적인 제한
        )

        # 베이스 커밋 제외하고 시간순 정렬
        commits = [
            commit for commit in commit_history
            if commit["id"] != base_commit
        ]

        # 시간순 정렬 (오래된 것부터)
        commits.sort(key=lambda c: c.get("timestamp", ""))

        return commits

    async def _apply_commit_to_branch(
        self,
        commit: Dict,
        target_branch: str,
        author: str
    ) -> str:
        """특정 커밋의 변경사항을 대상 브랜치에 적용"""

        # 커밋의 변경사항 추출
        commit_changes = await self.tdb.get_commit_changes(commit["id"])

        async with self.tdb.transaction(branch=target_branch) as tx:

            # 모든 변경사항 적용
            for change in commit_changes:
                if change["operation"] == "create":
                    await tx.insert_document(change["document"])
                elif change["operation"] == "update":
                    await tx.update_document(change["document_id"], change["document"])
                elif change["operation"] == "delete":
                    await tx.delete_document(change["document_id"])

            # 새 커밋 생성 (원본 메시지 유지)
            new_commit_id = await tx.commit(
                author=author,
                message=f"[REBASED] {commit.get('message', 'Rebased commit')}"
            )

        return new_commit_id

    def _generate_squash_commit_message(
        self,
        proposal: ChangeProposal,
        changes: List[Dict]
    ) -> str:
        """Squash 커밋 메시지 생성"""

        # 변경사항 통계
        stats = {
            "created": len([c for c in changes if c["operation"] == "create"]),
            "updated": len([c for c in changes if c["operation"] == "update"]),
            "deleted": len([c for c in changes if c["operation"] == "delete"])
        }

        base_message = f"[SQUASHED] {proposal.title}"

        if proposal.description:
            base_message += f"\n\n{proposal.description}"

        # 통계 정보 추가
        stats_line = []
        if stats["created"]:
            stats_line.append(f"{stats['created']} created")
        if stats["updated"]:
            stats_line.append(f"{stats['updated']} updated")
        if stats["deleted"]:
            stats_line.append(f"{stats['deleted']} deleted")

        if stats_line:
            base_message += f"\n\nChanges: {', '.join(stats_line)}"

        base_message += f"\n\nSquashed from branch: {proposal.sourceBranch}"

        return base_message
