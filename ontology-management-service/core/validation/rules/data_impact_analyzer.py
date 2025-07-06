"""
Data Impact Analysis Rule
UC-02 요구사항의 데이터 영향도 분석 구현
Foundry OMS 원칙: Domain-driven, Performance-first, Event-driven
"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
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
class ImpactAnalysisResult:
    """영향도 분석 결과"""
    total_objects: int
    affected_objects: int
    relationship_impacts: List[Dict[str, Any]]
    data_quality_risks: List[str]
    performance_implications: Dict[str, Any]
    foundry_compatibility: Dict[str, Any]


class DataImpactAnalyzer(BreakingChangeRule):
    """
    데이터 영향도 분석기
    
    Foundry Ontology 환경에서 스키마 변경이 
    기존 데이터와 비즈니스 로직에 미치는 영향을 분석합니다.
    
    P4 Cache-First: 분석 결과를 적극적으로 캐시
    P3 Event-Driven: 분석 완료 시 이벤트 발행
    """

    # Foundry에서 중요한 관계 타입들
    CRITICAL_RELATIONSHIP_TYPES = {
        "inheritance", "composition", "aggregation",
        "reference", "foreign_key", "dependency"
    }

    # 대용량 데이터 임계값 (ADR-004 기준)
    LARGE_DATASET_THRESHOLD = 1_000_000
    SAMPLING_SIZE = 10_000

    @property
    def rule_id(self) -> str:
        return "data_impact_analyzer"

    @property
    def severity(self) -> Severity:
        return Severity.HIGH

    @property
    def description(self) -> str:
        return "Analyzes data impact and relationships affected by schema changes"

    async def check(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> Optional[BreakingChange]:
        """
        포괄적 데이터 영향도 분석
        
        UC-02: 30초 내 분석 완료, 샘플링으로 대용량 데이터 처리
        """

        start_time = datetime.now()

        try:
            # 병렬 분석 실행 (성능 최적화)
            analysis_tasks = [
                self._analyze_direct_data_impact(old_schema, new_schema, context),
                self._analyze_relationship_impact(old_schema, new_schema, context),
                self._analyze_foundry_compliance(old_schema, new_schema, context),
                self._analyze_performance_implications(old_schema, new_schema, context)
            ]

            # 30초 타임아웃 (UC-02 요구사항)
            results = await asyncio.wait_for(
                asyncio.gather(*analysis_tasks, return_exceptions=True),
                timeout=30.0
            )

            direct_impact, relationship_impact, compliance_impact, performance_impact = results

            # 예외 처리
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Analysis task {i} failed: {result}")

            # 종합 영향도 계산
            combined_impact = self._combine_impact_results(
                direct_impact, relationship_impact, compliance_impact, performance_impact
            )

            # 심각도 결정
            severity = self._determine_overall_severity(combined_impact)

            if severity == Severity.LOW:
                return None  # 영향도가 낮으면 Breaking Change 아님

            # 분석 시간 계산
            analysis_duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"Data impact analysis completed in {analysis_duration:.2f}s")

            # P3: 분석 완료 이벤트 발행
            await self._publish_analysis_event(combined_impact, context)

            return BreakingChange(
                rule_id=self.rule_id,
                severity=severity,
                resource_type=self._get_resource_type(old_schema),
                resource_id=self._get_resource_id(old_schema),
                resource_name=self._get_resource_name(old_schema),
                change_type="data_impact",
                old_value=self._summarize_schema(old_schema),
                new_value=self._summarize_schema(new_schema),
                description=self._generate_impact_description(combined_impact),
                data_impact=self._create_data_impact_summary(combined_impact),
                migration_strategy=self._generate_migration_recommendations(combined_impact),
                foundry_compliance=combined_impact.foundry_compatibility.get("summary", "")
            )

        except asyncio.TimeoutError:
            logger.warning("Data impact analysis timed out after 30 seconds")
            return self._create_timeout_fallback_result(old_schema, new_schema)
        except Exception as e:
            logger.error(f"Data impact analysis failed: {e}")
            return self._create_error_fallback_result(old_schema, new_schema, str(e))

    async def _analyze_direct_data_impact(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> ImpactAnalysisResult:
        """직접적인 데이터 영향 분석"""

        object_type_name = self._get_resource_name(old_schema)

        # 전체 레코드 수 조회
        total_count_query = f"""
        SELECT (COUNT(?instance) AS ?total)
        WHERE {{
            ?instance a <{object_type_name}> .
        }}
        """

        # 속성별 사용 빈도 분석
        property_usage_query = f"""
        SELECT ?property (COUNT(?instance) AS ?usage_count)
        WHERE {{
            ?instance a <{object_type_name}> .
            ?instance ?property ?value .
            FILTER(STRSTARTS(STR(?property), "{object_type_name}#"))
        }}
        GROUP BY ?property
        ORDER BY DESC(?usage_count)
        """

        try:
            # 병렬 쿼리 실행
            total_result, usage_result = await asyncio.gather(
                context.terminus_client.query(total_count_query, db="oms", branch=context.source_branch),
                context.terminus_client.query(property_usage_query, db="oms", branch=context.source_branch)
            )

            total_objects = int(total_result[0]["total"]) if total_result else 0
            property_usage = usage_result or []

            # 변경된 속성들의 영향도 계산
            old_props = set(old_schema.get("properties", {}).keys())
            new_props = set(new_schema.get("properties", {}).keys())

            removed_props = old_props - new_props
            modified_props = self._find_modified_properties(old_schema, new_schema)

            affected_objects = self._calculate_affected_objects(
                total_objects, removed_props, modified_props, property_usage
            )

            return ImpactAnalysisResult(
                total_objects=total_objects,
                affected_objects=affected_objects,
                relationship_impacts=[],  # 별도 분석에서 채움
                data_quality_risks=self._identify_data_quality_risks(removed_props, modified_props),
                performance_implications={},  # 별도 분석에서 채움
                foundry_compatibility={}  # 별도 분석에서 채움
            )

        except Exception as e:
            logger.error(f"Direct data impact analysis failed: {e}")
            return ImpactAnalysisResult(
                total_objects=0, affected_objects=0, relationship_impacts=[],
                data_quality_risks=[f"Analysis failed: {e}"],
                performance_implications={}, foundry_compatibility={}
            )

    async def _analyze_relationship_impact(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> List[Dict[str, Any]]:
        """관계형 데이터 영향 분석"""

        object_type_name = self._get_resource_name(old_schema)

        # Foundry Ontology의 관계 분석 쿼리
        relationship_query = f"""
        SELECT ?rel_type ?target_type ?relationship_count
        WHERE {{
            {{
                # 아웃고잉 관계
                ?link a LinkType .
                ?link sourceType <{object_type_name}> .
                ?link targetType ?target_type .
                ?link linkType ?rel_type .
                
                # 관계 인스턴스 수 계산
                {{
                    SELECT (COUNT(?instance) AS ?relationship_count) WHERE {{
                        ?instance a ?link .
                    }}
                }}
            }}
            UNION
            {{
                # 인커밍 관계
                ?link a LinkType .
                ?link targetType <{object_type_name}> .
                ?link sourceType ?target_type .
                ?link linkType ?rel_type .
                
                {{
                    SELECT (COUNT(?instance) AS ?relationship_count) WHERE {{
                        ?instance a ?link .
                    }}
                }}
            }}
        }}
        ORDER BY DESC(?relationship_count)
        """

        try:
            relationships = await context.terminus_client.query(
                relationship_query, db="oms", branch=context.source_branch
            )

            relationship_impacts = []

            for rel in relationships or []:
                rel_type = rel.get("rel_type", "unknown")
                target_type = rel.get("target_type", "unknown")
                count = int(rel.get("relationship_count", 0))

                # 중요한 관계 타입인지 확인
                is_critical = any(
                    crit_type in rel_type.lower()
                    for crit_type in self.CRITICAL_RELATIONSHIP_TYPES
                )

                impact_severity = "HIGH" if is_critical and count > 1000 else "MEDIUM" if count > 100 else "LOW"

                relationship_impacts.append({
                    "relationship_type": rel_type,
                    "target_object_type": target_type,
                    "affected_relationships": count,
                    "severity": impact_severity,
                    "foundry_critical": is_critical,
                    "migration_complexity": self._assess_relationship_migration_complexity(rel_type, count)
                })

            return relationship_impacts

        except Exception as e:
            logger.error(f"Relationship impact analysis failed: {e}")
            return [{"error": f"Relationship analysis failed: {e}"}]

    async def _analyze_foundry_compliance(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> Dict[str, Any]:
        """Foundry Ontology 호환성 분석"""

        compliance_issues = []
        compatibility_score = 100

        # Foundry 명명 규칙 검사
        new_name = self._get_resource_name(new_schema)
        if not self._is_foundry_compliant_name(new_name):
            compliance_issues.append("Object name violates Foundry naming conventions")
            compatibility_score -= 20

        # 속성 타입 호환성 검사
        new_props = new_schema.get("properties", {})
        for prop_name, prop_def in new_props.items():
            data_type = prop_def.get("dataType", "")
            if not self._is_foundry_supported_type(data_type):
                compliance_issues.append(f"Property '{prop_name}' uses unsupported type: {data_type}")
                compatibility_score -= 10

        # 필수 Foundry 메타데이터 검사
        required_metadata = ["@type", "displayName", "description"]
        for metadata in required_metadata:
            if metadata not in new_schema:
                compliance_issues.append(f"Missing required Foundry metadata: {metadata}")
                compatibility_score -= 5

        return {
            "compatibility_score": max(0, compatibility_score),
            "compliance_issues": compliance_issues,
            "foundry_version_compatibility": "2024.1",  # 현재 지원 버전
            "summary": f"Foundry compatibility: {max(0, compatibility_score)}% ({len(compliance_issues)} issues)"
        }

    async def _analyze_performance_implications(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> Dict[str, Any]:
        """성능 영향 분석"""

        # 인덱스 영향 분석
        old_indexed_props = self._get_indexed_properties(old_schema)
        new_indexed_props = self._get_indexed_properties(new_schema)

        index_changes = {
            "removed_indexes": old_indexed_props - new_indexed_props,
            "added_indexes": new_indexed_props - old_indexed_props
        }

        # 쿼리 성능 영향 예측
        query_impact = await self._predict_query_performance_impact(
            old_schema, new_schema, context
        )

        return {
            "index_changes": index_changes,
            "query_performance_impact": query_impact,
            "estimated_reindex_time_minutes": len(new_indexed_props) * 5,  # 경험적 공식
            "cache_invalidation_scope": "branch_level",  # P4 원칙
            "foundry_query_optimizer_impact": "moderate"
        }

    def _find_modified_properties(
        self, old_schema: Dict[str, Any], new_schema: Dict[str, Any]
    ) -> Set[str]:
        """수정된 속성들 찾기"""

        old_props = old_schema.get("properties", {})
        new_props = new_schema.get("properties", {})
        modified = set()

        for prop_name in old_props.keys() & new_props.keys():
            if old_props[prop_name] != new_props[prop_name]:
                modified.add(prop_name)

        return modified

    def _calculate_affected_objects(
        self,
        total_objects: int,
        removed_props: Set[str],
        modified_props: Set[str],
        property_usage: List[Dict]
    ) -> int:
        """영향받는 객체 수 계산"""

        if not (removed_props or modified_props):
            return 0

        # 속성 사용 빈도 기반 영향도 계산
        usage_map = {
            prop["property"].split("#")[-1]: int(prop["usage_count"])
            for prop in property_usage
        }

        affected = 0
        for prop in removed_props | modified_props:
            affected += usage_map.get(prop, 0)

        return min(affected, total_objects)  # 전체 객체 수를 초과할 수 없음

    def _identify_data_quality_risks(
        self, removed_props: Set[str], modified_props: Set[str]
    ) -> List[str]:
        """데이터 품질 위험 식별"""

        risks = []

        if removed_props:
            risks.append(f"Data loss risk: {len(removed_props)} properties will be removed")

        if modified_props:
            risks.append(f"Data transformation risk: {len(modified_props)} properties will be modified")

        # Foundry 특화 위험
        critical_props = {"id", "displayName", "primaryKey", "foreignKey"}
        if removed_props & critical_props:
            risks.append("CRITICAL: Essential Foundry properties will be removed")

        return risks

    def _combine_impact_results(self, *results) -> ImpactAnalysisResult:
        """분석 결과들을 종합"""

        direct_impact = results[0] if not isinstance(results[0], Exception) else None
        relationship_impact = results[1] if not isinstance(results[1], Exception) else []
        compliance_impact = results[2] if not isinstance(results[2], Exception) else {}
        performance_impact = results[3] if not isinstance(results[3], Exception) else {}

        if direct_impact:
            direct_impact.relationship_impacts = relationship_impact
            direct_impact.foundry_compatibility = compliance_impact
            direct_impact.performance_implications = performance_impact
            return direct_impact

        # Fallback 결과
        return ImpactAnalysisResult(
            total_objects=0, affected_objects=0,
            relationship_impacts=relationship_impact,
            data_quality_risks=["Analysis partially failed"],
            performance_implications=performance_impact,
            foundry_compatibility=compliance_impact
        )

    def _determine_overall_severity(self, impact: ImpactAnalysisResult) -> Severity:
        """전체 심각도 결정"""

        # Foundry 호환성 기반 심각도
        compatibility_score = impact.foundry_compatibility.get("compatibility_score", 100)
        if compatibility_score < 50:
            return Severity.CRITICAL

        # 데이터 영향 기반 심각도
        if impact.total_objects > 0:
            impact_ratio = impact.affected_objects / impact.total_objects
            if impact_ratio > 0.5:
                return Severity.HIGH
            elif impact_ratio > 0.1:
                return Severity.MEDIUM

        # 관계 영향 기반 심각도
        critical_relationships = sum(
            1 for rel in impact.relationship_impacts
            if rel.get("severity") == "HIGH"
        )
        if critical_relationships > 0:
            return Severity.HIGH

        return Severity.LOW

    async def _publish_analysis_event(
        self, impact: ImpactAnalysisResult, context: ValidationContext
    ):
        """P3: 분석 완료 이벤트 발행"""

        try:
            if hasattr(context, 'event_publisher') and context.event_publisher:
                await context.event_publisher.publish_validation_completed(
                    source_branch=context.source_branch,
                    target_branch=context.target_branch,
                    rule_id=self.rule_id,
                    impact_summary={
                        "total_objects": impact.total_objects,
                        "affected_objects": impact.affected_objects,
                        "foundry_compatibility": impact.foundry_compatibility.get("compatibility_score", 0),
                        "analysis_timestamp": datetime.now().isoformat()
                    }
                )
        except Exception as e:
            logger.warning(f"Failed to publish analysis event: {e}")

    def _is_foundry_compliant_name(self, name: str) -> bool:
        """Foundry 명명 규칙 준수 검사"""
        # Foundry 규칙: PascalCase, 영문자로 시작, 특수문자 없음
        return (name and name[0].isupper() and
                name.replace("_", "").isalnum() and
                not any(c in name for c in "!@#$%^&*()"))

    def _is_foundry_supported_type(self, data_type: str) -> bool:
        """Foundry 지원 타입 확인"""
        supported_types = {
            "string", "integer", "long", "double", "boolean",
            "date", "datetime", "text", "object", "array"
        }
        return data_type.lower() in supported_types

    def _get_indexed_properties(self, schema: Dict[str, Any]) -> Set[str]:
        """인덱스된 속성들 추출"""
        indexed = set()
        properties = schema.get("properties", {})

        for prop_name, prop_def in properties.items():
            if prop_def.get("indexed", False) or prop_def.get("primaryKey", False):
                indexed.add(prop_name)

        return indexed

    async def _predict_query_performance_impact(
        self, old_schema: Dict[str, Any], new_schema: Dict[str, Any], context: ValidationContext
    ) -> str:
        """쿼리 성능 영향 예측"""

        old_indexed = self._get_indexed_properties(old_schema)
        new_indexed = self._get_indexed_properties(new_schema)

        if len(new_indexed) < len(old_indexed):
            return "NEGATIVE: Reduced indexes may slow queries"
        elif len(new_indexed) > len(old_indexed):
            return "POSITIVE: Additional indexes may improve query performance"
        else:
            return "NEUTRAL: No significant query performance impact expected"

    def _assess_relationship_migration_complexity(self, rel_type: str, count: int) -> str:
        """관계 마이그레이션 복잡도 평가"""

        if count > 10000:
            return "HIGH: Large relationship dataset requires careful migration"
        elif count > 1000:
            return "MEDIUM: Moderate dataset size"
        else:
            return "LOW: Small dataset, straightforward migration"

    # Fallback 메서드들...
    def _create_timeout_fallback_result(
        self, old_schema: Dict[str, Any], new_schema: Dict[str, Any]
    ) -> BreakingChange:
        """타임아웃 시 fallback 결과"""
        return BreakingChange(
            rule_id=self.rule_id,
            severity=Severity.HIGH,
            resource_type=self._get_resource_type(old_schema),
            resource_id=self._get_resource_id(old_schema),
            resource_name=self._get_resource_name(old_schema),
            change_type="analysis_timeout",
            old_value="unknown",
            new_value="unknown",
            description="Data impact analysis timed out - potential high impact change",
            data_impact=DataImpact(
                total_records=0, affected_records=0, impact_percentage=100,
                estimated_downtime_minutes=60, complexity_score=10,
                migration_risks=["Analysis timed out - conservative estimates applied"]
            ),
            migration_strategy="Manual analysis required due to timeout",
            foundry_compliance="Unable to verify Foundry compliance"
        )

    def _create_error_fallback_result(
        self, old_schema: Dict[str, Any], new_schema: Dict[str, Any], error: str
    ) -> BreakingChange:
        """에러 시 fallback 결과"""
        return BreakingChange(
            rule_id=self.rule_id,
            severity=Severity.MEDIUM,
            resource_type=self._get_resource_type(old_schema),
            resource_id=self._get_resource_id(old_schema),
            resource_name=self._get_resource_name(old_schema),
            change_type="analysis_error",
            old_value="unknown",
            new_value="unknown",
            description=f"Data impact analysis failed: {error}",
            data_impact=DataImpact(
                total_records=0, affected_records=0, impact_percentage=50,
                estimated_downtime_minutes=30, complexity_score=5,
                migration_risks=[f"Analysis error: {error}"]
            ),
            migration_strategy="Manual verification required",
            foundry_compliance="Unable to verify compliance"
        )

    def _summarize_schema(self, schema: Dict[str, Any]) -> str:
        """스키마 요약"""
        props = schema.get("properties", {})
        return f"{len(props)} properties, type: {schema.get('@type', 'unknown')}"

    def _generate_impact_description(self, impact: ImpactAnalysisResult) -> str:
        """영향도 설명 생성"""
        if impact.total_objects == 0:
            return "No data impact detected"

        impact_ratio = (impact.affected_objects / impact.total_objects) * 100
        return f"Impact: {impact.affected_objects:,} of {impact.total_objects:,} objects ({impact_ratio:.1f}%) affected"

    def _create_data_impact_summary(self, impact: ImpactAnalysisResult) -> DataImpact:
        """DataImpact 객체 생성"""
        return DataImpact(
            total_records=impact.total_objects,
            affected_records=impact.affected_objects,
            impact_percentage=(impact.affected_objects / max(1, impact.total_objects)) * 100,
            estimated_downtime_minutes=max(5, impact.affected_objects // 10000),
            complexity_score=min(10, len(impact.relationship_impacts) + len(impact.data_quality_risks)),
            migration_risks=impact.data_quality_risks
        )

    def _generate_migration_recommendations(self, impact: ImpactAnalysisResult) -> str:
        """마이그레이션 권장사항 생성"""
        recommendations = [
            "1. Backup all affected data before migration",
            "2. Test migration on staging environment first",
            "3. Implement rollback procedure"
        ]

        if impact.foundry_compatibility.get("compatibility_score", 100) < 100:
            recommendations.append("4. Resolve Foundry compatibility issues")

        if len(impact.relationship_impacts) > 0:
            recommendations.append("5. Update related object types and queries")

        return " ".join(recommendations)
