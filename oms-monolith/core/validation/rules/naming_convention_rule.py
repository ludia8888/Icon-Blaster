"""
Naming Convention Validation Rule
Breaking Change 검증 시 명명 규칙 위반 감지
"""
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple, Iterator

from core.validation.rules.base import BaseRule
from core.validation.models import (
    BreakingChange, RuleExecutionResult, Severity,
    ValidationContext, ValidationWarning
)
from core.validation.naming_convention import (
    EntityType, NamingConventionEngine, get_naming_engine
)
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class EntityConfig:
    """엔티티별 검증 설정"""
    entity_type: EntityType
    resource_type: str  # "ObjectType", "Property", "LinkType"
    
    # 스키마 접근 함수
    schema_accessor: Callable[[ValidationContext], Iterator[Tuple[str, Dict, Optional[str]]]]
    
    # ID 생성 함수 (entity_id, parent_id=None) -> change_id
    id_generator: Callable[[str, Optional[str]], str]
    
    # 리소스 ID 생성 함수
    resource_id_generator: Callable[[str, Optional[str]], str]
    
    # 기본 심각도
    default_severity: Severity = Severity.MEDIUM
    
    # 복잡도 계산 함수
    complexity_calculator: Optional[Callable[[bool, Any], str]] = None
    
    # 영향도 분석 함수
    impact_analyzer: Optional[Callable[[str, List], Optional[Dict]]] = None


