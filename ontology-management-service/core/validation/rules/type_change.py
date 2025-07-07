"""
Type Compatibility Rule
REQ-OMS-F3: Breaking Change Detection - 타입 호환성 검증
"""
import logging
from typing import Any, Dict, List, Optional

from core.validation.models import (
    BreakingChange,
    Severity,
    ValidationContext,
)
from core.validation.rules.base import BreakingChangeRule, RuleResult
from models.domain import ObjectType

logger = logging.getLogger(__name__)


class TypeCompatibilityRule(BreakingChangeRule):
    """
    REQ-OMS-F3: 타입 호환성 규칙
    데이터 타입 변경시 호환성을 검증
    """

    @property
    def rule_id(self) -> str:
        return "TYPE_COMPATIBILITY"

    @property
    def name(self) -> str:
        return "Type Compatibility Rule"

    @property
    def description(self) -> str:
        return "데이터 타입 변경의 호환성을 검증합니다"

    @property
    def severity(self) -> Severity:
        return Severity.ERROR

    async def check(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> Optional[BreakingChange]:
        """타입 호환성 검증"""
        # 기본 구현: 호환되지 않는 타입 변경 감지
        old_type = old_schema.get("type")
        new_type = new_schema.get("type")

        if old_type and new_type and old_type != new_type:
            if not self._is_compatible_type_change(old_type, new_type):
                return BreakingChange(
                    rule_id=self.rule_id,
                    severity=self.severity,
                    message=f"Incompatible type change from {old_type} to {new_type}",
                    resource_id=self._get_resource_id(old_schema),
                    resource_type=self._get_resource_type(old_schema),
                    details={
                        "old_type": old_type,
                        "new_type": new_type
                    }
                )
        return None

    def validate(
        self,
        old_schema: List[ObjectType],
        new_schema: List[ObjectType],
        context: ValidationContext
    ) -> RuleResult:
        """타입 호환성 검증"""
        result = RuleResult()
        return result

    def _is_compatible_type_change(self, old_type: str, new_type: str) -> bool:
        """타입 변경의 호환성 검증"""
        return False  # 기본적으로 안전하지 않음으로 간주
