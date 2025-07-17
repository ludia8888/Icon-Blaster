"""
온톨로지 병합기 구현
온톨로지 병합 작업을 전담하는 서비스
SRP: 오직 온톨로지 병합 로직만 담당
"""

import logging
from typing import Dict, List, Optional, Any, Union
from copy import deepcopy

from services.core.interfaces import IOntologyMerger, IOntologyRepository, IOntologyValidator
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'shared'))
from exceptions import (
    OntologyOperationError,
    OntologyValidationError,
    DomainException
)

logger = logging.getLogger(__name__)


class TerminusOntologyMerger(IOntologyMerger):
    """
    TerminusDB 온톨로지 병합기
    
    단일 책임: 온톨로지 병합 로직만 담당
    """
    
    def __init__(self, repository: IOntologyRepository, validator: IOntologyValidator):
        """
        초기화
        
        Args:
            repository: 온톨로지 저장소
            validator: 온톨로지 유효성 검증기
        """
        self.repository = repository
        self.validator = validator
    
    def merge(self, db_name: str, ontology_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        온톨로지 병합 (존재하면 업데이트, 없으면 생성)
        
        Args:
            db_name: 데이터베이스 이름
            ontology_data: 온톨로지 데이터
            
        Returns:
            병합 결과
            
        Raises:
            OntologyValidationError: 유효성 검증 실패
            OntologyOperationError: 병합 실패
        """
        ontology_id = ontology_data.get('id')
        if not ontology_id:
            raise OntologyValidationError(["Ontology ID is required for merge"], None)
        
        try:
            # 기존 온톨로지 확인
            existing_ontology = self.repository.get(db_name, ontology_id)
            
            if existing_ontology:
                # 업데이트 시나리오
                logger.info(f"Merging existing ontology '{ontology_id}' in '{db_name}'")
                merged_data = self._merge_with_existing(existing_ontology, ontology_data)
                
                # 유효성 검증
                validation_errors = self.validator.validate(merged_data)
                if validation_errors:
                    raise OntologyValidationError(validation_errors, ontology_id)
                
                # 업데이트 실행
                result = self.repository.update(db_name, ontology_id, merged_data)
                result['operation'] = 'update'
                result['merged'] = True
                
                return result
            else:
                # 생성 시나리오
                logger.info(f"Creating new ontology '{ontology_id}' in '{db_name}'")
                
                # 유효성 검증
                validation_errors = self.validator.validate(ontology_data)
                if validation_errors:
                    raise OntologyValidationError(validation_errors, ontology_id)
                
                # 생성 실행
                result = self.repository.create(db_name, ontology_data)
                result['operation'] = 'create'
                result['merged'] = True
                
                return result
                
        except (OntologyValidationError, DomainException):
            # 이미 적절한 예외이므로 재발생
            raise
        except Exception as e:
            logger.error(f"Failed to merge ontology '{ontology_id}' in '{db_name}': {e}")
            raise OntologyOperationError(
                operation="merge",
                message=str(e),
                ontology_id=ontology_id
            )
    
    def merge_properties(self, db_name: str, ontology_id: str, 
                        properties: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        속성만 병합
        
        Args:
            db_name: 데이터베이스 이름
            ontology_id: 온톨로지 ID
            properties: 병합할 속성들
            
        Returns:
            병합 결과
        """
        try:
            # 기존 온톨로지 가져오기
            existing_ontology = self.repository.get(db_name, ontology_id)
            if not existing_ontology:
                raise OntologyOperationError(
                    operation="merge_properties",
                    message=f"Ontology '{ontology_id}' not found",
                    ontology_id=ontology_id
                )
            
            # 속성 병합
            merged_properties = self._merge_properties_list(
                existing_ontology.get('properties', []),
                properties
            )
            
            # 업데이트 데이터 생성
            update_data = deepcopy(existing_ontology)
            update_data['properties'] = merged_properties
            
            # 업데이트 실행
            result = self.repository.update(db_name, ontology_id, update_data)
            result['operation'] = 'merge_properties'
            result['properties_merged'] = len(properties)
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to merge properties for '{ontology_id}': {e}")
            raise OntologyOperationError(
                operation="merge_properties",
                message=str(e),
                ontology_id=ontology_id
            )
    
    def merge_relationships(self, db_name: str, ontology_id: str,
                           relationships: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        관계만 병합
        
        Args:
            db_name: 데이터베이스 이름
            ontology_id: 온톨로지 ID
            relationships: 병합할 관계들
            
        Returns:
            병합 결과
        """
        try:
            # 기존 온톨로지 가져오기
            existing_ontology = self.repository.get(db_name, ontology_id)
            if not existing_ontology:
                raise OntologyOperationError(
                    operation="merge_relationships",
                    message=f"Ontology '{ontology_id}' not found",
                    ontology_id=ontology_id
                )
            
            # 관계 병합
            merged_relationships = self._merge_relationships_list(
                existing_ontology.get('relationships', []),
                relationships
            )
            
            # 업데이트 데이터 생성
            update_data = deepcopy(existing_ontology)
            update_data['relationships'] = merged_relationships
            
            # 업데이트 실행
            result = self.repository.update(db_name, ontology_id, update_data)
            result['operation'] = 'merge_relationships'
            result['relationships_merged'] = len(relationships)
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to merge relationships for '{ontology_id}': {e}")
            raise OntologyOperationError(
                operation="merge_relationships",
                message=str(e),
                ontology_id=ontology_id
            )
    
    def _merge_with_existing(self, existing: Dict[str, Any], 
                           new_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        기존 온톨로지와 새 데이터 병합
        
        Args:
            existing: 기존 온톨로지
            new_data: 새로운 데이터
            
        Returns:
            병합된 데이터
        """
        merged = deepcopy(existing)
        
        # 기본 필드 병합
        for field in ['label', 'description', 'parent', 'type']:
            if field in new_data:
                merged[field] = self._merge_field(
                    merged.get(field), 
                    new_data[field]
                )
        
        # 속성 병합
        if 'properties' in new_data:
            merged['properties'] = self._merge_properties_list(
                merged.get('properties', []),
                new_data['properties']
            )
        
        # 관계 병합
        if 'relationships' in new_data:
            merged['relationships'] = self._merge_relationships_list(
                merged.get('relationships', []),
                new_data['relationships']
            )
        
        return merged
    
    def _merge_field(self, existing: Any, new_value: Any) -> Any:
        """
        개별 필드 병합
        
        Args:
            existing: 기존 값
            new_value: 새로운 값
            
        Returns:
            병합된 값
        """
        # 새 값이 None이면 기존 값 유지
        if new_value is None:
            return existing
        
        # 둘 다 딕셔너리면 병합 (다국어 지원)
        if isinstance(existing, dict) and isinstance(new_value, dict):
            merged = deepcopy(existing)
            merged.update(new_value)
            return merged
        
        # 그 외의 경우 새 값으로 덮어쓰기
        return new_value
    
    def _merge_properties_list(self, existing: List[Dict[str, Any]], 
                              new_properties: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        속성 리스트 병합
        
        Args:
            existing: 기존 속성들
            new_properties: 새로운 속성들
            
        Returns:
            병합된 속성 리스트
        """
        if not isinstance(existing, list):
            existing = []
        if not isinstance(new_properties, list):
            new_properties = []
        
        # 기존 속성을 이름으로 인덱싱
        existing_props = {prop.get('name'): prop for prop in existing if prop.get('name')}
        
        # 새 속성들을 병합
        for new_prop in new_properties:
            prop_name = new_prop.get('name')
            if not prop_name:
                continue
            
            if prop_name in existing_props:
                # 기존 속성과 병합
                existing_props[prop_name] = self._merge_property(
                    existing_props[prop_name], 
                    new_prop
                )
            else:
                # 새 속성 추가
                existing_props[prop_name] = deepcopy(new_prop)
        
        return list(existing_props.values())
    
    def _merge_property(self, existing: Dict[str, Any], 
                       new_prop: Dict[str, Any]) -> Dict[str, Any]:
        """
        개별 속성 병합
        
        Args:
            existing: 기존 속성
            new_prop: 새로운 속성
            
        Returns:
            병합된 속성
        """
        merged = deepcopy(existing)
        
        # 기본 필드 병합
        for field in ['type', 'required', 'default', 'description', 'label']:
            if field in new_prop:
                merged[field] = self._merge_field(
                    merged.get(field), 
                    new_prop[field]
                )
        
        # 제약 조건 병합
        if 'constraints' in new_prop:
            merged['constraints'] = self._merge_field(
                merged.get('constraints', {}),
                new_prop['constraints']
            )
        
        return merged
    
    def _merge_relationships_list(self, existing: List[Dict[str, Any]], 
                                 new_relationships: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        관계 리스트 병합
        
        Args:
            existing: 기존 관계들
            new_relationships: 새로운 관계들
            
        Returns:
            병합된 관계 리스트
        """
        if not isinstance(existing, list):
            existing = []
        if not isinstance(new_relationships, list):
            new_relationships = []
        
        # 기존 관계를 predicate로 인덱싱
        existing_rels = {}
        for rel in existing:
            predicate = rel.get('predicate')
            target = rel.get('target')
            if predicate and target:
                key = f"{predicate}:{target}"
                existing_rels[key] = rel
        
        # 새 관계들을 병합
        for new_rel in new_relationships:
            predicate = new_rel.get('predicate')
            target = new_rel.get('target')
            if not predicate or not target:
                continue
            
            key = f"{predicate}:{target}"
            if key in existing_rels:
                # 기존 관계와 병합
                existing_rels[key] = self._merge_relationship(
                    existing_rels[key], 
                    new_rel
                )
            else:
                # 새 관계 추가
                existing_rels[key] = deepcopy(new_rel)
        
        return list(existing_rels.values())
    
    def _merge_relationship(self, existing: Dict[str, Any], 
                           new_rel: Dict[str, Any]) -> Dict[str, Any]:
        """
        개별 관계 병합
        
        Args:
            existing: 기존 관계
            new_rel: 새로운 관계
            
        Returns:
            병합된 관계
        """
        merged = deepcopy(existing)
        
        # 기본 필드 병합
        for field in ['type', 'cardinality', 'description', 'label']:
            if field in new_rel:
                merged[field] = self._merge_field(
                    merged.get(field), 
                    new_rel[field]
                )
        
        return merged
    
    def get_merge_preview(self, db_name: str, ontology_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        병합 미리보기 생성
        
        Args:
            db_name: 데이터베이스 이름
            ontology_data: 온톨로지 데이터
            
        Returns:
            병합 미리보기
        """
        ontology_id = ontology_data.get('id')
        if not ontology_id:
            return {"error": "Ontology ID is required"}
        
        try:
            existing_ontology = self.repository.get(db_name, ontology_id)
            
            if existing_ontology:
                # 업데이트 미리보기
                merged_data = self._merge_with_existing(existing_ontology, ontology_data)
                
                return {
                    "operation": "update",
                    "ontology_id": ontology_id,
                    "existing": existing_ontology,
                    "new_data": ontology_data,
                    "merged_result": merged_data,
                    "changes": self._detect_changes(existing_ontology, merged_data)
                }
            else:
                # 생성 미리보기
                return {
                    "operation": "create",
                    "ontology_id": ontology_id,
                    "new_data": ontology_data,
                    "validation_errors": self.validator.validate(ontology_data)
                }
                
        except Exception as e:
            return {"error": str(e)}
    
    def _detect_changes(self, existing: Dict[str, Any], 
                       merged: Dict[str, Any]) -> Dict[str, Any]:
        """
        변경 사항 탐지
        
        Args:
            existing: 기존 데이터
            merged: 병합된 데이터
            
        Returns:
            변경 사항 요약
        """
        changes = {
            "modified_fields": [],
            "added_properties": [],
            "modified_properties": [],
            "removed_properties": [],
            "added_relationships": [],
            "modified_relationships": [],
            "removed_relationships": []
        }
        
        # 기본 필드 변경 확인
        for field in ['label', 'description', 'parent', 'type']:
            if existing.get(field) != merged.get(field):
                changes["modified_fields"].append(field)
        
        # 속성 변경 확인
        existing_props = {p.get('name'): p for p in existing.get('properties', []) if p.get('name')}
        merged_props = {p.get('name'): p for p in merged.get('properties', []) if p.get('name')}
        
        for prop_name, prop_data in merged_props.items():
            if prop_name not in existing_props:
                changes["added_properties"].append(prop_name)
            elif existing_props[prop_name] != prop_data:
                changes["modified_properties"].append(prop_name)
        
        for prop_name in existing_props:
            if prop_name not in merged_props:
                changes["removed_properties"].append(prop_name)
        
        # 관계 변경 확인 (유사한 로직)
        existing_rels = {f"{r.get('predicate')}:{r.get('target')}": r for r in existing.get('relationships', [])}
        merged_rels = {f"{r.get('predicate')}:{r.get('target')}": r for r in merged.get('relationships', [])}
        
        for rel_key, rel_data in merged_rels.items():
            if rel_key not in existing_rels:
                changes["added_relationships"].append(rel_key)
            elif existing_rels[rel_key] != rel_data:
                changes["modified_relationships"].append(rel_key)
        
        for rel_key in existing_rels:
            if rel_key not in merged_rels:
                changes["removed_relationships"].append(rel_key)
        
        return changes