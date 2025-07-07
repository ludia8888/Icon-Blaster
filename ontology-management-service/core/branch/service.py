"""
REQ-OMS-F2: 브랜치 관리 핵심 서비스
버전 제어 (Branching & Merge) 시스템 구현
"""
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
import json
import httpx

from shared.models.domain import Branch as DomainBranch
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
    DiffEntry,
)
from middleware.three_way_merge import JsonMerger, MergeStrategy as MiddlewareMergeStrategy
from database.clients.terminus_db import TerminusDBClient

logger = logging.getLogger(__name__)


class BranchService:
    """
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
        self.tdb = TerminusDBClient(endpoint=tdb_endpoint)
        self.diff_engine = diff_engine
        self.conflict_resolver = conflict_resolver
        self.event_publisher = event_publisher
        self.db_name = os.getenv("TERMINUSDB_DB", "oms")
        self.merger = JsonMerger()
        self.merge_strategies = MergeStrategyImplementor(self.tdb)

    async def initialize(self):
        try:
            async with self.tdb:
                await self.tdb.create_database(self.db_name)
                logger.info(f"Database {self.db_name} initialized")
        except Exception as e:
            logger.warning(f"Database initialization failed: {e}")

    def _generate_id(self) -> str:
        return str(uuid.uuid4())

    def _generate_proposal_id(self) -> str:
        return f"proposal_{self._generate_id()}"

    def _validate_branch_name(self, name: str) -> bool:
        import re
        pattern = r'^[a-z][a-z0-9\-/]*$'
        return bool(re.match(pattern, name))

    async def _branch_exists(self, name: str) -> bool:
        logger.warning("Branch existence check is not yet implemented.")
        return False

    async def _get_branch_info(self, branch_name: str) -> Optional[Dict[str, Any]]:
        logger.warning("Get branch info is not yet implemented.")
        return None

    async def _get_branch_head(self, branch_name: str) -> Optional[str]:
        info = await self._get_branch_info(branch_name)
        return info.get("head") if info else None

    async def _is_protected_branch(self, branch_name: str) -> bool:
        if branch_name in ["main", "master", "_system", "_proposals"]:
            return True
        logger.warning("Protected branch check is not yet implemented.")
        return False

    async def create_branch(
        self, name: str, from_branch: str = "main", description: Optional[str] = None, user_id: str = "system"
    ) -> DomainBranch:
        """
        새로운 브랜치를 생성하고 메타데이터를 저장합니다.

        1. 이름 유효성 검사
        2. 중복 존재 여부 확인
        3. TerminusDB에 네이티브 브랜치 생성
        4. _system 브랜치에 메타데이터 문서 저장
        5. 이벤트 발행
        6. 완성된 브랜치 객체 반환

        Args:
            name (str): 새 브랜치 이름
            from_branch (str, optional): 기반이 될 브랜치. Defaults to "main".
            description (Optional[str], optional): 브랜치 설명. Defaults to None.
            user_id (str, optional): 생성자 ID. Defaults to "system".

        Raises:
            ValueError: 브랜치 이름이 유효하지 않거나 이미 존재할 경우
            Exception: 데이터베이스 작업 중 오류 발생 시

        Returns:
            DomainBranch: 생성된 브랜치의 상세 정보
        """
        logger.info(f"Attempting to create branch '{name}' from '{from_branch}' by user '{user_id}'.")
        
        # 1. 브랜치 이름 유효성 검사
        if not self._validate_branch_name(name):
            raise ValueError(f"Invalid branch name: {name}")

        # 2. 중복 존재 여부 확인
        existing_branch = await self.get_branch(name)
        if existing_branch:
            raise ValueError(f"Branch '{name}' already exists.")

        # 3. TerminusDB에 네이티브 브랜치 생성
        created = await self.tdb.create_branch(self.db_name, name, from_branch)
        if not created:
            # create_branch가 False를 반환하는 경우는 이미 존재할 때 이지만, get_branch에서 확인했으므로
            # 여기 도달했다면 다른 생성 실패 케이스로 간주
            raise Exception(f"Failed to create branch '{name}' in TerminusDB for an unknown reason.")

        # 4. _system 브랜치에 메타데이터 문서 저장
        now = datetime.utcnow()
        document_id = f"Branch/{name}"
        branch_metadata = {
            "@type": "Branch",
            "@id": document_id,
            "name": name,
            "displayName": name.replace("-", " ").replace("_", " ").title(),
            "description": description,
            "parentBranch": from_branch,
            "isProtected": False,
            "createdBy": user_id,
            "createdAt": now.isoformat() + "Z", # ISO 8601 UTC format
            "modifiedBy": user_id,
            "modifiedAt": now.isoformat() + "Z",
            "isActive": True
        }
        
        try:
            await self.tdb.insert_document(
                self.db_name,
                "_system",
                branch_metadata,
                commit_msg=f"Create metadata for branch '{name}'"
            )
            logger.info(f"Metadata for branch '{name}' created in _system branch.")
        except Exception as e:
            # 롤백: 메타데이터 생성 실패 시 네이티브 브랜치 삭제 시도
            logger.error(f"Failed to insert metadata for branch '{name}'. Attempting to roll back. Error: {e}")
            # await self.terminus_client.delete_branch(self.db_name, name) # 롤백 로직은 정책에 따라 추가
            raise Exception(f"Failed to insert metadata for branch '{name}'.") from e

        # 5. 이벤트 발행 (구현되어 있다면)
        if self.event_publisher:
            try:
                # 이벤트 발행에 필요한 데이터 형식에 맞춰 전달해야 함
                await self.event_publisher.publish_branch_created(
                    branch_name=name,
                    parent_branch=from_branch,
                    author=user_id,
                    description=description,
                    metadata={"id": document_id}
                )
                logger.info(f"Published 'branch.created' event for branch '{name}'.")
            except Exception as e:
                # 이벤트 발행 실패는 non-critical로 처리하고 로그만 남김
                logger.warning(f"Failed to publish branch creation event for '{name}': {e}")
        
        # 6. 완성된 브랜치 객체 반환
        # get_branch를 호출하여 DB에서 직접 읽어와 일관성을 보장
        final_branch = await self.get_branch(name)
        if not final_branch:
             # 이 경우는 거의 발생하지 않아야 함.
             raise Exception(f"Could not retrieve branch '{name}' immediately after creation.")
        return final_branch

    async def get_branch(self, branch_name: str) -> Optional[DomainBranch]:
        """
        특정 브랜치의 상세 정보를 가져옵니다.

        Args:
            branch_name (str): 조회할 브랜치 이름

        Returns:
            Optional[DomainBranch]: 브랜치 정보 객체. 브랜치가 없으면 None을 반환합니다.
        
        Raises:
            Exception: 데이터베이스 조회 중 에러 발생 시
        """
        logger.info(f"Fetching details for branch: {branch_name}")
        try:
            # 1. TerminusDB 네이티브 API로 브랜치 기본 정보 조회
            branch_info = await self.tdb.get_branch_info(self.db_name, branch_name)
            if not branch_info:
                logger.warning(f"Branch '{branch_name}' does not exist in TerminusDB.")
                return None

            head_commit_id = branch_info.get("head")
            # TerminusDB는 브랜치 정보에 마지막 수정 시간을 포함할 수 있습니다.
            # 하지만 여기서는 메타데이터를 우선시하고, 없을 경우 현재 시간으로 대체합니다.
            last_modified_raw = branch_info.get("@timestamp")
            last_modified = datetime.fromtimestamp(last_modified_raw) if last_modified_raw else datetime.utcnow()
            
            # 2. _system 브랜치에서 브랜치 메타데이터 문서 조회
            document_id = f"Branch/{branch_name}"
            metadata_doc = await self.tdb.get_document(self.db_name, "_system", document_id)

            if not metadata_doc:
                logger.warning(f"Metadata document not found for branch '{branch_name}'. "
                               f"Returning branch object with basic info from branch head.")
                return DomainBranch(
                    id=branch_name,
                    name=branch_name,
                    displayName=branch_name.title(),
                    versionHash=head_commit_id or "unknown",
                    createdBy="system", 
                    createdAt=last_modified, # 정확한 생성 시간을 알 수 없으므로 마지막 수정 시간으로 대체
                    modifiedBy="system",
                    modifiedAt=last_modified,
                )

            # 3. 정보 조합하여 DomainBranch 객체 생성
            created_at_str = metadata_doc.get("createdAt")
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00")) if created_at_str else datetime.utcnow()
            
            modified_at_str = metadata_doc.get("modifiedAt")
            # 수정 시간이 없다면 생성 시간으로 대체
            modified_at = datetime.fromisoformat(modified_at_str.replace("Z", "+00:00")) if modified_at_str else created_at
            
            return DomainBranch(
                id=metadata_doc.get("@id", document_id),
                name=metadata_doc.get("name", branch_name),
                displayName=metadata_doc.get("displayName", branch_name.title()),
                description=metadata_doc.get("description"),
                parentBranch=metadata_doc.get("parentBranch"),
                isProtected=metadata_doc.get("isProtected", False),
                createdBy=metadata_doc.get("createdBy", "unknown"),
                createdAt=created_at,
                modifiedBy=metadata_doc.get("modifiedBy", "unknown"),
                modifiedAt=modified_at,
                versionHash=head_commit_id or "unknown",
                isActive=metadata_doc.get("isActive", True),
            )

        except httpx.HTTPError as e:
            logger.error(f"HTTP error while fetching branch '{branch_name}': {e}")
            # 특정 유형의 오류는 더 구체적으로 처리할 수 있습니다.
            raise Exception(f"Failed to fetch branch '{branch_name}' due to a network issue.") from e
        except Exception as e:
            logger.error(f"An unexpected error occurred while fetching branch '{branch_name}': {e}")
            raise

    async def list_branches(self, include_system: bool = False, status: Optional[str] = None) -> List[DomainBranch]:
        """모든 브랜치 메타데이터를 _system 브랜치에서 조회합니다."""
        logger.info("Listing branches from _system branch")
        try:
            async with TerminusDBClient(self.tdb_endpoint) as tdb:
                # _system 브랜치에서 type이 'Branch'인 모든 문서를 가져오는 WOQL 쿼리
                woql_query = {
                    "@type": "Triple",
                    "subject": {"@type": "Variable", "name": "doc_uri"},
                    "predicate": {"@type": "NodeValue", "node": "rdf:type"},
                    "object": {"@type": "NodeValue", "node": "Branch"}
                }
                
                # WOQL 쿼리를 사용하여 문서의 전체 내용을 가져오도록 수정
                full_query = {
                    "@type": "Select",
                    "variables": ["doc"],
                    "query": {
                        "@type": "And",
                        "and": [
                            woql_query,
                            {
                                "@type": "Get",
                                "resource": {"@type": "Variable", "name": "doc_uri"},
                                "value": {"@type": "Variable", "name": "doc"}
                            }
                        ]
                    }
                }

                result = await tdb.query_branch(
                    db_name=self.db_name, 
                    branch_name="_system", 
                    query=json.dumps(full_query)
                )
                
                bindings = result.get("bindings", [])
                if not bindings:
                    return []

                branches = [DomainBranch(**item['doc']) for item in bindings]

                # 필터링 로직
                if not include_system:
                    branches = [b for b in branches if b.name not in ["_system", "_proposals"]]
                
                if status:
                    is_active = status.lower() == 'active'
                    branches = [b for b in branches if b.isActive == is_active]
                    
                return branches
                
        except Exception as e:
            logger.error(f"Failed to list branches: {e}", exc_info=True)
            return []

    async def delete_branch(self, branch_name: str, user_id: str = "system") -> bool:
        """
        브랜치와 관련 메타데이터를 삭제합니다.

        1. 브랜치 존재 및 보호 여부 확인
        2. _system 브랜치에서 메타데이터 문서 삭제
        3. TerminusDB에서 네이티브 브랜치 삭제
        4. 이벤트 발행

        Args:
            branch_name (str): 삭제할 브랜치 이름
            user_id (str, optional): 삭제 요청자 ID. Defaults to "system".

        Raises:
            ValueError: 브랜치를 찾을 수 없거나 보호된 브랜치일 경우

        Returns:
            bool: 성공적으로 삭제된 경우 True
        """
        logger.info(f"Attempting to delete branch '{branch_name}' by user '{user_id}'.")

        # 1. 브랜치 존재 및 보호 여부 확인
        if not await self.get_branch(branch_name):
            raise ValueError(f"Branch '{branch_name}' not found.")

        if self._is_protected_branch(branch_name):
            raise ValueError(f"Cannot delete protected branch: {branch_name}")

        # 2. _system 브랜치에서 메타데이터 문서 삭제
        document_id = f"Branch/{branch_name}"
        try:
            deleted_meta = await self.tdb.delete_document(
                self.db_name,
                "_system",
                document_id,
                commit_msg=f"Delete metadata for branch '{branch_name}'"
            )
            if deleted_meta:
                logger.info(f"Metadata document '{document_id}' for branch '{branch_name}' deleted.")
            else:
                logger.warning(f"Metadata document for branch '{branch_name}' not found, continuing with branch deletion.")
        except Exception as e:
            logger.error(f"Failed to delete metadata for branch '{branch_name}': {e}")
            # 메타데이터 삭제 실패 시, 브랜치 삭제를 진행하지 않음
            raise Exception(f"Failed to delete metadata for branch '{branch_name}'.") from e
            
        # 3. TerminusDB에서 네이티브 브랜치 삭제
        try:
            deleted_branch = await self.tdb.delete_branch(self.db_name, branch_name)
            if not deleted_branch:
                 # 이미 지워졌거나 없는 경우, 경고만 로깅하고 성공으로 간주
                 logger.warning(f"Native branch '{branch_name}' was not found during deletion, but proceeding.")
            logger.info(f"Native branch '{branch_name}' deleted successfully.")
        except Exception as e:
            # 네이티브 브랜치 삭제 실패는 심각한 오류. 하지만 메타데이터는 이미 지워진 상태.
            # 이 경우 수동 개입이 필요할 수 있음을 알리는 매우 심각한 로그를 남겨야 함.
            logger.critical(f"CRITICAL: Failed to delete native branch '{branch_name}' after its metadata was removed. Manual intervention required. Error: {e}")
            raise Exception(f"Failed to delete native branch '{branch_name}'.") from e
            
        # 4. 이벤트 발행
        if self.event_publisher:
            try:
                await self.event_publisher.publish_branch_deleted(
                    branch_name=branch_name,
                    author=user_id,
                )
                logger.info(f"Published 'branch.deleted' event for branch '{branch_name}'.")
            except Exception as e:
                logger.warning(f"Failed to publish branch deletion event for '{branch_name}': {e}")

        return True

    async def create_proposal(
        self, source_branch: str, target_branch: str, title: str,
        description: Optional[str] = None, user_id: str = "system"
    ) -> ChangeProposal:
        logger.warning("create_proposal is not fully implemented.")
        proposal_id = self._generate_proposal_id()
        now = datetime.utcnow()
        proposal_data = {
            "id": proposal_id, "title": title, "description": description,
            "source_branch": source_branch, "target_branch": target_branch,
            "status": ProposalStatus.DRAFT, "base_hash": "", "source_hash": "", "target_hash": "",
            "author": user_id, "created_at": now, "updated_at": now
        }
        if self.event_publisher:
            await self._publish_event("proposal.created", proposal_data)
        return ChangeProposal(**proposal_data)

    async def merge_branch(
        self, proposal_id: str, strategy: MergeStrategy, user_id: str = "system",
        conflict_resolutions: Optional[Dict[str, Any]] = None
    ) -> MergeResult:
        logger.warning("merge_branch is not fully implemented.")
        return MergeResult() # Return default empty MergeResult

    async def get_branch_diff(self, source_branch: str, target_branch: str, format: str = "summary") -> BranchDiff:
        logger.warning("get_branch_diff is not fully implemented.")
        return BranchDiff(
            source_branch=source_branch, target_branch=target_branch, base_hash="",
            source_hash="", target_hash="", total_changes=0, additions=0, modifications=0,
            deletions=0, renames=0
        )

    async def get_proposal(self, proposal_id: str) -> Optional[ChangeProposal]:
        logger.warning("get_proposal is not implemented.")
        return None

    async def list_proposals(
        self, branch: Optional[str] = None, status: Optional[ProposalStatus] = None, author: Optional[str] = None
    ) -> List[ChangeProposal]:
        logger.warning("list_proposals is not implemented.")
        return []

    async def update_proposal(self, proposal_id: str, update: ProposalUpdate, user_id: str) -> ChangeProposal:
        logger.warning("update_proposal is not implemented.")
        proposal = await self.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        return proposal

    async def approve_proposal(self, proposal_id: str, user_id: str, comment: Optional[str] = None) -> ChangeProposal:
        logger.warning("approve_proposal is not implemented.")
        proposal = await self.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        return proposal

    async def reject_proposal(self, proposal_id: str, user_id: str, reason: str) -> ChangeProposal:
        logger.warning("reject_proposal is not implemented.")
        proposal = await self.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        return proposal

    async def commit_changes(self, branch: str, message: str, author: str = "system") -> str:
        """Commit changes to a branch and return commit ID"""
        logger.warning("commit_changes is not fully implemented.")
        # For now, return a dummy commit ID
        import uuid
        commit_id = str(uuid.uuid4())[:16]
        
        if self.event_publisher:
            await self._publish_event("branch.commit", {
                "branch": branch,
                "message": message,
                "author": author,
                "commit_id": commit_id,
                "timestamp": datetime.utcnow().isoformat()
            })
        
        return commit_id

    async def create_pull_request(
        self, 
        source_branch: str, 
        target_branch: str, 
        title: str, 
        description: Optional[str] = None, 
        created_by: str = "system"
    ) -> Dict[str, Any]:
        """Create a pull request and return PR info"""
        logger.warning("create_pull_request is not fully implemented.")
        
        # For now, return a dummy PR result
        import uuid
        pr_id = str(uuid.uuid4())[:16]
        
        pr_result = {
            "id": pr_id,
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title,
            "description": description,
            "created_by": created_by,
            "status": "open",
            "created_at": datetime.utcnow().isoformat()
        }
        
        if self.event_publisher:
            await self._publish_event("pull_request.created", pr_result)
        
        return pr_result

    async def _publish_event(self, event_type: str, data: Dict[str, Any]):
        if self.event_publisher:
            try:
                await self.event_publisher.publish(event_type, data)
            except Exception as e:
                logger.error(f"Failed to publish event {event_type}: {e}")

    async def update_branch_properties(
        self, branch_name: str, updates: Dict[str, Any], user_id: str = "system"
    ) -> DomainBranch:
        """
        브랜치의 속성(메타데이터)을 업데이트합니다.

        Args:
            branch_name (str): 업데이트할 브랜치 이름
            updates (Dict[str, Any]): 변경할 속성 딕셔너리 (e.g., {"description": "new desc"})
            user_id (str, optional): 요청자 ID. Defaults to "system".

        Raises:
            ValueError: 브랜치를 찾을 수 없거나 업데이트하려는 속성이 유효하지 않을 경우
            Exception: 데이터베이스 작업 중 오류 발생 시

        Returns:
            DomainBranch: 업데이트된 브랜치의 상세 정보
        """
        logger.info(f"Attempting to update properties for branch '{branch_name}' by user '{user_id}'.")
        
        document_id = f"Branch/{branch_name}"

        # 1. 원본 메타데이터 문서 조회
        original_doc = await self.tdb.get_document(self.db_name, "_system", document_id)
        if not original_doc:
            raise ValueError(f"Could not find metadata for branch '{branch_name}' to update.")

        # 2. 변경 사항 적용
        updated_doc = original_doc.copy()
        for key, value in updates.items():
            # 모델에 정의된 필드만 업데이트하도록 제한할 수 있습니다.
            # 여기서는 전달된 모든 키를 업데이트한다고 가정합니다.
            updated_doc[key] = value
        
        # 수정자 및 수정 시간 업데이트
        updated_doc["modifiedBy"] = user_id
        updated_doc["modifiedAt"] = datetime.utcnow().isoformat() + "Z"

        # 3. 문서 업데이트
        try:
            await self.tdb.update_document(
                self.db_name,
                "_system",
                updated_doc,
                commit_msg=f"Update properties for branch '{branch_name}'"
            )
            logger.info(f"Successfully updated properties for branch '{branch_name}'.")
        except Exception as e:
            logger.error(f"Failed to update document for branch '{branch_name}': {e}")
            raise Exception("Failed to save branch property updates.") from e

        # 4. 이벤트 발행
        if self.event_publisher:
            try:
                await self.event_publisher.publish_branch_updated(
                    branch_name=branch_name,
                    updates=updates,
                    author=user_id,
                )
                logger.info(f"Published 'branch.updated' event for branch '{branch_name}'.")
            except Exception as e:
                logger.warning(f"Failed to publish branch update event for '{branch_name}': {e}")
        
        # 5. 최신 정보 반환
        updated_branch = await self.get_branch(branch_name)
        if not updated_branch:
            raise Exception(f"Could not retrieve branch '{branch_name}' immediately after update.")
        
        return updated_branch
