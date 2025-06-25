"""
Event Processor
OMS 이벤트를 감사 로그 및 히스토리로 변환/저장
"""
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from models.audit import AuditLogEntry, AuditEventType, SeverityLevel
from models.history import HistoryEntry, ChangeDetail, ResourceType, ChangeOperation
from utils.logger import get_logger, log_operation_start, log_operation_end


logger = get_logger(__name__)


class EventProcessor:
    """
    이벤트 처리기
    OMS CloudEvents를 Audit Service 데이터로 변환
    """
    
    def __init__(self):
        # TODO: 실제 구현에서는 repository 주입
        pass
    
    async def create_history_entry(self, event: Dict[str, Any]) -> HistoryEntry:
        """CloudEvent를 HistoryEntry로 변환 및 저장"""
        log_operation_start(logger, "create_history_entry", event_id=event.get("id"))
        
        try:
            data = event.get("data", {})
            
            # ChangeDetail 목록 생성
            changes = []
            for change_data in data.get("changes", []):
                change = ChangeDetail(
                    field=change_data.get("field"),
                    operation=ChangeOperation(change_data.get("operation", "update")),
                    old_value=change_data.get("old_value"),
                    new_value=change_data.get("new_value"),
                    path=change_data.get("path"),
                    breaking_change=change_data.get("breaking_change", False)
                )
                changes.append(change)
            
            # HistoryEntry 생성
            history_entry = HistoryEntry(
                commit_hash=data.get("commit_hash", f"commit_{uuid.uuid4().hex[:8]}"),
                branch=data.get("branch", "main"),
                timestamp=datetime.fromisoformat(event.get("time").replace("Z", "+00:00")),
                author=data.get("author", "unknown"),
                author_email=data.get("author_email"),
                message=data.get("message", f"{data.get('operation')} {data.get('resource_id')}"),
                operation=ChangeOperation(data.get("operation", "update")),
                resource_type=ResourceType(data.get("resource_type", "unknown")),
                resource_id=data.get("resource_id"),
                resource_name=data.get("resource_name"),
                changes=changes,
                total_changes=len(changes),
                breaking_changes=sum(1 for c in changes if c.breaking_change),
                metadata=data.get("metadata", {})
            )
            
            # 데이터베이스 저장
            await self._save_history_entry(history_entry)
            
            log_operation_end(logger, "create_history_entry", success=True)
            logger.info(f"History entry created: {history_entry.commit_hash}")
            
            return history_entry
            
        except Exception as e:
            log_operation_end(logger, "create_history_entry", success=False, error=str(e))
            logger.error(f"Failed to create history entry: {str(e)}")
            raise
    
    async def create_revert_history_entry(self, event: Dict[str, Any]) -> HistoryEntry:
        """스키마 복원 이벤트를 HistoryEntry로 변환"""
        log_operation_start(logger, "create_revert_history_entry", event_id=event.get("id"))
        
        try:
            data = event.get("data", {})
            
            # 복원 변경사항 생성
            reverted_changes = []
            for change_data in data.get("reverted_changes", []):
                change = ChangeDetail(
                    field=change_data.get("field"),
                    operation=ChangeOperation.REVERT,
                    old_value=change_data.get("new_value"),  # 복원이므로 순서 반대
                    new_value=change_data.get("old_value"),
                    path=change_data.get("path"),
                    breaking_change=change_data.get("breaking_change", False)
                )
                reverted_changes.append(change)
            
            # 복원 히스토리 엔트리
            history_entry = HistoryEntry(
                commit_hash=data.get("new_commit_hash", f"revert_{uuid.uuid4().hex[:8]}"),
                branch=data.get("branch", "main"),
                timestamp=datetime.fromisoformat(event.get("time").replace("Z", "+00:00")),
                author=data.get("author", "unknown"),
                message=f"Revert to {data.get('reverted_to', 'previous state')}: {data.get('reason', '')}",
                operation=ChangeOperation.REVERT,
                resource_type=ResourceType.SCHEMA,
                resource_id=f"schema_{data.get('branch', 'main')}",
                resource_name=f"Schema on {data.get('branch', 'main')}",
                changes=reverted_changes,
                total_changes=len(reverted_changes),
                breaking_changes=0,  # 복원은 일반적으로 breaking change가 아님
                metadata={
                    "revert_type": data.get("revert_type", "soft"),
                    "reverted_from": data.get("reverted_from"),
                    "reverted_to": data.get("reverted_to"),
                    "reason": data.get("reason")
                }
            )
            
            # 데이터베이스 저장
            await self._save_history_entry(history_entry)
            
            log_operation_end(logger, "create_revert_history_entry", success=True)
            logger.info(f"Revert history entry created: {history_entry.commit_hash}")
            
            return history_entry
            
        except Exception as e:
            log_operation_end(logger, "create_revert_history_entry", success=False, error=str(e))
            logger.error(f"Failed to create revert history entry: {str(e)}")
            raise
    
    async def create_audit_log(self, event: Dict[str, Any]) -> AuditLogEntry:
        """CloudEvent를 AuditLogEntry로 변환 및 저장"""
        log_operation_start(logger, "create_audit_log", event_id=event.get("id"))
        
        try:
            event_type_mapping = {
                "com.oms.schema.changed": AuditEventType.SCHEMA_CHANGE,
                "com.oms.schema.reverted": AuditEventType.SCHEMA_REVERT,
                "com.oms.audit.event": AuditEventType.SCHEMA_VALIDATION
            }
            
            data = event.get("data", {})
            
            # 감사 로그 엔트리 생성
            audit_entry = AuditLogEntry(
                log_id=f"audit_{uuid.uuid4().hex}",
                timestamp=datetime.fromisoformat(event.get("time").replace("Z", "+00:00")),
                service=data.get("service", "oms"),
                event_type=event_type_mapping.get(event.get("type"), AuditEventType.SCHEMA_CHANGE),
                severity=self._determine_severity(data),
                user_id=data.get("author", "system"),
                user_email=data.get("author_email"),
                action=self._get_action_description(event.get("type"), data),
                resource_type=data.get("resource_type", "unknown"),
                resource_id=data.get("resource_id", "unknown"),
                resource_name=data.get("resource_name"),
                result=data.get("result", "success"),
                ip_address=data.get("ip_address"),
                user_agent=data.get("user_agent"),
                session_id=data.get("session_id"),
                request_id=event.get("id"),
                details=self._extract_details(data),
                before_state=data.get("before_state"),
                after_state=data.get("after_state"),
                correlation_id=event.get("id"),
                metadata=data.get("metadata", {})
            )
            
            # 규제 준수 태그 결정
            compliance_tags = self._determine_compliance_tags(audit_entry)
            audit_entry.compliance_tags = compliance_tags
            
            # 데이터 분류 결정
            data_classification = self._determine_data_classification(audit_entry)
            audit_entry.data_classification = data_classification
            
            # 데이터베이스 저장
            await self._save_audit_log(audit_entry)
            
            log_operation_end(logger, "create_audit_log", success=True)
            logger.info(f"Audit log created: {audit_entry.log_id}")
            
            return audit_entry
            
        except Exception as e:
            log_operation_end(logger, "create_audit_log", success=False, error=str(e))
            logger.error(f"Failed to create audit log: {str(e)}")
            raise
    
    async def send_to_siem(self, event: Dict[str, Any]):
        """SIEM으로 이벤트 전송"""
        log_operation_start(logger, "send_to_siem", event_id=event.get("id"))
        
        try:
            # TODO: 실제 SIEM 서비스 구현
            # 현재는 로깅만
            
            data = event.get("data", {})
            
            siem_event = {
                "timestamp": event.get("time"),
                "source_system": "audit-service",
                "event_type": event.get("type"),
                "user_id": data.get("author"),
                "action": data.get("operation"),
                "resource_type": data.get("resource_type"),
                "resource_id": data.get("resource_id"),
                "result": data.get("result", "success"),
                "severity": self._map_to_siem_severity(data),
                "raw_event": event
            }
            
            # SIEM 전송 (실제 구현에서는 SIEM 클라이언트 사용)
            logger.info(f"Sending event to SIEM: {siem_event}")
            
            log_operation_end(logger, "send_to_siem", success=True)
            
        except Exception as e:
            log_operation_end(logger, "send_to_siem", success=False, error=str(e))
            logger.error(f"Failed to send event to SIEM: {str(e)}")
            # SIEM 전송 실패는 치명적이지 않으므로 예외를 재발생시키지 않음
    
    # Private methods
    
    def _determine_severity(self, data: Dict[str, Any]) -> SeverityLevel:
        """이벤트 데이터로부터 심각도 결정"""
        
        # Breaking change가 있으면 높은 심각도
        if any(change.get("breaking_change", False) for change in data.get("changes", [])):
            return SeverityLevel.WARNING
        
        # 삭제 작업은 주의 필요
        if data.get("operation") == "delete":
            return SeverityLevel.WARNING
        
        # 실패한 작업은 에러
        if data.get("result") == "failure":
            return SeverityLevel.ERROR
        
        # 기본값은 정보
        return SeverityLevel.INFO
    
    def _get_action_description(self, event_type: str, data: Dict[str, Any]) -> str:
        """액션 설명 생성"""
        operation = data.get("operation", "unknown")
        resource_type = data.get("resource_type", "resource")
        
        action_map = {
            "com.oms.schema.changed": f"{operation}_{resource_type}",
            "com.oms.schema.reverted": "revert_schema",
            "com.oms.audit.event": data.get("event_type", "audit_event")
        }
        
        return action_map.get(event_type, "unknown_action")
    
    def _extract_details(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """상세 정보 추출"""
        details = {}
        
        # 변경사항이 있으면 포함
        if "changes" in data:
            details["changes_count"] = len(data["changes"])
            details["breaking_changes"] = sum(
                1 for change in data["changes"] 
                if change.get("breaking_change", False)
            )
        
        # 브랜치 정보
        if "branch" in data:
            details["branch"] = data["branch"]
        
        # 커밋 정보
        if "commit_hash" in data:
            details["commit_hash"] = data["commit_hash"]
        
        return details
    
    def _determine_compliance_tags(self, audit_entry: AuditLogEntry) -> List[str]:
        """규제 준수 태그 결정"""
        tags = []
        
        # 스키마 변경은 SOX 대상
        if audit_entry.event_type in [AuditEventType.SCHEMA_CHANGE, AuditEventType.SCHEMA_REVERT]:
            tags.append("SOX")
        
        # 사용자 데이터 관련은 GDPR 대상
        if "user" in audit_entry.resource_type.lower():
            tags.append("GDPR")
        
        # 결제 관련은 PCI-DSS 대상
        if any(keyword in audit_entry.resource_id.lower() 
               for keyword in ["payment", "card", "transaction"]):
            tags.append("PCI-DSS")
        
        return tags
    
    def _determine_data_classification(self, audit_entry: AuditLogEntry) -> str:
        """데이터 분류 결정"""
        
        # 사용자 정보는 기밀
        if "user" in audit_entry.resource_type.lower():
            return "confidential"
        
        # 결제 정보는 제한
        if any(keyword in audit_entry.resource_id.lower() 
               for keyword in ["payment", "card", "financial"]):
            return "restricted"
        
        # 시스템 정보는 내부
        if audit_entry.resource_type in ["schema", "system"]:
            return "internal"
        
        # 기본값은 내부
        return "internal"
    
    def _map_to_siem_severity(self, data: Dict[str, Any]) -> int:
        """SIEM 심각도 매핑 (0-10)"""
        
        # 실패한 작업은 높은 심각도
        if data.get("result") == "failure":
            return 7
        
        # Breaking change는 중간 심각도
        if any(change.get("breaking_change", False) for change in data.get("changes", [])):
            return 5
        
        # 삭제 작업은 중간 심각도
        if data.get("operation") == "delete":
            return 4
        
        # 일반 작업은 낮은 심각도
        return 2
    
    async def _save_history_entry(self, history_entry: HistoryEntry):
        """히스토리 엔트리 저장"""
        # TODO: 실제 데이터베이스 저장 구현
        logger.info(f"Saving history entry: {history_entry.commit_hash}")
    
    async def _save_audit_log(self, audit_entry: AuditLogEntry):
        """감사 로그 저장"""
        # TODO: 실제 데이터베이스 저장 구현
        logger.info(f"Saving audit log: {audit_entry.log_id}")