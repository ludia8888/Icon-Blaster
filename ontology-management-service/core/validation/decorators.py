"""
Validation Rule 데코레이터
규칙 자동 등록 및 메타데이터 관리
"""
from typing import Type, Dict, Any, List
from functools import wraps
import logging

from core.validation.interfaces import BreakingChangeRule

logger = logging.getLogger(__name__)

# 전역 규칙 레지스트리
RULE_REGISTRY: List[Type[BreakingChangeRule]] = []
RULE_METADATA: Dict[str, Dict[str, Any]] = {}


def validation_rule(
    rule_id: str = None,
    category: str = "general",
    severity_default: str = "medium",
    enabled: bool = True,
    description: str = None
):
    """
    검증 규칙 데코레이터
    
    Args:
        rule_id: 규칙 ID (기본값: 클래스명에서 자동 생성)
        category: 규칙 카테고리 (schema, data, relationship 등)
        severity_default: 기본 심각도
        enabled: 규칙 활성화 여부
        description: 규칙 설명
    
    Usage:
        @validation_rule(category="schema", severity_default="high")
        class RequiredFieldRemovalRule(BreakingChangeRule):
            ...
    """
    def decorator(cls: Type[BreakingChangeRule]) -> Type[BreakingChangeRule]:
        # 규칙 ID 자동 생성 (클래스명 기반)
        nonlocal rule_id
        if rule_id is None:
            rule_id = cls.__name__.replace("Rule", "").lower()
            rule_id = "".join(["_" + c.lower() if c.isupper() else c for c in rule_id]).lstrip("_")
        
        # 클래스에 메타데이터 추가
        cls._rule_metadata = {
            "rule_id": rule_id,
            "category": category,
            "severity_default": severity_default,
            "enabled": enabled,
            "description": description or cls.__doc__ or f"{cls.__name__} validation rule"
        }
        
        # rule_id 속성 설정
        if not hasattr(cls, "rule_id"):
            cls.rule_id = rule_id
        
        # 레지스트리에 등록
        if enabled:
            RULE_REGISTRY.append(cls)
            RULE_METADATA[rule_id] = cls._rule_metadata
            logger.debug(f"Registered validation rule: {rule_id} ({cls.__name__})")
        
        return cls
    
    return decorator


def get_registered_rules() -> List[Type[BreakingChangeRule]]:
    """등록된 모든 규칙 반환"""
    return RULE_REGISTRY.copy()


def get_rule_metadata(rule_id: str) -> Dict[str, Any]:
    """특정 규칙의 메타데이터 반환"""
    return RULE_METADATA.get(rule_id, {})


def clear_rule_registry():
    """규칙 레지스트리 초기화 (테스트용)"""
    RULE_REGISTRY.clear()
    RULE_METADATA.clear()


def disable_rule(rule_id: str):
    """특정 규칙 비활성화"""
    for i, rule_cls in enumerate(RULE_REGISTRY):
        if getattr(rule_cls, "rule_id", None) == rule_id:
            RULE_REGISTRY.pop(i)
            RULE_METADATA[rule_id]["enabled"] = False
            logger.info(f"Disabled rule: {rule_id}")
            return True
    return False


def enable_rule(rule_id: str, rule_cls: Type[BreakingChangeRule] = None):
    """특정 규칙 활성화"""
    if rule_id in RULE_METADATA and RULE_METADATA[rule_id]["enabled"]:
        logger.warning(f"Rule {rule_id} is already enabled")
        return False
    
    if rule_cls:
        RULE_REGISTRY.append(rule_cls)
        RULE_METADATA[rule_id]["enabled"] = True
        logger.info(f"Enabled rule: {rule_id}")
        return True
    
    return False


# 카테고리별 규칙 필터링
def get_rules_by_category(category: str) -> List[Type[BreakingChangeRule]]:
    """특정 카테고리의 규칙만 반환"""
    return [
        rule for rule in RULE_REGISTRY
        if getattr(rule, "_rule_metadata", {}).get("category") == category
    ]


# 심각도별 규칙 필터링
def get_rules_by_severity(severity: str) -> List[Type[BreakingChangeRule]]:
    """특정 심각도의 규칙만 반환"""
    return [
        rule for rule in RULE_REGISTRY
        if getattr(rule, "_rule_metadata", {}).get("severity_default") == severity
    ]