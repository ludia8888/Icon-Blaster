"""
Refactored Validation Service with Dependency Injection
순환 참조 해결을 위한 DI 패턴 적용
"""
import asyncio
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

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
from core.validation.ports import CachePort, TerminusPort, EventPort, ValidationContext as PortContext
from core.validation.rule_registry import RuleRegistry, load_rules
from core.validation.interfaces import BreakingChangeRule

logger = logging.getLogger(__name__)


class ValidationServiceRefactored:
    """
    리팩토링된 스키마 변경 검증 서비스
    의존성 주입과 동적 규칙 로딩으로 순환 참조 해결
    """

    def __init__(
        self,
        cache: CachePort,
        tdb: TerminusPort,
        events: EventPort,
        rule_registry: Optional[RuleRegistry] = None
    ):
        """
        생성자에서 직접 규칙을 import하지 않고 Port 인터페이스만 받음
        """
        self.cache = cache
        self.tdb = tdb
        self.events = events
        
        # 규칙 레지스트리 초기화 또는 주입
        if rule_registry:
            self.rule_registry = rule_registry
        else:
            self.rule_registry = RuleRegistry(cache=cache, tdb=tdb, event=events)
            
        # 규칙들을 동적으로 로드 (import 순환 방지)
        self.rules: List[BreakingChangeRule] = []
        self._load_rules()
        
        logger.info(f"ValidationService initialized with {len(self.rules)} rules")

    def _load_rules(self):
        """규칙을 동적으로 로드"""
        try:
            self.rules = self.rule_registry.load_rules_from_package()
            logger.info(f"Loaded {len(self.rules)} validation rules dynamically")
        except Exception as e:
            logger.error(f"Failed to load validation rules: {e}")
            self.rules = []

    async def validate_breaking_changes(
        self,
        request: ValidationRequest
    ) -> ValidationResult:
        """
        Breaking Change 검증 - UC-02 메인 API
        원본 서비스와 동일한 인터페이스 유지
        """
        start_time = time.time()
        validation_id = str(uuid.uuid4())

        logger.info(f"Starting validation {validation_id}: {request.source_branch} -> {request.target_branch}")

        try:
            # 1. 검증 컨텍스트 구성 (Port 사용)
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
            # rule_results를 딕셔너리로 변환
            rule_results_dict = {
                result.rule_id: {
                    "success": result.success,
                    "execution_time_ms": result.execution_time_ms,
                    "breaking_changes_found": result.breaking_changes_found,
                    "error": result.error
                }
                for result in rule_results
            }
            
            result = ValidationResult(
                validation_id=validation_id,
                source_branch=request.source_branch,
                target_branch=request.target_branch,
                is_valid=len([bc for bc in breaking_changes if bc.severity in [Severity.CRITICAL, Severity.HIGH]]) == 0,
                breaking_changes=breaking_changes,
                warnings=warnings if request.include_warnings else [],
                impact_analysis=impact_analysis,
                suggested_migrations=[],  # MigrationOptions 리스트여야 함
                performance_metrics=performance_metrics,
                validated_at=datetime.utcnow(),
                rule_execution_results=rule_results_dict
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
        """Port를 사용한 검증 컨텍스트 구성"""
        
        # 스키마 조회 (Port 인터페이스 사용)
        source_schema = await self._fetch_branch_schema(request.source_branch)
        target_schema = await self._fetch_branch_schema(request.target_branch)
        
        # Port Context 생성
        port_context = PortContext(
            source_branch=request.source_branch,
            target_branch=request.target_branch,
            cache=self.cache,
            terminus_client=self.tdb,
            event_publisher=self.events,
            metadata=request.options
        )

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
        """Port를 통한 브랜치 스키마 조회"""
        
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

        # Port 인터페이스를 통한 쿼리 실행
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
                    "properties": obj.get("properties", []),
                    "titleProperty": obj.get("titleProperty"),
                    "status": obj.get("status", "active")
                }

        return {"objectTypes": object_types}

    async def _execute_rules(self, context: ValidationContext) -> tuple:
        """동적으로 로드된 규칙 실행"""
        breaking_changes = []
        warnings = []
        rule_results = []

        # 병렬 실행을 위한 태스크 생성
        tasks = []
        for rule in self.rules:
            task = self._execute_single_rule(rule, context)
            tasks.append(task)

        # 모든 규칙 병렬 실행
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 결과 수집
        for i, result in enumerate(results):
            rule = self.rules[i]
            if isinstance(result, Exception):
                logger.error(f"Rule {rule.rule_id} failed: {result}")
                rule_results.append(RuleExecutionResult(
                    rule_id=rule.rule_id,
                    success=False,
                    error=str(result),
                    execution_time_ms=0
                ))
            else:
                changes, warns, exec_result = result
                breaking_changes.extend(changes)
                warnings.extend(warns)
                rule_results.append(exec_result)

        return breaking_changes, warnings, rule_results

    async def _execute_single_rule(
        self, 
        rule: BreakingChangeRule, 
        context: ValidationContext
    ) -> tuple:
        """단일 규칙 실행"""
        start_time = time.time()
        changes = []
        warnings = []

        try:
            # 규칙이 새로운 인터페이스를 사용하는지 확인
            if hasattr(rule, 'check'):
                # 컨텍스트 변환이 필요한 경우
                if hasattr(context, 'source_schema') and hasattr(context, 'target_schema'):
                    for obj_name, old_obj in context.source_schema.get("objectTypes", {}).items():
                        new_obj = context.target_schema.get("objectTypes", {}).get(obj_name)
                        if new_obj:
                            # Port Context 생성
                            port_context = PortContext(
                                source_branch=context.source_branch,
                                target_branch=context.target_branch,
                                cache=self.cache,
                                terminus_client=self.tdb,
                                event_publisher=self.events,
                                metadata=context.metadata
                            )
                            
                            result = await rule.check(old_obj, new_obj, port_context)
                            if result:
                                if isinstance(result, list):
                                    changes.extend(result)
                                else:
                                    changes.append(result)

            execution_time = (time.time() - start_time) * 1000

            return changes, warnings, RuleExecutionResult(
                rule_id=rule.rule_id,
                success=True,
                execution_time_ms=execution_time,
                breaking_changes_found=len(changes)
            )

        except Exception as e:
            logger.error(f"Error executing rule {rule.rule_id}: {e}")
            raise

    async def _analyze_impact(
        self, 
        breaking_changes: List[BreakingChange], 
        context: ValidationContext
    ) -> Dict[str, Any]:
        """영향도 분석"""
        # 간단한 구현 - 실제로는 더 복잡한 분석 필요
        return {
            "total_breaking_changes": len(breaking_changes),
            "critical_changes": len([bc for bc in breaking_changes if bc.severity == Severity.CRITICAL]),
            "estimated_migration_hours": len(breaking_changes) * 2
        }

    async def _generate_migration_suggestions(
        self, 
        breaking_changes: List[BreakingChange]
    ) -> List[MigrationOptions]:
        """마이그레이션 제안 생성"""
        suggestions = []
        
        for bc in breaking_changes:
            # 간단한 제안 생성 로직
            if bc.severity in [Severity.CRITICAL, Severity.HIGH]:
                suggestions.append(MigrationOptions(
                    breaking_change_id=bc.id,
                    options=["Manual migration required", "Contact administrator"],
                    recommended_option=0,
                    estimated_effort_hours=8
                ))
                
        return suggestions

    async def _publish_validation_event(self, result: ValidationResult):
        """Port를 통한 이벤트 발행"""
        if self.events:
            await self.events.publish(
                event_type="validation.completed",
                data={
                    "validation_id": result.validation_id,
                    "source_branch": result.source_branch,
                    "target_branch": result.target_branch,
                    "is_valid": result.is_valid,
                    "breaking_change_count": len(result.breaking_changes)
                }
            )

    def _count_schema_objects(self, context: ValidationContext) -> int:
        """스키마 객체 수 계산"""
        count = 0
        if hasattr(context, 'source_schema'):
            count += len(context.source_schema.get("objectTypes", {}))
        if hasattr(context, 'target_schema'):
            count += len(context.target_schema.get("objectTypes", {}))
        return count

    def add_rule(self, rule: BreakingChangeRule):
        """규칙 동적 추가"""
        self.rule_registry.register_rule(rule)
        self.rules = self.rule_registry.get_all_rules()
        
    def remove_rule(self, rule_id: str):
        """규칙 동적 제거"""
        self.rule_registry.unregister_rule(rule_id)
        self.rules = self.rule_registry.get_all_rules()
        
    def reload_rules(self):
        """모든 규칙 재로드"""
        self.rules = self.rule_registry.reload_rules()