class NamingConventionRule(BaseRule):
    """
    명명 규칙 Breaking Change 검증
    
    감지하는 Breaking Changes:
    1. 기존 명명 규칙을 위반하는 새 엔티티
    2. 명명 규칙 변경으로 인한 비호환성
    3. 예약어 충돌
    4. 자동 생성 코드와의 충돌 위험
    """
    
    def __init__(self, convention_id: Optional[str] = None):
        super().__init__(
            rule_id="naming-convention",
            name="Naming Convention Rule",
            description="Validates entity naming conventions and detects breaking changes"
        )
        self.engine = get_naming_engine()
        self.convention_id = convention_id or "default"
        
        # 엔티티별 설정 정의
        self.entity_configs = self._create_entity_configs()
    
    def _create_entity_configs(self) -> List[EntityConfig]:
        """엔티티별 검증 설정 생성"""
        return [
            # ObjectType 설정
            EntityConfig(
                entity_type=EntityType.OBJECT_TYPE,
                resource_type="ObjectType",
                schema_accessor=lambda ctx: (
                    (obj_id, obj_type, None) 
                    for obj_id, obj_type in ctx.target_schemas.get("object_types", {}).items()
                ),
                id_generator=lambda entity_id, parent_id: f"naming-{entity_id}",
                resource_id_generator=lambda entity_id, parent_id: entity_id,
                default_severity=Severity.MEDIUM,
                complexity_calculator=lambda changed, result: "low" if result.suggestions else "medium"
            ),
            
            # Property 설정
            EntityConfig(
                entity_type=EntityType.PROPERTY,
                resource_type="Property",
                schema_accessor=lambda ctx: self._get_all_properties(ctx),
                id_generator=lambda entity_id, parent_id: f"naming-{parent_id}-{entity_id}",
                resource_id_generator=lambda entity_id, parent_id: f"{parent_id}.{entity_id}",
                default_severity=Severity.HIGH,  # API/SDK 영향으로 높은 심각도
                complexity_calculator=lambda changed, result: "high" if changed else "low",
                impact_analyzer=lambda name, issues: self._analyze_api_impact(name, issues)
            ),
            
            # LinkType 설정
            EntityConfig(
                entity_type=EntityType.LINK_TYPE,
                resource_type="LinkType",
                schema_accessor=lambda ctx: (
                    (link_id, link_type, None)
                    for link_id, link_type in ctx.target_schemas.get("link_types", {}).items()
                ),
                id_generator=lambda entity_id, parent_id: f"naming-{entity_id}",
                resource_id_generator=lambda entity_id, parent_id: entity_id,
                default_severity=Severity.MEDIUM,
                complexity_calculator=lambda changed, result: "low"
            )
        ]
    
    def _get_all_properties(self, context: ValidationContext) -> Iterator[Tuple[str, Dict, str]]:
        """모든 Property를 (prop_id, prop_data, obj_id) 형태로 반환"""
        for obj_id, obj_type in context.target_schemas.get("object_types", {}).items():
            for prop_id, prop in obj_type.get("properties", {}).items():
                yield prop_id, prop, obj_id
    
    async def execute(self, context: ValidationContext) -> RuleExecutionResult:
        """명명 규칙 검증 실행"""
        breaking_changes = []
        warnings = []
        
        try:
            # 모든 엔티티 타입에 대해 검증 (리팩터링된 방식)
            for config in self.entity_configs:
                breaking_changes.extend(
                    await self._check_entity_naming(context, config)
                )
            
            # 크로스 엔티티 충돌 검증
            warnings.extend(
                await self._check_cross_entity_conflicts(context)
            )
            
            return RuleExecutionResult(
                rule_id=self.rule_id,
                passed=len(breaking_changes) == 0,
                breaking_changes=breaking_changes,
                warnings=warnings,
                metadata={
                    "convention_id": self.convention_id,
                    "entities_checked": self._count_entities(context)
                }
            )
            
        except Exception as e:
            logger.error(f"Naming convention rule execution failed: {str(e)}")
            return RuleExecutionResult(
                rule_id=self.rule_id,
                passed=True,  # Fail open to not block on rule errors
                breaking_changes=[],
                warnings=[
                    ValidationWarning(
                        code="naming-rule-error",
                        message=f"Failed to validate naming conventions: {str(e)}",
                        severity=Severity.MEDIUM
                    )
                ]
            )
    
    async def _check_entity_naming(
        self,
        context: ValidationContext,
        config: EntityConfig
    ) -> List[BreakingChange]:
        """엔티티 명명 규칙 검증 (공통 로직)"""
        breaking_changes = []
        
        for entity_id, entity_data, parent_id in config.schema_accessor(context):
            # 변경 감지
            source_entity = self._get_source_entity(context, config, entity_id, parent_id)
            name_changed = self._detect_name_change(source_entity, entity_data)
            
            # 새 엔티티거나 이름이 변경된 경우만 검증
            if not source_entity or name_changed:
                name = entity_data.get("name", "")
                result = self.engine.validate(config.entity_type, name)
                
                if not result.is_valid:
                    breaking_change = self._create_breaking_change(
                        config, entity_id, entity_data, result,
                        source_entity, context, parent_id
                    )
                    breaking_changes.append(breaking_change)
        
        return breaking_changes
    
    def _get_source_entity(
        self,
        context: ValidationContext,
        config: EntityConfig,
        entity_id: str,
        parent_id: Optional[str] = None
    ) -> Optional[Dict]:
        """소스 스키마에서 엔티티 찾기"""
        if config.entity_type == EntityType.PROPERTY:
            # Property의 경우 ObjectType 안에서 찾기
            if parent_id:
                source_obj = context.source_schemas.get("object_types", {}).get(parent_id)
                if source_obj:
                    return source_obj.get("properties", {}).get(entity_id)
        elif config.entity_type == EntityType.OBJECT_TYPE:
            return context.source_schemas.get("object_types", {}).get(entity_id)
        elif config.entity_type == EntityType.LINK_TYPE:
            return context.source_schemas.get("link_types", {}).get(entity_id)
        
        return None
    
    def _detect_name_change(self, source_entity: Optional[Dict], target_entity: Dict) -> bool:
        """이름 변경 감지"""
        if not source_entity:
            return False
        return source_entity.get("name") != target_entity.get("name")
    
    def _create_breaking_change(
        self,
        config: EntityConfig,
        entity_id: str,
        entity_data: Dict,
        validation_result,
        source_entity: Optional[Dict],
        context: ValidationContext,
        parent_id: Optional[str] = None
    ) -> BreakingChange:
        """BreakingChange 객체 생성"""
        name = entity_data.get("name", "")
        
        # 심각도 결정
        severity = config.default_severity
        if config.impact_analyzer:
            api_impact = config.impact_analyzer(name, validation_result.issues)
            if api_impact:
                severity = Severity.HIGH
        else:
            severity = self._determine_severity(validation_result.issues)
        
        # 복잡도 계산
        is_name_changed = source_entity is not None
        if config.complexity_calculator:
            complexity = config.complexity_calculator(is_name_changed, validation_result)
        else:
            complexity = "medium" if is_name_changed else "low"
        
        # 영향받는 리소스 찾기
        affected_resources = self._find_affected_resources(
            entity_id, config.entity_type.value, context
        )
        
        # 세부 정보 구성
        details = {
            "issues": [
                {
                    "rule": issue.rule_violated,
                    "message": issue.message,
                    "suggestion": issue.suggestion
                }
                for issue in validation_result.issues
            ],
            "auto_fix_available": bool(validation_result.suggestions),
            "suggested_name": validation_result.suggestions.get(name)
        }
        
        # 이전 이름 정보 추가
        if source_entity:
            details["previous_name"] = source_entity.get("name")
            details["name_change_type"] = "rename"
        
        # 특별한 세부정보 추가
        if config.entity_type == EntityType.PROPERTY and parent_id:
            obj_type = context.target_schemas.get("object_types", {}).get(parent_id, {})
            details["object_type"] = obj_type.get("name")
        elif config.entity_type == EntityType.LINK_TYPE:
            details["from_type"] = entity_data.get("from_type_id")
            details["to_type"] = entity_data.get("to_type_id")
        
        # API 영향도 추가
        if config.impact_analyzer:
            api_impact = config.impact_analyzer(name, validation_result.issues)
            if api_impact:
                details["api_impact"] = api_impact
        
        return BreakingChange(
            change_id=config.id_generator(entity_id, parent_id),
            resource_type=config.resource_type,
            resource_id=config.resource_id_generator(entity_id, parent_id),
            change_type="naming-violation",
            severity=severity,
            description=self._format_description(name, source_entity, config.resource_type),
            affected_resources=affected_resources,
            migration_required=True,
            migration_complexity=complexity,
            details=details
        )
    
    def _format_description(self, name: str, source_entity: Optional[Dict], resource_type: str) -> str:
        """설명 메시지 포맷팅"""
        if source_entity:
            previous_name = source_entity.get("name", "unknown")
            return f"{resource_type} renamed from '{previous_name}' to '{name}' violates naming convention"
        else:
            return f"{resource_type} '{name}' violates naming convention"
    
