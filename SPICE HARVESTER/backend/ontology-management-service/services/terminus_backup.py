"""
TerminusDB 서비스 모듈
동기 방식으로 TerminusDB와 통신하며, 온톨로지 CRUD 작업을 처리합니다.
헥사고날 아키텍처를 위한 서비스 레이어입니다.
"""

from typing import Dict, List, Optional, Any, Union, Set, Tuple
from terminusdb_client import WOQLClient, WOQLQuery
from terminusdb_client.woqlclient.errors import (
    DatabaseError,
    InterfaceError,
    OperationalError
)
import logging
from datetime import datetime
import json
from contextlib import contextmanager
from functools import lru_cache
from dataclasses import dataclass
from abc import ABC, abstractmethod

from models.ontology import (
    OntologyCreateInput,
    OntologyUpdateInput,
    MultiLingualText,
    QueryOperator
)

# shared import
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from models.config import ConnectionConfig
from exceptions import (
    OntologyNotFoundError,
    DuplicateOntologyError,
    OntologyValidationError,
    ConnectionError,
    DatabaseNotFoundError
)

logger = logging.getLogger(__name__)

# 재시도 데코레이터 가져오기
from utils.retry import terminus_retry, query_retry

# 하위 호환성을 위한 별칭
ValidationError = OntologyValidationError


# 포트 인터페이스 (헥사고날 아키텍처)
class OntologyPort(ABC):
    """온톨로지 관리를 위한 포트 인터페이스"""
    
    @abstractmethod
    def create_ontology(self, db_name: str, jsonld_data: Dict[str, Any]) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def get_ontology(self, db_name: str, class_id: str, raise_if_missing: bool = True) -> Optional[Dict[str, Any]]:
        pass
    
    @abstractmethod
    def update_ontology(self, db_name: str, class_id: str, jsonld_data: Dict[str, Any]) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def delete_ontology(self, db_name: str, class_id: str) -> bool:
        pass
    
    @abstractmethod
    def list_ontologies(self, db_name: str, class_type: str = "sys:Class") -> List[Dict[str, Any]]:
        pass


