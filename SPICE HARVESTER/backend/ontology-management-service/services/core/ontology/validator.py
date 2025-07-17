"""
온톨로지 유효성 검증기 구현
온톨로지 데이터의 유효성을 검증하는 전담 서비스
SRP: 오직 온톨로지 유효성 검증만 담당
"""

import re
import logging
from typing import Dict, List, Optional, Any, Set

from services.core.interfaces import IOntologyValidator
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from entities.ontology import Ontology
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'shared'))
from value_objects.multilingual_text import MultiLingualText

logger = logging.getLogger(__name__)


class TerminusOntologyValidator(IOntologyValidator):
    """
    TerminusDB 온톨로지 유효성 검증기
    
    단일 책임: 온톨로지 데이터 유효성 검증만 담당
    """
    
    # 유효한 온톨로지 ID 패턴 (알파벳, 숫자, 언더스코어, 하이픈)
    VALID_ID_PATTERN = re.compile(r'^[a-zA-Z][a-zA-Z0-9_-]*$')
    
    # 예약어 목록
    RESERVED_WORDS = {
        'sys', 'rdf', 'rdfs', 'owl', 'xsd', 'woql', 'terminus',
        'Class', 'Property', 'DataProperty', 'ObjectProperty',
        'FunctionalProperty', 'InverseFunctionalProperty',
        'TransitiveProperty', 'SymmetricProperty', 'AsymmetricProperty',
        'ReflexiveProperty', 'IrreflexiveProperty'
    }
    
    # 지원하는 언어 코드
    SUPPORTED_LANGUAGES = {'ko', 'en', 'ja', 'zh', 'fr', 'de', 'es'}
    
    # 최대 길이 제한
    MAX_ID_LENGTH = 64
    MAX_LABEL_LENGTH = 255
    MAX_DESCRIPTION_LENGTH = 1000
    
    def __init__(self):
        """초기화"""
        self._validation_rules = self._setup_validation_rules()
    
    def validate(self, ontology_data: Dict[str, Any]) -> List[str]:
        """
        온톨로지 데이터 유효성 검증
        
        Args:
            ontology_data: 검증할 데이터
            
        Returns:
            오류 메시지 리스트 (빈 리스트면 유효함)
        """
        errors = []
        
        try:
            # 각 검증 규칙 실행
            for rule_name, rule_func in self._validation_rules.items():
                try:
                    rule_errors = rule_func(ontology_data)
                    if rule_errors:
                        errors.extend(rule_errors)
                except Exception as e:
                    logger.error(f"Validation rule '{rule_name}' failed: {e}")
                    errors.append(f"Validation rule '{rule_name}' execution failed")
            
            logger.debug(f"Validation completed with {len(errors)} errors")
            return errors
            
        except Exception as e:
            logger.error(f"Validation process failed: {e}")
            return [f"Validation process failed: {str(e)}"]
    
    def _setup_validation_rules(self) -> Dict[str, callable]:
        """
        검증 규칙 설정
        
        Returns:
            검증 규칙 딕셔너리
        """
        return {
            'required_fields': self._validate_required_fields,
            'id_format': self._validate_id_format,
            'id_uniqueness': self._validate_id_uniqueness,
            'label_format': self._validate_label_format,
            'description_format': self._validate_description_format,
            'properties_format': self._validate_properties_format,
            'relationships_format': self._validate_relationships_format,
            'data_types': self._validate_data_types,
            'circular_references': self._validate_circular_references,
            'language_tags': self._validate_language_tags
        }
    
    def _validate_required_fields(self, data: Dict[str, Any]) -> List[str]:
        """필수 필드 검증"""
        errors = []
        
        # ID는 필수
        if not data.get('id'):
            errors.append("Ontology ID is required")
        
        # 빈 객체 검증
        if not data:
            errors.append("Ontology data cannot be empty")
        
        return errors
    
    def _validate_id_format(self, data: Dict[str, Any]) -> List[str]:
        """ID 형식 검증"""
        errors = []
        ontology_id = data.get('id')
        
        if not ontology_id:
            return errors  # required_fields에서 처리됨
        
        # 타입 검증
        if not isinstance(ontology_id, str):
            errors.append("Ontology ID must be a string")
            return errors
        
        # 길이 검증
        if len(ontology_id) > self.MAX_ID_LENGTH:
            errors.append(f"Ontology ID cannot exceed {self.MAX_ID_LENGTH} characters")
        
        # 패턴 검증
        if not self.VALID_ID_PATTERN.match(ontology_id):
            errors.append("Ontology ID must start with a letter and contain only letters, numbers, underscores, and hyphens")
        
        # 예약어 검증
        if ontology_id.lower() in self.RESERVED_WORDS:
            errors.append(f"Ontology ID '{ontology_id}' is a reserved word")
        
        # 시스템 prefix 검증
        if ontology_id.startswith(('sys:', 'rdf:', 'rdfs:', 'owl:', 'xsd:')):
            errors.append(f"Ontology ID '{ontology_id}' uses reserved system prefix")
        
        return errors
    
    def _validate_id_uniqueness(self, data: Dict[str, Any]) -> List[str]:
        """ID 고유성 검증 (기본 체크만, 실제 중복은 Repository에서)"""
        errors = []
        
        # 기본적인 중복 가능성 체크
        ontology_id = data.get('id')
        if ontology_id:
            # 속성 이름과 동일한지 확인
            properties = data.get('properties', [])
            if isinstance(properties, list):
                for prop in properties:
                    if isinstance(prop, dict) and prop.get('name') == ontology_id:
                        errors.append(f"Ontology ID '{ontology_id}' conflicts with property name")
        
        return errors
    
    def _validate_label_format(self, data: Dict[str, Any]) -> List[str]:
        """레이블 형식 검증"""
        errors = []
        label = data.get('label')
        
        if not label:
            return errors  # 레이블은 선택사항
        
        # 문자열 또는 다국어 객체
        if isinstance(label, str):
            if len(label) > self.MAX_LABEL_LENGTH:
                errors.append(f"Label cannot exceed {self.MAX_LABEL_LENGTH} characters")
        elif isinstance(label, dict):
            for lang, text in label.items():
                if not isinstance(text, str):
                    errors.append(f"Label text for language '{lang}' must be a string")
                elif len(text) > self.MAX_LABEL_LENGTH:
                    errors.append(f"Label for language '{lang}' cannot exceed {self.MAX_LABEL_LENGTH} characters")
        else:
            errors.append("Label must be a string or language object")
        
        return errors
    
    def _validate_description_format(self, data: Dict[str, Any]) -> List[str]:
        """설명 형식 검증"""
        errors = []
        description = data.get('description')
        
        if not description:
            return errors  # 설명은 선택사항
        
        # 문자열 또는 다국어 객체
        if isinstance(description, str):
            if len(description) > self.MAX_DESCRIPTION_LENGTH:
                errors.append(f"Description cannot exceed {self.MAX_DESCRIPTION_LENGTH} characters")
        elif isinstance(description, dict):
            for lang, text in description.items():
                if not isinstance(text, str):
                    errors.append(f"Description text for language '{lang}' must be a string")
                elif len(text) > self.MAX_DESCRIPTION_LENGTH:
                    errors.append(f"Description for language '{lang}' cannot exceed {self.MAX_DESCRIPTION_LENGTH} characters")
        else:
            errors.append("Description must be a string or language object")
        
        return errors
    
    def _validate_properties_format(self, data: Dict[str, Any]) -> List[str]:
        """속성 형식 검증"""
        errors = []
        properties = data.get('properties')
        
        if not properties:
            return errors  # 속성은 선택사항
        
        if not isinstance(properties, list):
            errors.append("Properties must be a list")
            return errors
        
        property_names = set()
        
        for i, prop in enumerate(properties):
            if not isinstance(prop, dict):
                errors.append(f"Property {i} must be an object")
                continue
            
            # 속성 이름 검증
            prop_name = prop.get('name')
            if not prop_name:
                errors.append(f"Property {i} must have a name")
            elif not isinstance(prop_name, str):
                errors.append(f"Property {i} name must be a string")
            elif prop_name in property_names:
                errors.append(f"Duplicate property name: {prop_name}")
            else:
                property_names.add(prop_name)
                
                # 속성 이름 형식 검증
                if not self.VALID_ID_PATTERN.match(prop_name):
                    errors.append(f"Property '{prop_name}' has invalid name format")
            
            # 속성 타입 검증
            prop_type = prop.get('type')
            if prop_type and not isinstance(prop_type, str):
                errors.append(f"Property '{prop_name}' type must be a string")
        
        return errors
    
    def _validate_relationships_format(self, data: Dict[str, Any]) -> List[str]:
        """관계 형식 검증"""
        errors = []
        relationships = data.get('relationships')
        
        if not relationships:
            return errors  # 관계는 선택사항
        
        if not isinstance(relationships, list):
            errors.append("Relationships must be a list")
            return errors
        
        for i, rel in enumerate(relationships):
            if not isinstance(rel, dict):
                errors.append(f"Relationship {i} must be an object")
                continue
            
            # 관계 술어 검증
            predicate = rel.get('predicate')
            if not predicate:
                errors.append(f"Relationship {i} must have a predicate")
            elif not isinstance(predicate, str):
                errors.append(f"Relationship {i} predicate must be a string")
            
            # 관계 대상 검증
            target = rel.get('target')
            if not target:
                errors.append(f"Relationship {i} must have a target")
            elif not isinstance(target, str):
                errors.append(f"Relationship {i} target must be a string")
        
        return errors
    
    def _validate_data_types(self, data: Dict[str, Any]) -> List[str]:
        """데이터 타입 검증 - 통합 구현 (router와 validator 중복 제거)"""
        errors = []
        
        # 지원하는 기본 타입들 - 더 포괄적인 타입 지원
        supported_types = {
            'string', 'str', 'text',
            'integer', 'int', 'number',
            'float', 'double', 'decimal',
            'boolean', 'bool',
            'date', 'datetime', 'timestamp',
            'uri', 'url', 'iri',
            'xsd:string', 'xsd:integer', 'xsd:float', 'xsd:double', 'xsd:decimal',
            'xsd:boolean', 'xsd:date', 'xsd:datetime', 'xsd:anyURI'
        }
        
        # properties가 dict 형태인 경우 (OMS 형식)
        properties = data.get('properties', {})
        if isinstance(properties, dict):
            for prop_name, prop_type in properties.items():
                if prop_type and isinstance(prop_type, str):
                    # 콜론을 포함한 타입 (invalid:type 같은) 거부
                    if ':' in prop_type and not any(prop_type.startswith(prefix) for prefix in ['xsd:', 'rdfs:', 'owl:']):
                        errors.append(f"Property '{prop_name}' has invalid type format: {prop_type}")
                    elif prop_type not in supported_types and not prop_type.startswith(('http://', 'https://')):
                        errors.append(f"Property '{prop_name}' has unsupported type: {prop_type}")
        
        # properties가 list 형태인 경우 (BFF 형식)
        elif isinstance(properties, list):
            for prop in properties:
                if isinstance(prop, dict):
                    prop_name = prop.get('name')
                    prop_type = prop.get('type')
                    if prop_type and isinstance(prop_type, str):
                        # 콜론을 포함한 타입 (invalid:type 같은) 거부
                        if ':' in prop_type and not any(prop_type.startswith(prefix) for prefix in ['xsd:', 'rdfs:', 'owl:']):
                            errors.append(f"Property '{prop_name}' has invalid type format: {prop_type}")
                        elif prop_type not in supported_types and not prop_type.startswith(('http://', 'https://')):
                            errors.append(f"Property '{prop_name}' has unsupported type: {prop_type}")
        
        return errors
    
    def _validate_circular_references(self, data: Dict[str, Any]) -> List[str]:
        """순환 참조 검증"""
        errors = []
        ontology_id = data.get('id')
        
        if not ontology_id:
            return errors
        
        # 자기 자신을 상속하는지 확인
        parent = data.get('parent')
        if parent == ontology_id:
            errors.append(f"Ontology '{ontology_id}' cannot inherit from itself")
        
        # 속성에서 자기 자신을 참조하는지 확인
        properties = data.get('properties', [])
        if isinstance(properties, list):
            for prop in properties:
                if isinstance(prop, dict):
                    prop_type = prop.get('type')
                    if prop_type == ontology_id:
                        errors.append(f"Property '{prop.get('name')}' cannot reference its own ontology")
        
        return errors
    
    def _validate_language_tags(self, data: Dict[str, Any]) -> List[str]:
        """언어 태그 검증"""
        errors = []
        
        # 레이블 언어 태그 검증
        label = data.get('label')
        if isinstance(label, dict):
            for lang in label.keys():
                if lang not in self.SUPPORTED_LANGUAGES:
                    errors.append(f"Unsupported language code in label: {lang}")
        
        # 설명 언어 태그 검증
        description = data.get('description')
        if isinstance(description, dict):
            for lang in description.keys():
                if lang not in self.SUPPORTED_LANGUAGES:
                    errors.append(f"Unsupported language code in description: {lang}")
        
        return errors
    
    def is_valid_id(self, ontology_id: str) -> bool:
        """
        ID 유효성 간단 검사
        
        Args:
            ontology_id: 검사할 ID
            
        Returns:
            유효성 여부
        """
        if not isinstance(ontology_id, str):
            return False
        
        return (
            len(ontology_id) <= self.MAX_ID_LENGTH and
            self.VALID_ID_PATTERN.match(ontology_id) and
            ontology_id.lower() not in self.RESERVED_WORDS and
            not ontology_id.startswith(('sys:', 'rdf:', 'rdfs:', 'owl:', 'xsd:'))
        )
    
    def get_validation_summary(self, ontology_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        검증 요약 정보 생성
        
        Args:
            ontology_data: 온톨로지 데이터
            
        Returns:
            검증 요약
        """
        errors = self.validate(ontology_data)
        
        return {
            "is_valid": len(errors) == 0,
            "error_count": len(errors),
            "errors": errors,
            "ontology_id": ontology_data.get('id'),
            "validation_timestamp": logger.name  # 간단한 타임스탬프 대용
        }