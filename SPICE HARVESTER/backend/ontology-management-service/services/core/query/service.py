"""
쿼리 실행 서비스 구현
WOQL 쿼리 실행과 스키마 조회를 전담하는 서비스
SRP: 오직 쿼리 실행과 스키마 조회만 담당
"""

import logging
from typing import Dict, List, Optional, Any, Union
from functools import lru_cache

from terminusdb_client import WOQLQuery

from services.core.interfaces import (
    IQueryService,
    IQueryBuilder,
    IConnectionManager,
    IDatabaseService
)
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'shared'))
from exceptions import (
    QueryExecutionError,
    DomainException
)
from models.ontology import QueryOperator

logger = logging.getLogger(__name__)


class TerminusQueryService(IQueryService):
    """
    TerminusDB 쿼리 실행 서비스
    
    단일 책임: 쿼리 실행과 스키마 조회만 담당
    """
    
    def __init__(self, connection_manager: IConnectionManager,
                 database_service: IDatabaseService,
                 query_builder: IQueryBuilder):
        """
        초기화
        
        Args:
            connection_manager: 연결 관리자
            database_service: 데이터베이스 서비스
            query_builder: 쿼리 빌더
        """
        self.connection_manager = connection_manager
        self.database_service = database_service
        self.query_builder = query_builder
        self._schema_cache: Dict[str, Dict[str, Any]] = {}
    
    def execute_query(self, db_name: str, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        쿼리 실행
        
        Args:
            db_name: 데이터베이스 이름
            query: 쿼리 정보 (클래스, 필터, 정렬 등)
            
        Returns:
            쿼리 결과
            
        Raises:
            QueryExecutionError: 쿼리 실행 실패
        """
        # 데이터베이스 존재 확인
        self.database_service.ensure_database_exists(db_name)
        
        # 쿼리 유효성 검증
        validation_errors = self._validate_query(query)
        if validation_errors:
            raise QueryExecutionError(
                f"Invalid query: {', '.join(validation_errors)}",
                query
            )
        
        try:
            # WOQL 쿼리 빌드
            woql_query = self.query_builder.build_select_query(
                class_id=query.get('class_id'),
                filters=query.get('filters'),
                fields=query.get('select'),
                order_by=query.get('order_by'),
                limit=query.get('limit'),
                offset=query.get('offset')
            )
            
            # 쿼리 실행
            with self.connection_manager.get_connection(db_name) as client:
                result = client.query(woql_query)
            
            # 결과 변환
            instances = self._transform_query_result(result, query)
            
            logger.info(f"Executed query on class '{query.get('class_id')}' in '{db_name}', returned {len(instances)} results")
            
            return instances
            
        except Exception as e:
            logger.error(f"Failed to execute query in '{db_name}': {e}")
            raise QueryExecutionError(str(e), query)
    
    def get_schema(self, db_name: str, class_id: str) -> Dict[str, Any]:
        """
        클래스 스키마 조회
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            
        Returns:
            스키마 정보
            
        Raises:
            QueryExecutionError: 스키마 조회 실패
        """
        # 데이터베이스 존재 확인
        self.database_service.ensure_database_exists(db_name)
        
        # 캐시 확인
        cache_key = f"{db_name}:{class_id}"
        if cache_key in self._schema_cache:
            logger.debug(f"Retrieved schema for '{class_id}' from cache")
            return self._schema_cache[cache_key]
        
        try:
            with self.connection_manager.get_connection(db_name) as client:
                # 클래스 정보 조회
                class_info = self._get_class_info(client, class_id)
                
                # 속성 스키마 조회
                properties = self._get_property_schema(client, class_id)
                
                # 관계 스키마 조회
                relationships = self._get_relationship_schema(client, class_id)
                
                schema = {
                    "class_id": class_id,
                    "class_info": class_info,
                    "properties": properties,
                    "relationships": relationships,
                    "db_name": db_name
                }
                
                # 캐시 저장
                self._schema_cache[cache_key] = schema
                
                logger.debug(f"Retrieved schema for class '{class_id}' from '{db_name}'")
                
                return schema
                
        except Exception as e:
            logger.error(f"Failed to get schema for '{class_id}' from '{db_name}': {e}")
            raise QueryExecutionError(f"Failed to get schema: {str(e)}")
    
    def search(self, db_name: str, search_term: str, 
              class_ids: Optional[List[str]] = None,
              limit: int = 50) -> List[Dict[str, Any]]:
        """
        전체 텍스트 검색
        
        Args:
            db_name: 데이터베이스 이름
            search_term: 검색어
            class_ids: 검색할 클래스 ID 목록 (None이면 전체)
            limit: 결과 개수 제한
            
        Returns:
            검색 결과
        """
        # 데이터베이스 존재 확인
        self.database_service.ensure_database_exists(db_name)
        
        if not search_term or not search_term.strip():
            return []
        
        try:
            results = []
            
            # 클래스별로 검색
            if not class_ids:
                # 모든 클래스 검색
                class_ids = self._get_all_classes(db_name)
            
            for class_id in class_ids:
                # 각 클래스에 대해 CONTAINS 필터로 검색
                query = {
                    'class_id': class_id,
                    'filters': [
                        {
                            'field': 'rdfs:label',
                            'operator': QueryOperator.CONTAINS,
                            'value': search_term
                        }
                    ],
                    'limit': limit
                }
                
                try:
                    class_results = self.execute_query(db_name, query)
                    results.extend(class_results)
                except Exception as e:
                    logger.warning(f"Failed to search in class '{class_id}': {e}")
            
            # 중복 제거 및 정렬
            unique_results = self._deduplicate_results(results)
            
            logger.info(f"Search for '{search_term}' in '{db_name}' returned {len(unique_results)} results")
            
            return unique_results[:limit]
            
        except Exception as e:
            logger.error(f"Failed to search in '{db_name}': {e}")
            raise QueryExecutionError(f"Search failed: {str(e)}")
    
    def _validate_query(self, query: Dict[str, Any]) -> List[str]:
        """
        쿼리 유효성 검증
        
        Args:
            query: 쿼리 정보
            
        Returns:
            오류 메시지 리스트
        """
        errors = []
        
        # 필수 필드 확인
        if not query.get('class_id'):
            errors.append("class_id is required")
        
        # 필터 검증
        if 'filters' in query:
            if not isinstance(query['filters'], list):
                errors.append("filters must be a list")
            else:
                for i, filter_item in enumerate(query['filters']):
                    if not isinstance(filter_item, dict):
                        errors.append(f"filter {i} must be a dictionary")
                        continue
                    
                    if not filter_item.get('field'):
                        errors.append(f"filter {i} missing 'field'")
                    if not filter_item.get('operator'):
                        errors.append(f"filter {i} missing 'operator'")
                    if 'value' not in filter_item:
                        errors.append(f"filter {i} missing 'value'")
        
        # 정렬 검증
        if 'order_by' in query and not isinstance(query['order_by'], str):
            errors.append("order_by must be a string")
        
        # 페이지네이션 검증
        if 'limit' in query:
            if not isinstance(query['limit'], int) or query['limit'] <= 0:
                errors.append("limit must be a positive integer")
        
        if 'offset' in query:
            if not isinstance(query['offset'], int) or query['offset'] < 0:
                errors.append("offset must be a non-negative integer")
        
        return errors
    
    def _transform_query_result(self, result: Dict[str, Any], 
                               query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        쿼리 결과 변환
        
        Args:
            result: 원시 쿼리 결과
            query: 원본 쿼리
            
        Returns:
            변환된 결과
        """
        instances = []
        
        for binding in result.get('bindings', []):
            instance = {"@id": binding.get('Instance')}
            
            # 선택된 필드들만 포함
            if query.get('select'):
                for field in query['select']:
                    if field in binding:
                        instance[field] = binding[field]
            else:
                # 모든 바인딩 포함
                instance.update(binding)
            
            # 메타데이터 추가
            instance['@class'] = query.get('class_id')
            
            instances.append(instance)
        
        return instances
    
    def _get_class_info(self, client, class_id: str) -> Dict[str, Any]:
        """
        클래스 정보 조회
        
        Args:
            client: TerminusDB 클라이언트
            class_id: 클래스 ID
            
        Returns:
            클래스 정보
        """
        query = WOQLQuery().select("v:Label", "v:Comment").where(
            WOQLQuery().triple(class_id, "rdfs:label", "v:Label"),
            WOQLQuery().optional().triple(class_id, "rdfs:comment", "v:Comment")
        )
        
        result = client.query(query)
        
        if result.get('bindings'):
            binding = result['bindings'][0]
            return {
                "label": binding.get('Label'),
                "description": binding.get('Comment')
            }
        
        return {}
    
    def _get_property_schema(self, client, class_id: str) -> Dict[str, Any]:
        """
        속성 스키마 조회
        
        Args:
            client: TerminusDB 클라이언트
            class_id: 클래스 ID
            
        Returns:
            속성 스키마
        """
        query = (
            WOQLQuery()
            .select("v:Property", "v:Type", "v:Label", "v:Range")
            .where(
                WOQLQuery().triple(class_id, "v:Property", "v:Range"),
                WOQLQuery().triple("v:Property", "rdf:type", "v:Type"),
                WOQLQuery().optional().triple("v:Property", "rdfs:label", "v:Label")
            )
        )
        
        result = client.query(query)
        
        properties = {}
        for binding in result.get('bindings', []):
            prop_name = binding.get('Property')
            properties[prop_name] = {
                "type": binding.get('Type'),
                "range": binding.get('Range'),
                "label": binding.get('Label', prop_name)
            }
        
        return properties
    
    def _get_relationship_schema(self, client, class_id: str) -> Dict[str, Any]:
        """
        관계 스키마 조회
        
        Args:
            client: TerminusDB 클라이언트
            class_id: 클래스 ID
            
        Returns:
            관계 스키마
        """
        # 관계는 속성의 특별한 형태이므로 ObjectProperty 타입 필터링
        query = (
            WOQLQuery()
            .select("v:Property", "v:Range", "v:Label")
            .where(
                WOQLQuery().triple(class_id, "v:Property", "v:Range"),
                WOQLQuery().triple("v:Property", "rdf:type", "owl:ObjectProperty"),
                WOQLQuery().optional().triple("v:Property", "rdfs:label", "v:Label")
            )
        )
        
        result = client.query(query)
        
        relationships = {}
        for binding in result.get('bindings', []):
            rel_name = binding.get('Property')
            relationships[rel_name] = {
                "target": binding.get('Range'),
                "label": binding.get('Label', rel_name)
            }
        
        return relationships
    
    def _get_all_classes(self, db_name: str) -> List[str]:
        """
        모든 클래스 ID 조회
        
        Args:
            db_name: 데이터베이스 이름
            
        Returns:
            클래스 ID 목록
        """
        try:
            with self.connection_manager.get_connection(db_name) as client:
                query = WOQLQuery().select("v:Class").triple("v:Class", "rdf:type", "sys:Class")
                result = client.query(query)
                
                return [binding.get('Class') for binding in result.get('bindings', [])]
                
        except Exception as e:
            logger.error(f"Failed to get all classes from database '{db_name}': {e}")
            raise QueryError(f"Unable to retrieve classes from database: {str(e)}")
    
    def _deduplicate_results(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        결과 중복 제거
        
        Args:
            results: 검색 결과
            
        Returns:
            중복 제거된 결과
        """
        seen = set()
        unique_results = []
        
        for result in results:
            result_id = result.get('@id')
            if result_id and result_id not in seen:
                seen.add(result_id)
                unique_results.append(result)
        
        return unique_results
    
    def clear_cache(self, db_name: Optional[str] = None) -> None:
        """
        스키마 캐시 삭제
        
        Args:
            db_name: 데이터베이스 이름 (None이면 전체 삭제)
        """
        if db_name:
            # 특정 DB의 캐시만 삭제
            keys_to_delete = [k for k in self._schema_cache if k.startswith(f"{db_name}:")]
            for key in keys_to_delete:
                del self._schema_cache[key]
        else:
            # 전체 캐시 삭제
            self._schema_cache.clear()
        
        logger.debug(f"Cleared schema cache for {'all databases' if not db_name else db_name}")


class TerminusQueryBuilder(IQueryBuilder):
    """
    TerminusDB 쿼리 빌더
    
    단일 책임: WOQL 쿼리 생성만 담당
    """
    
    def build_select_query(self, class_id: str, 
                          filters: Optional[List[Dict[str, Any]]] = None,
                          fields: Optional[List[str]] = None,
                          order_by: Optional[str] = None,
                          limit: Optional[int] = None,
                          offset: Optional[int] = None) -> Any:
        """
        SELECT 쿼리 생성
        
        Args:
            class_id: 클래스 ID
            filters: 필터 조건들
            fields: 선택할 필드들
            order_by: 정렬 필드
            limit: 결과 개수 제한
            offset: 오프셋
            
        Returns:
            WOQL 쿼리 객체
        """
        # 기본 쿼리 구성
        woql = WOQLQuery()
        
        # FROM 절 (클래스 선택)
        woql = woql.triple("v:Instance", "rdf:type", class_id)
        
        # WHERE 절 (필터 적용)
        if filters:
            for filter_item in filters:
                filter_condition = self.build_filter(
                    filter_item['field'],
                    filter_item['operator'],
                    filter_item['value']
                )
                woql = woql.where(filter_condition)
        
        # SELECT 절 (특정 필드만 선택)
        if fields:
            select_vars = ["v:Instance"] + [f"v:{field}" for field in fields]
            woql = WOQLQuery().select(*select_vars).where(woql)
            
            # 선택된 필드들 조회
            for field in fields:
                woql = woql.optional().triple("v:Instance", field, f"v:{field}")
        else:
            # 모든 필드 선택
            woql = WOQLQuery().select("v:Instance").where(woql)
        
        # ORDER BY
        if order_by:
            woql = woql.order_by(f"v:{order_by}")
        
        # LIMIT/OFFSET
        if limit is not None:
            woql = woql.limit(limit)
        if offset is not None:
            woql = woql.offset(offset)
        
        return woql
    
    def build_filter(self, field: str, operator: str, 
                    value: Union[str, int, float, List]) -> Any:
        """
        필터 조건 생성
        
        Args:
            field: 필드명
            operator: 연산자
            value: 값
            
        Returns:
            필터 조건
        """
        woql = WOQLQuery()
        
        # 연산자별 처리
        if operator == QueryOperator.EQUALS:
            return woql.triple("v:Instance", field, value)
            
        elif operator == QueryOperator.NOT_EQUALS:
            return woql.not_().triple("v:Instance", field, value)
            
        elif operator == QueryOperator.GREATER_THAN:
            woql = woql.triple("v:Instance", field, "v:Value")
            return woql.greater("v:Value", value)
            
        elif operator == QueryOperator.GREATER_THAN_OR_EQUAL:
            woql = woql.triple("v:Instance", field, "v:Value")
            return woql.greater_or_equal("v:Value", value)
            
        elif operator == QueryOperator.LESS_THAN:
            woql = woql.triple("v:Instance", field, "v:Value")
            return woql.less("v:Value", value)
            
        elif operator == QueryOperator.LESS_THAN_OR_EQUAL:
            woql = woql.triple("v:Instance", field, "v:Value")
            return woql.less_or_equal("v:Value", value)
            
        elif operator == QueryOperator.IN:
            if isinstance(value, list):
                or_conditions = []
                for v in value:
                    or_conditions.append(WOQLQuery().triple("v:Instance", field, v))
                return woql.or_(*or_conditions)
            else:
                return woql.triple("v:Instance", field, value)
                
        elif operator == QueryOperator.NOT_IN:
            if isinstance(value, list):
                and_conditions = []
                for v in value:
                    and_conditions.append(woql.not_().triple("v:Instance", field, v))
                return woql.and_(*and_conditions)
            else:
                return woql.not_().triple("v:Instance", field, value)
                
        elif operator == QueryOperator.CONTAINS:
            woql = woql.triple("v:Instance", field, "v:Value")
            return woql.regexp("v:Value", f".*{value}.*", "i")  # Case insensitive
            
        elif operator == QueryOperator.STARTS_WITH:
            woql = woql.triple("v:Instance", field, "v:Value")
            return woql.regexp("v:Value", f"^{value}.*", "i")
            
        elif operator == QueryOperator.ENDS_WITH:
            woql = woql.triple("v:Instance", field, "v:Value")
            return woql.regexp("v:Value", f".*{value}$", "i")
            
        elif operator == QueryOperator.EXISTS:
            return woql.triple("v:Instance", field, "v:Value")
            
        elif operator == QueryOperator.NOT_EXISTS:
            return woql.not_().triple("v:Instance", field, "v:Value")
            
        else:
            raise ValueError(f"Unsupported operator: {operator}")
    
    def build_aggregate_query(self, class_id: str, 
                            aggregations: List[Dict[str, Any]],
                            group_by: Optional[List[str]] = None) -> Any:
        """
        집계 쿼리 생성
        
        Args:
            class_id: 클래스 ID
            aggregations: 집계 정의 (field, function)
            group_by: 그룹핑 필드
            
        Returns:
            WOQL 쿼리 객체
        """
        woql = WOQLQuery()
        
        # 기본 클래스 선택
        woql = woql.triple("v:Instance", "rdf:type", class_id)
        
        # GROUP BY 처리
        if group_by:
            for field in group_by:
                woql = woql.triple("v:Instance", field, f"v:{field}")
        
        # 집계 함수 적용
        for agg in aggregations:
            field = agg.get('field')
            func = agg.get('function')
            alias = agg.get('alias', f"{func}_{field}")
            
            if func == 'count':
                woql = woql.count("v:Instance", f"v:{alias}")
            elif func == 'sum':
                woql = woql.sum(f"v:{field}", f"v:{alias}")
            elif func == 'avg':
                woql = woql.avg(f"v:{field}", f"v:{alias}")
            elif func == 'min':
                woql = woql.min(f"v:{field}", f"v:{alias}")
            elif func == 'max':
                woql = woql.max(f"v:{field}", f"v:{alias}")
        
        return woql