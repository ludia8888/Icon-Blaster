"""
Naming Convention History Management
명명 규칙 변경 이력 관리
"""
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from enum import Enum
from pathlib import Path
import difflib
from dataclasses import dataclass, field

from core.validation.naming_convention import (
    NamingConvention, EntityType, NamingPattern
)
from utils.logger import get_logger

logger = get_logger(__name__)


def json_serializer(obj: Any) -> Any:
    """
    커스텀 JSON 직렬화 함수
    
    Enum과 기타 객체들을 명시적으로 처리하여 일관된 직렬화 보장
    
    Args:
        obj: 직렬화할 객체
        
    Returns:
        직렬화 가능한 값
        
    Raises:
        TypeError: 직렬화할 수 없는 타입인 경우
    """
    if isinstance(obj, Enum):
        # Enum은 항상 .value를 사용하여 일관성 보장
        return obj.value
    elif hasattr(obj, 'isoformat'):
        # datetime 객체
        return obj.isoformat()
    elif hasattr(obj, 'model_dump'):
        # Pydantic 모델
        return obj.model_dump()
    elif hasattr(obj, '__dict__'):
        # 일반 객체의 경우 딕셔너리로 변환
        return obj.__dict__
    else:
        # 최후의 수단으로 str() 사용
        return str(obj)


def safe_enum_parse(enum_class: type, value: Any, default: Optional[Any] = None) -> Any:
    """
    안전한 Enum 파싱 함수
    
    문자열 값을 Enum으로 안전하게 변환. 실패 시 기본값 반환 또는 예외 발생
    
    Args:
        enum_class: Enum 클래스 타입
        value: 변환할 값 (문자열 또는 이미 Enum인 경우)
        default: 변환 실패 시 기본값 (None이면 예외 발생)
        
    Returns:
        Enum 인스턴스 또는 기본값
        
    Raises:
        ValueError: 변환 실패하고 default가 None인 경우
    """
    # 이미 올바른 Enum 타입인 경우
    if isinstance(value, enum_class):
        return value
    
    # None이나 빈 값 처리
    if value is None or value == "":
        if default is not None:
            return default
        raise ValueError(f"Cannot convert None/empty value to {enum_class.__name__}")
    
    # 문자열을 Enum으로 변환 시도
    if isinstance(value, str):
        # 1. 직접 value로 찾기 (권장)
        for enum_item in enum_class:
            if enum_item.value == value:
                return enum_item
        
        # 2. name으로 찾기 (호환성)
        try:
            return enum_class[value]
        except KeyError:
            pass
        
        # 3. 대소문자 무시하고 value로 찾기
        value_lower = value.lower()
        for enum_item in enum_class:
            if enum_item.value.lower() == value_lower:
                return enum_item
        
        # 4. 대소문자 무시하고 name으로 찾기
        for enum_item in enum_class:
            if enum_item.name.lower() == value_lower:
                return enum_item
    
    # 변환 실패
    if default is not None:
        logger.warning(f"Failed to convert '{value}' to {enum_class.__name__}, using default: {default}")
        return default
    
    valid_values = [item.value for item in enum_class]
    raise ValueError(f"Cannot convert '{value}' to {enum_class.__name__}. Valid values: {valid_values}")


class ChangeType(str, Enum):
    """변경 유형"""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    RULE_ADD = "rule_add"
    RULE_UPDATE = "rule_update"
    RULE_DELETE = "rule_delete"


@dataclass
class ChangeDiff:
    """변경 사항 차이점"""
    field: str
    old_value: Any
    new_value: Any
    path: Optional[str] = None  # 중첩된 필드의 경로 (예: "rules.ObjectType.pattern")
    
    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        return {
            "field": self.field,
            "old_value": self._serialize_value(self.old_value),
            "new_value": self._serialize_value(self.new_value),
            "path": self.path
        }
    
    def _serialize_value(self, value: Any) -> Any:
        """값을 직렬화 가능한 형태로 변환"""
        if isinstance(value, Enum):
            return value.value
        elif hasattr(value, 'model_dump'):
            return value.model_dump()
        elif isinstance(value, (list, dict, str, int, float, bool, type(None))):
            return value
        else:
            return str(value)


