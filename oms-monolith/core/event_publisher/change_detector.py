"""
REQ-OMS-IF1-AC1: Terminus DB 변경 감지
REQ-OMS-IF1-AC4: Funnel 서비스 트리거
섹션 8.5.2의 Change Detector 구현
"""
import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional

from services.event_publisher.core.models import Change
from services.event_publisher.core.state_store import StateStore
from shared.clients.terminus_db import TerminusDBClient

logger = logging.getLogger(__name__)


class ChangeDetector:
    """
    REQ-OMS-IF1-AC1: Terminus DB 변경 감지
    모든 스키마 변경 사항에 대한 이벤트 발행
    """

    def __init__(
        self,
        tdb_client: TerminusDBClient,
        state_store: StateStore
    ):
        self.tdb = tdb_client
        self.state = state_store
        self.poll_interval = 1.0  # 1초

    async def start_polling(self):
        """
        REQ-OMS-IF1-AC1: 변경 감지 폴링 시작
        스키마 변경 사항을 지속적으로 모니터링
        """

        while True:
            start_time = time.time()

            try:
                await self._poll_changes()
            except Exception as e:
                logger.error(f"Polling error: {e}")

            # 정확히 1초 간격 유지
            elapsed = time.time() - start_time
            sleep_time = max(0, self.poll_interval - elapsed)
            await asyncio.sleep(sleep_time)

    async def _poll_changes(self):
        """모든 브랜치의 변경사항 확인"""

        # 활성 브랜치 목록
        branches = await self.tdb.list_branches()

        for branch in branches:
            if branch.name.startswith("_"):
                # 시스템 브랜치 제외
                continue

            # 현재 HEAD
            current_head = await self._get_branch_head(branch.name)

            # 마지막 확인한 HEAD
            last_head = await self.state.get(f"branch:{branch.name}:head")

            if current_head != last_head:
                # 변경 감지
                await self._handle_branch_change(
                    branch.name,
                    last_head,
                    current_head
                )

                # 상태 업데이트
                await self.state.set(
                    f"branch:{branch.name}:head",
                    current_head
                )

    async def _handle_branch_change(
        self,
        branch: str,
        old_head: Optional[str],
        new_head: str
    ):
        """브랜치 변경 처리"""

        # 1. 커밋 정보 조회
        if old_head:
            # 증분 변경
            commits = await self._get_commits_between(
                branch, old_head, new_head
            )
        else:
            # 초기 상태
            commits = await self._get_all_commits(branch, new_head)

        # 2. 각 커밋에 대한 이벤트 생성
        for commit in commits:
            changes = await self._analyze_commit(branch, commit)

            # 3. Outbox에 이벤트 추가
            for change in changes:
                await self._create_outbox_event(
                    branch, commit, change
                )

    async def _analyze_commit(
        self,
        branch: str,
        commit: Dict
    ) -> List[Change]:
        """커밋 내용 분석"""

        # 커밋의 diff 조회
        diff = await self.tdb.get_commit_diff(
            branch=branch,
            commit_id=commit["id"]
        )

        changes = []

        for item in diff:
            if item["type"] == "create":
                changes.append(Change(
                    operation="create",
                    resource_type=self._extract_resource_type(item["path"]),
                    resource_id=self._extract_resource_id(item["path"]),
                    new_value=item["value"]
                ))
            elif item["type"] == "update":
                changes.append(Change(
                    operation="update",
                    resource_type=self._extract_resource_type(item["path"]),
                    resource_id=self._extract_resource_id(item["path"]),
                    old_value=item["old_value"],
                    new_value=item["new_value"]
                ))
            elif item["type"] == "delete":
                changes.append(Change(
                    operation="delete",
                    resource_type=self._extract_resource_type(item["path"]),
                    resource_id=self._extract_resource_id(item["path"]),
                    old_value=item["old_value"]
                ))

        return changes

    def _extract_resource_type(self, path: str) -> str:
        """경로에서 리소스 타입 추출"""
        # 예: "ObjectType_Order" -> "object_type"
        if path.startswith("ObjectType_"):
            return "object_type"
        elif path.startswith("Property_"):
            return "property"
        elif path.startswith("LinkType_"):
            return "link_type"
        elif path.startswith("ActionType_"):
            return "action_type"
        else:
            return "unknown"

    def _extract_resource_id(self, path: str) -> str:
        """경로에서 리소스 ID 추출"""
        # 예: "ObjectType_Order" -> "Order"
        parts = path.split("_", 1)
        return parts[1] if len(parts) > 1 else path

    async def _get_branch_head(self, branch: str) -> Optional[str]:
        """브랜치의 현재 HEAD 조회"""
        try:
            result = await self.tdb.get_branch_info(branch)
            return result.get("head") if result else None
        except Exception as e:
            logger.error(f"Failed to get branch head for {branch}: {e}")
            return None

    async def _get_commits_between(
        self,
        branch: str,
        old_head: str,
        new_head: str
    ) -> List[Dict]:
        """두 커밋 사이의 커밋 목록 조회"""
        query = """
        SELECT ?commit ?id ?author ?message ?timestamp
        WHERE {
            ?commit a ont:Commit .
            ?commit ont:branch $branch .
            ?commit ont:id ?id .
            ?commit ont:author ?author .
            ?commit ont:message ?message .
            ?commit ont:timestamp ?timestamp .
            FILTER(?timestamp > $old_timestamp && ?timestamp <= $new_timestamp)
        }
        ORDER BY ?timestamp
        """

        return await self.tdb.query(
            query,
            branch=branch,
            bindings={
                "branch": branch,
                "old_timestamp": old_head,
                "new_timestamp": new_head
            }
        )

    async def _get_all_commits(self, branch: str, head: str) -> List[Dict]:
        """브랜치의 모든 커밋 조회"""
        query = """
        SELECT ?commit ?id ?author ?message ?timestamp
        WHERE {
            ?commit a ont:Commit .
            ?commit ont:branch $branch .
            ?commit ont:id ?id .
            ?commit ont:author ?author .
            ?commit ont:message ?message .
            ?commit ont:timestamp ?timestamp .
        }
        ORDER BY ?timestamp
        """

        return await self.tdb.query(
            query,
            branch=branch,
            bindings={"branch": branch}
        )

    async def _create_outbox_event(
        self,
        branch: str,
        commit: Dict,
        change: Change
    ):
        """Outbox 이벤트 생성"""
        event_id = str(uuid.uuid4())

        # 이벤트 타입 결정
        event_type = "schema.changed"

        # 이벤트 페이로드 구성
        payload = {
            "branch": branch,
            "commit_id": commit["id"],
            "author": commit["author"],
            "timestamp": commit["timestamp"],
            "change": {
                "operation": change.operation,
                "resource_type": change.resource_type,
                "resource_id": change.resource_id,
                "old_value": change.old_value,
                "new_value": change.new_value
            }
        }

        # Outbox에 이벤트 저장
        doc = {
            "@type": "OutboxEvent",
            "@id": f"OutboxEvent_{event_id}",
            "id": event_id,
            "type": event_type,
            "payload": json.dumps(payload),
            "created_at": datetime.utcnow().isoformat(),
            "status": "pending",
            "retry_count": 0
        }

        await self.tdb.insert_document(
            document=doc,
            branch="_outbox",
            message=f"Create outbox event for {change.resource_type} {change.operation}",
            author="event-publisher"
        )
