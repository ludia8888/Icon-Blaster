"""
쿼리 변환기 구현
레이블 기반 쿼리와 ID 기반 쿼리 간 변환을 담당
SRP: 오직 쿼리 변환만 담당
"""

import logging
from typing import Dict, List, Optional, Any
from copy import deepcopy

from services.core.interfaces import IQueryTransformer, ILabelMapperService
from domain.exceptions import QueryExecutionError

logger = logging.getLogger(__name__)


class TerminusQueryTransformer(IQueryTransformer):
    """
    TerminusDB 쿼리 변환기
    
    단일 책임: 레이블 기반 쿼리와 내부 ID 기반 쿼리 간 변환만 담당
    """
    
    def __init__(self, label_mapper: ILabelMapperService):
        """
        초기화
        
        Args:
            label_mapper: 레이블 매퍼 서비스
        """
        self.label_mapper = label_mapper
    
    def transform_label_query(self, db_name: str, label_query: Dict[str, Any],
                            language: str = "ko") -> Dict[str, Any]:
        """
        레이블 기반 쿼리를 내부 ID 기반으로 변환
        
        Args:
            db_name: 데이터베이스 이름
            label_query: 레이블 기반 쿼리
            language: 언어 코드
            
        Returns:
            ID 기반 쿼리
            
        Raises:
            QueryExecutionError: 변환 실패
        """
        try:
            # 쿼리 복사
            id_query = deepcopy(label_query)
            
            # 클래스 레이블을 ID로 변환
            if 'class_label' in id_query:
                class_label = id_query.pop('class_label')
                class_id = self.label_mapper.get_id_by_label(
                    db_name, 
                    class_label, 
                    "class",
                    None,
                    language
                )
                
                if not class_id:
                    raise QueryExecutionError(
                        f"Class with label '{class_label}' not found",
                        label_query
                    )
                
                id_query['class_id'] = class_id
            
            # 필터의 필드 레이블을 ID로 변환
            if 'filters' in id_query:
                id_query['filters'] = self._transform_filters(
                    db_name, 
                    id_query['filters'],
                    id_query.get('class_id', ''),
                    language
                )
            
            # SELECT 필드 레이블을 ID로 변환
            if 'select' in id_query:
                id_query['select'] = self._transform_select_fields(
                    db_name,
                    id_query['select'],
                    id_query.get('class_id', ''),
                    language
                )
            
            # ORDER BY 필드 레이블을 ID로 변환
            if 'order_by' in id_query:
                field_label = id_query['order_by']
                field_id = self.label_mapper.get_property_id_by_label(
                    db_name,
                    id_query.get('class_id', ''),  # Need class_id for property lookup
                    field_label,
                    language
                )
                
                if field_id:
                    id_query['order_by'] = field_id
            
            logger.debug(f"Transformed label query to ID query for '{db_name}'")
            
            return id_query
            
        except Exception as e:
            logger.error(f"Failed to transform label query: {e}")
            raise QueryExecutionError(
                f"Query transformation failed: {str(e)}",
                label_query
            )
    
    def transform_result(self, db_name: str, result: List[Dict[str, Any]],
                        language: str = "ko") -> List[Dict[str, Any]]:
        """
        쿼리 결과를 레이블 기반으로 변환
        
        Args:
            db_name: 데이터베이스 이름
            result: 쿼리 결과
            language: 언어 코드
            
        Returns:
            레이블 기반 결과
        """
        try:
            labeled_results = []
            
            for item in result:
                labeled_item = self._transform_result_item(
                    db_name,
                    item,
                    language
                )
                labeled_results.append(labeled_item)
            
            logger.debug(f"Transformed {len(result)} result items to label-based format")
            
            return labeled_results
            
        except Exception as e:
            logger.error(f"Failed to transform result: {e}")
            # 변환 실패 시 원본 반환
            return result
    
    def _transform_filters(self, db_name: str, filters: List[Dict[str, Any]], 
                          class_id: str, language: str) -> List[Dict[str, Any]]:
        """
        필터 목록 변환
        
        Args:
            db_name: 데이터베이스 이름
            filters: 필터 목록
            language: 언어 코드
            
        Returns:
            변환된 필터 목록
        """
        transformed_filters = []
        
        for filter_item in filters:
            transformed_filter = deepcopy(filter_item)
            
            # 필드 레이블을 ID로 변환
            if 'field_label' in transformed_filter:
                field_label = transformed_filter.pop('field_label')
                field_id = self.label_mapper.get_property_id_by_label(
                    db_name,
                    class_id,
                    field_label,
                    language
                )
                
                if field_id:
                    transformed_filter['field'] = field_id
                else:
                    # 필드를 찾을 수 없는 경우 원본 사용
                    transformed_filter['field'] = field_label
                    logger.warning(f"Field with label '{field_label}' not found, using as-is")
            
            # 값이 레이블인 경우 ID로 변환 (IN, NOT_IN 연산자 등)
            if 'value_labels' in transformed_filter:
                value_labels = transformed_filter.pop('value_labels')
                if isinstance(value_labels, list):
                    value_ids = []
                    for label in value_labels:
                        value_id = self.label_mapper.get_id_by_label(
                            db_name,
                            label,
                            "class",  # Assuming values are class references
                            None,
                            language
                        )
                        value_ids.append(value_id if value_id else label)
                    transformed_filter['value'] = value_ids
                else:
                    value_id = self.label_mapper.get_id_by_label(
                        db_name,
                        value_labels,
                        "class",  # Assuming values are class references
                        None,
                        language
                    )
                    transformed_filter['value'] = value_id if value_id else value_labels
            
            transformed_filters.append(transformed_filter)
        
        return transformed_filters
    
    def _transform_select_fields(self, db_name: str, fields: List[str], 
                                class_id: str, language: str) -> List[str]:
        """
        SELECT 필드 목록 변환
        
        Args:
            db_name: 데이터베이스 이름
            fields: 필드 레이블 목록
            language: 언어 코드
            
        Returns:
            필드 ID 목록
        """
        field_ids = []
        
        for field_label in fields:
            field_id = self.label_mapper.get_property_id_by_label(
                db_name,
                class_id,
                field_label,
                language
            )
            
            if field_id:
                field_ids.append(field_id)
            else:
                # 필드를 찾을 수 없는 경우 원본 사용
                field_ids.append(field_label)
                logger.warning(f"Field with label '{field_label}' not found, using as-is")
        
        return field_ids
    
    def _transform_result_item(self, db_name: str, item: Dict[str, Any], 
                              language: str) -> Dict[str, Any]:
        """
        개별 결과 아이템 변환
        
        Args:
            db_name: 데이터베이스 이름
            item: 결과 아이템
            language: 언어 코드
            
        Returns:
            레이블 기반 아이템
        """
        labeled_item = {}
        
        for key, value in item.items():
            # 메타데이터 필드는 그대로 유지
            if key.startswith('@'):
                labeled_item[key] = value
                continue
            
            # 필드 ID를 레이블로 변환
            field_label = self.label_mapper.get_label_by_id(
                db_name,
                key,
                "property",  # Assuming fields are properties
                None,  # We don't have class_id context here
                language
            )
            
            if field_label:
                labeled_key = field_label
            else:
                labeled_key = key
            
            # 값이 ID인 경우 레이블로 변환
            if isinstance(value, str) and self._is_ontology_id(value):
                value_label = self.label_mapper.get_label_by_id(
                    db_name,
                    value,
                    "class",  # Ontology IDs are typically classes
                    None,
                    language
                )
                
                if value_label:
                    labeled_item[labeled_key] = {
                        'id': value,
                        'label': value_label
                    }
                else:
                    labeled_item[labeled_key] = value
            else:
                labeled_item[labeled_key] = value
        
        return labeled_item
    
    def _is_ontology_id(self, value: str) -> bool:
        """
        값이 온톨로지 ID인지 확인
        
        Args:
            value: 확인할 값
            
        Returns:
            온톨로지 ID 여부
        """
        # 간단한 휴리스틱: 대문자로 시작하거나 특정 패턴을 가진 경우
        if not isinstance(value, str):
            return False
        
        # 시스템 프리픽스 체크
        system_prefixes = ['sys:', 'rdf:', 'rdfs:', 'owl:', 'xsd:']
        if any(value.startswith(prefix) for prefix in system_prefixes):
            return True
        
        # 대문자로 시작하는 경우 (예: Product, Customer)
        if value and value[0].isupper():
            return True
        
        return False
    
    def create_label_query_builder(self) -> 'LabelQueryBuilder':
        """
        레이블 기반 쿼리 빌더 생성
        
        Returns:
            레이블 쿼리 빌더
        """
        return LabelQueryBuilder(self)