@dataclass
class NamingConventionHistory:
    """명명 규칙 변경 이력"""
    id: str
    convention_id: str
    version: int
    change_type: ChangeType
    change_summary: str
    diffs: List[ChangeDiff] = field(default_factory=list)
    full_snapshot: Optional[Dict] = None  # 변경 후 전체 스냅샷
    changed_by: str = "system"
    changed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    change_reason: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        return {
            "id": self.id,
            "convention_id": self.convention_id,
            "version": self.version,
            "change_type": self.change_type.value,
            "change_summary": self.change_summary,
            "diffs": [diff.to_dict() for diff in self.diffs],
            "full_snapshot": self.full_snapshot,
            "changed_by": self.changed_by,
            "changed_at": self.changed_at.isoformat(),
            "change_reason": self.change_reason
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'NamingConventionHistory':
        """
        딕셔너리에서 생성
        
        안전한 Enum 변환을 통해 역직렬화 수행
        
        Args:
            data: 역직렬화할 딕셔너리 데이터
            
        Returns:
            NamingConventionHistory 인스턴스
            
        Raises:
            ValueError: 필수 필드 누락 또는 잘못된 데이터 형식
        """
        diffs = []
        for diff_data in data.get("diffs", []):
            diffs.append(ChangeDiff(
                field=diff_data["field"],
                old_value=diff_data["old_value"],
                new_value=diff_data["new_value"],
                path=diff_data.get("path")
            ))
        
        # ChangeType 안전 변환
        change_type = safe_enum_parse(ChangeType, data["change_type"])
        
        # datetime 안전 변환
        try:
            changed_at = datetime.fromisoformat(data["changed_at"])
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse datetime '{data.get('changed_at')}', using current time: {e}")
            changed_at = datetime.now(timezone.utc)
        
        return cls(
            id=data["id"],
            convention_id=data["convention_id"],
            version=data["version"],
            change_type=change_type,
            change_summary=data["change_summary"],
            diffs=diffs,
            full_snapshot=data.get("full_snapshot"),
            changed_by=data.get("changed_by", "system"),
            changed_at=changed_at,
            change_reason=data.get("change_reason")
        )


class NamingConventionHistoryService:
    """명명 규칙 이력 관리 서비스"""
    
    def __init__(self, history_path: Optional[str] = None):
        """
        초기화
        
        Args:
            history_path: 이력 저장 경로
        """
        self.history_path = history_path or "/etc/oms/naming_history.json"
        self.history: Dict[str, List[NamingConventionHistory]] = {}
        self._load_history()
    
    def _load_history(self):
        """이력 파일 로드"""
        history_file = Path(self.history_path)
        
        if history_file.exists():
            try:
                with open(history_file, 'r') as f:
                    data = json.load(f)
                    for convention_id, history_list in data.items():
                        self.history[convention_id] = [
                            NamingConventionHistory.from_dict(h) for h in history_list
                        ]
                logger.info(f"Loaded history for {len(self.history)} conventions")
            except Exception as e:
                logger.error(f"Failed to load naming history: {e}")
    
    def _save_history(self):
        """이력을 파일에 저장"""
        try:
            history_file = Path(self.history_path)
            history_file.parent.mkdir(parents=True, exist_ok=True)
            
            data = {}
            for convention_id, history_list in self.history.items():
                data[convention_id] = [h.to_dict() for h in history_list]
            
            with open(history_file, 'w') as f:
                json.dump(data, f, indent=2, default=json_serializer)
                
            logger.info(f"Saved history to {history_file}")
        except Exception as e:
            logger.error(f"Failed to save naming history: {e}")
    
    def record_creation(
        self,
        convention: NamingConvention,
        user_id: str,
        reason: Optional[str] = None
    ) -> NamingConventionHistory:
        """명명 규칙 생성 기록"""
        history_entry = NamingConventionHistory(
            id=f"{convention.id}_v1_{datetime.now(timezone.utc).timestamp()}",
            convention_id=convention.id,
            version=1,
            change_type=ChangeType.CREATE,
            change_summary=f"Created naming convention '{convention.name}'",
            full_snapshot=convention.model_dump(),
            changed_by=user_id,
            change_reason=reason
        )
        
        if convention.id not in self.history:
            self.history[convention.id] = []
        
        self.history[convention.id].append(history_entry)
        self._save_history()
        
        return history_entry
    
    def record_update(
        self,
        old_convention: NamingConvention,
        new_convention: NamingConvention,
        user_id: str,
        reason: Optional[str] = None
    ) -> NamingConventionHistory:
        """명명 규칙 업데이트 기록"""
        # 버전 계산
        version = self._get_next_version(new_convention.id)
        
        # 변경 사항 비교
        diffs = self._compare_conventions(old_convention, new_convention)
        
        # 변경 요약 생성
        change_summary = self._generate_change_summary(diffs)
        
        history_entry = NamingConventionHistory(
            id=f"{new_convention.id}_v{version}_{datetime.now(timezone.utc).timestamp()}",
            convention_id=new_convention.id,
            version=version,
            change_type=ChangeType.UPDATE,
            change_summary=change_summary,
            diffs=diffs,
            full_snapshot=new_convention.model_dump(),
            changed_by=user_id,
            change_reason=reason
        )
        
        if new_convention.id not in self.history:
            self.history[new_convention.id] = []
        
        self.history[new_convention.id].append(history_entry)
        self._save_history()
        
        return history_entry
    
    def record_deletion(
        self,
        convention: NamingConvention,
        user_id: str,
        reason: Optional[str] = None
    ) -> NamingConventionHistory:
        """명명 규칙 삭제 기록"""
        version = self._get_next_version(convention.id)
        
        history_entry = NamingConventionHistory(
            id=f"{convention.id}_v{version}_{datetime.now(timezone.utc).timestamp()}",
            convention_id=convention.id,
            version=version,
            change_type=ChangeType.DELETE,
            change_summary=f"Deleted naming convention '{convention.name}'",
            full_snapshot=convention.model_dump(),
            changed_by=user_id,
            change_reason=reason
        )
        
        if convention.id not in self.history:
            self.history[convention.id] = []
        
        self.history[convention.id].append(history_entry)
        self._save_history()
        
        return history_entry
    
    def get_history(
        self,
        convention_id: str,
        version: Optional[int] = None
    ) -> List[NamingConventionHistory]:
        """특정 명명 규칙의 이력 조회"""
        if convention_id not in self.history:
            return []
        
        history_list = self.history[convention_id]
        
        if version is not None:
            return [h for h in history_list if h.version == version]
        
        return sorted(history_list, key=lambda h: h.version)
    
    def get_convention_at_version(
        self,
        convention_id: str,
        version: int
    ) -> Optional[Dict]:
        """특정 버전의 명명 규칙 스냅샷 조회"""
        history_list = self.get_history(convention_id, version)
        
        if history_list:
            return history_list[0].full_snapshot
        
        return None
    
    def get_diff_between_versions(
        self,
        convention_id: str,
        from_version: int,
        to_version: int
    ) -> List[ChangeDiff]:
        """두 버전 간의 차이점 조회"""
        from_snapshot = self.get_convention_at_version(convention_id, from_version)
        to_snapshot = self.get_convention_at_version(convention_id, to_version)
        
        if not from_snapshot or not to_snapshot:
            return []
        
        # 스냅샷을 NamingConvention으로 변환하여 비교
        # 여기서는 간단히 딕셔너리 비교로 구현
        return self._compare_snapshots(from_snapshot, to_snapshot)
    
    def _get_next_version(self, convention_id: str) -> int:
        """다음 버전 번호 계산"""
        if convention_id not in self.history or not self.history[convention_id]:
            return 1
        
        max_version = max(h.version for h in self.history[convention_id])
        return max_version + 1
    
    def _compare_conventions(
        self,
        old_conv: NamingConvention,
        new_conv: NamingConvention
    ) -> List[ChangeDiff]:
        """두 명명 규칙 비교"""
        diffs = []
        
        # 기본 필드 비교
        for field in ["name", "description", "case_sensitive", "auto_fix_enabled"]:
            old_value = getattr(old_conv, field)
            new_value = getattr(new_conv, field)
            if old_value != new_value:
                diffs.append(ChangeDiff(field, old_value, new_value))
        
        # reserved_words 비교
        old_words = set(old_conv.reserved_words)
        new_words = set(new_conv.reserved_words)
        if old_words != new_words:
            added = new_words - old_words
            removed = old_words - new_words
            if added or removed:
                diffs.append(ChangeDiff(
                    "reserved_words",
                    list(old_words),
                    list(new_words)
                ))
        
        # rules 비교
        old_rules = old_conv.rules
        new_rules = new_conv.rules
        
        # 추가된 규칙
        for entity_type in new_rules:
            if entity_type not in old_rules:
                diffs.append(ChangeDiff(
                    "rules",
                    None,
                    new_rules[entity_type].model_dump(),
                    path=f"rules.{entity_type.value}"
                ))
        
        # 삭제된 규칙
        for entity_type in old_rules:
            if entity_type not in new_rules:
                diffs.append(ChangeDiff(
                    "rules",
                    old_rules[entity_type].model_dump(),
                    None,
                    path=f"rules.{entity_type.value}"
                ))
        
        # 변경된 규칙
        for entity_type in old_rules:
            if entity_type in new_rules:
                old_rule = old_rules[entity_type]
                new_rule = new_rules[entity_type]
                rule_diffs = self._compare_rules(old_rule, new_rule, entity_type.value)
                diffs.extend(rule_diffs)
        
        return diffs
    
    def _compare_rules(self, old_rule, new_rule, entity_type: str) -> List[ChangeDiff]:
        """규칙 비교"""
        diffs = []
        
        # 모든 필드 비교
        for field in ["pattern", "custom_regex", "required_prefix", "required_suffix",
                     "forbidden_prefix", "forbidden_suffix", "forbidden_words",
                     "min_length", "max_length", "allow_numbers", "allow_underscores",
                     "description"]:
            if hasattr(old_rule, field) and hasattr(new_rule, field):
                old_value = getattr(old_rule, field)
                new_value = getattr(new_rule, field)
                if old_value != new_value:
                    diffs.append(ChangeDiff(
                        field,
                        old_value,
                        new_value,
                        path=f"rules.{entity_type}.{field}"
                    ))
        
        return diffs
    
    def _compare_snapshots(self, old_snapshot: Dict, new_snapshot: Dict) -> List[ChangeDiff]:
        """스냅샷 비교 (딕셔너리 레벨)"""
        diffs = []
        
        def compare_dict(old, new, path=""):
            for key in set(old.keys()) | set(new.keys()):
                current_path = f"{path}.{key}" if path else key
                
                if key not in old:
                    diffs.append(ChangeDiff(key, None, new[key], path=current_path))
                elif key not in new:
                    diffs.append(ChangeDiff(key, old[key], None, path=current_path))
                elif old[key] != new[key]:
                    if isinstance(old[key], dict) and isinstance(new[key], dict):
                        compare_dict(old[key], new[key], current_path)
                    else:
                        diffs.append(ChangeDiff(key, old[key], new[key], path=current_path))
        
        compare_dict(old_snapshot, new_snapshot)
        return diffs
    
    def _generate_change_summary(self, diffs: List[ChangeDiff]) -> str:
        """변경 사항 요약 생성"""
        if not diffs:
            return "No changes detected"
        
        summary_parts = []
        
        # 필드별 변경 수 계산
        field_changes = {}
        for diff in diffs:
            base_field = diff.field
            if base_field not in field_changes:
                field_changes[base_field] = 0
            field_changes[base_field] += 1
        
        # 요약 생성
        for field, count in field_changes.items():
            if field == "rules":
                summary_parts.append(f"{count} rule changes")
            elif field == "reserved_words":
                summary_parts.append("reserved words updated")
            else:
                summary_parts.append(f"{field} changed")
        
        return "Updated: " + ", ".join(summary_parts)
    
    def generate_diff_report(
        self,
        convention_id: str,
        from_version: Optional[int] = None,
        to_version: Optional[int] = None
    ) -> str:
        """변경 이력 리포트 생성"""
        history = self.get_history(convention_id)
        
        if not history:
            return f"No history found for convention '{convention_id}'"
        
        # 버전 범위 결정
        if from_version is None:
            from_version = 1
        if to_version is None:
            to_version = history[-1].version
        
        report_lines = [
            f"=== Naming Convention History Report ===",
            f"Convention ID: {convention_id}",
            f"Version Range: v{from_version} → v{to_version}",
            ""
        ]
        
        # 해당 범위의 이력만 필터링
        relevant_history = [
            h for h in history
            if from_version <= h.version <= to_version
        ]
        
        for entry in relevant_history:
            report_lines.extend([
                f"\n--- Version {entry.version} ---",
                f"Date: {entry.changed_at.isoformat()}",
                f"Changed by: {entry.changed_by}",
                f"Type: {entry.change_type.value}",
                f"Summary: {entry.change_summary}"
            ])
            
            if entry.change_reason:
                report_lines.append(f"Reason: {entry.change_reason}")
            
            if entry.diffs:
                report_lines.append("\nChanges:")
                for diff in entry.diffs:
                    path = diff.path or diff.field
                    report_lines.append(f"  • {path}:")
                    report_lines.append(f"    Old: {diff.old_value}")
                    report_lines.append(f"    New: {diff.new_value}")
        
        return "\n".join(report_lines)


# 싱글톤 인스턴스 딕셔너리 (경로별로 관리)
_history_services: Dict[str, NamingConventionHistoryService] = {}

def get_naming_history_service(history_path: Optional[str] = None) -> NamingConventionHistoryService:
    """명명 규칙 이력 서비스 인스턴스 반환"""
    global _history_services
    path_key = history_path or "/etc/oms/naming_history.json"
    
    if path_key not in _history_services:
        _history_services[path_key] = NamingConventionHistoryService(history_path)
    
    return _history_services[path_key]