# 기존의 중복된 메서드들이 _check_entity_naming()으로 통합되었음
    
    async def _check_cross_entity_conflicts(
        self,
        context: ValidationContext
    ) -> List[ValidationWarning]:
        """크로스 엔티티 명명 충돌 검증"""
        warnings = []
        
        # 모든 엔티티 이름 수집
        all_names = set()
        duplicates = set()
        name_to_entities = {}  # 이름별 엔티티 추적
        
        # ObjectType 이름
        for obj_id, obj in context.target_schemas.get("object_types", {}).items():
            name = obj.get("name", "")
            normalized_name = self.engine.normalize(name)
            
            if normalized_name in all_names:
                duplicates.add(normalized_name)
                # 중복된 엔티티들 기록
                if normalized_name not in name_to_entities:
                    name_to_entities[normalized_name] = []
                name_to_entities[normalized_name].append(f"ObjectType:{obj_id}")
            else:
                all_names.add(normalized_name)
                name_to_entities[normalized_name] = [f"ObjectType:{obj_id}"]
        
        # LinkType 이름도 중복 체크에 포함
        for link_id, link in context.target_schemas.get("link_types", {}).items():
            name = link.get("name", "")
            normalized_name = self.engine.normalize(name)
            
            if normalized_name in all_names:
                duplicates.add(normalized_name)
                if normalized_name not in name_to_entities:
                    name_to_entities[normalized_name] = []
                name_to_entities[normalized_name].append(f"LinkType:{link_id}")
            else:
                all_names.add(normalized_name)
                name_to_entities[normalized_name] = [f"LinkType:{link_id}"]
        
        # Property 이름 (글로벌 충돌 체크)
        property_names = set()
        for obj_id, obj in context.target_schemas.get("object_types", {}).items():
            for prop_id, prop in obj.get("properties", {}).items():
                name = prop.get("name", "")
                normalized_name = self.engine.normalize(name)
                property_names.add(normalized_name)
                
                # Property도 엔티티 충돌 체크에 포함 (옵션)
                if normalized_name in all_names:
                    duplicates.add(normalized_name)
                    if normalized_name not in name_to_entities:
                        name_to_entities[normalized_name] = []
                    name_to_entities[normalized_name].append(f"Property:{obj_id}.{prop_id}")
        
        # 예약어와 충돌 검증
        # normalize된 예약어 목록 생성
        normalized_reserved_words = {
            self.engine.normalize(word) 
            for word in self.engine.convention.reserved_words
        }
        reserved_conflicts = all_names.intersection(normalized_reserved_words)
        
        if reserved_conflicts:
            warnings.append(
                ValidationWarning(
                    code="reserved-word-conflict",
                    message=f"Entity names conflict with reserved words: {', '.join(reserved_conflicts)}",
                    severity=Severity.HIGH,
                    details={
                        "conflicts": list(reserved_conflicts)
                    }
                )
            )
        
        # 중복 이름 경고
        if duplicates:
            # 중복된 엔티티 정보 수집
            duplicate_details = {}
            for dup_name in duplicates:
                if dup_name in name_to_entities:
                    duplicate_details[dup_name] = name_to_entities[dup_name]
            
            case_mode = "case-sensitive" if self.engine.convention.case_sensitive else "case-insensitive"
            warnings.append(
                ValidationWarning(
                    code="duplicate-names",
                    message=f"Duplicate entity names found ({case_mode}): {', '.join(duplicates)}",
                    severity=Severity.MEDIUM,
                    details={
                        "duplicates": list(duplicates),
                        "entities": duplicate_details,
                        "case_sensitive": self.engine.convention.case_sensitive
                    }
                )
            )
        
        # 공통 프로퍼티 이름 패턴 검증
        common_properties = {"id", "name", "type", "created", "updated"}
        non_standard_common = property_names - common_properties
        if len(non_standard_common) > 50:  # 너무 많은 고유 프로퍼티명
            warnings.append(
                ValidationWarning(
                    code="property-naming-inconsistency",
                    message="High number of unique property names may indicate naming inconsistency",
                    severity=Severity.LOW,
                    details={
                        "unique_property_count": len(non_standard_common)
                    }
                )
            )
        
        return warnings
    
    def _determine_severity(self, issues) -> Severity:
        """명명 규칙 위반의 심각도 결정"""
        # 예약어 충돌이나 패턴 위반은 HIGH
        for issue in issues:
            if issue.rule_violated in ["reserved_word", "pattern", "custom_regex"]:
                return Severity.HIGH
        
        # 필수 접두사/접미사 누락은 MEDIUM
        for issue in issues:
            if "required" in issue.rule_violated:
                return Severity.MEDIUM
        
        return Severity.LOW
    
    def _find_affected_resources(
        self,
        entity_id: str,
        entity_type: str,
        context: ValidationContext
    ) -> List[str]:
        """명명 규칙 변경으로 영향받는 리소스 찾기"""
        affected = []
        
        # 자동 생성되는 코드/API에 영향
        affected.append(f"api:/{entity_type}/{entity_id}")
        affected.append(f"sdk:{entity_type}.{entity_id}")
        
        # GraphQL 스키마에 영향
        affected.append(f"graphql:{entity_type}")
        
        return affected
    
    def _analyze_api_impact(self, name: str, issues) -> Optional[Dict[str, Any]]:
        """API/SDK 생성에 미치는 영향 분석"""
        impacts = []
        
        for issue in issues:
            if issue.rule_violated == "pattern":
                impacts.append({
                    "type": "method_naming",
                    "description": "Generated SDK methods may not follow language conventions"
                })
            elif issue.rule_violated == "reserved_word":
                impacts.append({
                    "type": "keyword_conflict",
                    "description": f"'{name}' conflicts with programming language keywords"
                })
            elif "-" in name or " " in name:
                impacts.append({
                    "type": "invalid_identifier",
                    "description": "Name contains characters invalid in most programming languages"
                })
        
        return {"impacts": impacts} if impacts else None
    
    def _count_entities(self, context: ValidationContext) -> Dict[str, int]:
        """검증한 엔티티 수 집계"""
        return {
            "object_types": len(context.target_schemas.get("object_types", {})),
            "properties": sum(
                len(obj.get("properties", {}))
                for obj in context.target_schemas.get("object_types", {}).values()
            ),
            "link_types": len(context.target_schemas.get("link_types", {}))
        }