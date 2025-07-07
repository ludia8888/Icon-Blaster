"""
Type Incompatibility Detection Rule
ADR-004의 TypeIncompatibilityRule 구현
Foundry OMS 핵심 원칙: Domain-driven, Cache-first, Event-driven
"""
import logging
from typing import Any, Dict, List, Optional

from core.validation.models import (
    BreakingChange,
    DataImpact,
    Severity,
    ValidationContext,
)
from core.validation.rules.base import BreakingChangeRule

logger = logging.getLogger(__name__)


class TypeIncompatibilityRule(BreakingChangeRule):
    """
    데이터 타입 비호환성 감지 규칙
    
    Foundry Ontology의 타입 시스템에서 허용되지 않는 
    타입 변경을 감지하고 데이터 영향도를 분석합니다.
    """

    # Foundry 호환 타입 매트릭스 (ADR-004 기반)
    COMPATIBLE_TYPE_MAPPINGS = {
        "string": {"string", "text"},
        "integer": {"integer", "long", "double"},  # 상위 타입으로 안전한 변환
        "long": {"long", "double"},
        "double": {"double"},
        "boolean": {"boolean"},
        "date": {"date", "datetime"},  # date -> datetime 안전
        "datetime": {"datetime"},
        "text": {"text"},  # text는 가장 제한적
        "object": {"object"},  # object 타입은 구조 변경 불가
    }

    # 손실 가능한 변환 (경고 수준)
    LOSSY_CONVERSIONS = {
        ("double", "integer"): "Precision loss in numeric conversion",
        ("double", "long"): "Precision loss in numeric conversion",
        ("datetime", "date"): "Time information loss",
        ("text", "string"): "Text truncation possible",
    }

    @property
    def rule_id(self) -> str:
        return "type_incompatibility"

    @property
    def severity(self) -> Severity:
        return Severity.CRITICAL

    @property
    def description(self) -> str:
        return "Detects incompatible data type changes that could cause data corruption"

    async def check(
        self,
        old_schema: Dict[str, Any],
        new_schema: Dict[str, Any],
        context: ValidationContext
    ) -> Optional[BreakingChange]:
        """
        타입 비호환성 검사 - Foundry Ontology 타입 시스템 준수
        
        P4 Cache-First: 분석 결과를 캐시하여 성능 최적화
        """

        # 캐시 키 생성 (P4 원칙)
        cache_key = f"type_compat:{context.source_branch}:{context.target_branch}:{self._get_resource_id(old_schema)}"

        # 캐시된 결과 확인
        if hasattr(context, 'cache') and context.cache:
            cached_result = await context.cache.get(cache_key)
            if cached_result:
                return cached_result

        breaking_changes = []

        # ObjectType의 속성들 비교
        old_properties = old_schema.get("properties", {})
        new_properties = new_schema.get("properties", {})

        # 공통 속성에 대한 타입 호환성 검사
        for prop_name in old_properties.keys() & new_properties.keys():
            old_prop = old_properties[prop_name]
            new_prop = new_properties[prop_name]

            old_type = old_prop.get("dataType", "unknown")
            new_type = new_prop.get("dataType", "unknown")

            if old_type != new_type:
                compatibility_result = await self._check_type_compatibility(
                    prop_name, old_type, new_type, old_schema, context
                )

                if compatibility_result:
                    breaking_changes.append(compatibility_result)

        # 가장 심각한 변경사항 반환
        if breaking_changes:
            # Severity 우선순위로 정렬
            breaking_changes.sort(key=lambda x: self._severity_priority(x.severity), reverse=True)
            result = breaking_changes[0]

            # 결과 캐싱 (P4 원칙)
            if hasattr(context, 'cache') and context.cache:
                await context.cache.set(cache_key, result, ttl=3600)  # 1시간 캐시

            return result

        return None

    async def _check_type_compatibility(
        self,
        property_name: str,
        old_type: str,
        new_type: str,
        schema: Dict[str, Any],
        context: ValidationContext
    ) -> Optional[BreakingChange]:
        """
        개별 속성의 타입 호환성 검사
        """

        # 호환 가능한 변환인지 확인
        compatible_types = self.COMPATIBLE_TYPE_MAPPINGS.get(old_type, {old_type})

        if new_type not in compatible_types:
            # 완전히 비호환인 경우
            data_impact = await self._analyze_data_impact(
                schema, property_name, old_type, new_type, context
            )

            return BreakingChange(
                rule_id=self.rule_id,
                severity=Severity.CRITICAL,
                resource_type="ObjectType",
                resource_id=self._get_resource_id(schema),
                resource_name=self._get_resource_name(schema),
                change_type="type_incompatibility",
                old_value=old_type,
                new_value=new_type,
                description=f"Property '{property_name}' type change from {old_type} to {new_type} is incompatible",
                data_impact=data_impact,
                migration_strategy=self._generate_migration_strategy(old_type, new_type),
                foundry_compliance="Violates Foundry Ontology type system constraints"
            )

        # 손실 가능한 변환 체크
        conversion_key = (old_type, new_type)
        if conversion_key in self.LOSSY_CONVERSIONS:
            data_impact = await self._analyze_data_impact(
                schema, property_name, old_type, new_type, context
            )

            return BreakingChange(
                rule_id=self.rule_id,
                severity=Severity.HIGH,
                resource_type="ObjectType",
                resource_id=self._get_resource_id(schema),
                resource_name=self._get_resource_name(schema),
                change_type="lossy_type_conversion",
                old_value=old_type,
                new_value=new_type,
                description=f"Property '{property_name}' type conversion may cause data loss: {self.LOSSY_CONVERSIONS[conversion_key]}",
                data_impact=data_impact,
                migration_strategy=self._generate_migration_strategy(old_type, new_type),
                foundry_compliance="Foundry recommends data validation before lossy conversions"
            )

        return None

    async def _analyze_data_impact(
        self,
        schema: Dict[str, Any],
        property_name: str,
        old_type: str,
        new_type: str,
        context: ValidationContext
    ) -> DataImpact:
        """
        데이터 영향도 분석 - UC-02 요구사항 구현
        
        Foundry Ontology의 실제 데이터를 분석하여 
        타입 변경이 미치는 영향을 정량화합니다.
        """

        try:
            object_type_name = self._get_resource_name(schema)

            # TerminusDB 쿼리로 영향받는 레코드 수 계산
            count_query = f"""
            SELECT (COUNT(?instance) AS ?totalCount)
            WHERE {{
                ?instance a <{object_type_name}> .
                ?instance <{property_name}> ?value .
            }}
            """

            # 샘플링 쿼리 (대용량 데이터셋 대응)
            sample_query = f"""
            SELECT ?instance ?value
            WHERE {{
                ?instance a <{object_type_name}> .
                ?instance <{property_name}> ?value .
            }}
            LIMIT 1000
            """

            # 병렬로 쿼리 실행 (성능 최적화)
            total_count = 0
            sample_data = []

            if hasattr(context, 'terminus_client'):
                count_result = await context.terminus_client.query(
                    count_query, db="oms", branch=context.source_branch
                )
                if count_result:
                    total_count = int(count_result[0].get("totalCount", 0))

                sample_result = await context.terminus_client.query(
                    sample_query, db="oms", branch=context.source_branch
                )
                sample_data = sample_result or []

            # 변환 실패 예상 비율 계산
            conversion_failure_rate = self._estimate_conversion_failures(
                sample_data, old_type, new_type
            )

            affected_records = int(total_count * conversion_failure_rate)

            return DataImpact(
                total_records=total_count,
                affected_records=affected_records,
                impact_percentage=conversion_failure_rate * 100,
                estimated_downtime_minutes=self._estimate_migration_downtime(total_count),
                complexity_score=self._calculate_complexity_score(old_type, new_type, total_count),
                migration_risks=[
                    f"Data loss risk: {conversion_failure_rate:.1%}",
                    f"Conversion errors: ~{affected_records:,} records",
                    "Foundry Ontology constraints may be violated"
                ]
            )

        except Exception as e:
            logger.error(f"Data impact analysis failed: {e}")
            # 보수적 추정치 반환
            return DataImpact(
                total_records=0,
                affected_records=0,
                impact_percentage=100,  # 보수적 추정
                estimated_downtime_minutes=60,
                complexity_score=10,
                migration_risks=["Unable to analyze data impact", str(e)]
            )

    def _estimate_conversion_failures(
        self, sample_data: List[Dict], old_type: str, new_type: str
    ) -> float:
        """샘플 데이터 기반 변환 실패율 추정"""

        if not sample_data:
            return 1.0  # 보수적 추정

        failure_count = 0

        for record in sample_data:
            value = record.get("value")
            if not self._can_convert_value(value, old_type, new_type):
                failure_count += 1

        return failure_count / len(sample_data) if sample_data else 1.0

    def _can_convert_value(self, value: Any, old_type: str, new_type: str) -> bool:
        """개별 값의 변환 가능성 검사"""

        if value is None:
            return True  # null 값은 항상 변환 가능

        try:
            # 실제 변환 시도
            if new_type == "integer":
                int(value)
            elif new_type == "double":
                float(value)
            elif new_type == "boolean":
                bool(value)
            elif new_type == "date":
                # 날짜 형식 검증 (간단한 버전)
                str(value)  # 실제로는 더 정교한 검증 필요

            return True

        except (ValueError, TypeError):
            return False

    def _estimate_migration_downtime(self, record_count: int) -> int:
        """마이그레이션 예상 다운타임 계산 (분 단위)"""

        # Foundry 환경에서의 경험적 공식
        # 10만 레코드당 약 1분 (배치 처리 기준)
        base_minutes = max(1, record_count // 100000)

        # 타입 변환 복잡도에 따른 가중치
        complexity_multiplier = 1.5  # 타입 변환은 복잡

        return int(base_minutes * complexity_multiplier)

    def _calculate_complexity_score(self, old_type: str, new_type: str, record_count: int) -> int:
        """마이그레이션 복잡도 점수 (1-10)"""

        base_score = 5

        # 타입별 복잡도
        type_complexity = {
            "object": 3,
            "text": 2,
            "string": 1,
            "datetime": 2,
            "date": 1,
            "double": 2,
            "integer": 1,
            "boolean": 1
        }

        old_complexity = type_complexity.get(old_type, 2)
        new_complexity = type_complexity.get(new_type, 2)

        # 레코드 수에 따른 복잡도
        volume_score = min(3, record_count // 1000000)  # 100만 레코드당 +1점

        total_score = base_score + old_complexity + new_complexity + volume_score

        return min(10, max(1, total_score))

    def _generate_migration_strategy(self, old_type: str, new_type: str) -> str:
        """Foundry 호환 마이그레이션 전략 생성"""

        strategies = {
            ("string", "integer"): "1. Validate numeric format 2. Handle non-numeric values 3. Batch convert with validation",
            ("integer", "string"): "1. Direct conversion (safe) 2. Update Foundry object type definition",
            ("date", "datetime"): "1. Append default time (00:00:00) 2. Update temporal queries",
            ("datetime", "date"): "1. Truncate time component 2. Verify no time-dependent logic",
        }

        key = (old_type, new_type)
        if key in strategies:
            return strategies[key]

        return "1. Backup data 2. Validate conversion logic 3. Implement rollback plan 4. Test with Foundry Ontology constraints"

    def _severity_priority(self, severity: Severity) -> int:
        """Severity 우선순위 매핑"""
        priority_map = {
            Severity.CRITICAL: 4,
            Severity.HIGH: 3,
            Severity.MEDIUM: 2,
            Severity.LOW: 1
        }
        return priority_map.get(severity, 0)
