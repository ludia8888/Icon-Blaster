"""
OMS History Event Publisher
OMS 핵심 책임: 메타데이터 변경 이벤트 발행만 담당
감사 로그 조회/서빙은 별도 Audit Service MSA로 분리

OMS 책임:
- 스키마 변경 이벤트 발행 (CloudEvents)
- 버전 복원 (스키마 메타데이터만)
- 감사 로그 이벤트 생성

분리된 Audit Service MSA 책임:
- 감사 로그 수집/저장/조회
- SIEM 통합
- 규제 준수 리포트
- 감사 로그 보존 정책
"""
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from database.clients.terminus_db import TerminusDBClient
from shared.events import EventPublisher
from utils.logger import get_logger, log_operation_start, log_operation_end
from .models import (
    AuditEvent, ChangeDetail, ChangeOperation,
    ResourceType, RevertRequest, RevertResult
)

logger = get_logger(__name__)


class HistoryEventPublisher:
    """
    OMS History Event Publisher
    메타데이터 변경 이벤트 발행 전담 서비스
    """
    
    def __init__(
        self,
        terminus_client: TerminusDBClient,
        event_publisher: EventPublisher
    ):
        self.terminus_client = terminus_client
        self.event_publisher = event_publisher
    
    async def publish_schema_change_event(
        self,
        operation: ChangeOperation,
        resource_type: ResourceType,
        resource_id: str,
        resource_name: Optional[str],
        changes: List[ChangeDetail],
        branch: str,
        commit_hash: str,
        user_context: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        스키마 변경 이벤트 발행 (OMS 핵심 책임)
        
        Args:
            operation: 변경 타입 (CREATE, UPDATE, DELETE 등)
            resource_type: 리소스 타입 (ObjectType, Property 등)
            resource_id: 리소스 ID
            resource_name: 리소스 이름
            changes: 상세 변경 내역
            branch: 대상 브랜치
            commit_hash: 커밋 해시
            user_context: 사용자 컨텍스트
            metadata: 추가 메타데이터
            
        Returns:
            event_id: 발행된 이벤트 ID
        """
        log_operation_start(logger, "schema_change_event_publish", 
                          resource_type=resource_type.value, resource_id=resource_id)
        
        try:
            # 감사 이벤트 생성
            audit_event = AuditEvent(
                event_id=f"audit_{uuid4().hex[:12]}",
                timestamp=datetime.now(timezone.utc),
                service="oms",
                event_type="schema.changed",
                operation=operation,
                resource_type=resource_type,
                resource_id=resource_id,
                resource_name=resource_name,
                branch=branch,
                commit_hash=commit_hash,
                author=user_context.get('user_id'),
                author_email=user_context.get('email'),
                ip_address=user_context.get('ip_address'),
                user_agent=user_context.get('user_agent'),
                session_id=user_context.get('session_id'),
                changes=changes,
                metadata=metadata or {}
            )
            
            # CloudEvents 형식으로 이벤트 발행
            event_id = await self.event_publisher.publish_schema_changed(
                event_id=audit_event.event_id,
                source="oms.history",
                operation=operation.value,
                resource_type=resource_type.value,
                resource_id=resource_id,
                resource_name=resource_name,
                branch=branch,
                commit_hash=commit_hash,
                author=audit_event.author,
                changes=audit_event.changes,
                metadata=audit_event.metadata
            )
            
            # 구조화 로깅
            logger.info("Schema change event published", extra={
                "event_id": event_id,
                "operation": operation.value,
                "resource_type": resource_type.value,
                "resource_id": resource_id,
                "branch": branch,
                "commit_hash": commit_hash[:8],
                "author": audit_event.author,
                "changes_count": len(changes)
            })
            
            log_operation_end(logger, "schema_change_event_publish", success=True,
                            event_id=event_id)
            
            return event_id
            
        except Exception as e:
            log_operation_end(logger, "schema_change_event_publish", success=False,
                            error=str(e))
            logger.error(f"Failed to publish schema change event: {str(e)}")
            raise
    
    async def revert_schema_to_commit(
        self,
        branch: str,
        request: RevertRequest,
        user_context: Dict[str, Any]
    ) -> RevertResult:
        """
        스키마를 특정 커밋으로 복원 (OMS 핵심 책임)
        
        OMS는 스키마 메타데이터 복원만 담당
        데이터 복원은 별도 서비스 영역
        """
        log_operation_start(logger, "schema_revert", 
                          branch=branch, target_commit=request.target_commit)
        
        try:
            # 권한 체크 (schema:write 필요)
            if not self._has_write_permission(user_context):
                raise PermissionError("Insufficient permissions to revert schema")
            
            # 보호된 브랜치 체크
            if self._is_protected_branch(branch) and request.strategy == "hard":
                raise ValueError("Hard revert not allowed on protected branches")
            
            # 대상 커밋 검증
            target_commit = await self.terminus_client.get_commit(branch, request.target_commit)
            if not target_commit:
                raise ValueError(f"Target commit {request.target_commit} not found")
            
            # Dry run 모드
            if request.dry_run:
                return await self._simulate_revert(branch, request, target_commit)
            
            # 실제 복원 수행 (스키마 메타데이터만)
            result = await self._perform_schema_revert(
                branch, request, target_commit, user_context
            )
            
            # 복원 이벤트 발행
            await self.publish_schema_change_event(
                operation=ChangeOperation.REVERT,
                resource_type=ResourceType.SCHEMA,
                resource_id=f"schema_{branch}",
                resource_name=f"Schema on {branch}",
                changes=result.reverted_changes or [],
                branch=branch,
                commit_hash=result.new_commit_hash,
                user_context=user_context,
                metadata={
                    "revert_type": request.strategy,
                    "reverted_to": request.target_commit,
                    "reason": request.message
                }
            )
            
            log_operation_end(logger, "schema_revert", success=True,
                            new_commit=result.new_commit_hash)
            
            return result
            
        except Exception as e:
            log_operation_end(logger, "schema_revert", success=False, error=str(e))
            logger.error(f"Failed to revert schema: {str(e)}")
            raise
    
    async def publish_audit_event(
        self,
        event_type: str,
        operation: str,
        resource_type: str,
        resource_id: str,
        user_context: Dict[str, Any],
        result: str = "success",
        details: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        감사 이벤트 발행 (OMS 핵심 책임)
        
        실제 감사 로그 저장/조회/관리는 Audit Service MSA로 위임
        OMS는 이벤트 발행만 담당
        """
        try:
            # 감사 이벤트 생성
            audit_event = AuditEvent(
                event_id=f"audit_{uuid4().hex[:12]}",
                timestamp=datetime.now(timezone.utc),
                service="oms",
                event_type=event_type,
                operation=ChangeOperation(operation) if operation in ChangeOperation.__members__.values() else ChangeOperation.UPDATE,
                resource_type=ResourceType(resource_type) if resource_type in ResourceType.__members__.values() else ResourceType.UNKNOWN,
                resource_id=resource_id,
                author=user_context.get('user_id'),
                author_email=user_context.get('email'),
                ip_address=user_context.get('ip_address'),
                user_agent=user_context.get('user_agent'),
                session_id=user_context.get('session_id'),
                result=result,
                metadata=details or {}
            )
            
            # CloudEvents 형식으로 감사 이벤트 발행
            event_id = await self.event_publisher.publish_audit_event(
                event_id=audit_event.event_id,
                source="oms.audit",
                event_type=event_type,
                operation=operation,
                resource_type=resource_type,
                resource_id=resource_id,
                author=audit_event.author,
                result=result,
                timestamp=audit_event.timestamp,
                metadata=audit_event.metadata
            )
            
            # 구조화 로깅 (SIEM 수집용)
            logger.info("Audit event published", extra={
                "event_id": event_id,
                "event_type": event_type,
                "operation": operation,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "author": audit_event.author,
                "result": result,
                "ip_address": audit_event.ip_address,
                "user_agent": audit_event.user_agent,
                "session_id": audit_event.session_id
            })
            
            return event_id
            
        except Exception as e:
            logger.error(f"Failed to publish audit event: {str(e)}")
            raise
    
    # Private methods (OMS 핵심 기능만 유지)
    
    async def _perform_schema_revert(
        self,
        branch: str,
        request: RevertRequest,
        target_commit: Dict[str, Any],
        user_context: Dict[str, Any]
    ) -> RevertResult:
        """
        스키마 복원 수행 (메타데이터만)
        
        데이터 복원은 OSv2, 파이프라인 복원은 Funnel로 위임
        """
        try:
            # 현재 스키마 상태 조회
            current_schema = await self._get_schema_snapshot(branch, "HEAD")
            
            # 대상 커밋의 스키마 조회
            target_schema = await self._get_schema_snapshot(branch, request.target_commit)
            
            # 스키마 차이점 분석
            schema_changes = self._compare_schema_snapshots(current_schema, target_schema)
            
            # 스키마 변경사항 적용 (새 커밋으로)
            new_commit_hash = await self._apply_schema_changes(
                branch,
                schema_changes,
                f"Revert schema to {request.target_commit[:8]}: {request.message}",
                user_context['user_id']
            )
            
            return RevertResult(
                success=True,
                new_commit_hash=new_commit_hash,
                reverted_from="HEAD",
                reverted_to=request.target_commit,
                message=request.message,
                reverted_changes=schema_changes,
                dry_run=False
            )
            
        except Exception as e:
            logger.error(f"Schema revert failed: {str(e)}")
            return RevertResult(
                success=False,
                reverted_from="HEAD",
                reverted_to=request.target_commit,
                message=str(e),
                dry_run=False
            )
    
    def _has_write_permission(self, user_context: Dict[str, Any]) -> bool:
        """스키마 쓰기 권한 확인"""
        permissions = user_context.get('permissions', [])
        return 'schema:write' in permissions or 'admin' in user_context.get('roles', [])
    
    def _is_protected_branch(self, branch: str) -> bool:
        """보호된 브랜치 여부"""
        protected = ['main', 'master', 'production', 'release']
        return branch in protected or branch.startswith('release/')
    
    async def _get_schema_snapshot(
        self,
        branch: str,
        commit_hash: str
    ) -> Dict[str, Any]:
        """특정 커밋의 스키마 스냅샷 조회 (메타데이터만)"""
        try:
            return await self.terminus_client.get_schema_snapshot(branch, commit_hash)
        except Exception as e:
            logger.error(f"Failed to get schema snapshot: {e}")
            return {}
    
    def _compare_schema_snapshots(
        self,
        current: Dict[str, Any],
        target: Dict[str, Any]
    ) -> List[ChangeDetail]:
        """두 스키마 스냅샷 간 차이 분석 (메타데이터만)"""
        changes = []
        
        # ObjectType 변경사항 분석
        current_objects = current.get('object_types', {})
        target_objects = target.get('object_types', {})
        
        for obj_id, obj_data in target_objects.items():
            if obj_id not in current_objects:
                changes.append(ChangeDetail(
                    field="object_type",
                    operation=ChangeOperation.CREATE,
                    old_value=None,
                    new_value=obj_data,
                    path=f"object_types.{obj_id}"
                ))
            elif current_objects[obj_id] != obj_data:
                changes.append(ChangeDetail(
                    field="object_type",
                    operation=ChangeOperation.UPDATE,
                    old_value=current_objects[obj_id],
                    new_value=obj_data,
                    path=f"object_types.{obj_id}"
                ))
        
        # 삭제된 ObjectType 처리
        for obj_id in current_objects:
            if obj_id not in target_objects:
                changes.append(ChangeDetail(
                    field="object_type",
                    operation=ChangeOperation.DELETE,
                    old_value=current_objects[obj_id],
                    new_value=None,
                    path=f"object_types.{obj_id}"
                ))
        
        return changes
    
    async def _apply_schema_changes(
        self,
        branch: str,
        changes: List[ChangeDetail],
        message: str,
        author: str
    ) -> str:
        """스키마 변경사항을 새 커밋으로 적용"""
        try:
            # TerminusDB에 스키마 변경사항 적용
            commit_result = await self.terminus_client.apply_schema_changes(
                branch=branch,
                changes=changes,
                message=message,
                author=author
            )
            return commit_result['commit_hash']
        except Exception as e:
            logger.error(f"Failed to apply schema changes: {e}")
            raise
    
    async def _simulate_revert(
        self,
        branch: str,
        request: RevertRequest,
        target_commit: Dict[str, Any]
    ) -> RevertResult:
        """스키마 복원 시뮬레이션 (Dry Run)"""
        try:
            # 스키마 차이점만 분석 (실제 적용하지 않음)
            current_schema = await self._get_schema_snapshot(branch, "HEAD")
            target_schema = await self._get_schema_snapshot(branch, request.target_commit)
            schema_changes = self._compare_schema_snapshots(current_schema, target_schema)
            
            return RevertResult(
                success=True,
                reverted_from="HEAD",
                reverted_to=request.target_commit,
                message=f"Simulation: Would revert {len(schema_changes)} schema changes",
                reverted_changes=schema_changes,
                dry_run=True
            )
        except Exception as e:
            return RevertResult(
                success=False,
                reverted_from="HEAD",
                reverted_to=request.target_commit,
                message=f"Simulation failed: {e}",
                dry_run=True
            )