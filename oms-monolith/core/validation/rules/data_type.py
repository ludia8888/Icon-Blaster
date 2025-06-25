"""
데이터 타입 변경 감지 규칙
"""
import logging
from typing import Any, Dict, List, Optional

from core.validation.models import (
    BreakingChange,
    ImpactEstimate,
    MigrationStrategy,
    Severity,
    ValidationContext,
)
from core.validation.rules.base import BreakingChangeRule

logger = logging.getLogger(__name__)


class DataTypeChangeRule(BreakingChangeRule):
    """Property의 데이터 타입 변경 감지"""

    @property
    def rule_id(self) -> str:
        return "data_type_change"

    @property
    def severity(self) -> Severity:
        return Severity.HIGH

    async def check(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> Optional[BreakingChange]:
        """데이터 타입 변경 검사"""

        if old_schema.get("@type") != "ObjectType":
            return None

        breaking_changes = []

        # 각 속성의 데이터 타입 변경 확인
        old_props = {p["name"]: p for p in old_schema.get("properties", [])}
        new_props = {p["name"]: p for p in new_schema.get("properties", [])}

        for prop_name, old_prop in old_props.items():
            if prop_name in new_props:
                new_prop = new_props[prop_name]
                old_type = old_prop.get("dataTypeId")
                new_type = new_prop.get("dataTypeId")

                if old_type != new_type and old_type and new_type:
                    # 호환 가능한 타입 변경인지 확인
                    if not self._is_compatible_type_change(old_type, new_type):
                        breaking_changes.append({
                            "property": prop_name,
                            "old_type": old_type,
                            "new_type": new_type,
                            "compatible": False
                        })

        if breaking_changes:
            object_type_name = old_schema.get("name", "Unknown")

            return BreakingChange(
                rule_id=self.rule_id,
                severity=self.severity,
                resource_type="ObjectType",
                resource_id=self._get_resource_id(old_schema),
                resource_name=object_type_name,
                description=self._format_description(breaking_changes),
                old_value={
                    "typeChanges": breaking_changes
                },
                new_value=None,
                impact_estimate=ImpactEstimate(
                    affected_records=-1,  # Need to query
                    estimated_duration_seconds=3600,  # 1 hour estimate
                    requires_downtime=True,
                    affected_services=["all"]
                ),
                migration_strategies=[
                    MigrationStrategy.COPY_THEN_DROP,
                    MigrationStrategy.PROGRESSIVE_ROLLOUT
                ],
                metadata={
                    "incompatibleChanges": len(breaking_changes),
                    "affectedProperties": [c["property"] for c in breaking_changes]
                }
            )

        return None

    def _is_compatible_type_change(self, old_type: str, new_type: str) -> bool:
        """타입 변경이 호환 가능한지 확인"""
        # 호환 가능한 타입 변경 매핑
        compatible_changes = {
            "xsd:integer": ["xsd:long", "xsd:decimal", "xsd:float", "xsd:double", "xsd:string"],
            "xsd:long": ["xsd:decimal", "xsd:float", "xsd:double", "xsd:string"],
            "xsd:float": ["xsd:double", "xsd:string"],
            "xsd:double": ["xsd:string"],
            "xsd:boolean": ["xsd:string"],
            "xsd:date": ["xsd:dateTime", "xsd:string"],
            "xsd:dateTime": ["xsd:string"]
        }

        return new_type in compatible_changes.get(old_type, [])

    def _format_description(self, changes: List[Dict[str, Any]]) -> str:
        """변경사항을 읽기 쉬운 설명으로 포맷"""
        descriptions = []
        for change in changes:
            descriptions.append(
                f"{change['property']}: {change['old_type']} → {change['new_type']}"
            )
        return f"Incompatible data type changes: {'; '.join(descriptions)}"


class UniqueConstraintAdditionRule(BreakingChangeRule):
    """Unique 제약조건 추가 감지"""

    @property
    def rule_id(self) -> str:
        return "unique_constraint_addition"

    @property
    def severity(self) -> Severity:
        return Severity.MEDIUM

    async def check(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> Optional[BreakingChange]:
        """Unique 제약조건 추가 검사"""

        if old_schema.get("@type") != "ObjectType":
            return None

        newly_unique = []

        old_props = {p["name"]: p for p in old_schema.get("properties", [])}
        new_props = {p["name"]: p for p in new_schema.get("properties", [])}

        for prop_name, old_prop in old_props.items():
            if prop_name in new_props:
                new_prop = new_props[prop_name]
                old_unique = old_prop.get("isUnique", False)
                new_unique = new_prop.get("isUnique", False)

                if not old_unique and new_unique:
                    newly_unique.append(prop_name)

        if newly_unique:
            object_type_name = old_schema.get("name", "Unknown")

            return BreakingChange(
                rule_id=self.rule_id,
                severity=self.severity,
                resource_type="ObjectType",
                resource_id=self._get_resource_id(old_schema),
                resource_name=object_type_name,
                description=f"Unique constraints added to existing fields: {', '.join(newly_unique)}",
                old_value=None,
                new_value={
                    "uniqueFields": newly_unique
                },
                impact_estimate=ImpactEstimate(
                    affected_records=-1,
                    estimated_duration_seconds=1800,  # 30 minutes
                    requires_downtime=False,
                    affected_services=["schema-service", "validation-service"]
                ),
                migration_strategies=[
                    MigrationStrategy.PROGRESSIVE_ROLLOUT
                ],
                metadata={
                    "fields": newly_unique,
                    "potentialDuplicates": True
                }
            )

        return None


class IndexRemovalRule(BreakingChangeRule):
    """인덱스 제거 감지 (성능 저하 경고)"""

    @property
    def rule_id(self) -> str:
        return "index_removal"

    @property
    def severity(self) -> Severity:
        return Severity.LOW  # 성능 저하이지만 breaking change는 아님

    async def check(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> Optional[BreakingChange]:
        """인덱스 제거 검사"""

        if old_schema.get("@type") != "ObjectType":
            return None

        removed_indexes = []

        old_props = {p["name"]: p for p in old_schema.get("properties", [])}
        new_props = {p["name"]: p for p in new_schema.get("properties", [])}

        for prop_name, old_prop in old_props.items():
            if prop_name in new_props:
                new_prop = new_props[prop_name]
                old_indexed = old_prop.get("isIndexed", False)
                new_indexed = new_prop.get("isIndexed", False)

                if old_indexed and not new_indexed:
                    removed_indexes.append(prop_name)

        if removed_indexes:
            object_type_name = old_schema.get("name", "Unknown")

            return BreakingChange(
                rule_id=self.rule_id,
                severity=self.severity,
                resource_type="ObjectType",
                resource_id=self._get_resource_id(old_schema),
                resource_name=object_type_name,
                description=f"Indexes removed (potential performance impact): {', '.join(removed_indexes)}",
                old_value={
                    "indexedFields": removed_indexes
                },
                new_value=None,
                impact_estimate=ImpactEstimate(
                    affected_records=0,  # No data change
                    estimated_duration_seconds=0,
                    requires_downtime=False,
                    affected_services=["query-service", "search-service"]
                ),
                migration_strategies=[],  # No migration needed
                metadata={
                    "performanceImpact": "high",
                    "affectedQueries": True
                }
            )

        return None
