"""
Required Field Removal Detection Rule
ADR-004 RequiredFieldRemovalRule 구현
Foundry OMS 핵심 원칙: Domain-driven, Cache-first, Event-driven
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from core.validation.models import (
    BreakingChange,
    DataImpact,
    Severity,
    ValidationContext,
)
from core.validation.rules.base import BreakingChangeRule
from database.clients.terminus_db import TerminusDBClient

logger = logging.getLogger(__name__)


@dataclass
class RequiredFieldAnalysis:
    """Required Field 변경 분석 결과"""
    removed_required_fields: Set[str]
    field_usage_statistics: Dict[str, int]
    validation_constraints: List[Dict[str, Any]]
    business_critical_fields: Set[str]
    foundry_ontology_dependencies: List[Dict[str, Any]]


class RequiredFieldRemovalRule(BreakingChangeRule):
    """
    필수 필드 제거 감지 규칙
    
    Foundry Ontology에서 필수 필드 제거는 데이터 무결성과 비즈니스 로직에 중대한 영향을 미칩니다.
    특히 Foundry의 강타입 시스템에서는 필수 필드 제거가 전체 온톨로지 일관성을 위협할 수 있습니다.
    
    P2 Domain Boundary: 필수 필드는 도메인 규칙을 강제하는 핵심 요소
    P4 Cache-First: 필드 분석 결과를 캐시하여 성능 최적화
    """

    # Foundry에서 중요한 비즈니스 필드 패턴
    BUSINESS_CRITICAL_PATTERNS = {
        "id", "identifier", "name", "title", "status", "state",
        "created", "modified", "updated", "deleted", "active",
        "email", "phone", "address", "amount", "price", "quantity"
    }

    # Foundry Ontology에서 메타데이터 필수 필드들
    FOUNDRY_METADATA_FIELDS = {
        "displayName", "description", "@type", "@id",
        "objectTypeVersion", "validFrom", "validTo"
    }

    @property
    def rule_id(self) -> str:
        return "required_field_removal"

    @property
    def severity(self) -> Severity:
        return Severity.HIGH

    @property
    def description(self) -> str:
        return "Detects removal of required fields that could break data integrity"

    async def check(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> Optional[BreakingChange]:
        """
        필수 필드 제거 검사
        
        P4 Cache-First 원칙: 필드 분석 결과를 캐시하여 반복 분석 최적화
        """

        # 캐시 키 생성 (P4 원칙)
        cache_key = f"required_field_analysis:{context.source_branch}:{context.target_branch}:{self._get_resource_id(old_schema)}"

        # 캐시된 분석 결과 확인
        if hasattr(context, 'cache') and context.cache:
            cached_analysis = await context.cache.get(cache_key)
            if cached_analysis:
                return await self._create_breaking_change_from_cached(cached_analysis, old_schema, new_schema, context)

        # Required Field 분석 수행
        field_analysis = await self._analyze_required_field_changes(old_schema, new_schema, context)

        # 결과 캐싱 (P4 원칙)
        if hasattr(context, 'cache') and context.cache:
            await context.cache.set(cache_key, field_analysis, ttl=3600)

        # Breaking Change 여부 결정
        if field_analysis.removed_required_fields:
            return await self._create_breaking_change(field_analysis, old_schema, new_schema, context)

        return None

    async def _analyze_required_field_changes(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> RequiredFieldAnalysis:
        """필수 필드 변경사항 종합 분석"""

        # 필수 필드 식별
        old_required = self._identify_required_fields(old_schema)
        new_fields = self._get_all_field_names(new_schema)

        # 제거된 필수 필드들
        removed_required = old_required - new_fields

        # 필드 사용 통계 분석
        usage_stats = await self._analyze_field_usage_statistics(
            old_schema, removed_required, context
        )

        # 검증 제약 조건 분석
        validation_constraints = await self._analyze_validation_constraints(
            old_schema, removed_required, context
        )

        # 비즈니스 중요 필드 식별
        business_critical = self._identify_business_critical_fields(removed_required)

        # Foundry Ontology 의존성 분석
        foundry_dependencies = await self._analyze_foundry_dependencies(
            old_schema, removed_required, context
        )

        return RequiredFieldAnalysis(
            removed_required_fields=removed_required,
            field_usage_statistics=usage_stats,
            validation_constraints=validation_constraints,
            business_critical_fields=business_critical,
            foundry_ontology_dependencies=foundry_dependencies
        )

    def _identify_required_fields(self, schema: Dict[str, Any]) -> Set[str]:
        """스키마에서 필수 필드들 식별"""

        required_fields = set()
        properties = schema.get("properties", {})

        for prop_name, prop_def in properties.items():
            # 명시적 required 표시
            if prop_def.get("required", False):
                required_fields.add(prop_name)
                continue

            # Foundry 메타데이터 필수 필드
            if prop_name in self.FOUNDRY_METADATA_FIELDS:
                required_fields.add(prop_name)
                continue

            # nullable이 false이고 default 값이 없는 필드
            if (not prop_def.get("nullable", True) and
                "default" not in prop_def):
                required_fields.add(prop_name)
                continue

        # Schema 레벨의 required 정의
        schema_required = schema.get("required", [])
        if isinstance(schema_required, list):
            required_fields.update(schema_required)

        return required_fields

    def _get_all_field_names(self, schema: Dict[str, Any]) -> Set[str]:
        """스키마의 모든 필드 이름들 추출"""
        return set(schema.get("properties", {}).keys())

    async def _analyze_field_usage_statistics(
        self,
        schema: Dict[str, Any],
        removed_fields: Set[str],
        context: ValidationContext
    ) -> Dict[str, int]:
        """제거된 필드들의 사용 통계 분석"""

        usage_stats = {}
        object_type_name = self._get_resource_name(schema)

        try:
            for field in removed_fields:
                # 필드에 값이 있는 레코드 수 계산
                usage_query = f"""
                SELECT (COUNT(?instance) AS ?usage_count)
                WHERE {{
                    ?instance a <{object_type_name}> .
                    ?instance <{field}> ?value .
                    FILTER(BOUND(?value))
                }}
                """

                if hasattr(context, 'terminus_client'):
                    result = await context.terminus_client.query(
                        usage_query, db="oms", branch=context.source_branch
                    )

                    usage_count = int(result[0].get("usage_count", 0)) if result else 0
                    usage_stats[field] = usage_count

        except Exception as e:
            logger.error(f"Field usage statistics analysis failed: {e}")
            # 보수적 추정: 모든 필드가 광범위하게 사용된다고 가정
            for field in removed_fields:
                usage_stats[field] = 100000  # 보수적 추정치

        return usage_stats

    async def _analyze_validation_constraints(
        self,
        schema: Dict[str, Any],
        removed_fields: Set[str],
        context: ValidationContext
    ) -> List[Dict[str, Any]]:
        """제거된 필드들의 검증 제약 조건 분석"""

        constraints = []
        properties = schema.get("properties", {})

        for field in removed_fields:
            field_def = properties.get(field, {})

            field_constraints = {
                "field": field,
                "constraints": [],
                "validation_impact": "MEDIUM"
            }

            # 타입 제약
            if "dataType" in field_def:
                field_constraints["constraints"].append({
                    "type": "data_type",
                    "value": field_def["dataType"]
                })

            # 길이 제약
            if "maxLength" in field_def:
                field_constraints["constraints"].append({
                    "type": "max_length",
                    "value": field_def["maxLength"]
                })

            # 패턴 제약
            if "pattern" in field_def:
                field_constraints["constraints"].append({
                    "type": "pattern",
                    "value": field_def["pattern"]
                })

            # 고유성 제약
            if field_def.get("unique", False):
                field_constraints["constraints"].append({
                    "type": "uniqueness",
                    "value": True
                })
                field_constraints["validation_impact"] = "HIGH"

            # 참조 무결성 제약
            if "references" in field_def:
                field_constraints["constraints"].append({
                    "type": "foreign_key",
                    "value": field_def["references"]
                })
                field_constraints["validation_impact"] = "CRITICAL"

            # Foundry 특화 제약
            if field in self.FOUNDRY_METADATA_FIELDS:
                field_constraints["constraints"].append({
                    "type": "foundry_metadata",
                    "value": "Required for Foundry Ontology compliance"
                })
                field_constraints["validation_impact"] = "CRITICAL"

            constraints.append(field_constraints)

        return constraints

    def _identify_business_critical_fields(self, removed_fields: Set[str]) -> Set[str]:
        """비즈니스 중요 필드 식별"""

        business_critical = set()

        for field in removed_fields:
            field_lower = field.lower()

            # 직접 매칭
            if field_lower in self.BUSINESS_CRITICAL_PATTERNS:
                business_critical.add(field)
                continue

            # 패턴 매칭
            for pattern in self.BUSINESS_CRITICAL_PATTERNS:
                if pattern in field_lower or field_lower.endswith(pattern):
                    business_critical.add(field)
                    break

        return business_critical

    async def _analyze_foundry_dependencies(
        self,
        schema: Dict[str, Any],
        removed_fields: Set[str],
        context: ValidationContext
    ) -> List[Dict[str, Any]]:
        """Foundry Ontology 의존성 분석"""

        dependencies = []
        object_type_name = self._get_resource_name(schema)

        try:
            for field in removed_fields:
                # 이 필드를 참조하는 LinkType들 조회
                dependency_query = f"""
                SELECT ?link_type ?source_type ?target_type
                WHERE {{
                    ?link a LinkType .
                    ?link property <{field}> .
                    ?link sourceType ?source_type .
                    ?link targetType ?target_type .
                    ?link linkType ?link_type .
                }}
                """

                if hasattr(context, 'terminus_client'):
                    result = await context.terminus_client.query(
                        dependency_query, db="oms", branch=context.source_branch
                    )

                    for dep in result or []:
                        dependencies.append({
                            "field": field,
                            "dependency_type": "link_property",
                            "link_type": dep.get("link_type", "unknown"),
                            "source_type": dep.get("source_type", "unknown"),
                            "target_type": dep.get("target_type", "unknown"),
                            "impact": "CRITICAL"
                        })

                # Foundry 메타데이터 의존성
                if field in self.FOUNDRY_METADATA_FIELDS:
                    dependencies.append({
                        "field": field,
                        "dependency_type": "foundry_metadata",
                        "description": f"Required for Foundry Ontology {field} compliance",
                        "impact": "CRITICAL"
                    })

        except Exception as e:
            logger.error(f"Foundry dependency analysis failed: {e}")
            # 보수적 추정: 모든 제거된 필드가 의존성을 가진다고 가정
            for field in removed_fields:
                dependencies.append({
                    "field": field,
                    "dependency_type": "unknown",
                    "description": f"Unable to analyze dependencies: {e}",
                    "impact": "HIGH"
                })

        return dependencies

    async def _create_breaking_change(
        self,
        analysis: RequiredFieldAnalysis,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> BreakingChange:
        """Breaking Change 객체 생성"""

        # 심각도 결정
        severity = self._determine_severity(analysis)

        # 데이터 영향도 계산
        data_impact = await self._calculate_data_impact(analysis, old_schema, new_schema, context)

        # 설명 생성
        description = self._generate_description(analysis)

        return BreakingChange(
            rule_id=self.rule_id,
            severity=severity,
            resource_type="ObjectType",
            resource_id=self._get_resource_id(old_schema),
            resource_name=self._get_resource_name(old_schema),
            change_type="required_field_removal",
            old_value=list(analysis.removed_required_fields),
            new_value=None,
            description=description,
            data_impact=data_impact,
            migration_strategy=self._generate_migration_strategy(analysis),
            foundry_compliance=self._assess_foundry_compliance(analysis)
        )

    def _determine_severity(self, analysis: RequiredFieldAnalysis) -> Severity:
        """변경사항 심각도 결정"""

        # Foundry 메타데이터 필드나 비즈니스 중요 필드 제거
        if (analysis.business_critical_fields or
            any(field in self.FOUNDRY_METADATA_FIELDS for field in analysis.removed_required_fields)):
            return Severity.CRITICAL

        # 높은 사용률을 가진 필드 제거
        high_usage_fields = [
            field for field, usage in analysis.field_usage_statistics.items()
            if usage > 10000
        ]
        if high_usage_fields:
            return Severity.HIGH

        # 검증 제약이 많은 필드 제거
        critical_constraints = any(
            constraint.get("validation_impact") == "CRITICAL"
            for constraint in analysis.validation_constraints
        )
        if critical_constraints:
            return Severity.HIGH

        # Foundry 의존성이 있는 필드 제거
        critical_dependencies = any(
            dep.get("impact") == "CRITICAL"
            for dep in analysis.foundry_ontology_dependencies
        )
        if critical_dependencies:
            return Severity.HIGH

        return Severity.MEDIUM

    async def _calculate_data_impact(
        self,
        analysis: RequiredFieldAnalysis,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> DataImpact:
        """데이터 영향도 계산"""

        try:
            # 전체 레코드 수와 영향받는 레코드 수 계산
            total_records = sum(analysis.field_usage_statistics.values()) or 0
            affected_records = max(analysis.field_usage_statistics.values()) if analysis.field_usage_statistics else 0

            # 마이그레이션 복잡도 계산
            complexity_score = self._calculate_migration_complexity(analysis)

            # 예상 다운타임 계산
            estimated_downtime = self._estimate_downtime(analysis, affected_records)

            return DataImpact(
                total_records=total_records,
                affected_records=affected_records,
                impact_percentage=(affected_records / max(1, total_records)) * 100,
                estimated_downtime_minutes=estimated_downtime,
                complexity_score=complexity_score,
                migration_risks=self._identify_migration_risks(analysis)
            )

        except Exception as e:
            logger.error(f"Data impact calculation failed: {e}")
            return DataImpact(
                total_records=0,
                affected_records=len(analysis.removed_required_fields) * 1000,  # 보수적 추정
                impact_percentage=100.0,
                estimated_downtime_minutes=60,
                complexity_score=8,
                migration_risks=[f"Impact calculation failed: {e}"]
            )

    def _calculate_migration_complexity(self, analysis: RequiredFieldAnalysis) -> int:
        """마이그레이션 복잡도 점수 (1-10)"""

        base_score = 3

        # 제거된 필드 수에 따른 복잡도
        base_score += len(analysis.removed_required_fields)

        # 비즈니스 중요 필드 복잡도
        if analysis.business_critical_fields:
            base_score += len(analysis.business_critical_fields) * 2

        # 검증 제약 복잡도
        critical_constraints = sum(
            1 for constraint in analysis.validation_constraints
            if constraint.get("validation_impact") in ["HIGH", "CRITICAL"]
        )
        base_score += critical_constraints

        # Foundry 의존성 복잡도
        if analysis.foundry_ontology_dependencies:
            base_score += len(analysis.foundry_ontology_dependencies)

        # 사용률 기반 복잡도
        high_usage_count = sum(
            1 for usage in analysis.field_usage_statistics.values()
            if usage > 10000
        )
        base_score += high_usage_count

        return min(10, max(1, base_score))

    def _estimate_downtime(self, analysis: RequiredFieldAnalysis, affected_records: int) -> int:
        """예상 다운타임 계산 (분 단위)"""

        # 기본 다운타임: 데이터 정리 및 검증 시간
        base_minutes = max(10, affected_records // 10000)  # 1만 레코드당 1분

        # 비즈니스 중요 필드 제거 시 추가 시간 (검증 및 테스트)
        if analysis.business_critical_fields:
            base_minutes *= 2

        # Foundry 의존성 해결 시간
        if analysis.foundry_ontology_dependencies:
            base_minutes += len(analysis.foundry_ontology_dependencies) * 5

        # 복잡한 검증 제약 해결 시간
        critical_constraints = sum(
            1 for constraint in analysis.validation_constraints
            if constraint.get("validation_impact") == "CRITICAL"
        )
        base_minutes += critical_constraints * 10

        return int(base_minutes)

    def _identify_migration_risks(self, analysis: RequiredFieldAnalysis) -> List[str]:
        """마이그레이션 위험 식별"""

        risks = []

        # 기본 위험
        risks.append(f"Data loss risk: {len(analysis.removed_required_fields)} required fields will be removed")

        # 비즈니스 중요 필드 위험
        if analysis.business_critical_fields:
            risks.append(f"Business critical fields affected: {', '.join(analysis.business_critical_fields)}")

        # 높은 사용률 필드 위험
        high_usage_fields = [
            field for field, usage in analysis.field_usage_statistics.items()
            if usage > 10000
        ]
        if high_usage_fields:
            risks.append(f"High-usage fields will be removed: {', '.join(high_usage_fields)}")

        # 검증 제약 위험
        for constraint in analysis.validation_constraints:
            if constraint.get("validation_impact") == "CRITICAL":
                risks.append(f"Critical validation constraint lost: {constraint['field']}")

        # Foundry 의존성 위험
        critical_deps = [
            dep for dep in analysis.foundry_ontology_dependencies
            if dep.get("impact") == "CRITICAL"
        ]
        if critical_deps:
            risks.append("Foundry Ontology dependencies will be broken")

        # Foundry 특화 위험
        risks.append("Schema validation will need to be updated across all services")
        risks.append("Client applications may fail without proper field handling")

        return risks

    def _generate_description(self, analysis: RequiredFieldAnalysis) -> str:
        """변경사항 설명 생성"""

        field_count = len(analysis.removed_required_fields)
        field_list = ', '.join(sorted(analysis.removed_required_fields))

        description = f"Required fields removed ({field_count}): {field_list}"

        if analysis.business_critical_fields:
            critical_list = ', '.join(sorted(analysis.business_critical_fields))
            description += f" [Business critical: {critical_list}]"

        return description

    def _generate_migration_strategy(self, analysis: RequiredFieldAnalysis) -> str:
        """마이그레이션 전략 생성"""

        strategies = []

        # 기본 전략
        strategies.append("1. Backup all data before field removal")
        strategies.append("2. Update all client applications to handle missing fields")

        # 비즈니스 중요 필드 전략
        if analysis.business_critical_fields:
            strategies.append("3. Review business impact with stakeholders")
            strategies.append("4. Consider deprecation period instead of immediate removal")

        # 높은 사용률 필드 전략
        high_usage_fields = [
            field for field, usage in analysis.field_usage_statistics.items()
            if usage > 1000
        ]
        if high_usage_fields:
            strategies.append("5. Implement graceful degradation for high-usage fields")

        # Foundry 의존성 전략
        if analysis.foundry_ontology_dependencies:
            strategies.append("6. Update all Foundry LinkType definitions")
            strategies.append("7. Verify Foundry Ontology consistency")

        # 검증 제약 전략
        if analysis.validation_constraints:
            strategies.append("8. Update schema validation rules")
            strategies.append("9. Test API endpoints with new schema")

        # Foundry 특화 전략
        strategies.append("10. Invalidate all related cache entries")
        strategies.append("11. Update Foundry object type documentation")

        return " ".join(strategies)

    def _assess_foundry_compliance(self, analysis: RequiredFieldAnalysis) -> str:
        """Foundry 호환성 평가"""

        compliance_issues = []

        # Foundry 메타데이터 필드 제거
        foundry_metadata_removed = analysis.removed_required_fields & self.FOUNDRY_METADATA_FIELDS
        if foundry_metadata_removed:
            compliance_issues.append(f"Foundry metadata fields removed: {', '.join(foundry_metadata_removed)}")

        # Foundry 의존성 위반
        critical_deps = [
            dep for dep in analysis.foundry_ontology_dependencies
            if dep.get("impact") == "CRITICAL"
        ]
        if critical_deps:
            compliance_issues.append("Critical Foundry Ontology dependencies affected")

        # 비즈니스 중요 필드와 Foundry 패턴 충돌
        business_foundry_overlap = analysis.business_critical_fields & self.BUSINESS_CRITICAL_PATTERNS
        if business_foundry_overlap:
            compliance_issues.append("Business critical fields violate Foundry patterns")

        if compliance_issues:
            return f"Foundry compliance violations: {'; '.join(compliance_issues)}"
        else:
            return "Required field removal appears to be Foundry-compliant"

    async def _create_breaking_change_from_cached(
        self,
        cached_analysis: RequiredFieldAnalysis,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> Optional[BreakingChange]:
        """캐시된 분석 결과로부터 Breaking Change 생성"""

        if cached_analysis.removed_required_fields:
            return await self._create_breaking_change(cached_analysis, old_schema, new_schema, context)
        return None


class RequiredFieldAdditionRule(BreakingChangeRule):
    """필수 필드 추가 감지"""

    def __init__(self, tdb_client: TerminusDBClient):
        self.tdb = tdb_client

    @property
    def rule_id(self) -> str:
        return "required_field_addition"

    @property
    def severity(self) -> Severity:
        return Severity.MEDIUM

    async def check(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> Optional[BreakingChange]:
        """필수 필드 추가 검사"""

        if old_schema.get("@type") != "ObjectType":
            return None

        # 이전 스키마의 필수 필드들
        old_required = self._get_required_fields(old_schema)

        # 새 스키마의 필수 필드들
        new_required = self._get_required_fields(new_schema)

        # 추가된 필수 필드들
        added_required = new_required - old_required

        if added_required:
            object_type_name = old_schema.get("name", "Unknown")

            # 기존 레코드 수 확인
            existing_records = await self._count_existing_records(
                context, object_type_name
            )

            if existing_records > 0:
                return BreakingChange(
                    rule_id=self.rule_id,
                    severity=self.severity,
                    resource_type="ObjectType",
                    resource_id=self._get_resource_id(old_schema),
                    resource_name=object_type_name,
                    description=f"Required fields added to existing type: {', '.join(sorted(added_required))}",
                    old_value=None,
                    new_value={
                        "requiredFields": list(added_required)
                    },
                    impact_estimate=ImpactEstimate(
                        affected_records=existing_records,
                        estimated_duration_seconds=existing_records * 0.01,
                        requires_downtime=False,
                        affected_services=["schema-service"]
                    ),
                    migration_strategies=[
                        MigrationStrategy.SET_DEFAULT_VALUES,
                        MigrationStrategy.BACKFILL_NULLABLE
                    ],
                    metadata={
                        "addedFields": list(added_required),
                        "existingRecords": existing_records
                    }
                )

        return None

    def _get_required_fields(self, schema: Dict[str, Any]) -> Set[str]:
        """스키마에서 필수 필드 이름들 추출"""
        required_fields = set()

        for prop in schema.get("properties", []):
            if prop.get("isRequired", False):
                required_fields.add(prop.get("name", ""))

        return required_fields

    async def _count_existing_records(
        self,
        context: ValidationContext,
        object_type_name: str
    ) -> int:
        """기존 레코드 수 계산"""
        try:
            count_query = f"""
            SELECT (COUNT(?instance) AS ?count)
            WHERE {{
                ?instance a <{object_type_name}> .
            }}
            """

            result = await self.tdb.query(
                count_query,
                db="oms",
                branch=context.target_branch
            )

            return result[0]["count"] if result else 0

        except Exception as e:
            logger.error(f"Error counting records: {e}")
            return 0
