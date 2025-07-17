"""
레이블 매퍼 서비스 구현
레이블과 ID 간의 매핑을 관리하는 서비스
SRP: 오직 레이블 매핑 관리만 담당
"""

import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

from services.core.interfaces import ILabelMapperService, IOntologyRepository
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'shared'))
from exceptions import LabelNotFoundError, DomainException
from value_objects.multilingual_text import MultiLingualText
# Fix import path for label mapping entity
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))
from entities.label_mapping import LabelMapping

logger = logging.getLogger(__name__)


class TerminusLabelMapperService(ILabelMapperService):
    """
    TerminusDB 레이블 매퍼 서비스
    
    단일 책임: 레이블과 ID 간의 매핑 관리만 담당
    IOntologyRepository를 사용하여 TerminusDB에 레이블 매핑 저장
    """
    
    def __init__(self, ontology_repository: IOntologyRepository):
        """
        초기화
        
        Args:
            ontology_repository: 온톨로지 저장소 (TerminusDB 접근용)
        """
        self.ontology_repository = ontology_repository
        self._ensure_label_mapping_schema()
    
    def _ensure_label_mapping_schema(self):
        """
        LabelMapping 스키마가 TerminusDB에 있는지 확인하고 없으면 생성
        
        주의: 이 메서드는 시스템 초기화 시에만 호출되어야 함
        """
        try:
            from schemas.label_mapping_schema import get_label_mapping_ontology
            
            # 시스템 데이터베이스에 LabelMapping 스키마 등록
            # 실제로는 시스템 초기화 스크립트에서 이미 생성되어 있어야 함
            logger.debug("LabelMapping schema should be initialized during system setup")
            
        except Exception as e:
            logger.warning(f"Could not ensure LabelMapping schema: {e}")
            # 스키마 생성 실패는 치명적이지 않음 (이미 존재할 수 있음)
    
    def _upsert_label_mapping(self, db_name: str, label_mapping: LabelMapping) -> None:
        """
        레이블 매핑을 TerminusDB에 저장/업데이트
        
        Args:
            db_name: 데이터베이스 이름
            label_mapping: 레이블 매핑 엔티티
        """
        try:
            # 기존 매핑 확인
            existing_mapping = self._get_label_mapping(db_name, label_mapping.id)
            
            if existing_mapping:
                # 업데이트
                label_mapping.update_timestamp()
                self.ontology_repository.update(
                    db_name,
                    label_mapping.id,
                    label_mapping.to_terminusdb_document()
                )
            else:
                # 새로 생성
                self.ontology_repository.create(
                    db_name,
                    label_mapping.to_terminusdb_document()
                )
                
        except Exception as e:
            logger.error(f"Failed to upsert label mapping {label_mapping.id}: {e}")
            raise
    
    def _get_label_mapping(self, db_name: str, mapping_id: str) -> Optional[LabelMapping]:
        """
        ID로 레이블 매핑 조회
        
        Args:
            db_name: 데이터베이스 이름
            mapping_id: 매핑 ID
            
        Returns:
            레이블 매핑 엔티티 또는 None
        """
        try:
            doc = self.ontology_repository.get(db_name, mapping_id)
            if doc and doc.get("@type") == "LabelMapping":
                return LabelMapping.from_terminusdb_document(doc)
            return None
        except Exception as e:
            logger.debug(f"Label mapping {mapping_id} not found: {e}")
            return None
    
    def _query_label_mappings(self, db_name: str, filters: Dict[str, Any]) -> List[LabelMapping]:
        """
        레이블 매핑 문서들을 쿼리
        
        Args:
            db_name: 데이터베이스 이름
            filters: 쿼리 필터
            
        Returns:
            레이블 매핑 엔티티 리스트
        """
        try:
            # 실제 구현: TerminusDB에서 레이블 매핑 쿼리
            with self.connection_manager.get_connection(db_name) as client:
                # WOQL 쿼리로 LabelMapping 문서 조회
                from terminusdb_client import WOQLQuery
                
                query = WOQLQuery()
                
                # 기본 필터 조건 설정
                conditions = []
                
                # resource_type 필터
                if filters.get('resource_type'):
                    conditions.append(
                        query.triple("v:Mapping", "resource_type", filters['resource_type'])
                    )
                
                # resource_id 필터
                if filters.get('resource_id'):
                    conditions.append(
                        query.triple("v:Mapping", "resource_id", filters['resource_id'])
                    )
                
                # language 필터
                if filters.get('language'):
                    conditions.append(
                        query.triple("v:Mapping", "language", filters['language'])
                    )
                
                # 쿼리 구성
                final_query = query.select("v:Mapping").triple("v:Mapping", "rdf:type", "LabelMapping")
                
                if conditions:
                    for condition in conditions:
                        final_query = final_query.woql_and(condition)
                
                # 쿼리 실행
                result = client.query(final_query)
                
                # 결과를 LabelMapping 엔티티로 변환
                mappings = []
                for binding in result.get('bindings', []):
                    mapping_id = binding.get('Mapping')
                    if mapping_id:
                        # 전체 문서 조회
                        doc = client.get_document(mapping_id)
                        if doc:
                            mappings.append(LabelMapping(**doc))
                
                return mappings
            
        except Exception as e:
            logger.error(f"Failed to query label mappings from database '{db_name}': {e}")
            # 쿼리 실패는 예외를 던져야 함
            raise ServiceError(f"Unable to query label mappings: {str(e)}")
    
    def register_class(self, db_name: str, class_id: str, 
                      label: Any, description: Optional[Any] = None) -> None:
        """
        클래스 레이블 매핑 등록
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            label: 클래스 레이블 (문자열 또는 MultiLingualText)
            description: 클래스 설명
        """
        try:
            # 다국어 레이블 처리
            labels = self._extract_labels(label)
            descriptions = self._extract_labels(description) if description else {}
            
            for lang, label_text in labels.items():
                desc_text = descriptions.get(lang, "")
                
                # LabelMapping 엔티티 생성
                label_mapping = LabelMapping(
                    id=LabelMapping.generate_id(db_name, "class", class_id, lang),
                    db_name=db_name,
                    mapping_type="class",
                    target_id=class_id,
                    label=label_text,
                    language=lang,
                    description=desc_text if desc_text else None
                )
                
                # TerminusDB에 저장 (기존 것이 있으면 업데이트)
                self._upsert_label_mapping(db_name, label_mapping)
            
            logger.info(f"Registered class mapping: {class_id} -> {labels}")
            
        except Exception as e:
            logger.error(f"Failed to register class mapping for {class_id}: {e}")
            raise DomainException(
                message=f"Failed to register class mapping for {class_id}",
                code="LABEL_MAPPING_REGISTER_ERROR",
                details={"class_id": class_id, "db_name": db_name, "error": str(e)}
            )
    
    def register_property(self, db_name: str, class_id: str, 
                         property_id: str, label: Any) -> None:
        """
        속성 레이블 매핑 등록
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            property_id: 속성 ID
            label: 속성 레이블
        """
        try:
            labels = self._extract_labels(label)
            
            for lang, label_text in labels.items():
                # LabelMapping 엔티티 생성
                label_mapping = LabelMapping(
                    id=LabelMapping.generate_id(db_name, "property", property_id, lang, class_id),
                    db_name=db_name,
                    mapping_type="property",
                    target_id=property_id,
                    label=label_text,
                    language=lang,
                    class_id=class_id  # property 매핑에는 class_id 필요
                )
                
                # TerminusDB에 저장 (기존 것이 있으면 업데이트)
                self._upsert_label_mapping(db_name, label_mapping)
            
            logger.info(f"Registered property mapping: {property_id} -> {labels}")
            
        except Exception as e:
            logger.error(f"Failed to register property mapping for {property_id}: {e}")
            raise DomainException(
                message=f"Failed to register property mapping for {property_id}",
                code="LABEL_MAPPING_REGISTER_ERROR",
                details={"property_id": property_id, "class_id": class_id, "db_name": db_name, "error": str(e)}
            )
    
    def register_relationship(self, db_name: str, predicate: str, label: Any) -> None:
        """
        관계 레이블 매핑 등록
        
        Args:
            db_name: 데이터베이스 이름
            predicate: 관계 술어
            label: 관계 레이블
        """
        try:
            labels = self._extract_labels(label)
            
            for lang, label_text in labels.items():
                # LabelMapping 엔티티 생성
                label_mapping = LabelMapping(
                    id=LabelMapping.generate_id(db_name, "relationship", predicate, lang),
                    db_name=db_name,
                    mapping_type="relationship",
                    target_id=predicate,
                    label=label_text,
                    language=lang
                )
                
                # TerminusDB에 저장 (기존 것이 있으면 업데이트)
                self._upsert_label_mapping(db_name, label_mapping)
            
            logger.info(f"Registered relationship mapping: {predicate} -> {labels}")
            
        except Exception as e:
            logger.error(f"Failed to register relationship mapping for {predicate}: {e}")
            raise DomainException(
                message=f"Failed to register relationship mapping for {predicate}",
                code="LABEL_MAPPING_REGISTER_ERROR",
                details={"predicate": predicate, "db_name": db_name, "error": str(e)}
            )
    
    def get_id_by_label(self, db_name: str, label: str, 
                       label_type: str = "class", class_id: Optional[str] = None,
                       lang: str = 'ko') -> Optional[str]:
        """
        레이블로 ID 조회 (통합 메서드)
        
        Args:
            db_name: 데이터베이스 이름
            label: 레이블
            label_type: 레이블 타입 ("class", "property", "relationship")
            class_id: 클래스 ID (property 조회 시 필요)
            lang: 언어 코드
            
        Returns:
            ID 또는 None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if label_type == "class":
                cursor.execute("""
                    SELECT class_id FROM class_mappings 
                    WHERE db_name = ? AND label = ? AND label_lang = ?
                """, (db_name, label, lang))
                row = cursor.fetchone()
                return row['class_id'] if row else None
                
            elif label_type == "property":
                if not class_id:
                    raise ValueError("class_id is required for property lookup")
                cursor.execute("""
                    SELECT property_id FROM property_mappings 
                    WHERE db_name = ? AND class_id = ? AND label = ? AND label_lang = ?
                """, (db_name, class_id, label, lang))
                row = cursor.fetchone()
                return row['property_id'] if row else None
                
            elif label_type == "relationship":
                cursor.execute("""
                    SELECT predicate FROM relationship_mappings 
                    WHERE db_name = ? AND label = ? AND label_lang = ?
                """, (db_name, label, lang))
                row = cursor.fetchone()
                return row['predicate'] if row else None
            
            else:
                raise ValueError(f"Unknown label_type: {label_type}")
    
    def get_label_by_id(self, db_name: str, id_value: str,
                       label_type: str = "class", class_id: Optional[str] = None,
                       lang: str = 'ko') -> Optional[str]:
        """
        ID로 레이블 조회 (통합 메서드)
        
        Args:
            db_name: 데이터베이스 이름
            id_value: ID 값
            label_type: 레이블 타입 ("class", "property", "relationship")
            class_id: 클래스 ID (property 조회 시 필요)
            lang: 언어 코드
            
        Returns:
            레이블 또는 None
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if label_type == "class":
                cursor.execute("""
                    SELECT label FROM class_mappings 
                    WHERE db_name = ? AND class_id = ? AND label_lang = ?
                """, (db_name, id_value, lang))
                row = cursor.fetchone()
                return row['label'] if row else None
                
            elif label_type == "property":
                if not class_id:
                    raise ValueError("class_id is required for property lookup")
                cursor.execute("""
                    SELECT label FROM property_mappings 
                    WHERE db_name = ? AND class_id = ? AND property_id = ? AND label_lang = ?
                """, (db_name, class_id, id_value, lang))
                row = cursor.fetchone()
                return row['label'] if row else None
                
            elif label_type == "relationship":
                cursor.execute("""
                    SELECT label FROM relationship_mappings 
                    WHERE db_name = ? AND predicate = ? AND label_lang = ?
                """, (db_name, id_value, lang))
                row = cursor.fetchone()
                return row['label'] if row else None
            
            else:
                raise ValueError(f"Unknown label_type: {label_type}")
    
    def get_property_id_by_label(self, db_name: str, class_id: str,
                                label: str, lang: str = 'ko') -> Optional[str]:
        """
        속성 레이블로 ID 조회 (편의 메서드)
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            label: 속성 레이블
            lang: 언어 코드
            
        Returns:
            속성 ID 또는 None
        """
        return self.get_id_by_label(db_name, label, "property", class_id, lang)
    
    def convert_query_to_internal(self, db_name: str, query: Dict[str, Any], 
                                 lang: str = 'ko') -> Dict[str, Any]:
        """
        레이블 기반 쿼리를 내부 ID 기반으로 변환
        
        Args:
            db_name: 데이터베이스 이름
            query: 레이블 기반 쿼리
            lang: 언어 코드
            
        Returns:
            내부 ID 기반 쿼리
            
        Raises:
            LabelNotFoundError: 레이블을 찾을 수 없는 경우
        """
        # 클래스 레이블을 ID로 변환
        class_label = query.get('class_label') or query.get('class')
        class_id = self.get_id_by_label(db_name, class_label, "class", None, lang)
        
        if not class_id:
            raise LabelNotFoundError(class_label, "class")
        
        internal_query = {
            'class_id': class_id,
            'filters': [],
            'select': query.get('select'),
            'limit': query.get('limit'),
            'offset': query.get('offset'),
            'order_by': query.get('order_by'),
            'order_direction': query.get('order_direction')
        }
        
        # 필터 변환
        for filter_item in query.get('filters', []):
            field_label = filter_item.get('field')
            
            # 속성 레이블을 ID로 변환
            property_id = self.get_property_id_by_label(db_name, class_id, field_label, lang)
            if not property_id:
                # 관계일 수도 있으므로 확인
                predicate = self.get_id_by_label(db_name, field_label, "relationship", None, lang)
                if not predicate:
                    raise LabelNotFoundError(field_label, "field")
                property_id = predicate
            
            internal_filter = {
                'field': property_id,
                'operator': filter_item.get('operator'),
                'value': filter_item.get('value')
            }
            internal_query['filters'].append(internal_filter)
        
        # SELECT 필드 변환
        if internal_query['select']:
            internal_select = []
            for field_label in internal_query['select']:
                property_id = self.get_property_id_by_label(db_name, class_id, field_label, lang)
                if not property_id:
                    predicate = self.get_id_by_label(db_name, field_label, "relationship", None, lang)
                    if not predicate:
                        raise LabelNotFoundError(field_label, "select field")
                    property_id = predicate
                internal_select.append(property_id)
            internal_query['select'] = internal_select
        
        # ORDER BY 필드 변환
        if internal_query['order_by']:
            order_field = internal_query['order_by']
            property_id = self.get_property_id_by_label(db_name, class_id, order_field, lang)
            if not property_id:
                predicate = self.get_id_by_label(db_name, order_field, "relationship", None, lang)
                if not predicate:
                    raise LabelNotFoundError(order_field, "order by field")
                property_id = predicate
            internal_query['order_by'] = property_id
        
        return internal_query
    
    def convert_to_display(self, db_name: str, data: Dict[str, Any], 
                          lang: str = 'ko') -> Dict[str, Any]:
        """
        내부 ID 기반 데이터를 레이블 기반으로 변환
        
        Args:
            db_name: 데이터베이스 이름
            data: 내부 ID 기반 데이터
            lang: 언어 코드
            
        Returns:
            레이블 기반 데이터
        """
        if not data:
            return data
        
        display_data = data.copy()
        
        # 클래스 ID를 레이블로 변환
        if 'id' in display_data:
            class_id = display_data['id']
            class_label = self.get_label_by_id(db_name, class_id, "class", None, lang)
            if class_label:
                display_data['label'] = class_label
        
        # @id 필드 처리 (TerminusDB 형식)
        if '@id' in display_data:
            class_id = display_data['@id']
            class_label = self.get_label_by_id(db_name, class_id, "class", None, lang)
            if class_label:
                display_data['@label'] = class_label
        
        # 속성들을 레이블로 변환
        if 'properties' in display_data:
            for prop in display_data['properties']:
                if 'name' in prop:
                    property_label = self.get_label_by_id(
                        db_name, prop['name'], "property", display_data.get('id', ''), lang
                    )
                    if property_label:
                        prop['display_label'] = property_label
        
        # 관계들을 레이블로 변환
        if 'relationships' in display_data:
            for rel in display_data['relationships']:
                if 'predicate' in rel:
                    rel_label = self.get_label_by_id(
                        db_name, rel['predicate'], "relationship", None, lang
                    )
                    if rel_label:
                        rel['display_label'] = rel_label
        
        return display_data
    
    def update_mappings(self, db_name: str, ontology_data: Dict[str, Any]) -> None:
        """
        온톨로지 데이터로부터 모든 매핑 업데이트
        
        Args:
            db_name: 데이터베이스 이름
            ontology_data: 온톨로지 데이터
        """
        # 클래스 매핑 업데이트
        if 'id' in ontology_data and 'label' in ontology_data:
            self.register_class(
                db_name,
                ontology_data['id'],
                ontology_data['label'],
                ontology_data.get('description')
            )
        
        # 속성 매핑 업데이트
        for prop in ontology_data.get('properties', []):
            if 'name' in prop and 'label' in prop:
                self.register_property(
                    db_name,
                    ontology_data['id'],
                    prop['name'],
                    prop['label']
                )
        
        # 관계 매핑 업데이트
        for rel in ontology_data.get('relationships', []):
            if 'predicate' in rel and 'label' in rel:
                self.register_relationship(
                    db_name,
                    rel['predicate'],
                    rel['label']
                )
    
    def remove_class(self, db_name: str, class_id: str) -> None:
        """
        클래스 관련 모든 매핑 제거
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 클래스 매핑 삭제
            cursor.execute("""
                DELETE FROM class_mappings 
                WHERE db_name = ? AND class_id = ?
            """, (db_name, class_id))
            
            # 속성 매핑 삭제
            cursor.execute("""
                DELETE FROM property_mappings 
                WHERE db_name = ? AND class_id = ?
            """, (db_name, class_id))
            
            conn.commit()
            logger.info(f"Removed all mappings for class: {class_id}")
    
    def export_mappings(self, db_name: str) -> Dict[str, Any]:
        """
        특정 데이터베이스의 모든 매핑 내보내기
        
        Args:
            db_name: 데이터베이스 이름
            
        Returns:
            매핑 데이터
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # 클래스 매핑
            cursor.execute("""
                SELECT * FROM class_mappings WHERE db_name = ?
            """, (db_name,))
            classes = [dict(row) for row in cursor.fetchall()]
            
            # 속성 매핑
            cursor.execute("""
                SELECT * FROM property_mappings WHERE db_name = ?
            """, (db_name,))
            properties = [dict(row) for row in cursor.fetchall()]
            
            # 관계 매핑
            cursor.execute("""
                SELECT * FROM relationship_mappings WHERE db_name = ?
            """, (db_name,))
            relationships = [dict(row) for row in cursor.fetchall()]
            
            return {
                'db_name': db_name,
                'classes': classes,
                'properties': properties,
                'relationships': relationships,
                'exported_at': datetime.utcnow().isoformat()
            }
    
    def import_mappings(self, data: Dict[str, Any]) -> None:
        """
        매핑 데이터 가져오기
        
        Args:
            data: 매핑 데이터
        """
        db_name = data['db_name']
        
        # 클래스 매핑 가져오기
        for class_mapping in data.get('classes', []):
            self.register_class(
                db_name,
                class_mapping['class_id'],
                {class_mapping['label_lang']: class_mapping['label']},
                {class_mapping['label_lang']: class_mapping.get('description', '')}
            )
        
        # 속성 매핑 가져오기
        for prop_mapping in data.get('properties', []):
            self.register_property(
                db_name,
                prop_mapping['class_id'],
                prop_mapping['property_id'],
                {prop_mapping['label_lang']: prop_mapping['label']}
            )
        
        # 관계 매핑 가져오기
        for rel_mapping in data.get('relationships', []):
            self.register_relationship(
                db_name,
                rel_mapping['predicate'],
                {rel_mapping['label_lang']: rel_mapping['label']}
            )
        
        logger.info(f"Imported mappings for database: {db_name}")
    
    def _extract_labels(self, label: Any) -> Dict[str, str]:
        """
        레이블에서 언어별 텍스트 추출
        
        Args:
            label: 문자열 또는 MultiLingualText 또는 dict
            
        Returns:
            언어 코드를 키로 하는 딕셔너리
        """
        if isinstance(label, str):
            return {'ko': label}  # 기본 언어는 한국어
        
        if isinstance(label, dict):
            # MultiLingualText의 dict 형태
            return {k: v for k, v in label.items() if v}
        
        if isinstance(label, MultiLingualText):
            # MultiLingualText 객체
            return label.to_dict()
        
        if hasattr(label, 'dict'):
            # Pydantic 모델
            return {k: v for k, v in label.dict().items() if v}
        
        return {'ko': str(label)}