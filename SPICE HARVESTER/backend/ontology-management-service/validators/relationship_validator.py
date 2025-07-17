"""
🔥 THINK ULTRA! RelationshipValidator
관계 무결성 검증 및 카디널리티 일관성 보장
"""

from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass
from enum import Enum
import logging
import re

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from models.ontology import Relationship, MultiLingualText, Cardinality, OntologyBase

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """검증 결과 심각도"""
    ERROR = "error"      # 생성/업데이트 차단
    WARNING = "warning"  # 경고만 표시
    INFO = "info"       # 정보성 메시지


@dataclass
class ValidationResult:
    """검증 결과"""
    severity: ValidationSeverity
    code: str
    message: str
    field: Optional[str] = None
    related_objects: Optional[List[str]] = None


class RelationshipValidator:
    """
    🔥 THINK ULTRA! 고급 관계 검증기
    
    기능:
    1. 카디널리티 일관성 검증
    2. 관계 무결성 검증  
    3. 타겟 클래스 존재 검증
    4. 역관계 일관성 검증
    5. 관계명 규칙 검증
    """
    
    def __init__(self, existing_ontologies: Optional[List[OntologyBase]] = None):
        self.existing_ontologies = existing_ontologies or []
        self.known_classes = {ont.id for ont in self.existing_ontologies}
        
        # 카디널리티 호환성 매트릭스
        self.cardinality_matrix = {
            ("1:1", "1:1"): True,   # 일대일 ↔ 일대일
            ("1:n", "n:1"): True,   # 일대다 ↔ 다대일  
            ("n:1", "1:n"): True,   # 다대일 ↔ 일대다
            ("n:n", "n:n"): True,   # 다대다 ↔ 다대다
            ("one", "many"): True,  # 단일 ↔ 다중
            ("many", "one"): True,  # 다중 ↔ 단일
        }
        
        # 허용되지 않는 카디널리티 조합
        self.invalid_combinations = {
            ("1:1", "1:n"), ("1:1", "n:1"), ("1:1", "n:n"),
            ("1:n", "1:1"), ("1:n", "1:n"), ("1:n", "n:n"),
            ("n:1", "1:1"), ("n:1", "n:1"), ("n:1", "n:n"),
            ("n:n", "1:1"), ("n:n", "1:n"), ("n:n", "n:1")
        }
    
    def validate_relationship(self, relationship: Relationship, source_class: str) -> List[ValidationResult]:
        """단일 관계 검증"""
        
        results = []
        
        # 기본 필드 검증
        results.extend(self._validate_basic_fields(relationship))
        
        # predicate 규칙 검증
        results.extend(self._validate_predicate(relationship.predicate))
        
        # 카디널리티 검증
        results.extend(self._validate_cardinality(relationship.cardinality))
        
        # 타겟 클래스 검증
        results.extend(self._validate_target_class(relationship.target))
        
        # 자기 참조 검증
        results.extend(self._validate_self_reference(relationship, source_class))
        
        # 레이블 검증
        results.extend(self._validate_labels(relationship))
        
        return results
    
    def validate_relationship_pair(
        self, 
        forward: Relationship, 
        inverse: Relationship,
        source_class: str,
        target_class: str
    ) -> List[ValidationResult]:
        """관계 쌍 검증 (정방향 + 역방향)"""
        
        results = []
        
        # 개별 관계 검증
        results.extend(self.validate_relationship(forward, source_class))
        results.extend(self.validate_relationship(inverse, target_class))
        
        # 카디널리티 일관성 검증
        results.extend(self._validate_cardinality_consistency(forward, inverse))
        
        # 상호 참조 검증  
        results.extend(self._validate_mutual_reference(forward, inverse))
        
        # 타겟 일관성 검증
        results.extend(self._validate_target_consistency(forward, inverse, source_class, target_class))
        
        return results
    
    def validate_ontology_relationships(self, ontology: OntologyBase) -> List[ValidationResult]:
        """온톨로지 전체 관계 검증"""
        
        results = []
        
        # 개별 관계 검증
        for rel in ontology.relationships:
            results.extend(self.validate_relationship(rel, ontology.id))
        
        # 관계 간 충돌 검증
        results.extend(self._validate_relationship_conflicts(ontology.relationships))
        
        # predicate 중복 검증
        results.extend(self._validate_predicate_uniqueness(ontology.relationships))
        
        # 관계 네트워크 검증
        results.extend(self._validate_relationship_network(ontology))
        
        return results
    
    def validate_multiple_ontologies(self, ontologies: List[OntologyBase]) -> List[ValidationResult]:
        """다중 온톨로지 간 관계 검증"""
        
        results = []
        
        # 각 온톨로지 개별 검증
        for ontology in ontologies:
            results.extend(self.validate_ontology_relationships(ontology))
        
        # 온톨로지 간 관계 검증
        results.extend(self._validate_cross_ontology_relationships(ontologies))
        
        # 전역 관계 일관성 검증
        results.extend(self._validate_global_relationship_consistency(ontologies))
        
        return results
    
    def _validate_basic_fields(self, relationship: Relationship) -> List[ValidationResult]:
        """기본 필드 검증"""
        
        results = []
        
        if not relationship.predicate:
            results.append(ValidationResult(
                severity=ValidationSeverity.ERROR,
                code="MISSING_PREDICATE",
                message="Relationship predicate is required",
                field="predicate"
            ))
        
        if not relationship.target:
            results.append(ValidationResult(
                severity=ValidationSeverity.ERROR,
                code="MISSING_TARGET", 
                message="Relationship target is required",
                field="target"
            ))
        
        if not relationship.label:
            results.append(ValidationResult(
                severity=ValidationSeverity.WARNING,
                code="MISSING_LABEL",
                message="Relationship label is recommended",
                field="label"
            ))
        
        return results
    
    def _validate_predicate(self, predicate: str) -> List[ValidationResult]:
        """predicate 명명 규칙 검증"""
        
        results = []
        
        # 기본 패턴 검증 (영문자로 시작, 영문/숫자/언더스코어)
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', predicate):
            results.append(ValidationResult(
                severity=ValidationSeverity.ERROR,
                code="INVALID_PREDICATE_FORMAT",
                message=f"Predicate '{predicate}' must start with letter and contain only letters, numbers, underscores",
                field="predicate"
            ))
        
        # camelCase 권장
        if not re.match(r'^[a-z][a-zA-Z0-9]*$', predicate):
            results.append(ValidationResult(
                severity=ValidationSeverity.INFO,
                code="PREDICATE_NAMING_CONVENTION",
                message=f"Predicate '{predicate}' should follow camelCase convention",
                field="predicate"
            ))
        
        # 예약어 검증
        reserved_words = {'id', 'type', 'class', 'property', 'relationship', 'rdf', 'rdfs', 'owl', 'xsd'}
        if predicate.lower() in reserved_words:
            results.append(ValidationResult(
                severity=ValidationSeverity.ERROR,
                code="RESERVED_PREDICATE",
                message=f"Predicate '{predicate}' is a reserved word",
                field="predicate"
            ))
        
        return results
    
    def _validate_cardinality(self, cardinality: Any) -> List[ValidationResult]:
        """카디널리티 검증"""
        
        results = []
        
        # 문자열 변환
        card_str = str(cardinality.value if hasattr(cardinality, 'value') else cardinality)
        
        # 유효한 카디널리티 값 체크
        valid_cardinalities = {"one", "many", "1:1", "1:n", "n:1", "n:n", "n:m"}
        if card_str not in valid_cardinalities:
            results.append(ValidationResult(
                severity=ValidationSeverity.ERROR,
                code="INVALID_CARDINALITY",
                message=f"Invalid cardinality '{card_str}'. Valid values: {', '.join(valid_cardinalities)}",
                field="cardinality"
            ))
        
        # 권장 카디널리티 체크
        recommended = {"1:1", "1:n", "n:n"}
        if card_str not in recommended:
            results.append(ValidationResult(
                severity=ValidationSeverity.INFO,
                code="CARDINALITY_RECOMMENDATION",
                message=f"Consider using more specific cardinality instead of '{card_str}'",
                field="cardinality"
            ))
        
        return results
    
    def _validate_target_class(self, target: str) -> List[ValidationResult]:
        """타겟 클래스 검증"""
        
        results = []
        
        # 클래스 ID 형식 검증
        if not re.match(r'^[A-Z][a-zA-Z0-9]*$', target):
            results.append(ValidationResult(
                severity=ValidationSeverity.ERROR,
                code="INVALID_TARGET_FORMAT",
                message=f"Target class '{target}' must be PascalCase",
                field="target"
            ))
        
        # 존재 여부 검증 (알려진 클래스만)
        if self.known_classes and target not in self.known_classes:
            results.append(ValidationResult(
                severity=ValidationSeverity.WARNING,
                code="UNKNOWN_TARGET_CLASS",
                message=f"Target class '{target}' is not known. Ensure it exists.",
                field="target"
            ))
        
        return results
    
    def _validate_self_reference(self, relationship: Relationship, source_class: str) -> List[ValidationResult]:
        """자기 참조 검증"""
        
        results = []
        
        if relationship.target == source_class:
            # 자기 참조는 허용하지만 카디널리티에 주의
            if relationship.cardinality in ["1:1"]:
                results.append(ValidationResult(
                    severity=ValidationSeverity.WARNING,
                    code="SELF_REFERENCE_ONE_TO_ONE",
                    message=f"Self-reference with 1:1 cardinality may cause issues",
                    field="cardinality",
                    related_objects=[source_class]
                ))
            
            results.append(ValidationResult(
                severity=ValidationSeverity.INFO,
                code="SELF_REFERENCE_DETECTED",
                message=f"Self-referential relationship detected in {source_class}",
                field="target",
                related_objects=[source_class]
            ))
        
        return results
    
    def _validate_labels(self, relationship: Relationship) -> List[ValidationResult]:
        """레이블 검증"""
        
        results = []
        
        if relationship.label:
            # 다국어 레이블 검증
            if isinstance(relationship.label, MultiLingualText):
                label_dict = relationship.label.dict()
                if not any(label_dict.values()):
                    results.append(ValidationResult(
                        severity=ValidationSeverity.WARNING,
                        code="EMPTY_MULTILINGUAL_LABEL",
                        message="All language labels are empty",
                        field="label"
                    ))
        
        return results
    
    def _validate_cardinality_consistency(
        self, 
        forward: Relationship, 
        inverse: Relationship
    ) -> List[ValidationResult]:
        """카디널리티 일관성 검증"""
        
        results = []
        
        forward_card = str(forward.cardinality.value if hasattr(forward.cardinality, 'value') else forward.cardinality)
        inverse_card = str(inverse.cardinality.value if hasattr(inverse.cardinality, 'value') else inverse.cardinality)
        
        # 카디널리티 쌍 검증
        card_pair = (forward_card, inverse_card)
        
        if card_pair in self.invalid_combinations:
            results.append(ValidationResult(
                severity=ValidationSeverity.ERROR,
                code="INCOMPATIBLE_CARDINALITIES",
                message=f"Incompatible cardinalities: {forward_card} and {inverse_card}",
                field="cardinality",
                related_objects=[forward.predicate, inverse.predicate]
            ))
        
        # 권장 카디널리티 쌍
        if not self.cardinality_matrix.get(card_pair, False):
            results.append(ValidationResult(
                severity=ValidationSeverity.WARNING,
                code="UNUSUAL_CARDINALITY_PAIR",
                message=f"Unusual cardinality combination: {forward_card} ↔ {inverse_card}",
                field="cardinality",
                related_objects=[forward.predicate, inverse.predicate]
            ))
        
        return results
    
    def _validate_mutual_reference(
        self, 
        forward: Relationship, 
        inverse: Relationship
    ) -> List[ValidationResult]:
        """상호 참조 검증"""
        
        results = []
        
        # 정방향의 inverse_predicate가 역방향의 predicate와 일치하는지
        if forward.inverse_predicate and forward.inverse_predicate != inverse.predicate:
            results.append(ValidationResult(
                severity=ValidationSeverity.ERROR,
                code="MISMATCHED_INVERSE_PREDICATE",
                message=f"Forward inverse_predicate '{forward.inverse_predicate}' doesn't match inverse predicate '{inverse.predicate}'",
                field="inverse_predicate",
                related_objects=[forward.predicate, inverse.predicate]
            ))
        
        # 역방향의 inverse_predicate가 정방향의 predicate와 일치하는지
        if inverse.inverse_predicate and inverse.inverse_predicate != forward.predicate:
            results.append(ValidationResult(
                severity=ValidationSeverity.ERROR,
                code="MISMATCHED_INVERSE_PREDICATE",
                message=f"Inverse inverse_predicate '{inverse.inverse_predicate}' doesn't match forward predicate '{forward.predicate}'",
                field="inverse_predicate",
                related_objects=[forward.predicate, inverse.predicate]
            ))
        
        return results
    
    def _validate_target_consistency(
        self,
        forward: Relationship,
        inverse: Relationship, 
        source_class: str,
        target_class: str
    ) -> List[ValidationResult]:
        """타겟 일관성 검증"""
        
        results = []
        
        # 정방향 관계의 타겟이 역방향 관계의 소스와 일치하는지
        if forward.target != target_class:
            results.append(ValidationResult(
                severity=ValidationSeverity.ERROR,
                code="TARGET_MISMATCH",
                message=f"Forward target '{forward.target}' doesn't match expected target class '{target_class}'",
                field="target",
                related_objects=[forward.predicate, target_class]
            ))
        
        # 역방향 관계의 타겟이 정방향 관계의 소스와 일치하는지
        if inverse.target != source_class:
            results.append(ValidationResult(
                severity=ValidationSeverity.ERROR,
                code="TARGET_MISMATCH",
                message=f"Inverse target '{inverse.target}' doesn't match expected source class '{source_class}'",
                field="target",
                related_objects=[inverse.predicate, source_class]
            ))
        
        return results
    
    def _validate_relationship_conflicts(self, relationships: List[Relationship]) -> List[ValidationResult]:
        """관계 간 충돌 검증"""
        
        results = []
        
        predicate_targets = {}
        
        for rel in relationships:
            key = (rel.predicate, rel.target)
            if key in predicate_targets:
                results.append(ValidationResult(
                    severity=ValidationSeverity.ERROR,
                    code="DUPLICATE_RELATIONSHIP",
                    message=f"Duplicate relationship: {rel.predicate} -> {rel.target}",
                    field="predicate",
                    related_objects=[rel.predicate, rel.target]
                ))
            predicate_targets[key] = rel
        
        return results
    
    def _validate_predicate_uniqueness(self, relationships: List[Relationship]) -> List[ValidationResult]:
        """predicate 유일성 검증"""
        
        results = []
        predicates = {}
        
        for rel in relationships:
            if rel.predicate in predicates:
                results.append(ValidationResult(
                    severity=ValidationSeverity.ERROR,
                    code="DUPLICATE_PREDICATE",
                    message=f"Duplicate predicate '{rel.predicate}' found",
                    field="predicate",
                    related_objects=[rel.predicate]
                ))
            predicates[rel.predicate] = rel
        
        return results
    
    def _validate_relationship_network(self, ontology: OntologyBase) -> List[ValidationResult]:
        """관계 네트워크 검증"""
        
        results = []
        
        # 고립된 관계 탐지
        targets = {rel.target for rel in ontology.relationships}
        predicates = {rel.predicate for rel in ontology.relationships}
        
        # 참조되지 않는 클래스 탐지
        if ontology.id not in targets and ontology.relationships:
            results.append(ValidationResult(
                severity=ValidationSeverity.INFO,
                code="ISOLATED_CLASS",
                message=f"Class '{ontology.id}' is not referenced by any relationships",
                field="relationships",
                related_objects=[ontology.id]
            ))
        
        return results
    
    def _validate_cross_ontology_relationships(self, ontologies: List[OntologyBase]) -> List[ValidationResult]:
        """온톨로지 간 관계 검증"""
        
        results = []
        
        all_class_ids = {ont.id for ont in ontologies}
        
        for ontology in ontologies:
            for rel in ontology.relationships:
                # 다른 온톨로지 클래스를 참조하는 관계 체크
                if rel.target not in all_class_ids:
                    results.append(ValidationResult(
                        severity=ValidationSeverity.WARNING,
                        code="EXTERNAL_CLASS_REFERENCE",
                        message=f"Relationship '{rel.predicate}' references external class '{rel.target}'",
                        field="target",
                        related_objects=[ontology.id, rel.predicate, rel.target]
                    ))
        
        return results
    
    def _validate_global_relationship_consistency(self, ontologies: List[OntologyBase]) -> List[ValidationResult]:
        """전역 관계 일관성 검증"""
        
        results = []
        
        # 전역 predicate 유일성 검증
        global_predicates = {}
        
        for ontology in ontologies:
            for rel in ontology.relationships:
                full_predicate = f"{ontology.id}.{rel.predicate}"
                if rel.predicate in global_predicates:
                    other_class = global_predicates[rel.predicate]
                    if other_class != ontology.id:
                        results.append(ValidationResult(
                            severity=ValidationSeverity.WARNING,
                            code="GLOBAL_PREDICATE_CONFLICT",
                            message=f"Predicate '{rel.predicate}' used in multiple classes: {ontology.id}, {other_class}",
                            field="predicate",
                            related_objects=[ontology.id, other_class, rel.predicate]
                        ))
                global_predicates[rel.predicate] = ontology.id
        
        return results
    
    def get_validation_summary(self, results: List[ValidationResult]) -> Dict[str, Any]:
        """검증 결과 요약"""
        
        summary = {
            "total_issues": len(results),
            "errors": len([r for r in results if r.severity == ValidationSeverity.ERROR]),
            "warnings": len([r for r in results if r.severity == ValidationSeverity.WARNING]),  
            "info": len([r for r in results if r.severity == ValidationSeverity.INFO]),
            "can_proceed": not any(r.severity == ValidationSeverity.ERROR for r in results),
            "issue_codes": list(set(r.code for r in results)),
            "affected_fields": list(set(r.field for r in results if r.field))
        }
        
        return summary