"""
Schema Service - Refactored with Repository Pattern
리포지토리 패턴을 적용하여 비즈니스 로직과 데이터 접근 로직을 분리.
"""
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from models.domain import ObjectType, ObjectTypeCreate
from shared.terminus_context import get_author, get_branch
from core.interfaces.schema import SchemaServiceProtocol
from .repository import SchemaRepository

logger = logging.getLogger(__name__)


class SchemaService(SchemaServiceProtocol):
    """
    스키마 관리 서비스 - 브랜치 기반 워크플로우.
    
    스키마 변경은 다음과 같은 프로세스를 따릅니다:
    1. 스키마 변경을 위한 브랜치 생성 (schema-change/XXXX)
    2. 브랜치에서 스키마 변경사항 작성
    3. PR(Pull Request)을 통한 리뷰 및 승인
    4. main 브랜치로 병합
    """

    def __init__(
        self, 
        repository: SchemaRepository,
        branch_service: 'BranchService',  # 브랜치 관리를 위한 서비스
        event_publisher: Optional[Any] = None
    ):
        """
        서비스 초기화.
        
        Args:
            repository (SchemaRepository): 데이터 접근을 담당하는 리포지토리
            branch_service (BranchService): 브랜치 관리 서비스
            event_publisher (Optional[Any]): 이벤트 발행을 위한 퍼블리셔
        """
        self.repository = repository
        self.branch_service = branch_service
        self.event_publisher = event_publisher

    async def list_object_types(self, branch: str = "main") -> List[Dict[str, Any]]:
        """모든 ObjectType의 목록을 조회합니다."""
        try:
            return await self.repository.list_all_object_types(branch)
        except Exception as e:
            logger.error(f"Error listing object types: {e}")
            # 서비스 계층에서는 비즈니스 요구사항에 따라 빈 리스트를 반환하거나
            # 예외를 다시 발생시킬 수 있습니다.
            return []

    async def create_object_type(self, branch: str, data: ObjectTypeCreate, use_branch_workflow: bool = True) -> ObjectType:
        """
        새로운 ObjectType을 생성합니다.
        
        Args:
            branch: 타겟 브랜치 (use_branch_workflow=False일 때만 사용)
            data: 생성할 ObjectType 데이터
            use_branch_workflow: True면 PR 워크플로우 사용, False면 직접 생성
        """
        try:
            # 1. 권한 확인
            user = {"user_id": get_author(), "branch": branch}
            if not await self._check_permission(user, "schema:write", branch):
                raise PermissionError(f"사용자 {get_author()}는 스키마 쓰기 권한이 없습니다.")

            # 2. 유효성 검증
            validation_result = await self._validate_object_type(data)
            if not validation_result["valid"]:
                raise ValueError(f"Invalid ObjectType data: {validation_result.get('reason')}")

            if use_branch_workflow:
                # 브랜치 기반 워크플로우 사용
                # 1. 스키마 생성을 위한 브랜치 생성
                create_branch_name = f"schema-create/{data.name}-{uuid.uuid4().hex[:8]}"
                await self.branch_service.create_branch(
                    branch_name=create_branch_name,
                    parent_branch="main",
                    created_by=get_author()
                )
                
                # 2. 새 브랜치에서 스키마 생성
                success = await self.repository.create_new_object_type(
                    branch=create_branch_name,
                    data=data,
                    author=get_author()
                )
                
                if not success:
                    raise Exception(f"Failed to create ObjectType in branch '{create_branch_name}'")
                
                # 3. 커밋 생성
                commit_id = await self.branch_service.commit_changes(
                    branch=create_branch_name,
                    message=f"Create new schema: {data.name}",
                    author=get_author()
                )
                
                # 4. PR 생성
                pr_result = await self.branch_service.create_pull_request(
                    source_branch=create_branch_name,
                    target_branch="main",
                    title=f"Create new schema: {data.name}",
                    description=f"New schema creation by {get_author()}\n\n{data.description or 'No description'}",
                    created_by=get_author()
                )
                
                logger.info(f"Created PR for new schema: {pr_result.get('pr_id')}")
                
                # PR이 생성되었으므로 비동기적으로 처리됨
                return ObjectType(
                    id=data.name,
                    name=data.name,
                    display_name=data.display_name or data.name,
                    description=data.description,
                    properties=[],
                    version_hash=pr_result.get("pr_id", str(uuid.uuid4())[:16]),
                    created_by=get_author(),
                    created_at=datetime.now(),
                    modified_by=get_author(),
                    modified_at=datetime.now()
                )
            else:
                # 직접 생성 (기존 방식)
                success = await self.repository.create_new_object_type(branch, data, get_author())
                
                if success:
                    logger.info(f"Created ObjectType: {data.name} in branch {branch}")
                    await self._publish_schema_event("schema_created", {"name": data.name, "branch": branch})

                    return ObjectType(
                        id=data.name,
                        name=data.name,
                        display_name=data.display_name or data.name,
                        description=data.description,
                        properties=[],
                        version_hash=str(uuid.uuid4())[:16],
                        created_by=get_author(),
                        created_at=datetime.now(),
                        modified_by=get_author(),
                        modified_at=datetime.now()
                    )
                else:
                    raise Exception(f"Failed to create ObjectType: {data.name}")
                
        except Exception as e:
            logger.error(f"Error creating object type: {e}")
            raise

    async def _check_permission(self, user: Dict[str, Any], permission: str, branch: str) -> bool:
        """권한 확인 - 실제 구현"""
        logger.warning(f"Permission check for {permission} by {user.get('user_id')} on {branch} - NOT IMPLEMENTED")
        return True # 임시로 항상 허용

    async def _validate_object_type(self, data: ObjectTypeCreate) -> Dict[str, Any]:
        """유효성 검증"""
        if not data.name:
            return {"valid": False, "reason": "Name cannot be empty."}
        return {"valid": True}

    async def _publish_schema_event(self, event_type: str, payload: Dict[str, Any]):
        """스키마 관련 이벤트를 발행합니다."""
        if self.event_publisher:
            try:
                await self.event_publisher.publish(event_type, payload)
                logger.info(f"Published event '{event_type}' with payload: {payload}")
            except Exception as e:
                logger.error(f"Failed to publish event '{event_type}': {e}")
        else:
            logger.info(f"Event publisher not configured. Skipping event '{event_type}'.")

    # SchemaServiceProtocol 구현 메소드들
    async def create_schema(self, name: str, schema_def: Dict[str, Any], 
                          created_by: str) -> Dict[str, Any]:
        """새로운 스키마 생성 (ObjectType 생성을 위한 어댑터)"""
        try:
            # schema_def에서 ObjectTypeCreate 모델 생성
            object_type_data = ObjectTypeCreate(
                name=name,
                display_name=schema_def.get("display_name", name),
                description=schema_def.get("description", "")
            )
            
            # 기존 create_object_type 메소드 사용
            result = await self.create_object_type(
                branch=schema_def.get("branch", "main"),
                data=object_type_data
            )
            
            return {
                "id": result.id,
                "name": result.name,
                "display_name": result.display_name,
                "description": result.description,
                "version": result.version_hash,
                "created_by": result.created_by,
                "created_at": result.created_at.isoformat(),
                "schema_def": schema_def
            }
            
        except Exception as e:
            logger.error(f"Error creating schema: {e}")
            raise

    async def get_schema(self, schema_id: str) -> Dict[str, Any]:
        """스키마 조회 (ID로)"""
        # 이 메소드는 리포지토리를 사용하도록 완전히 재작성되어야 합니다.
        # 현재는 이전 로직을 임시로 유지합니다.
        # all_types = await self.repository.list_all_object_types()
        # ...
        raise NotImplementedError

    async def update_schema(self, schema_id: str, name: Optional[str] = None,
                          schema_def: Optional[Dict[str, Any]] = None,
                          updated_by: Optional[str] = None) -> Dict[str, Any]:
        """
        스키마를 업데이트합니다.
        브랜치 기반 워크플로우를 통해 안전하게 변경사항을 적용합니다.
        """
        if not schema_def:
            raise ValueError("schema_def is required for update")
        
        updated_by = updated_by or get_author()
        
        try:
            # 1. 스키마 변경을 위한 브랜치 생성
            change_branch_name = f"schema-change/{schema_id}-{uuid.uuid4().hex[:8]}"
            await self.branch_service.create_branch(
                branch_name=change_branch_name,
                parent_branch="main",
                created_by=updated_by
            )
            logger.info(f"Created branch '{change_branch_name}' for schema update")
            
            # 2. 새 브랜치에서 스키마 업데이트
            success = await self.repository.update_object_type(
                schema_id=schema_id,
                branch=change_branch_name,
                schema_def=schema_def,
                updated_by=updated_by
            )
            
            if not success:
                raise Exception(f"Failed to update schema in branch '{change_branch_name}'")
            
            # 3. 변경사항을 커밋으로 기록
            commit_message = f"Update schema '{schema_id}'"
            if name:
                commit_message += f" - rename to '{name}'"
            
            commit_id = await self.branch_service.commit_changes(
                branch=change_branch_name,
                message=commit_message,
                author=updated_by
            )
            
            # 4. Pull Request 생성 (자동 병합은 하지 않음)
            pr_result = await self.branch_service.create_pull_request(
                source_branch=change_branch_name,
                target_branch="main",
                title=f"Update schema: {schema_id}",
                description=f"Schema update requested by {updated_by}\n\nChanges:\n{schema_def}",
                created_by=updated_by
            )
            
            logger.info(f"Created PR for schema update: {pr_result.get('pr_id')}")
            
            return {
                "message": "Schema update PR created successfully",
                "schema_id": schema_id,
                "branch": change_branch_name,
                "pr_id": pr_result.get("pr_id"),
                "status": "pending_review"
            }
            
        except Exception as e:
            logger.error(f"Error updating schema '{schema_id}': {e}")
            raise

    async def delete_schema(self, schema_id: str, deleted_by: Optional[str] = None) -> None:
        raise NotImplementedError

    async def list_schemas(self, offset: int = 0, limit: int = 100,
                         filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        raise NotImplementedError

    async def validate_schema(self, schema_def: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError

    async def get_schema_version(self, schema_id: str, version: int) -> Dict[str, Any]:
        raise NotImplementedError

    async def get_schema_versions(self, schema_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError
    
    # 브랜치 워크플로우를 위한 추가 메소드들
    async def get_pending_schema_changes(self, branch: str = "main") -> List[Dict[str, Any]]:
        """
        보류 중인 스키마 변경 PR 목록을 조회합니다.
        """
        try:
            # schema-change/ 또는 schema-create/ 로 시작하는 브랜치들의 PR 조회
            all_prs = await self.branch_service.list_pull_requests(
                target_branch=branch,
                status="open"
            )
            
            schema_prs = []
            for pr in all_prs:
                if pr.get("source_branch", "").startswith(("schema-change/", "schema-create/")):
                    schema_prs.append({
                        "pr_id": pr.get("id"),
                        "type": "change" if "schema-change/" in pr.get("source_branch", "") else "create",
                        "source_branch": pr.get("source_branch"),
                        "title": pr.get("title"),
                        "author": pr.get("created_by"),
                        "created_at": pr.get("created_at"),
                        "status": pr.get("status")
                    })
            
            return schema_prs
            
        except Exception as e:
            logger.error(f"Error getting pending schema changes: {e}")
            return []
    
    async def approve_schema_change(self, pr_id: str, approved_by: str) -> Dict[str, Any]:
        """
        스키마 변경 PR을 승인하고 병합합니다.
        """
        try:
            # PR 병합
            merge_result = await self.branch_service.merge_pull_request(
                pr_id=pr_id,
                merged_by=approved_by,
                merge_method="squash"  # 스키마 변경은 squash merge 사용
            )
            
            if merge_result.get("success"):
                await self._publish_schema_event("schema_change_approved", {
                    "pr_id": pr_id,
                    "approved_by": approved_by
                })
                
            return merge_result
            
        except Exception as e:
            logger.error(f"Error approving schema change PR {pr_id}: {e}")
            raise
    
    async def reject_schema_change(self, pr_id: str, rejected_by: str, reason: str) -> Dict[str, Any]:
        """
        스키마 변경 PR을 거부합니다.
        """
        try:
            # PR 닫기
            close_result = await self.branch_service.close_pull_request(
                pr_id=pr_id,
                closed_by=rejected_by,
                comment=f"Schema change rejected: {reason}"
            )
            
            if close_result.get("success"):
                await self._publish_schema_event("schema_change_rejected", {
                    "pr_id": pr_id,
                    "rejected_by": rejected_by,
                    "reason": reason
                })
                
            return close_result
            
        except Exception as e:
            logger.error(f"Error rejecting schema change PR {pr_id}: {e}")
            raise