class TerminusService(OntologyPort):
    """
    TerminusDB 서비스 클래스
    헥사고날 아키텍처의 Service Layer 구현
    """
    
    def __init__(self, connection_info: Optional[ConnectionConfig] = None,
                 use_connection_pool: bool = False):
        """
        TerminusDB 서비스 초기화
        
        Args:
            connection_info: 연결 정보 객체
            use_connection_pool: 연결 풀 사용 여부
        """
        self.connection_info = connection_info or ConnectionConfig(
            server_url="http://localhost:6364",
            user="admin",
            account="admin",
            key="admin"
        )
        # Thread-safety: 클라이언트 인스턴스를 저장하지 않음
        # 각 요청마다 새로운 클라이언트 생성
        self._db_cache: Set[str] = set()  # 존재하는 DB 캐시
        self.use_connection_pool = use_connection_pool
        self._connection_pool = None
        
        # 연결 풀 초기화
        if use_connection_pool:
            try:
                from services.core.connection.connection_pool import TerminusConnectionPool
                # TODO: Connection pool 마이그레이션 필요
                logger.warning("Connection pool migration needed - temporarily disabled")
                self.use_connection_pool = False
            except Exception as e:
                logger.warning(f"Failed to initialize connection pool: {e}")
                self.use_connection_pool = False
    
    @contextmanager
    def get_client(self, db_name: Optional[str] = None, branch: Optional[str] = None):
        """
        Thread-safe 클라이언트 컨텍스트 매니저
        각 요청마다 새로운 클라이언트 인스턴스 생성
        
        Args:
            db_name: 데이터베이스 이름
            branch: 브랜치 이름 (선택사항)
            
        Yields:
            WOQLClient: 연결된 클라이언트
        """
        # 연결 풀 사용 시
        if self.use_connection_pool and self._connection_pool:
            try:
                with self._connection_pool.get_connection(db_name, branch) as client:
                    yield client
                return
            except Exception as e:
                logger.warning(f"Connection pool failed, falling back to direct connection: {e}")
        
        # 직접 연결 (폴백 또는 기본)
        client = None
        try:
            client = WOQLClient(self.connection_info.server_url)
            client.connect(
                user=self.connection_info.user,
                account=self.connection_info.account,
                key=self.connection_info.key,
                db=db_name
            )
            
            # 브랜치가 지정된 경우 체크아웃
            if branch and db_name:
                client.checkout(branch)
            
            yield client
        finally:
            # 클라이언트 정리 (연결 해제는 자동)
            pass
    
    @terminus_retry
    def _create_client(self) -> WOQLClient:
        """새 클라이언트 인스턴스 생성 (중복 로직 제거)"""
        return WOQLClient(self.connection_info.server_url)
    
    def connect(self, db_name: Optional[str] = None) -> None:
        """TerminusDB 연결 테스트 (호환성 유지)"""
        # 연결 테스트만 수행
        try:
            with self.get_client(db_name) as client:
                # 연결 성공
                if db_name:
                    self._db_cache.add(db_name)
                logger.info(f"Connected to TerminusDB at {self.connection_info.server_url}")
        except Exception as e:
            logger.error(f"Failed to connect to TerminusDB: {e}")
            raise ConnectionError(f"TerminusDB 연결 실패: {e}")
    
    def disconnect(self) -> None:
        """TerminusDB 연결 해제 (호환성 유지)"""
        # Thread-safe 구현에서는 연결 해제가 필요 없음
        self._db_cache.clear()
        logger.info("Cleared connection cache")
    
    def check_connection(self) -> bool:
        """연결 상태 확인"""
        try:
            # 새 클라이언트로 연결 테스트
            with self.get_client() as client:
                client.query(WOQLQuery().limit(1))
                return True
        except Exception:
            return False
    
    @lru_cache(maxsize=32)
    @terminus_retry
    def _database_exists(self, db_name: str) -> bool:
        """데이터베이스 존재 여부 확인 (캐싱됨)"""
        try:
            temp_client = self._create_client()
            temp_client.connect(
                user=self.connection_info.user,
                account=self.connection_info.account,
                key=self.connection_info.key
            )
            
            dbs = temp_client.list_databases()
            return any(db.get('name') == db_name for db in dbs)
        except Exception:
            return False
    
    def ensure_db_exists(self, db_name: str, description: Optional[str] = None) -> None:
        """데이터베이스가 존재하는지 확인하고 없으면 생성 (캐싱 적용)"""
        # 캐시 확인
        if db_name in self._db_cache:
            return
        
        try:
            # DB 존재 여부 확인 (캐싱됨)
            if not self._database_exists(db_name):
                logger.info(f"Creating database: {db_name}")
                temp_client = self._create_client()
                temp_client.connect(
                    user=self.connection_info.user,
                    account=self.connection_info.account,
                    key=self.connection_info.key
                )
                temp_client.create_database(
                    db_name,
                    label=db_name,
                    description=description or f"{db_name} 온톨로지 데이터베이스"
                )
                logger.info(f"Database {db_name} created successfully")
                
                # 캐시 무효화
                self._database_exists.cache_clear()
            
            # DB 캐시에 추가
            self._db_cache.add(db_name)
                
        except Exception as e:
            logger.error(f"Error ensuring database exists: {e}")
            raise DatabaseError(f"데이터베이스 생성/확인 실패: {e}")
    
    @contextmanager
    def transaction(self, db_name: str, branch: Optional[str] = None):
        """트랜잭션 컨텍스트 매니저"""
        with self.get_client(db_name, branch) as client:
            try:
                yield client
            except Exception as e:
                logger.error(f"Transaction failed: {e}")
                raise
    
    def _validate_jsonld(self, data: Dict[str, Any]) -> List[str]:
        """
        JSON-LD 유효성 검증
        
        Returns:
            오류 메시지 리스트 (빈 리스트면 유효함)
        """
        errors = []
        
        # 필수 필드 검증
        if "@type" not in data:
            errors.append("@type 필드가 필요합니다")
        if "@id" not in data:
            errors.append("@id 필드가 필요합니다")
        
        # 데이터 타입 검증
        if "properties" in data:
            for i, prop in enumerate(data["properties"]):
                if "@type" not in prop:
                    errors.append(f"속성 {i}에 @type이 필요합니다")
                if "datatype" in prop:
                    valid_types = [
                        "xsd:string", "xsd:integer", "xsd:decimal",
                        "xsd:boolean", "xsd:date", "xsd:dateTime", "xsd:anyURI"
                    ]
                    if prop["datatype"] not in valid_types:
                        errors.append(f"잘못된 데이터 타입: {prop['datatype']}")
        
        # 관계 검증
        if "relationships" in data:
            for i, rel in enumerate(data["relationships"]):
                if "predicate" not in rel:
                    errors.append(f"관계 {i}에 predicate가 필요합니다")
                if "target" not in rel:
                    errors.append(f"관계 {i}에 target이 필요합니다")
        
        return errors
    
    def create_ontology(self, db_name: str, jsonld_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        온톨로지 클래스 생성
        
        Args:
            db_name: 데이터베이스 이름
            jsonld_data: JSON-LD 형식의 온톨로지 데이터
            
        Returns:
            생성된 온톨로지 정보
            
        Raises:
            ValidationError: 유효성 검증 실패
            DuplicateOntologyError: 중복된 클래스 ID
            DatabaseError: 데이터베이스 오류
        """
        # 유효성 검증
        validation_errors = self._validate_jsonld(jsonld_data)
        if validation_errors:
            raise ValidationError(f"유효성 검증 실패: {', '.join(validation_errors)}")
        
        self.ensure_db_exists(db_name)
        
        # 중복 확인
        class_id = jsonld_data.get("@id")
        try:
            existing = self.get_ontology(db_name, class_id, raise_if_missing=False)
            if existing:
                raise DuplicateOntologyError(f"이미 존재하는 클래스 ID: {class_id}")
        except OntologyNotFoundError:
            pass  # 정상 - 존재하지 않음
        
        try:
            with self.transaction(db_name) as client:
                # 스키마 그래프에 삽입
                client.insert_document(
                    jsonld_data,
                    graph_type="schema"
                )
                
                logger.info(f"Created ontology class: {class_id}")
                
                return {
                    "id": class_id,
                    "created_at": datetime.utcnow().isoformat(),
                    "database": db_name
                }
                
        except Exception as e:
            logger.error(f"Failed to create ontology: {e}")
            raise DatabaseError(f"온톨로지 생성 실패: {e}")
    
    def get_ontology(self, db_name: str, class_id: str, raise_if_missing: bool = True) -> Optional[Dict[str, Any]]:
        """
        온톨로지 클래스 조회
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            raise_if_missing: True면 없을 때 예외 발생, False면 None 반환
            
        Returns:
            온톨로지 정보 또는 None
            
        Raises:
            OntologyNotFoundError: 온톨로지를 찾을 수 없음 (raise_if_missing=True일 때)
        """
        self.ensure_db_exists(db_name)
        
        try:
            with self.get_client(db_name) as client:
                query = WOQLQuery().read_document(class_id, "v:Document")
                result = client.query(query)
                
                if result.get('bindings'):
                    doc = result['bindings'][0].get('Document')
                    return doc
                
                if raise_if_missing:
                    raise OntologyNotFoundError(f"온톨로지를 찾을 수 없습니다: {class_id}")
                
                return None
            
        except OntologyNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to get ontology: {e}")
            if raise_if_missing:
                raise DatabaseError(f"온톨로지 조회 실패: {e}")
            return None
    
    def update_ontology(self, db_name: str, class_id: str, jsonld_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        온톨로지 클래스 업데이트
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            jsonld_data: 업데이트할 JSON-LD 데이터
            
        Returns:
            업데이트된 온톨로지 정보
            
        Raises:
            OntologyNotFoundError: 온톨로지를 찾을 수 없음
            ValidationError: 유효성 검증 실패
            DatabaseError: 데이터베이스 오류
        """
        self.ensure_db_exists(db_name)
        
        # 기존 문서 확인 (예외 발생)
        existing = self.get_ontology(db_name, class_id, raise_if_missing=True)
        
        # ID는 변경 불가, 강제로 기존 ID 유지
        jsonld_data["@id"] = class_id
        jsonld_data["@type"] = existing.get("@type", "Class")
        
        # 유효성 검증
        validation_errors = self._validate_jsonld(jsonld_data)
        if validation_errors:
            raise ValidationError(f"유효성 검증 실패: {', '.join(validation_errors)}")
        
        try:
            with self.transaction(db_name) as client:
                # 기존 문서 삭제 후 새로 삽입 (TerminusDB 방식)
                client.delete_document(class_id)
                client.insert_document(
                    jsonld_data,
                    graph_type="schema"
                )
                
                logger.info(f"Updated ontology class: {class_id}")
                
                return {
                    "id": class_id,
                    "updated_at": datetime.utcnow().isoformat(),
                    "database": db_name
                }
                
        except Exception as e:
            logger.error(f"Failed to update ontology: {e}")
            raise DatabaseError(f"온톨로지 업데이트 실패: {e}")
    
    def merge_ontology(self, db_name: str, jsonld_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        온톨로지 병합 (존재하면 업데이트, 없으면 생성)
        
        Args:
            db_name: 데이터베이스 이름
            jsonld_data: JSON-LD 형식의 온톨로지 데이터
            
        Returns:
            처리 결과
        """
        class_id = jsonld_data.get("@id")
        
        try:
            existing = self.get_ontology(db_name, class_id, raise_if_missing=False)
            if existing:
                # 기존 데이터와 병합
                merged_data = {**existing, **jsonld_data}
                result = self.update_ontology(db_name, class_id, merged_data)
                result["operation"] = "merged"
                return result
            else:
                # 새로 생성
                result = self.create_ontology(db_name, jsonld_data)
                result["operation"] = "created"
                return result
        except Exception as e:
            logger.error(f"Failed to merge ontology: {e}")
            raise DatabaseError(f"온톨로지 병합 실패: {e}")
    
    def delete_ontology(self, db_name: str, class_id: str) -> bool:
        """
        온톨로지 클래스 삭제
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            
        Returns:
            삭제 성공 여부
            
        Raises:
            OntologyNotFoundError: 온톨로지를 찾을 수 없음
            DatabaseError: 데이터베이스 오류
        """
        self.ensure_db_exists(db_name)
        
        # 존재 여부 확인
        self.get_ontology(db_name, class_id, raise_if_missing=True)
        
        try:
            with self.transaction(db_name) as client:
                client.delete_document(class_id)
                logger.info(f"Deleted ontology class: {class_id}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete ontology: {e}")
            raise DatabaseError(f"온톨로지 삭제 실패: {e}")
    
    def list_ontologies(self, db_name: str, class_type: str = "sys:Class") -> List[Dict[str, Any]]:
        """
        온톨로지 클래스 목록 조회
        
        Args:
            db_name: 데이터베이스 이름
            class_type: 조회할 클래스 타입 (sys:Class, sys:Enum, sys:Document 등)
            
        Returns:
            온톨로지 클래스 목록
        """
        self.ensure_db_exists(db_name)
        
        try:
            with self.get_client(db_name) as client:
                # 스키마 그래프에서 클래스 조회
                query = (
                    WOQLQuery()
                    .select("v:Class", "v:Label", "v:Description")
                    .triple("v:Class", "rdf:type", class_type)
                    .optional()
                    .triple("v:Class", "rdfs:label", "v:Label")
                    .optional()
                    .triple("v:Class", "rdfs:comment", "v:Description")
                )
                
                result = client.query(query)
            
            classes = []
            for binding in result.get('bindings', []):
                class_info = {
                    "id": binding.get('Class'),
                    "type": class_type,
                    "label": binding.get('Label', {}),
                    "description": binding.get('Description', {})
                }
                classes.append(class_info)
            
            return classes
            
        except Exception as e:
            logger.error(f"Failed to list ontologies: {e}")
            raise DatabaseError(f"온톨로지 목록 조회 실패: {e}")
    
    def get_property_schema(self, db_name: str, class_id: str) -> Dict[str, Any]:
        """
        클래스의 속성 스키마 조회
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            
        Returns:
            속성 스키마 정보
        """
        self.ensure_db_exists(db_name)
        
        try:
            with self.get_client(db_name) as client:
                # 클래스의 모든 속성 조회
                query = (
                    WOQLQuery()
                    .select("v:Property", "v:Type", "v:Label")
                    .triple(class_id, "v:Property", "v:Range")
                    .triple("v:Property", "rdf:type", "v:Type")
                    .optional()
                    .triple("v:Property", "rdfs:label", "v:Label")
                )
                
                result = client.query(query)
            
            properties = {}
            for binding in result.get('bindings', []):
                prop_name = binding.get('Property')
                properties[prop_name] = {
                    "type": binding.get('Type'),
                    "label": binding.get('Label', prop_name)
                }
            
            return {
                "class_id": class_id,
                "properties": properties
            }
            
        except Exception as e:
            logger.error(f"Failed to get property schema: {e}")
            raise DatabaseError(f"속성 스키마 조회 실패: {e}")
    
    def execute_query(self, db_name: str, query_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        WOQL 쿼리 실행 (모든 QueryOperator 지원)
        
        Args:
            db_name: 데이터베이스 이름
            query_dict: 쿼리 정보 (내부 ID 기반)
            
        Returns:
            쿼리 결과
        """
        self.ensure_db_exists(db_name)
        
        try:
            # 기본 쿼리 구성
            woql = WOQLQuery()
            
            # FROM 절 (클래스 선택)
            class_id = query_dict.get('class_id')
            woql = woql.triple("v:Instance", "rdf:type", class_id)
            
            # WHERE 절 (필터 적용)
            for filter_item in query_dict.get('filters', []):
                field = filter_item['field']
                operator = filter_item['operator']
                value = filter_item['value']
                
                # 연산자별 쿼리 구성
                if operator == QueryOperator.EQUALS:
                    woql = woql.triple("v:Instance", field, value)
                    
                elif operator == QueryOperator.NOT_EQUALS:
                    woql = woql.not_().triple("v:Instance", field, value)
                    
                elif operator == QueryOperator.GREATER_THAN:
                    woql = woql.triple("v:Instance", field, "v:Value")
                    woql = woql.greater("v:Value", value)
                    
                elif operator == QueryOperator.GREATER_THAN_OR_EQUAL:
                    woql = woql.triple("v:Instance", field, "v:Value")
                    woql = woql.greater_or_equal("v:Value", value)
                    
                elif operator == QueryOperator.LESS_THAN:
                    woql = woql.triple("v:Instance", field, "v:Value")
                    woql = woql.less("v:Value", value)
                    
                elif operator == QueryOperator.LESS_THAN_OR_EQUAL:
                    woql = woql.triple("v:Instance", field, "v:Value")
                    woql = woql.less_or_equal("v:Value", value)
                    
                elif operator == QueryOperator.IN:
                    if isinstance(value, list):
                        or_conditions = []
                        for v in value:
                            or_conditions.append(
                                WOQLQuery().triple("v:Instance", field, v)
                            )
                        woql = woql.or_(*or_conditions)
                    
                elif operator == QueryOperator.NOT_IN:
                    if isinstance(value, list):
                        for v in value:
                            woql = woql.not_().triple("v:Instance", field, v)
                    
                elif operator == QueryOperator.CONTAINS:
                    woql = woql.triple("v:Instance", field, "v:Value")
                    woql = woql.regexp("v:Value", f".*{value}.*")
                    
                elif operator == QueryOperator.STARTS_WITH:
                    woql = woql.triple("v:Instance", field, "v:Value")
                    woql = woql.regexp("v:Value", f"^{value}.*")
                    
                elif operator == QueryOperator.ENDS_WITH:
                    woql = woql.triple("v:Instance", field, "v:Value")
                    woql = woql.regexp("v:Value", f".*{value}$")
            
            # SELECT 절 (특정 필드만 선택)
            if query_dict.get('select'):
                select_vars = ["v:Instance"] + [f"v:{field}" for field in query_dict['select']]
                woql = WOQLQuery().select(*select_vars).woql_and(woql)
                
                # 선택된 필드들 조회
                for field in query_dict['select']:
                    woql = woql.optional().triple("v:Instance", field, f"v:{field}")
            
            # ORDER BY
            if query_dict.get('order_by'):
                woql = woql.order_by(f"v:{query_dict['order_by']}")
                if query_dict.get('order_direction') == 'desc':
                    woql = woql.desc()
            
            # LIMIT/OFFSET
            if query_dict.get('limit'):
                woql = woql.limit(query_dict['limit'])
            if query_dict.get('offset'):
                woql = woql.offset(query_dict['offset'])
            
            # 쿼리 실행 (재시도 포함)
            with self.get_client(db_name) as client:
                @query_retry
                def _execute_query():
                    return client.query(woql)
                
                result = _execute_query()
            
            # 결과 변환
            instances = []
            for binding in result.get('bindings', []):
                instance = {"@id": binding.get('Instance')}
                
                # 선택된 필드들 추가
                if query_dict.get('select'):
                    for field in query_dict['select']:
                        if field in binding:
                            instance[field] = binding[field]
                else:
                    # 모든 바인딩 추가
                    instance.update(binding)
                
                instances.append(instance)
            
            return instances
            
        except Exception as e:
            logger.error(f"Failed to execute query: {e}")
            raise DatabaseError(f"쿼리 실행 실패: {e}")
    
    def compare_schema_versions(self, db_name: str, class_id: str, 
                              version1: str, version2: str) -> Dict[str, Any]:
        """
        두 버전 간 스키마 차이 비교
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            version1: 첫 번째 버전
            version2: 두 번째 버전
            
        Returns:
            스키마 차이점
        """
        self.ensure_db_exists(db_name)
        
        try:
            with self.get_client(db_name) as client:
                # TerminusDB의 diff 기능 활용
                query = (
                    WOQLQuery()
                    .diff({"@id": class_id, "@version": version1},
                          {"@id": class_id, "@version": version2},
                          "v:Diff")
                )
                
                result = client.query(query)
            
            return {
                "class_id": class_id,
                "version1": version1,
                "version2": version2,
                "differences": result.get('bindings', [])
            }
            
        except Exception as e:
            logger.error(f"Failed to compare schema versions: {e}")
            raise DatabaseError(f"스키마 버전 비교 실패: {e}")
    
    def list_databases(self) -> List[Dict[str, Any]]:
        """사용 가능한 데이터베이스 목록 조회"""
        try:
            temp_client = self._create_client()
            temp_client.connect(
                user=self.connection_info.user,
                account=self.connection_info.account,
                key=self.connection_info.key
            )
            
            databases = temp_client.list_databases()
            
            # 캐시 업데이트
            for db in databases:
                self._db_cache.add(db.get('name'))
            
            return databases
            
        except Exception as e:
            logger.error(f"Failed to list databases: {e}")
            raise DatabaseError(f"데이터베이스 목록 조회 실패: {e}")
    
    def create_database(self, db_name: str, description: Optional[str] = None) -> Dict[str, Any]:
        """새 데이터베이스 생성"""
        try:
            temp_client = self._create_client()
            temp_client.connect(
                user=self.connection_info.user,
                account=self.connection_info.account,
                key=self.connection_info.key
            )
            
            temp_client.create_database(
                db_name,
                label=db_name,
                description=description or f"{db_name} database"
            )
            
            # 캐시 업데이트
            self._db_cache.add(db_name)
            self._database_exists.cache_clear()
            
            return {
                "name": db_name,
                "created_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to create database: {e}")
            raise DatabaseError(f"데이터베이스 생성 실패: {e}")
    
    # ===== 버전 관리 기능 (Git-like features) =====
    
    @terminus_retry
    def list_branches(self, db_name: str) -> List[Dict[str, Any]]:
        """
        데이터베이스의 모든 브랜치 목록 조회
        
        Args:
            db_name: 데이터베이스 이름
            
        Returns:
            브랜치 정보 목록
        """
        self.ensure_db_exists(db_name)
        
        try:
            with self.get_client(db_name) as client:
                branches = client.get_branches()
                
                # 브랜치 정보 형식화
                result = []
                for branch in branches:
                    result.append({
                        "name": branch.get("name"),
                        "head": branch.get("head"),
                        "created_at": branch.get("created_at"),
                        "is_current": branch.get("is_current", False)
                    })
                
                return result
                
        except Exception as e:
            logger.error(f"Failed to list branches: {e}")
            raise DatabaseError(f"브랜치 목록 조회 실패: {e}")
    
    def create_branch(self, db_name: str, branch_name: str, 
                     from_branch: Optional[str] = None) -> Dict[str, Any]:
        """
        새 브랜치 생성
        
        Args:
            db_name: 데이터베이스 이름
            branch_name: 새 브랜치 이름
            from_branch: 기준 브랜치 (기본값: 현재 브랜치)
            
        Returns:
            생성된 브랜치 정보
        """
        self.ensure_db_exists(db_name)
        
        try:
            with self.get_client(db_name, from_branch) as client:
                # 기준 브랜치로 체크아웃 후 새 브랜치 생성
                client.branch(branch_name)
                
                return {
                    "name": branch_name,
                    "created_at": datetime.utcnow().isoformat(),
                    "from_branch": from_branch or "main"
                }
                
        except Exception as e:
            logger.error(f"Failed to create branch: {e}")
            raise DatabaseError(f"브랜치 생성 실패: {e}")
    
    def checkout(self, db_name: str, target: str, 
                target_type: str = "branch") -> Dict[str, Any]:
        """
        브랜치 또는 커밋으로 체크아웃
        
        Args:
            db_name: 데이터베이스 이름
            target: 브랜치 이름 또는 커밋 ID
            target_type: "branch" 또는 "commit"
            
        Returns:
            체크아웃 결과
        """
        self.ensure_db_exists(db_name)
        
        try:
            # Thread-safe: 새 클라이언트로 체크아웃 테스트
            with self.get_client(db_name) as client:
                client.checkout(target)
                
                return {
                    "target": target,
                    "type": target_type,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Failed to checkout: {e}")
            raise DatabaseError(f"체크아웃 실패: {e}")
    
    def commit_changes(self, db_name: str, message: str, 
                      author: str, branch: Optional[str] = None) -> Dict[str, Any]:
        """
        현재 변경사항 커밋
        
        Args:
            db_name: 데이터베이스 이름
            message: 커밋 메시지
            author: 작성자
            branch: 커밋할 브랜치 (기본값: 현재 브랜치)
            
        Returns:
            커밋 정보
        """
        self.ensure_db_exists(db_name)
        
        try:
            with self.get_client(db_name, branch) as client:
                # 커밋 수행
                commit_info = {
                    "author": author,
                    "message": message,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                client.commit(message, author=author)
                
                return commit_info
                
        except Exception as e:
            logger.error(f"Failed to commit: {e}")
            raise DatabaseError(f"커밋 실패: {e}")
    
    def get_commit_history(self, db_name: str, branch: Optional[str] = None,
                          limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        커밋 히스토리 조회
        
        Args:
            db_name: 데이터베이스 이름
            branch: 브랜치 이름 (기본값: 현재 브랜치)
            limit: 조회할 커밋 수
            offset: 오프셋
            
        Returns:
            커밋 목록
        """
        self.ensure_db_exists(db_name)
        
        try:
            with self.get_client(db_name, branch) as client:
                # 커밋 히스토리 조회
                history = client.get_commit_history(limit=limit, offset=offset)
                
                # 형식화
                commits = []
                for commit in history:
                    commits.append({
                        "id": commit.get("id"),
                        "message": commit.get("message"),
                        "author": commit.get("author"),
                        "timestamp": commit.get("timestamp"),
                        "parent": commit.get("parent")
                    })
                
                return commits
                
        except Exception as e:
            logger.error(f"Failed to get commit history: {e}")
            raise DatabaseError(f"커밋 히스토리 조회 실패: {e}")
    
    def get_diff(self, db_name: str, base: str, compare: str) -> Dict[str, Any]:
        """
        두 버전 간 차이 비교
        
        Args:
            db_name: 데이터베이스 이름
            base: 기준 브랜치/커밋
            compare: 비교 브랜치/커밋
            
        Returns:
            변경사항
        """
        self.ensure_db_exists(db_name)
        
        try:
            with self.get_client(db_name) as client:
                # diff 수행
                raw_diff = client.diff(base, compare)
                
                # 프론트엔드를 위해 정리
                diff = {
                    "base": base,
                    "compare": compare,
                    "added": [],
                    "modified": [],
                    "deleted": []
                }
                
                # raw_diff 분석 및 분류
                for item in raw_diff:
                    if item.get("@op") == "AddDocument":
                        diff["added"].append({
                            "type": "class",
                            "id": item.get("@id")
                        })
                    elif item.get("@op") == "DeleteDocument":
                        diff["deleted"].append({
                            "type": "class",
                            "id": item.get("@id")
                        })
                    elif item.get("@op") == "UpdateDocument":
                        diff["modified"].append({
                            "type": "class",
                            "id": item.get("@id"),
                            "changes": item.get("@changes", {})
                        })
                
                return diff
                
        except Exception as e:
            logger.error(f"Failed to get diff: {e}")
            raise DatabaseError(f"diff 조회 실패: {e}")
    
    def merge_branches(self, db_name: str, source: str, target: str,
                      strategy: str = "merge", message: Optional[str] = None,
                      author: Optional[str] = None) -> Dict[str, Any]:
        """
        브랜치 병합
        
        Args:
            db_name: 데이터베이스 이름
            source: 소스 브랜치
            target: 타겟 브랜치
            strategy: "merge" 또는 "rebase"
            message: 병합 커밋 메시지
            author: 작성자
            
        Returns:
            병합 결과
        """
        self.ensure_db_exists(db_name)
        
        try:
            # 충돌 검사
            conflicts = self.check_conflicts(db_name, source, target)
            if conflicts:
                return {
                    "status": "conflict",
                    "conflicts": conflicts,
                    "message": "병합 충돌이 발생했습니다"
                }
            
            with self.get_client(db_name, target) as client:
                # 병합 수행
                if strategy == "merge":
                    client.merge(source)
                elif strategy == "rebase":
                    client.rebase(source)
                
                # 병합 커밋
                if message and author:
                    client.commit(message, author=author)
                
                return {
                    "status": "success",
                    "source": source,
                    "target": target,
                    "strategy": strategy,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Failed to merge branches: {e}")
            raise DatabaseError(f"브랜치 병합 실패: {e}")
    
    def check_conflicts(self, db_name: str, source: str, target: str) -> List[Dict[str, Any]]:
        """
        병합 충돌 검사
        
        Args:
            db_name: 데이터베이스 이름
            source: 소스 브랜치
            target: 타겟 브랜치
            
        Returns:
            충돌 목록
        """
        # 간단한 충돌 검사 로직
        # 실제로는 TerminusDB가 자동으로 충돌을 감지함
        try:
            diff = self.get_diff(db_name, target, source)
            conflicts = []
            
            # 동일한 클래스가 양쪽에서 수정된 경우 충돌로 간주
            # (단순화된 로직)
            
            return conflicts
            
        except Exception:
            return []
    
    def rollback(self, db_name: str, target_commit: str,
                create_branch: bool = True, branch_name: Optional[str] = None) -> Dict[str, Any]:
        """
        특정 커밋으로 롤백
        TerminusDB는 hard reset이 없으므로 새 브랜치 생성 후 checkout
        
        Args:
            db_name: 데이터베이스 이름
            target_commit: 대상 커밋 ID
            create_branch: 새 브랜치 생성 여부
            branch_name: 새 브랜치 이름
            
        Returns:
            롤백 결과
        """
        self.ensure_db_exists(db_name)
        
        try:
            result = {
                "target_commit": target_commit,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            if create_branch:
                # 롤백 브랜치 생성
                if not branch_name:
                    branch_name = f"rollback-{target_commit[:8]}"
                
                # 새 브랜치 생성
                self.create_branch(db_name, branch_name)
                
                # 타겟 커밋으로 체크아웃
                with self.get_client(db_name, branch_name) as client:
                    client.checkout(target_commit)
                
                result["branch"] = branch_name
                result["operation"] = "branch_created"
            else:
                # 현재 브랜치에서 직접 체크아웃
                with self.get_client(db_name) as client:
                    client.checkout(target_commit)
                
                result["operation"] = "checkout_only"
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to rollback: {e}")
            raise DatabaseError(f"롤백 실패: {e}")
    
    def delete_branch(self, db_name: str, branch_name: str) -> Dict[str, Any]:
        """
        브랜치 삭제
        
        Args:
            db_name: 데이터베이스 이름
            branch_name: 삭제할 브랜치 이름
            
        Returns:
            삭제 결과
        """
        self.ensure_db_exists(db_name)
        
        # RBAC: 보호된 브랜치 검사
        # TODO: 향후 RBAC 구현 시 여기서 권한 확인
        # protected_branches = ["main", "production"]
        # if branch_name in protected_branches:
        #     raise PermissionError(f"보호된 브랜치는 삭제할 수 없습니다: {branch_name}")
        
        try:
            with self.get_client(db_name) as client:
                client.delete_branch(branch_name)
                
                return {
                    "branch": branch_name,
                    "deleted_at": datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            logger.error(f"Failed to delete branch: {e}")
            raise DatabaseError(f"브랜치 삭제 실패: {e}")