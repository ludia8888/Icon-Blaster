"""
Primary Key 변경 감지 규칙
섹션 8.3.2의 PrimaryKeyChangeRule 구현
"""
import logging
from typing import Any, Dict, Optional

from core.validation.models import BreakingChange, Severity
from core.validation.rules.base import BreakingChangeRule

logger = logging.getLogger(__name__)


class PrimaryKeyChangeRule(BreakingChangeRule):
    """Primary Key 변경 감지"""

    def __init__(self):
        pass

    @property
    def rule_id(self) -> str:
        return "PRIMARY_KEY_CHANGE"

    @property
    def severity(self) -> Severity:
        return Severity.CRITICAL

    async def check(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context
    ) -> Optional[BreakingChange]:
        """Primary Key 변경 검사"""

        old_pk = self._find_primary_key(old_schema)
        new_pk = self._find_primary_key(new_schema)

        # Primary Key 변경 감지
        if old_pk and new_pk and old_pk["name"] != new_pk["name"]:
            object_type_name = old_schema.get("name", "Unknown")

            return BreakingChange(
                rule_id=self.rule_id,
                severity=self.severity,
                resource_type="ObjectType",
                resource_id=self._get_resource_id(old_schema),
                resource_name=object_type_name,
                description=f"Primary key changed from '{old_pk['name']}' to '{new_pk['name']}'",
                old_value=old_pk["name"],
                new_value=new_pk["name"],
                metadata={
                    "oldPkName": old_pk["name"],
                    "newPkName": new_pk["name"],
                    "change_type": "primary_key_modification"
                }
            )

        # Primary Key가 추가된 경우
        elif not old_pk and new_pk:
            return BreakingChange(
                rule_id=self.rule_id,
                severity=Severity.HIGH,
                resource_type="ObjectType",
                resource_id=self._get_resource_id(old_schema),
                resource_name=old_schema.get("name", "Unknown"),
                description=f"Primary key '{new_pk['name']}' added to existing type",
                old_value=None,
                new_value=new_pk["name"],
                metadata={"change_type": "primary_key_addition"}
            )

        # Primary Key가 제거된 경우
        elif old_pk and not new_pk:
            return BreakingChange(
                rule_id=self.rule_id,
                severity=Severity.HIGH,
                resource_type="ObjectType",
                resource_id=self._get_resource_id(old_schema),
                resource_name=old_schema.get("name", "Unknown"),
                description=f"Primary key '{old_pk['name']}' removed",
                old_value=old_pk["name"],
                new_value=None,
                metadata={"change_type": "primary_key_removal"}
            )

        return None

    def _find_primary_key(self, schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """스키마에서 Primary Key 속성 찾기"""
        properties = schema.get("properties", [])
        for prop in properties:
            if prop.get("isPrimaryKey", False) or prop.get("is_primary_key", False):
                return prop
        return None
