"""
TerminusDB 서비스 모듈 - Facade Pattern
기존 인터페이스를 유지하면서 내부적으로 리팩토링된 서비스들을 사용합니다.
"""

from typing import Dict, List, Optional, Any, Union, Set, Tuple
from terminusdb_client import WOQLClient, WOQLQuery
from terminusdb_client.errors import (
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
from container import ServiceContainer
from services.core.config import ServiceConfig, ConnectionConfig

logger = logging.getLogger(__name__)

# 재시도 데코레이터 가져오기
try:
    from utils.retry import terminus_retry, query_retry
except ImportError:
    # 재시도 기능 없이 실행 (fallback)
    terminus_retry = lambda f: f
    query_retry = lambda f: f


@dataclass
class ConnectionInfo:
    """연결 정보 데이터 클래스 (하위 호환성)"""
    server_url: str
    user: str
    account: str
    key: str
    
    def to_connection_config(self) -> ConnectionConfig:
        """ConnectionConfig로 변환"""
        return ConnectionConfig(
            server_url=self.server_url,
            user=self.user,
            account=self.account,
            key=self.key
        )
    
    
class OntologyNotFoundError(Exception):
    """온톨로지를 찾을 수 없을 때 발생하는 예외"""
    pass


class DuplicateOntologyError(Exception):
    """중복된 온톨로지 ID일 때 발생하는 예외"""
    pass


class ValidationError(Exception):
    """유효성 검증 실패시 발생하는 예외"""
    pass


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
    TerminusDB 서비스 Facade
    기존 인터페이스를 유지하면서 내부적으로 리팩토링된 서비스들을 사용합니다.
    """
    
    def __init__(self, connection_info: Optional[ConnectionInfo] = None,
                 use_connection_pool: bool = False):
        """
        TerminusDB 서비스 초기화
        
        Args:
            connection_info: 연결 정보 객체
            use_connection_pool: 연결 풀 사용 여부
        """
        self.connection_info = connection_info or ConnectionInfo(
            server_url="http://localhost:6364",
            user="admin",
            account="admin",
            key="admin"
        )
        
        # 서비스 컨테이너 설정
        self._container = ServiceContainer()
        
        # 서비스 설정
        config = ServiceConfig(
            connection=self.connection_info.to_connection_config(),
            use_connection_pool=use_connection_pool
        )
        self._container.configure(config)
        
        # 서비스들 초기화
        self._connection_manager = self._container.get_connection_manager()
        self._database_service = self._container.get_database_service()
        self._ontology_repository = self._container.get_ontology_repository()
        self._branch_service = self._container.get_branch_service()
        self._version_service = self._container.get_version_service()
        self._query_service = self._container.get_query_service()
        self._label_mapper = self._container.get_label_mapper_service()
        
        # 하위 호환성을 위한 속성
        self._db_cache: Set[str] = set()
        self.use_connection_pool = use_connection_pool
        self._connection_pool = None
        self.current_db: Optional[str] = None
    
    @contextmanager
    def get_client(self, db_name: Optional[str] = None, branch: Optional[str] = None):
        """
        Thread-safe 클라이언트 컨텍스트 매니저 (하위 호환성)
        
        Args:
            db_name: 데이터베이스 이름
            branch: 브랜치 이름 (선택사항)
            
        Yields:
            WOQLClient: 연결된 클라이언트
        """
        # 새로운 ConnectionManager 사용
        with self._connection_manager.get_connection(db_name, branch) as client:
            yield client
    
    @terminus_retry
    def _create_client(self) -> WOQLClient:
        """새 클라이언트 인스턴스 생성 (하위 호환성)"""
        # ConnectionManager가 내부적으로 처리
        return WOQLClient(self.connection_info.server_url)
    
    def connect(self, db_name: Optional[str] = None) -> None:
        """TerminusDB 연결 테스트 (호환성 유지)"""
        try:
            self._connection_manager.test_connection()
            if db_name:
                self._db_cache.add(db_name)
                self.current_db = db_name
            logger.info(f"Connected to TerminusDB")
        except Exception as e:
            logger.error(f"Failed to connect to TerminusDB: {e}")
            raise ConnectionError(f"TerminusDB 연결 실패: {e}")
    
    def disconnect(self) -> None:
        """TerminusDB 연결 해제 (호환성 유지)"""
        self._connection_manager.close()
        self._db_cache.clear()
        self.current_db = None
        logger.info("Disconnected from TerminusDB")
    
    def check_connection(self) -> bool:
        """연결 상태 확인"""
        try:
            return self._connection_manager.test_connection()
        except Exception:
            return False
    
    @lru_cache(maxsize=32)
    @terminus_retry
    def _database_exists(self, db_name: str) -> bool:
        """데이터베이스 존재 여부 확인 (하위 호환성)"""
        return self._database_service.exists(db_name)
    
    def ensure_db_exists(self, db_name: str, description: Optional[str] = None) -> None:
        """데이터베이스가 존재하는지 확인하고 없으면 생성"""
        # 캐시 확인
        if db_name in self._db_cache:
            return
        
        try:
            # DatabaseService 사용
            self._database_service.ensure_exists(
                db_name, 
                description or f"{db_name} 온톨로지 데이터베이스"
            )
            
            # DB 캐시에 추가
            self._db_cache.add(db_name)
            self.current_db = db_name
                
        except Exception as e:
            logger.error(f"Error ensuring database exists: {e}")
            raise DatabaseError(f"데이터베이스 생성/확인 실패: {e}")
    
    @contextmanager
    def transaction(self, db_name: str, branch: Optional[str] = None):
        """트랜잭션 컨텍스트 매니저 (하위 호환성)"""
        with self._connection_manager.get_connection(db_name, branch) as client:
            try:
                yield client
            except Exception as e:
                logger.error(f"Transaction failed: {e}")
                raise
    
    def _validate_jsonld(self, data: Dict[str, Any]) -> List[str]:
        """
        JSON-LD 유효성 검증 (하위 호환성)
        
        Returns:
            오류 메시지 리스트 (빈 리스트면 유효함)
        """
        # OntologyValidator 서비스 사용
        from services.core.domain.models import OntologyDefinition
        
        try:
            # JSON-LD를 OntologyDefinition으로 변환
            ontology = OntologyDefinition(
                id=data.get("@id", ""),
                type=data.get("@type", "Class"),
                label=data.get("rdfs:label", {}),
                description=data.get("rdfs:comment", {}),
                properties=data.get("properties", []),
                relationships=data.get("relationships", [])
            )
            
            # Validator 사용
            is_valid, errors = self._ontology_repository._validator.validate(ontology)
            return errors if not is_valid else []
            
        except Exception as e:
            return [str(e)]
    
    def create_ontology(self, db_name: str, jsonld_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        온톨로지 클래스 생성 (하위 호환성)
        
        Args:
            db_name: 데이터베이스 이름
            jsonld_data: JSON-LD 형식의 온톨로지 데이터
            
        Returns:
            생성된 온톨로지 정보
        """
        try:
            # OntologyRepository 사용
            from services.core.domain.models import OntologyDefinition
            
            # JSON-LD를 OntologyDefinition으로 변환
            ontology = OntologyDefinition(
                id=jsonld_data.get("@id"),
                type=jsonld_data.get("@type", "Class"),
                label=jsonld_data.get("rdfs:label", {}),
                description=jsonld_data.get("rdfs:comment", {}),
                properties=jsonld_data.get("properties", []),
                relationships=jsonld_data.get("relationships", [])
            )
            
            result = self._ontology_repository.create(db_name, ontology)
            
            return {
                "id": result.id,
                "created_at": datetime.utcnow().isoformat(),
                "database": db_name
            }
            
        except Exception as e:
            # 예외 타입 매핑 (하위 호환성)
            if "already exists" in str(e):
                raise DuplicateOntologyError(str(e))
            elif "validation" in str(e).lower():
                raise ValidationError(str(e))
            else:
                raise DatabaseError(f"온톨로지 생성 실패: {e}")
    
    def get_ontology(self, db_name: str, class_id: str, raise_if_missing: bool = True) -> Optional[Dict[str, Any]]:
        """
        온톨로지 클래스 조회 (하위 호환성)
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            raise_if_missing: True면 없을 때 예외 발생, False면 None 반환
            
        Returns:
            온톨로지 정보 또는 None
        """
        try:
            result = self._ontology_repository.get(db_name, class_id)
            if result:
                # OntologyDefinition을 JSON-LD 형식으로 변환
                return {
                    "@id": result.id,
                    "@type": result.type,
                    "rdfs:label": result.label,
                    "rdfs:comment": result.description,
                    "properties": result.properties,
                    "relationships": result.relationships
                }
            elif raise_if_missing:
                raise OntologyNotFoundError(f"온톨로지를 찾을 수 없습니다: {class_id}")
            return None
            
        except Exception as e:
            if "not found" in str(e).lower() and raise_if_missing:
                raise OntologyNotFoundError(str(e))
            elif raise_if_missing:
                raise DatabaseError(f"온톨로지 조회 실패: {e}")
            return None
    
    def update_ontology(self, db_name: str, class_id: str, jsonld_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        온톨로지 클래스 업데이트 (하위 호환성)
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            jsonld_data: 업데이트할 JSON-LD 데이터
            
        Returns:
            업데이트된 온톨로지 정보
        """
        try:
            from services.core.domain.models import OntologyDefinition
            
            # JSON-LD를 OntologyDefinition으로 변환
            ontology = OntologyDefinition(
                id=class_id,  # ID는 변경 불가
                type=jsonld_data.get("@type", "Class"),
                label=jsonld_data.get("rdfs:label", {}),
                description=jsonld_data.get("rdfs:comment", {}),
                properties=jsonld_data.get("properties", []),
                relationships=jsonld_data.get("relationships", [])
            )
            
            result = self._ontology_repository.update(db_name, class_id, ontology)
            
            return {
                "id": result.id,
                "updated_at": datetime.utcnow().isoformat(),
                "database": db_name
            }
            
        except Exception as e:
            if "not found" in str(e).lower():
                raise OntologyNotFoundError(str(e))
            elif "validation" in str(e).lower():
                raise ValidationError(str(e))
            else:
                raise DatabaseError(f"온톨로지 업데이트 실패: {e}")
    
    def merge_ontology(self, db_name: str, jsonld_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        온톨로지 병합 (존재하면 업데이트, 없으면 생성) - 하위 호환성
        
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
        온톨로지 클래스 삭제 (하위 호환성)
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            
        Returns:
            삭제 성공 여부
        """
        try:
            result = self._ontology_repository.delete(db_name, class_id)
            return result
            
        except Exception as e:
            if "not found" in str(e).lower():
                raise OntologyNotFoundError(str(e))
            else:
                raise DatabaseError(f"온톨로지 삭제 실패: {e}")
    
    def list_ontologies(self, db_name: str, class_type: str = "sys:Class") -> List[Dict[str, Any]]:
        """
        온톨로지 클래스 목록 조회 (하위 호환성)
        
        Args:
            db_name: 데이터베이스 이름
            class_type: 조회할 클래스 타입 (sys:Class, sys:Enum, sys:Document 등)
            
        Returns:
            온톨로지 클래스 목록
        """
        try:
            results = self._ontology_repository.list_all(db_name, class_type)
            
            # OntologyDefinition 목록을 JSON-LD 형식으로 변환
            classes = []
            for ontology in results:
                class_info = {
                    "id": ontology.id,
                    "type": ontology.type,
                    "label": ontology.label,
                    "description": ontology.description
                }
                classes.append(class_info)
            
            return classes
            
        except Exception as e:
            logger.error(f"Failed to list ontologies: {e}")
            raise DatabaseError(f"온톨로지 목록 조회 실패: {e}")
    
    def get_property_schema(self, db_name: str, class_id: str) -> Dict[str, Any]:
        """
        클래스의 속성 스키마 조회 (하위 호환성)
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            
        Returns:
            속성 스키마 정보
        """
        try:
            # QueryService를 사용하여 스키마 조회
            schema = self._query_service.get_schema(db_name)
            
            # 특정 클래스의 스키마만 선택
            if class_id in schema:
                return {
                    "class_id": class_id,
                    "properties": schema[class_id]
                }
            else:
                # 클래스가 없으면 빈 스키마 반환
                return {
                    "class_id": class_id,
                    "properties": {}
                }
            
        except Exception as e:
            logger.error(f"Failed to get property schema: {e}")
            raise DatabaseError(f"속성 스키마 조회 실패: {e}")
    
    def execute_query(self, db_name: str, query_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        WOQL 쿼리 실행 (하위 호환성)
        
        Args:
            db_name: 데이터베이스 이름
            query_dict: 쿼리 정보 (내부 ID 기반)
            
        Returns:
            쿼리 결과
        """
        try:
            # QueryService 사용
            return self._query_service.execute_query(db_name, query_dict)
            
        except Exception as e:
            logger.error(f"Failed to execute query: {e}")
            raise DatabaseError(f"쿼리 실행 실패: {e}")
    
    def compare_schema_versions(self, db_name: str, class_id: str, 
                              version1: str, version2: str) -> Dict[str, Any]:
        """
        두 버전 간 스키마 차이 비교 (하위 호환성)
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            version1: 첫 번째 버전
            version2: 두 번째 버전
            
        Returns:
            스키마 차이점
        """
        try:
            # 버전 서비스의 diff 기능 사용
            diff_result = self._version_service.get_diff(db_name, version1, version2)
            
            # 특정 클래스의 차이점만 필터링
            class_differences = []
            for item in diff_result.get("added", []) + diff_result.get("modified", []) + diff_result.get("deleted", []):
                if item.get("id") == class_id:
                    class_differences.append(item)
            
            return {
                "class_id": class_id,
                "version1": version1,
                "version2": version2,
                "differences": class_differences
            }
            
        except Exception as e:
            logger.error(f"Failed to compare schema versions: {e}")
            raise DatabaseError(f"스키마 버전 비교 실패: {e}")
    
    def list_databases(self) -> List[Dict[str, Any]]:
        """사용 가능한 데이터베이스 목록 조회 (하위 호환성)"""
        try:
            databases = self._database_service.list_all()
            
            # 캐시 업데이트
            for db in databases:
                self._db_cache.add(db.get('name'))
            
            return databases
            
        except Exception as e:
            logger.error(f"Failed to list databases: {e}")
            raise DatabaseError(f"데이터베이스 목록 조회 실패: {e}")
    
    def create_database(self, db_name: str, description: Optional[str] = None) -> Dict[str, Any]:
        """새 데이터베이스 생성 (하위 호환성)"""
        try:
            result = self._database_service.create(
                db_name,
                description or f"{db_name} database"
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
        새 브랜치 생성 (하위 호환성)
        
        Args:
            db_name: 데이터베이스 이름
            branch_name: 새 브랜치 이름
            from_branch: 기준 브랜치 (기본값: 현재 브랜치)
            
        Returns:
            생성된 브랜치 정보
        """
        try:
            result = self._branch_service.create_branch(db_name, branch_name, from_branch)
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
        브랜치 또는 커밋으로 체크아웃 (하위 호환성)
        
        Args:
            db_name: 데이터베이스 이름
            target: 브랜치 이름 또는 커밋 ID
            target_type: "branch" 또는 "commit"
            
        Returns:
            체크아웃 결과
        """
        try:
            result = self._branch_service.checkout_branch(db_name, target)
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
        현재 변경사항 커밋 (하위 호환성)
        
        Args:
            db_name: 데이터베이스 이름
            message: 커밋 메시지
            author: 작성자
            branch: 커밋할 브랜치 (기본값: 현재 브랜치)
            
        Returns:
            커밋 정보
        """
        try:
            result = self._version_service.commit(
                db_name, 
                message, 
                author, 
                branch
            )
            return {
                "author": author,
                "message": message,
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Failed to commit: {e}")
            raise DatabaseError(f"커밋 실패: {e}")
    
    def get_commit_history(self, db_name: str, branch: Optional[str] = None,
                          limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        커밋 히스토리 조회 (하위 호환성)
        
        Args:
            db_name: 데이터베이스 이름
            branch: 브랜치 이름 (기본값: 현재 브랜치)
            limit: 조회할 커밋 수
            offset: 오프셋
            
        Returns:
            커밋 목록
        """
        try:
            return self._version_service.get_commit_history(
                db_name, 
                branch, 
                limit, 
                offset
            )
        except Exception as e:
            logger.error(f"Failed to get commit history: {e}")
            raise DatabaseError(f"커밋 히스토리 조회 실패: {e}")
    
    def get_diff(self, db_name: str, base: str, compare: str) -> Dict[str, Any]:
        """
        두 버전 간 차이 비교 (하위 호환성)
        
        Args:
            db_name: 데이터베이스 이름
            base: 기준 브랜치/커밋
            compare: 비교 브랜치/커밋
            
        Returns:
            변경사항
        """
        try:
            return self._version_service.get_diff(db_name, base, compare)
        except Exception as e:
            logger.error(f"Failed to get diff: {e}")
            raise DatabaseError(f"diff 조회 실패: {e}")
    
    def merge_branches(self, db_name: str, source: str, target: str,
                      strategy: str = "merge", message: Optional[str] = None,
                      author: Optional[str] = None) -> Dict[str, Any]:
        """
        브랜치 병합 (하위 호환성)
        
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
        try:
            # BranchService의 merger 사용
            from services.core.domain.models import MergeStrategy
            
            merge_strategy = MergeStrategy.MERGE if strategy == "merge" else MergeStrategy.REBASE
            result = self._branch_service.merge_branches(
                db_name, 
                source, 
                target, 
                merge_strategy, 
                message, 
                author
            )
            
            if result.get("conflicts"):
                return {
                    "status": "conflict",
                    "conflicts": result["conflicts"],
                    "message": "병합 충돌이 발생했습니다"
                }
            
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
        병합 충돌 검사 (하위 호환성)
        
        Args:
            db_name: 데이터베이스 이름
            source: 소스 브랜치
            target: 타겟 브랜치
            
        Returns:
            충돌 목록
        """
        try:
            # BranchService에서 충돌 검사
            conflicts = self._branch_service.check_conflicts(db_name, source, target)
            return conflicts if conflicts else []
        except Exception:
            return []
    
    def rollback(self, db_name: str, target_commit: str,
                create_branch: bool = True, branch_name: Optional[str] = None) -> Dict[str, Any]:
        """
        특정 커밋으로 롤백 (하위 호환성)
        
        Args:
            db_name: 데이터베이스 이름
            target_commit: 대상 커밋 ID
            create_branch: 새 브랜치 생성 여부
            branch_name: 새 브랜치 이름
            
        Returns:
            롤백 결과
        """
        try:
            result = self._version_service.rollback(
                db_name, 
                target_commit, 
                create_branch, 
                branch_name
            )
            return {
                "target_commit": target_commit,
                "timestamp": datetime.utcnow().isoformat(),
                "branch": result.get("branch"),
                "operation": result.get("operation", "rollback")
            }
        except Exception as e:
            logger.error(f"Failed to rollback: {e}")
            raise DatabaseError(f"롤백 실패: {e}")
    
    def delete_branch(self, db_name: str, branch_name: str) -> Dict[str, Any]:
        """
        브랜치 삭제 (하위 호환성)
        
        Args:
            db_name: 데이터베이스 이름
            branch_name: 삭제할 브랜치 이름
            
        Returns:
            삭제 결과
        """
        try:
            result = self._branch_service.delete_branch(db_name, branch_name)
            return {
                "branch": branch_name,
                "deleted_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Failed to delete branch: {e}")
            raise DatabaseError(f"브랜치 삭제 실패: {e}")