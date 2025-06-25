"""
Validation Service 핵심 비즈니스 로직
UC-02: Breaking Change Detection 구현
섹션 8.3의 ValidationService 명세 완전 구현
"""
import asyncio
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List

from core.validation.models import (
    BreakingChange,
    ImpactEstimate,
    MigrationOptions,
    MigrationPlan,
    MigrationStep,
    RuleExecutionResult,
    Severity,
    ValidationContext,
    ValidationRequest,
    ValidationResult,
    ValidationWarning,
)
from core.validation.rules.data_impact_analyzer import DataImpactAnalyzer
from core.validation.rules.primary_key_change import PrimaryKeyChangeRule
from core.validation.rules.required_field import RequiredFieldRemovalRule
from core.validation.rules.shared_property import SharedPropertyChangeRule
from core.validation.rules.type_change import TypeCompatibilityRule
from core.validation.rules.type_incompatibility import TypeIncompatibilityRule
from shared.cache.smart_cache import SmartCacheManager
from database.clients.terminus_db import TerminusDBClient
from shared.events import EventPublisher

logger = logging.getLogger(__name__)


class ValidationService:
    """
    스키마 변경 검증 및 Breaking Change 감지 서비스
    UC-02: Breaking Change Detection 완전 구현
    """

    def __init__(
        self,
        tdb_client: TerminusDBClient,
        cache: SmartCacheManager,
        event_publisher: EventPublisher
    ):
        self.tdb = tdb_client
        self.cache = cache
        self.events = event_publisher

        # Breaking Change 검증 규칙들 초기화 (Foundry OMS 원칙 준수)
        self.rules = [
            # ADR-004 Core Breaking Change Rules
            PrimaryKeyChangeRule(),                    # P2: Domain boundary integrity
            RequiredFieldRemovalRule(),               # P2: Domain rule enforcement
            TypeIncompatibilityRule(),               # P4: Cache-first with type safety
            DataImpactAnalyzer(),                    # UC-02: Comprehensive impact analysis

            # Legacy compatibility rules
            TypeCompatibilityRule(),                 # Backwards compatibility
            SharedPropertyChangeRule()               # Cross-domain property changes
        ]

        logger.info(f"ValidationService initialized with {len(self.rules)} rules")

    async def validate_breaking_changes(
        self,
        request: ValidationRequest
    ) -> ValidationResult:
        """
        Breaking Change 검증 - UC-02 메인 API

        성능 요구사항: 30초 내 완료
        정확도 요구사항: Critical breaking changes 100% 정확도
        """
        start_time = time.time()
        validation_id = str(uuid.uuid4())

        logger.info(f"Starting validation {validation_id}: {request.source_branch} -> {request.target_branch}")

        try:
            # 1. 스키마 조회 및 캐싱
            context = await self._build_validation_context(request)

            # 2. Breaking Change 규칙 실행
            breaking_changes, warnings, rule_results = await self._execute_rules(context)

            # 3. 영향도 분석
            impact_analysis = None
            if request.include_impact_analysis:
                impact_analysis = await self._analyze_impact(breaking_changes, context)

            # 4. 마이그레이션 제안 생성
            suggested_migrations = await self._generate_migration_suggestions(breaking_changes)

            # 5. 성능 메트릭 수집
            execution_time = time.time() - start_time
            performance_metrics = {
                "execution_time_seconds": execution_time,
                "rule_count": len(self.rules),
                "schema_objects_analyzed": self._count_schema_objects(context)
            }

            # 6. 결과 구성
            result = ValidationResult(
                validation_id=validation_id,
                source_branch=request.source_branch,
                target_branch=request.target_branch,
                is_valid=len([bc for bc in breaking_changes if bc.severity in [Severity.CRITICAL, Severity.HIGH]]) == 0,
                breaking_changes=breaking_changes,
                warnings=warnings if request.include_warnings else [],
                impact_analysis=impact_analysis,
                suggested_migrations=suggested_migrations,
                performance_metrics=performance_metrics,
                validated_at=datetime.utcnow(),
                rule_execution_results=rule_results
            )

            # 7. 검증 완료 이벤트 발행
            await self._publish_validation_event(result)

            logger.info(f"Validation {validation_id} completed in {execution_time:.2f}s")
            logger.info(f"Found {len(breaking_changes)} breaking changes, {len(warnings)} warnings")

            return result

        except Exception as e:
            logger.error(f"Validation {validation_id} failed: {e}")
            raise

    async def _build_validation_context(self, request: ValidationRequest) -> ValidationContext:
        """검증 컨텍스트 구성"""

        # 캐시 키 생성
        # 스키마 조회 (TerminusDB 내부 캐싱 활용)
        source_schema = await self._fetch_branch_schema(request.source_branch)
        target_schema = await self._fetch_branch_schema(request.target_branch)

        return ValidationContext(
            source_branch=request.source_branch,
            target_branch=request.target_branch,
            source_schema=source_schema,
            target_schema=target_schema,
            terminus_client=self.tdb,
            event_publisher=self.events,
            metadata=request.options
        )

    async def _fetch_branch_schema(self, branch: str) -> Dict[str, Any]:
        """브랜치에서 전체 스키마 조회"""

        # ObjectType들 조회
        object_types_query = """
        SELECT ?objectType ?name ?displayName ?properties ?titleProperty ?status
        WHERE {
            ?objectType a ObjectType .
            ?objectType name ?name .
            OPTIONAL { ?objectType displayName ?displayName }
            OPTIONAL { ?objectType titleProperty ?titleProperty }
            OPTIONAL { ?objectType status ?status }
            OPTIONAL {
                SELECT ?objectType (ARRAY(?prop) AS ?properties)
                WHERE {
                    ?objectType properties ?prop
                }
                GROUP BY ?objectType
            }
        }
        """

        object_types_result = await self.tdb.query(
            object_types_query,
            db="oms",
            branch=branch
        )

        # 결과를 딕셔너리로 변환
        object_types = {}
        for obj in object_types_result:
            name = obj.get("name")
            if name:
                object_types[name] = {
                    "@type": "ObjectType",
                    "@id": obj.get("objectType"),
                    "name": name,
                    "displayName": obj.get("displayName", name),
                    "titleProperty": obj.get("titleProperty"),
                    "status": obj.get("status", "active"),
                    "properties": obj.get("properties", [])
                }

        # LinkType들 조회
        link_types_query = """
        SELECT ?linkType ?name ?sourceType ?targetType ?multiplicity
        WHERE {
            ?linkType a LinkType .
            ?linkType name ?name .
            OPTIONAL { ?linkType sourceType ?sourceType }
            OPTIONAL { ?linkType targetType ?targetType }
            OPTIONAL { ?linkType multiplicity ?multiplicity }
        }
        """

        link_types_result = await self.tdb.query(
            link_types_query,
            db="oms",
            branch=branch
        )

        link_types = {}
        for link in link_types_result:
            name = link.get("name")
            if name:
                link_types[name] = {
                    "@type": "LinkType",
                    "@id": link.get("linkType"),
                    "name": name,
                    "sourceType": link.get("sourceType"),
                    "targetType": link.get("targetType"),
                    "multiplicity": link.get("multiplicity", "many-to-many")
                }

        return {
            "branch": branch,
            "object_types": object_types,
            "link_types": link_types,
            "timestamp": datetime.utcnow().isoformat()
        }

    async def _execute_rules(self, context: ValidationContext) -> tuple[List[BreakingChange], List[ValidationWarning], Dict[str, Any]]:
        """모든 Breaking Change 규칙 실행"""

        breaking_changes = []
        warnings = []
        rule_results = {}

        # 규칙들을 병렬로 실행하여 성능 최적화
        rule_tasks = []
        for rule in self.rules:
            if rule.enabled:
                task = asyncio.create_task(self._execute_single_rule(rule, context))
                rule_tasks.append((rule.rule_id, task))

        # 모든 규칙 실행 대기
        for rule_id, task in rule_tasks:
            try:
                start_time = time.time()
                rule_result = await task
                execution_time = (time.time() - start_time) * 1000  # ms

                breaking_changes.extend(rule_result.breaking_changes)
                warnings.extend(rule_result.warnings)

                rule_results[rule_id] = RuleExecutionResult(
                    rule_id=rule_id,
                    executed=True,
                    execution_time_ms=execution_time,
                    breaking_changes_found=len(rule_result.breaking_changes),
                    warnings_found=len(rule_result.warnings)
                )

            except Exception as e:
                logger.error(f"Rule {rule_id} execution failed: {e}")
                rule_results[rule_id] = RuleExecutionResult(
                    rule_id=rule_id,
                    executed=False,
                    execution_time_ms=0,
                    breaking_changes_found=0,
                    warnings_found=0,
                    error=str(e)
                )

        return breaking_changes, warnings, rule_results

    async def _execute_single_rule(self, rule, context: ValidationContext):
        """단일 규칙 실행"""
        return await rule.evaluate(context)

    async def _analyze_impact(self, breaking_changes: List[BreakingChange], context: ValidationContext) -> Dict[str, Any]:
        """영향도 분석 - UC-02 요구사항"""

        total_affected_records = 0
        affected_services = set()
        affected_apis = set()

        for change in breaking_changes:
            # 각 변경사항에 대한 영향도 계산
            if change.resource_type == "ObjectType":
                # 해당 ObjectType의 레코드 수 조회
                count_query = f"""
                SELECT (COUNT(?instance) AS ?count)
                WHERE {{
                    ?instance a <{change.resource_name}> .
                }}
                """

                try:
                    count_result = await self.tdb.query(
                        count_query,
                        db="oms",
                        branch=context.source_branch
                    )

                    record_count = int(count_result[0]["count"]) if count_result else 0
                    total_affected_records += record_count

                    # 영향도 추정 업데이트
                    change.impact_estimate = ImpactEstimate(
                        affected_records=record_count,
                        estimated_duration_seconds=record_count * 0.001,  # 레코드당 1ms 추정
                        requires_downtime=change.severity == Severity.CRITICAL,
                        affected_services=["schema-service", "validation-service"],
                        affected_apis=[f"/api/v1/{change.resource_name.lower()}s"]
                    )

                    affected_services.update(change.impact_estimate.affected_services)
                    affected_apis.update(change.impact_estimate.affected_apis)

                except Exception as e:
                    logger.warning(f"Failed to analyze impact for {change.resource_name}: {e}")

        return {
            "total_affected_records": total_affected_records,
            "affected_services": list(affected_services),
            "affected_apis": list(affected_apis),
            "estimated_migration_duration_hours": total_affected_records * 0.001 / 3600,
            "requires_maintenance_window": any(
                bc.severity == Severity.CRITICAL for bc in breaking_changes
            ),
            "risk_level": self._calculate_risk_level(breaking_changes, total_affected_records)
        }

    def _calculate_risk_level(self, breaking_changes: List[BreakingChange], affected_records: int) -> str:
        """리스크 레벨 계산"""

        critical_count = sum(1 for bc in breaking_changes if bc.severity == Severity.CRITICAL)
        high_count = sum(1 for bc in breaking_changes if bc.severity == Severity.HIGH)

        if critical_count > 0 or affected_records > 1000000:
            return "CRITICAL"
        elif high_count > 0 or affected_records > 100000:
            return "HIGH"
        elif len(breaking_changes) > 0 or affected_records > 10000:
            return "MEDIUM"
        else:
            return "LOW"

    async def _generate_migration_suggestions(self, breaking_changes: List[BreakingChange]) -> List[str]:
        """마이그레이션 제안 생성"""

        suggestions = []

        for change in breaking_changes:
            if change.rule_id == "PRIMARY_KEY_CHANGE":
                suggestions.append(
                    f"Consider creating a mapping table for {change.resource_name} "
                    f"to preserve relationships during primary key migration"
                )
            elif change.rule_id == "REQUIRED_FIELD_REMOVAL":
                suggestions.append(
                    f"Archive existing data for removed field '{change.old_value}' "
                    f"in {change.resource_name} before removal"
                )
            elif change.rule_id == "TYPE_INCOMPATIBILITY":
                suggestions.append(
                    f"Create data transformation script for {change.resource_name}.{change.metadata.get('field_name')} "
                    f"from {change.old_value} to {change.new_value}"
                )

        return suggestions

    def _count_schema_objects(self, context: ValidationContext) -> Dict[str, int]:
        """스키마 객체 수 계산"""
        return {
            "object_types": len(context.source_schema.get("object_types", {})),
            "link_types": len(context.source_schema.get("link_types", {})),
            "total_properties": sum(
                len(obj.get("properties", []))
                for obj in context.source_schema.get("object_types", {}).values()
            )
        }

    async def _publish_validation_event(self, result: ValidationResult):
        """검증 완료 이벤트 발행"""

        event_data = {
            "validation_id": result.validation_id,
            "source_branch": result.source_branch,
            "target_branch": result.target_branch,
            "is_valid": result.is_valid,
            "breaking_changes_count": len(result.breaking_changes),
            "warnings_count": len(result.warnings),
            "execution_time": result.performance_metrics.get("execution_time_seconds"),
            "validated_at": result.validated_at.isoformat()
        }

        await self.events.publish(
            subject="validation.completed",
            event_type="ValidationCompleted",
            source="validation-service",
            data=event_data
        )

    async def create_migration_plan(
        self,
        breaking_changes: List[BreakingChange],
        target_branch: str,
        options: MigrationOptions
    ) -> MigrationPlan:
        """마이그레이션 계획 생성"""

        plan_id = str(uuid.uuid4())
        steps = []
        rollback_steps = []

        # 각 Breaking Change에 대한 마이그레이션 단계 생성
        for change in breaking_changes:
            if change.rule_id == "PRIMARY_KEY_CHANGE":
                # Primary Key 변경 마이그레이션
                steps.append(MigrationStep(
                    type="create_temp_collection",
                    description=f"Create temporary collection for {change.resource_name}",
                    estimated_duration=60.0,
                    requires_downtime=False
                ))

                steps.append(MigrationStep(
                    type="copy_with_transformation",
                    description=f"Copy data with new primary key for {change.resource_name}",
                    estimated_duration=change.impact_estimate.estimated_duration_seconds if change.impact_estimate else 300.0,
                    requires_downtime=True,
                    batch_size=options.batch_size
                ))

        total_duration = sum(step.estimated_duration for step in steps)
        requires_downtime = any(step.requires_downtime for step in steps)

        return MigrationPlan(
            id=plan_id,
            breaking_changes=breaking_changes,
            target_branch=target_branch,
            steps=steps,
            rollback_steps=rollback_steps,
            execution_order=[change.resource_name for change in breaking_changes],
            estimated_duration=total_duration,
            requires_downtime=requires_downtime,
            created_at=datetime.utcnow(),
            status="draft"
        )