class LabelQueryBuilder:
    """
    레이블 기반 쿼리 빌더
    개발자가 아닌 사용자를 위한 편의 기능
    """
    
    def __init__(self, transformer: TerminusQueryTransformer):
        """
        초기화
        
        Args:
            transformer: 쿼리 변환기
        """
        self.transformer = transformer
        self.query = {}
    
    def from_class(self, class_label: str) -> 'LabelQueryBuilder':
        """
        클래스 레이블 설정
        
        Args:
            class_label: 클래스 레이블
            
        Returns:
            self (체이닝)
        """
        self.query['class_label'] = class_label
        return self
    
    def select(self, *field_labels: str) -> 'LabelQueryBuilder':
        """
        선택할 필드 레이블 설정
        
        Args:
            field_labels: 필드 레이블들
            
        Returns:
            self (체이닝)
        """
        self.query['select'] = list(field_labels)
        return self
    
    def where(self, field_label: str, operator: str, value: Any) -> 'LabelQueryBuilder':
        """
        필터 조건 추가
        
        Args:
            field_label: 필드 레이블
            operator: 연산자
            value: 값
            
        Returns:
            self (체이닝)
        """
        if 'filters' not in self.query:
            self.query['filters'] = []
        
        filter_item = {
            'field_label': field_label,
            'operator': operator,
            'value': value
        }
        
        self.query['filters'].append(filter_item)
        return self
    
    def order_by(self, field_label: str, direction: str = 'asc') -> 'LabelQueryBuilder':
        """
        정렬 설정
        
        Args:
            field_label: 필드 레이블
            direction: 정렬 방향 ('asc' 또는 'desc')
            
        Returns:
            self (체이닝)
        """
        self.query['order_by'] = field_label
        self.query['order_direction'] = direction
        return self
    
    def limit(self, count: int) -> 'LabelQueryBuilder':
        """
        결과 개수 제한
        
        Args:
            count: 개수
            
        Returns:
            self (체이닝)
        """
        self.query['limit'] = count
        return self
    
    def offset(self, count: int) -> 'LabelQueryBuilder':
        """
        오프셋 설정
        
        Args:
            count: 오프셋
            
        Returns:
            self (체이닝)
        """
        self.query['offset'] = count
        return self
    
    def build(self) -> Dict[str, Any]:
        """
        쿼리 빌드
        
        Returns:
            레이블 기반 쿼리
        """
        return self.query