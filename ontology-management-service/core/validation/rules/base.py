"""
Breaking Change Rule 베이스 클래스
섹션 8.3.2의 Breaking Change Rules 구현
"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from core.validation.models import (
    BreakingChange,
    Severity,
    ValidationContext,
    ValidationWarning,
)

logger = logging.getLogger(__name__)


class RuleResult(BaseModel):
    """규칙 실행 결과"""
    breaking_changes: List[BreakingChange] = Field(default_factory=list)
    warnings: List[ValidationWarning] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BaseRule(ABC):
    """Breaking change 검증 규칙 베이스 클래스"""
    
    def __init__(self, rule_id: str, name: str, description: str):
        self._rule_id = rule_id
        self._name = name
        self._description = description
    
    @property
    def rule_id(self) -> str:
        return self._rule_id
    
    @property 
    def name(self) -> str:
        return self._name
    
    @property
    def description(self) -> str:
        return self._description
    
    @abstractmethod
    async def execute(self, context: ValidationContext):
        """규칙 실행"""
        pass


class BreakingChangeRule(ABC):
    """Breaking change 검증 규칙 베이스"""

    @property
    @abstractmethod
    def rule_id(self) -> str:
        """규칙 ID"""
        pass

    @property
    @abstractmethod
    def severity(self) -> Severity:
        """규칙 심각도"""
        pass

    @property
    def description(self) -> str:
        """규칙 설명"""
        return self.__doc__ or "No description available"

    @property
    def enabled(self) -> bool:
        """규칙 활성화 여부"""
        return True

    @abstractmethod
    async def check(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> Optional[BreakingChange]:
        """
        Breaking change 검사

        Args:
            old_schema: 이전 스키마
            new_schema: 새 스키마
            context: 검증 컨텍스트

        Returns:
            BreakingChange 또는 None
        """
        pass

    async def evaluate(self, context) -> RuleResult:
        """컨텍스트 기반 평가 - 새로운 인터페이스"""

        breaking_changes = []
        warnings = []

        # Source와 Target 스키마에서 ObjectType들 비교
        source_objects = context.source_schema.get("object_types", {})
        target_objects = context.target_schema.get("object_types", {})

        # 공통 ObjectType들에 대해 규칙 적용
        for obj_name in source_objects.keys() & target_objects.keys():
            source_obj = source_objects[obj_name]
            target_obj = target_objects[obj_name]

            try:
                change = await self.check(source_obj, target_obj, context)
                if change:
                    breaking_changes.append(change)
            except Exception as e:
                logger.error(f"Rule {self.rule_id} failed for {obj_name}: {e}")

        return RuleResult(
            breaking_changes=breaking_changes,
            warnings=warnings
        )

    async def batch_check(
        self,
        schema_pairs: List[tuple[Dict[str, Any], Dict[str, Any]]],
        context: ValidationContext
    ) -> List[BreakingChange]:
        """
        배치 검사 (성능 최적화)

        기본 구현은 개별 check를 순차 실행
        필요시 하위 클래스에서 오버라이드
        """
        results = []
        for old_schema, new_schema in schema_pairs:
            try:
                change = await self.check(old_schema, new_schema, context)
                if change:
                    results.append(change)
            except Exception as e:
                logger.error(
                    f"Error in rule {self.rule_id} for {old_schema.get('@id', 'unknown')}: {e}"
                )
        return results

    def _get_resource_type(self, schema: Dict[str, Any]) -> str:
        """스키마에서 리소스 타입 추출"""
        return schema.get("@type", "Unknown")

    def _get_resource_id(self, schema: Dict[str, Any]) -> str:
        """스키마에서 리소스 ID 추출"""
        return schema.get("id", schema.get("@id", "unknown"))

    def _get_resource_name(self, schema: Dict[str, Any]) -> str:
        """스키마에서 리소스 이름 추출"""
        return schema.get("name", schema.get("displayName", "unknown"))


class CompositeRule(BreakingChangeRule):
    """여러 규칙을 조합한 복합 규칙"""

    def __init__(self, rules: List[BreakingChangeRule]):
        self.rules = rules

    @property
    def rule_id(self) -> str:
        return "composite_" + "_".join(r.rule_id for r in self.rules)

    @property
    def severity(self) -> Severity:
        # 가장 높은 심각도 반환
        severities = [r.severity for r in self.rules]
        if Severity.CRITICAL in severities:
            return Severity.CRITICAL
        elif Severity.HIGH in severities:
            return Severity.HIGH
        elif Severity.MEDIUM in severities:
            return Severity.MEDIUM
        else:
            return Severity.LOW

    async def check(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> Optional[BreakingChange]:
        """모든 하위 규칙 실행 후 가장 심각한 것 반환"""
        breaking_changes = []

        for rule in self.rules:
            if rule.enabled:
                try:
                    change = await rule.check(old_schema, new_schema, context)
                    if change:
                        breaking_changes.append(change)
                except Exception as e:
                    logger.error(f"Error in composite rule {rule.rule_id}: {e}")

        if not breaking_changes:
            return None

        # 가장 심각한 변경사항 반환
        return max(breaking_changes, key=lambda c: self._severity_order(c.severity))

    def _severity_order(self, severity: Severity) -> int:
        """심각도를 정수로 변환"""
        order = {
            Severity.LOW: 1,
            Severity.MEDIUM: 2,
            Severity.HIGH: 3,
            Severity.CRITICAL: 4
        }
        return order.get(severity, 0)
