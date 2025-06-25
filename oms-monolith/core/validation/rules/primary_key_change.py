"""
Primary Key Change Detection Rule
ADR-004 PrimaryKeyChangeRule 구현
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

logger = logging.getLogger(__name__)


@dataclass
class PrimaryKeyAnalysis:
    """Primary Key 변경 분석 결과"""
    old_primary_keys: Set[str]
    new_primary_keys: Set[str]
    removed_keys: Set[str]
    added_keys: Set[str]
    modified_keys: Set[str]
    composite_key_changes: List[Dict[str, Any]]
    uniqueness_violations: List[str]
    referential_integrity_risks: List[Dict[str, Any]]


class PrimaryKeyChangeRule(BreakingChangeRule):
    """
    Primary Key 변경 감지 규칙
    
    Foundry Ontology에서 Primary Key 변경은 가장 위험한 Breaking Change입니다.
    데이터 무결성, 참조 무결성, 인덱싱 전략에 전면적 영향을 미칩니다.
    
    P2 Domain Boundary: ObjectType의 식별자 변경은 모든 관련 도메인에 영향
    P4 Cache-First: Primary Key 기반 캐시 무효화 전략 필요
    """

    # Foundry에서 Primary Key로 인식되는 속성들
    PRIMARY_KEY_INDICATORS = {
        "primaryKey", "id", "identifier", "key",
        "uniqueId", "objectId", "entityId"
    }

    # 위험한 Primary Key 변경 시나리오
    CRITICAL_SCENARIOS = {
        "pk_removal": "Primary key field completely removed",
        "pk_type_change": "Primary key data type changed",
        "composite_pk_change": "Composite primary key structure modified",
        "pk_constraint_change": "Primary key constraints modified",
        "pk_nullable_change": "Primary key nullable status changed"
    }

    @property
    def rule_id(self) -> str:
        return "primary_key_change"

    @property
    def severity(self) -> Severity:
        return Severity.CRITICAL

    @property
    def description(self) -> str:
        return "Detects primary key changes that violate data integrity constraints"

    async def check(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> Optional[BreakingChange]:
        """
        Primary Key 변경 검사
        
        P4 Cache-First 원칙: PK 분석 결과를 캐시하여 반복 분석 최적화
        """

        # 캐시 키 생성 (P4 원칙)
        cache_key = f"pk_analysis:{context.source_branch}:{context.target_branch}:{self._get_resource_id(old_schema)}"

        # 캐시된 분석 결과 확인
        if hasattr(context, 'cache') and context.cache:
            cached_analysis = await context.cache.get(cache_key)
            if cached_analysis:
                return await self._create_breaking_change_from_cached(cached_analysis, old_schema, new_schema, context)

        # Primary Key 분석 수행
        pk_analysis = await self._analyze_primary_key_changes(old_schema, new_schema, context)

        # 결과 캐싱 (P4 원칙)
        if hasattr(context, 'cache') and context.cache:
            await context.cache.set(cache_key, pk_analysis, ttl=3600)

        # Breaking Change 여부 결정
        if self._has_breaking_changes(pk_analysis):
            return await self._create_breaking_change(pk_analysis, old_schema, new_schema, context)

        return None

    async def _analyze_primary_key_changes(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> PrimaryKeyAnalysis:
        """Primary Key 변경사항 종합 분석"""

        # Primary Key 필드 식별
        old_pk_fields = self._identify_primary_keys(old_schema)
        new_pk_fields = self._identify_primary_keys(new_schema)

        # 변경사항 분석
        removed_keys = old_pk_fields - new_pk_fields
        added_keys = new_pk_fields - old_pk_fields
        modified_keys = self._find_modified_primary_keys(old_schema, new_schema, old_pk_fields & new_pk_fields)

        # Composite Key 변경 분석
        composite_changes = await self._analyze_composite_key_changes(
            old_schema, new_schema, old_pk_fields, new_pk_fields, context
        )

        # 고유성 제약 위반 분석
        uniqueness_violations = await self._analyze_uniqueness_violations(
            old_schema, new_schema, new_pk_fields, context
        )

        # 참조 무결성 위험 분석
        referential_risks = await self._analyze_referential_integrity_risks(
            old_schema, new_schema, removed_keys, modified_keys, context
        )

        return PrimaryKeyAnalysis(
            old_primary_keys=old_pk_fields,
            new_primary_keys=new_pk_fields,
            removed_keys=removed_keys,
            added_keys=added_keys,
            modified_keys=modified_keys,
            composite_key_changes=composite_changes,
            uniqueness_violations=uniqueness_violations,
            referential_integrity_risks=referential_risks
        )

    def _identify_primary_keys(self, schema: Dict[str, Any]) -> Set[str]:
        """스키마에서 Primary Key 필드들 식별"""

        primary_keys = set()
        properties = schema.get("properties", {})

        for prop_name, prop_def in properties.items():
            # 명시적 Primary Key 표시
            if prop_def.get("primaryKey", False):
                primary_keys.add(prop_name)
                continue

            # 속성명 기반 식별
            if prop_name.lower() in {"id", "identifier", "key"}:
                primary_keys.add(prop_name)
                continue

            # Foundry 규칙: 'id'로 끝나는 속성
            if prop_name.lower().endswith("id") and prop_def.get("unique", False):
                primary_keys.add(prop_name)
                continue

            # 고유 제약이 있는 필수 필드
            if (prop_def.get("required", False) and
                prop_def.get("unique", False) and
                not prop_def.get("nullable", True)):
                primary_keys.add(prop_name)

        # Schema 레벨의 Primary Key 정의
        schema_pk = schema.get("primaryKey")
        if schema_pk:
            if isinstance(schema_pk, str):
                primary_keys.add(schema_pk)
            elif isinstance(schema_pk, list):
                primary_keys.update(schema_pk)

        return primary_keys

    def _find_modified_primary_keys(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        common_keys: Set[str]
    ) -> Set[str]:
        """공통 Primary Key 필드의 변경사항 식별"""

        modified = set()
        old_props = old_schema.get("properties", {})
        new_props = new_schema.get("properties", {})

        for key in common_keys:
            old_prop = old_props.get(key, {})
            new_prop = new_props.get(key, {})

            # 타입 변경
            if old_prop.get("dataType") != new_prop.get("dataType"):
                modified.add(key)
                continue

            # Nullable 변경
            if old_prop.get("nullable", True) != new_prop.get("nullable", True):
                modified.add(key)
                continue

            # 제약 조건 변경
            if old_prop.get("unique", False) != new_prop.get("unique", False):
                modified.add(key)
                continue

            # 길이/정밀도 제약 변경 (축소 시 위험)
            old_max_length = old_prop.get("maxLength")
            new_max_length = new_prop.get("maxLength")
            if (old_max_length and new_max_length and
                new_max_length < old_max_length):
                modified.add(key)
                continue

        return modified

    async def _analyze_composite_key_changes(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        old_pk_fields: Set[str],
        new_pk_fields: Set[str],
        context: ValidationContext
    ) -> List[Dict[str, Any]]:
        """Composite Primary Key 변경 분석"""

        changes = []

        # Composite Key 구조 분석
        old_composite = len(old_pk_fields) > 1
        new_composite = len(new_pk_fields) > 1

        if old_composite and not new_composite:
            changes.append({
                "type": "composite_to_single",
                "description": "Composite primary key changed to single key",
                "risk": "HIGH",
                "impact": "Index reorganization required"
            })
        elif not old_composite and new_composite:
            changes.append({
                "type": "single_to_composite",
                "description": "Single primary key changed to composite key",
                "risk": "HIGH",
                "impact": "All queries and indexes need restructuring"
            })
        elif old_composite and new_composite:
            # Composite Key 순서 변경 검사
            old_order = self._get_primary_key_order(old_schema)
            new_order = self._get_primary_key_order(new_schema)

            if old_order != new_order:
                changes.append({
                    "type": "composite_order_change",
                    "description": "Composite primary key field order changed",
                    "risk": "MEDIUM",
                    "impact": "Index efficiency may be affected",
                    "old_order": old_order,
                    "new_order": new_order
                })

        return changes

    async def _analyze_uniqueness_violations(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        new_pk_fields: Set[str],
        context: ValidationContext
    ) -> List[str]:
        """새로운 Primary Key의 고유성 제약 위반 분석"""

        violations = []

        if not new_pk_fields:
            violations.append("No primary key defined - uniqueness cannot be guaranteed")
            return violations

        # 실제 데이터에서 고유성 검증
        try:
            object_type_name = self._get_resource_name(old_schema)

            for pk_field in new_pk_fields:
                # 중복 값 존재 확인 쿼리
                duplicate_check_query = f"""
                SELECT ?value (COUNT(?instance) AS ?count)
                WHERE {{
                    ?instance a <{object_type_name}> .
                    ?instance <{pk_field}> ?value .
                }}
                GROUP BY ?value
                HAVING (?count > 1)
                ORDER BY DESC(?count)
                LIMIT 10
                """

                if hasattr(context, 'terminus_client'):
                    duplicates = await context.terminus_client.query(
                        duplicate_check_query, db="oms", branch=context.source_branch
                    )

                    if duplicates:
                        total_duplicates = sum(int(dup.get("count", 0)) for dup in duplicates)
                        violations.append(
                            f"Field '{pk_field}' has {len(duplicates)} duplicate values "
                            f"affecting {total_duplicates} records"
                        )

        except Exception as e:
            logger.warning(f"Could not verify uniqueness constraints: {e}")
            violations.append(f"Unable to verify uniqueness: {e}")

        return violations

    async def _analyze_referential_integrity_risks(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        removed_keys: Set[str],
        modified_keys: Set[str],
        context: ValidationContext
    ) -> List[Dict[str, Any]]:
        """참조 무결성 위험 분석 - Foundry Ontology Link 기반"""

        risks = []
        object_type_name = self._get_resource_name(old_schema)

        try:
            # Primary Key를 참조하는 LinkType들 조회
            referencing_links_query = f"""
            SELECT ?link_type ?source_type ?property_name
            WHERE {{
                ?link a LinkType .
                ?link targetType <{object_type_name}> .
                ?link sourceType ?source_type .
                ?link linkType ?link_type .
                ?link property ?property_name .
            }}
            """

            if hasattr(context, 'terminus_client'):
                referencing_links = await context.terminus_client.query(
                    referencing_links_query, db="oms", branch=context.source_branch
                )

                for link in referencing_links or []:
                    link_type = link.get("link_type", "unknown")
                    source_type = link.get("source_type", "unknown")

                    # 삭제된 Primary Key에 대한 참조
                    for removed_key in removed_keys:
                        risks.append({
                            "type": "referential_integrity_violation",
                            "severity": "CRITICAL",
                            "description": f"Removed primary key '{removed_key}' is referenced by LinkType '{link_type}'",
                            "affected_link": link_type,
                            "source_object_type": source_type,
                            "impact": "Foreign key constraints will be violated"
                        })

                    # 변경된 Primary Key에 대한 참조
                    for modified_key in modified_keys:
                        risks.append({
                            "type": "referential_integrity_risk",
                            "severity": "HIGH",
                            "description": f"Modified primary key '{modified_key}' is referenced by LinkType '{link_type}'",
                            "affected_link": link_type,
                            "source_object_type": source_type,
                            "impact": "Reference relationships may break"
                        })

        except Exception as e:
            logger.error(f"Referential integrity analysis failed: {e}")
            risks.append({
                "type": "analysis_error",
                "severity": "MEDIUM",
                "description": f"Could not analyze referential integrity: {e}",
                "impact": "Manual verification required"
            })

        return risks

    def _get_primary_key_order(self, schema: Dict[str, Any]) -> List[str]:
        """Primary Key 필드들의 순서 추출"""

        # Schema에 명시적 순서가 있는 경우
        schema_pk = schema.get("primaryKey")
        if isinstance(schema_pk, list):
            return schema_pk

        # Properties 정의 순서 기반
        properties = schema.get("properties", {})
        pk_fields = []

        for prop_name, prop_def in properties.items():
            if (prop_def.get("primaryKey", False) or
                prop_name.lower() in self.PRIMARY_KEY_INDICATORS):
                pk_fields.append(prop_name)

        return pk_fields

    def _has_breaking_changes(self, analysis: PrimaryKeyAnalysis) -> bool:
        """Breaking Change 여부 결정"""

        # Primary Key 제거는 항상 Breaking Change
        if analysis.removed_keys:
            return True

        # Primary Key 타입/제약 변경
        if analysis.modified_keys:
            return True

        # Composite Key 구조 변경
        if analysis.composite_key_changes:
            return True

        # 고유성 제약 위반
        if analysis.uniqueness_violations:
            return True

        # 참조 무결성 위험
        critical_referential_risks = any(
            risk.get("severity") == "CRITICAL"
            for risk in analysis.referential_integrity_risks
        )
        if critical_referential_risks:
            return True

        return False

    async def _create_breaking_change(
        self,
        analysis: PrimaryKeyAnalysis,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> BreakingChange:
        """Breaking Change 객체 생성"""

        # 심각도 결정
        severity = self._determine_severity(analysis)

        # 데이터 영향도 분석
        data_impact = await self._calculate_data_impact(analysis, old_schema, new_schema, context)

        # 변경 유형 결정
        change_type = self._determine_change_type(analysis)

        # 설명 생성
        description = self._generate_description(analysis)

        return BreakingChange(
            rule_id=self.rule_id,
            severity=severity,
            resource_type="ObjectType",
            resource_id=self._get_resource_id(old_schema),
            resource_name=self._get_resource_name(old_schema),
            change_type=change_type,
            old_value=list(analysis.old_primary_keys),
            new_value=list(analysis.new_primary_keys),
            description=description,
            data_impact=data_impact,
            migration_strategy=self._generate_migration_strategy(analysis),
            foundry_compliance=self._assess_foundry_compliance(analysis)
        )

    def _determine_severity(self, analysis: PrimaryKeyAnalysis) -> Severity:
        """변경사항 심각도 결정"""

        # Primary Key 완전 제거
        if analysis.removed_keys and not analysis.new_primary_keys:
            return Severity.CRITICAL

        # 참조 무결성 위반
        critical_referential_risks = any(
            risk.get("severity") == "CRITICAL"
            for risk in analysis.referential_integrity_risks
        )
        if critical_referential_risks:
            return Severity.CRITICAL

        # Primary Key 부분 제거 또는 타입 변경
        if analysis.removed_keys or analysis.modified_keys:
            return Severity.HIGH

        # Composite Key 구조 변경
        if analysis.composite_key_changes:
            return Severity.HIGH

        # 고유성 제약 위반
        if analysis.uniqueness_violations:
            return Severity.MEDIUM

        return Severity.LOW

    def _determine_change_type(self, analysis: PrimaryKeyAnalysis) -> str:
        """변경 유형 결정"""

        if analysis.removed_keys and not analysis.new_primary_keys:
            return "primary_key_removal"
        elif analysis.removed_keys:
            return "primary_key_partial_removal"
        elif analysis.modified_keys:
            return "primary_key_modification"
        elif analysis.composite_key_changes:
            return "composite_key_restructure"
        else:
            return "primary_key_constraint_change"

    async def _calculate_data_impact(
        self,
        analysis: PrimaryKeyAnalysis,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> DataImpact:
        """데이터 영향도 계산"""

        try:
            object_type_name = self._get_resource_name(old_schema)

            # 전체 레코드 수 조회
            count_query = f"""
            SELECT (COUNT(?instance) AS ?total)
            WHERE {{
                ?instance a <{object_type_name}> .
            }}
            """

            total_records = 0
            if hasattr(context, 'terminus_client'):
                result = await context.terminus_client.query(
                    count_query, db="oms", branch=context.source_branch
                )
                if result:
                    total_records = int(result[0].get("total", 0))

            # 영향받는 레코드 계산
            affected_records = total_records  # Primary Key 변경은 모든 레코드에 영향

            # 마이그레이션 복잡도 계산
            complexity_score = self._calculate_migration_complexity(analysis, total_records)

            # 예상 다운타임 계산
            estimated_downtime = self._estimate_downtime(analysis, total_records)

            return DataImpact(
                total_records=total_records,
                affected_records=affected_records,
                impact_percentage=100.0 if total_records > 0 else 0.0,
                estimated_downtime_minutes=estimated_downtime,
                complexity_score=complexity_score,
                migration_risks=self._identify_migration_risks(analysis)
            )

        except Exception as e:
            logger.error(f"Data impact calculation failed: {e}")
            return DataImpact(
                total_records=0,
                affected_records=0,
                impact_percentage=100.0,
                estimated_downtime_minutes=120,  # 보수적 추정
                complexity_score=10,
                migration_risks=[f"Impact calculation failed: {e}"]
            )

    def _calculate_migration_complexity(self, analysis: PrimaryKeyAnalysis, record_count: int) -> int:
        """마이그레이션 복잡도 점수 (1-10)"""

        base_score = 5

        # Primary Key 제거/추가에 따른 복잡도
        if analysis.removed_keys:
            base_score += len(analysis.removed_keys) * 2
        if analysis.added_keys:
            base_score += len(analysis.added_keys)

        # Composite Key 변경 복잡도
        if analysis.composite_key_changes:
            base_score += len(analysis.composite_key_changes)

        # 참조 무결성 위험 복잡도
        if analysis.referential_integrity_risks:
            base_score += len(analysis.referential_integrity_risks)

        # 데이터 볼륨 복잡도
        if record_count > 10_000_000:  # 1000만 레코드 이상
            base_score += 3
        elif record_count > 1_000_000:  # 100만 레코드 이상
            base_score += 2
        elif record_count > 100_000:   # 10만 레코드 이상
            base_score += 1

        return min(10, max(1, base_score))

    def _estimate_downtime(self, analysis: PrimaryKeyAnalysis, record_count: int) -> int:
        """예상 다운타임 계산 (분 단위)"""

        # 기본 다운타임: 인덱스 재구축 시간
        base_minutes = max(5, record_count // 100000)  # 10만 레코드당 1분

        # Primary Key 변경 유형별 가중치
        if analysis.removed_keys and not analysis.new_primary_keys:
            base_minutes *= 3  # 완전 제거는 3배
        elif analysis.removed_keys or analysis.modified_keys:
            base_minutes *= 2  # 부분 변경은 2배

        # Composite Key 변경 가중치
        if analysis.composite_key_changes:
            base_minutes *= 1.5

        # 참조 무결성 업데이트 시간
        if analysis.referential_integrity_risks:
            base_minutes += len(analysis.referential_integrity_risks) * 10

        return int(base_minutes)

    def _identify_migration_risks(self, analysis: PrimaryKeyAnalysis) -> List[str]:
        """마이그레이션 위험 식별"""

        risks = []

        if analysis.removed_keys:
            risks.append(f"Primary key fields removed: {', '.join(analysis.removed_keys)}")

        if analysis.modified_keys:
            risks.append(f"Primary key fields modified: {', '.join(analysis.modified_keys)}")

        if analysis.uniqueness_violations:
            risks.extend(analysis.uniqueness_violations)

        if analysis.referential_integrity_risks:
            for risk in analysis.referential_integrity_risks:
                risks.append(risk.get("description", "Unknown referential integrity risk"))

        if analysis.composite_key_changes:
            risks.append("Composite primary key structure changed")

        # Foundry 특화 위험
        risks.append("All Foundry Ontology queries referencing this ObjectType need updating")
        risks.append("Cache invalidation will affect entire branch")
        risks.append("Link relationships may need re-establishment")

        return risks

    def _generate_description(self, analysis: PrimaryKeyAnalysis) -> str:
        """변경사항 설명 생성"""

        if analysis.removed_keys and not analysis.new_primary_keys:
            return f"Primary key completely removed: {', '.join(analysis.removed_keys)}"

        if analysis.removed_keys:
            return f"Primary key fields removed: {', '.join(analysis.removed_keys)}"

        if analysis.modified_keys:
            return f"Primary key fields modified: {', '.join(analysis.modified_keys)}"

        if analysis.composite_key_changes:
            change_types = [change.get("type", "unknown") for change in analysis.composite_key_changes]
            return f"Composite primary key changes: {', '.join(change_types)}"

        return "Primary key constraints or structure changed"

    def _generate_migration_strategy(self, analysis: PrimaryKeyAnalysis) -> str:
        """마이그레이션 전략 생성"""

        strategies = []

        # 기본 전략
        strategies.append("1. Create comprehensive backup before migration")
        strategies.append("2. Identify all objects and links referencing this ObjectType")

        # Primary Key 변경별 전략
        if analysis.removed_keys and not analysis.new_primary_keys:
            strategies.append("3. Define new primary key strategy")
            strategies.append("4. Update all queries to use new identification method")
        elif analysis.removed_keys or analysis.modified_keys:
            strategies.append("3. Migrate data to new primary key structure")
            strategies.append("4. Update all referencing LinkTypes")

        # Composite Key 변경 전략
        if analysis.composite_key_changes:
            strategies.append("5. Rebuild composite indexes in correct order")

        # 참조 무결성 전략
        if analysis.referential_integrity_risks:
            strategies.append("6. Update all referencing objects and links")
            strategies.append("7. Re-establish foreign key relationships")

        # Foundry 특화 전략
        strategies.append("8. Invalidate all related cache entries")
        strategies.append("9. Test all Foundry Ontology queries")
        strategies.append("10. Verify Link relationship integrity")

        return " ".join(strategies)

    def _assess_foundry_compliance(self, analysis: PrimaryKeyAnalysis) -> str:
        """Foundry 호환성 평가"""

        compliance_issues = []

        if not analysis.new_primary_keys:
            compliance_issues.append("Missing primary key violates Foundry ObjectType requirements")

        if analysis.referential_integrity_risks:
            compliance_issues.append("Referential integrity violations affect Foundry Link consistency")

        if analysis.composite_key_changes:
            compliance_issues.append("Composite key changes may affect Foundry query performance")

        if compliance_issues:
            return f"Foundry compliance issues: {'; '.join(compliance_issues)}"
        else:
            return "Primary key changes appear to be Foundry-compliant"

    async def _create_breaking_change_from_cached(
        self,
        cached_analysis: PrimaryKeyAnalysis,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> Optional[BreakingChange]:
        """캐시된 분석 결과로부터 Breaking Change 생성"""

        if self._has_breaking_changes(cached_analysis):
            return await self._create_breaking_change(cached_analysis, old_schema, new_schema, context)
        return None
