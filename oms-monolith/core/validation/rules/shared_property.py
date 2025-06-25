"""
Shared Property 변경 감지 규칙
섹션 8.3.2의 SharedPropertyChangeRule 구현
"""
import logging
from typing import Any, Dict, List, Optional

from core.validation.models import BreakingChange, Severity
from core.validation.rules.base import BreakingChangeRule

logger = logging.getLogger(__name__)


class SharedPropertyChangeRule(BreakingChangeRule):
    """Shared Property 변경 감지"""

    def __init__(self):
        pass

    @property
    def rule_id(self) -> str:
        return "SHARED_PROPERTY_CHANGE"

    @property
    def severity(self) -> Severity:
        return Severity.CRITICAL

    async def check(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context
    ) -> Optional[BreakingChange]:
        """Shared Property 변경 검사"""

        # 공유 속성인지 확인 (base interface나 상속 관계)
        old_interfaces = old_schema.get("baseInterfaces", [])
        new_interfaces = new_schema.get("baseInterfaces", [])

        # 공유 속성을 가진 ObjectType인지 확인
        if not old_interfaces and not new_interfaces:
            return None

        old_properties = old_schema.get("properties", [])
        new_properties = new_schema.get("properties", [])

        # 공유 속성 변경 검사
        shared_property_changes = self._detect_shared_property_changes(
            old_properties, new_properties, old_interfaces
        )

        if shared_property_changes:
            object_type_name = old_schema.get("name", "Unknown")

            change_descriptions = []
            for change in shared_property_changes:
                change_descriptions.append(
                    f"Property '{change['name']}' inherited from {change['interface']}"
                )

            return BreakingChange(
                rule_id=self.rule_id,
                severity=self.severity,
                resource_type="ObjectType",
                resource_id=self._get_resource_id(old_schema),
                resource_name=object_type_name,
                description=f"Shared property changes detected: {'; '.join(change_descriptions)}",
                old_value={"shared_properties": [c["name"] for c in shared_property_changes]},
                new_value=None,
                metadata={
                    "shared_property_changes": shared_property_changes,
                    "affected_interfaces": list(set(c["interface"] for c in shared_property_changes)),
                    "change_type": "shared_property_modification"
                }
            )

        return None

    def _detect_shared_property_changes(
        self,
        old_properties: List[Dict[str, Any]],
        new_properties: List[Dict[str, Any]],
        interfaces: List[str]
    ) -> List[Dict[str, Any]]:
        """공유 속성 변경 감지"""

        changes = []

        # 인터페이스에서 상속받는 속성들 (일반적으로 공통 속성들)
        common_shared_properties = [
            "id", "createdAt", "updatedAt", "createdBy", "updatedBy",
            "status", "version", "lastModified"
        ]

        old_props_by_name = {prop.get("name"): prop for prop in old_properties}
        new_props_by_name = {prop.get("name"): prop for prop in new_properties}

        for prop_name in common_shared_properties:
            old_prop = old_props_by_name.get(prop_name)
            new_prop = new_props_by_name.get(prop_name)

            # 공유 속성이 제거된 경우
            if old_prop and not new_prop:
                changes.append({
                    "name": prop_name,
                    "change_type": "removed",
                    "interface": "CommonInterface",
                    "old_value": old_prop,
                    "new_value": None
                })

            # 공유 속성의 타입이 변경된 경우
            elif old_prop and new_prop:
                old_type = old_prop.get("dataType") or old_prop.get("type")
                new_type = new_prop.get("dataType") or new_prop.get("type")

                if old_type != new_type:
                    changes.append({
                        "name": prop_name,
                        "change_type": "type_changed",
                        "interface": "CommonInterface",
                        "old_value": old_type,
                        "new_value": new_type
                    })

        return changes
