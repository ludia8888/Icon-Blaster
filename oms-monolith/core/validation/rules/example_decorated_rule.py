"""
데코레이터를 사용한 검증 규칙 예제
새로운 규칙 작성 시 참고용
"""
from typing import Dict, Any, Optional, List

from core.validation.interfaces import BreakingChangeRule
from core.validation.decorators import validation_rule
from core.validation.models import BreakingChange, Severity
from core.validation.ports import ValidationContext


@validation_rule(
    rule_id="example_decorated",
    category="schema",
    severity_default="medium",
    description="데코레이터를 사용한 예제 규칙"
)
class ExampleDecoratedRule(BreakingChangeRule):
    """
    데코레이터를 사용한 규칙 예제
    
    이 규칙은 실제로는 아무것도 검사하지 않고
    데코레이터 사용법을 보여주기 위한 예제입니다.
    """
    
    async def check(
        self, 
        old_schema: Dict[str, Any], 
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> Optional[List[BreakingChange]]:
        """
        스키마 변경 검사 (예제용)
        """
        # 실제 규칙에서는 여기에 검증 로직을 구현
        # 예: 필드 삭제, 타입 변경 등을 확인
        
        # 데모를 위해 항상 None 반환 (변경 없음)
        return None
    
    @property
    def description(self) -> str:
        """규칙 설명"""
        return self._rule_metadata.get("description", self.__doc__)
    
    @property
    def severity(self) -> Severity:
        """기본 심각도"""
        severity_str = self._rule_metadata.get("severity_default", "medium")
        return Severity[severity_str.upper()]


@validation_rule(
    category="data",
    severity_default="high",
    enabled=False  # 이 규칙은 비활성화됨
)
class DisabledExampleRule(BreakingChangeRule):
    """
    비활성화된 규칙 예제
    enabled=False로 설정하면 레지스트리에 등록되지 않음
    """
    
    async def check(
        self, 
        old_schema: Dict[str, Any], 
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> Optional[List[BreakingChange]]:
        # 이 규칙은 실행되지 않음
        return None