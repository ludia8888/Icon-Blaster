"""
온톨로지 저장소 구현
온톨로지 CRUD 작업을 전담하는 서비스
SRP: 오직 온톨로지 저장소 관리만 담당
"""

import logging
from typing import Dict, List, Optional, Any
from functools import lru_cache

from services.core.interfaces import (
    IOntologyRepository, 
    IConnectionManager, 
    IDatabaseService, 
    IOntologyValidator
)
from domain.exceptions import (
    OntologyNotFoundError,
    DuplicateOntologyError,
    OntologyValidationError,
    DomainException
)
from domain.entities.ontology import Ontology
from domain.value_objects.multilingual_text import MultiLingualText

logger = logging.getLogger(__name__)


class TerminusOntologyRepository(IOntologyRepository):
    """
    TerminusDB 온톨로지 저장소
    
    단일 책임: 온톨로지 CRUD 작업만 담당
    """
    
    def __init__(self, connection_manager: IConnectionManager, 
                 database_service: IDatabaseService,
                 validator: IOntologyValidator):
        """
        초기화
        
        Args:
            connection_manager: 연결 관리자
            database_service: 데이터베이스 서비스
            validator: 온톨로지 유효성 검증기
        """
        self.connection_manager = connection_manager
        self.database_service = database_service
        self.validator = validator
        self._class_cache: Dict[str, set] = {}
    
    def create(self, db_name: str, ontology_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        온톨로지 생성
        
        Args:
            db_name: 데이터베이스 이름
            ontology_data: 온톨로지 데이터
            
        Returns:
            생성된 온톨로지 정보
            
        Raises:
            DuplicateOntologyError: 중복된 ID
            OntologyValidationError: 유효성 검증 실패
            DomainException: 생성 실패
        """
        # 데이터베이스 존재 확인
        self.database_service.ensure_database_exists(db_name)
        
        # 유효성 검증
        validation_errors = self.validator.validate(ontology_data)
        if validation_errors:
            raise OntologyValidationError(validation_errors, ontology_data.get("id"))
        
        ontology_id = ontology_data.get("id")
        if not ontology_id:
            raise OntologyValidationError(["Ontology ID is required"], None)
        
        # 중복 확인
        if self.get(db_name, ontology_id):
            raise DuplicateOntologyError(ontology_id, db_name)
        
        try:
            with self.connection_manager.get_connection(db_name) as client:
                # 온톨로지 생성 쿼리
                create_query = self._build_create_query(ontology_data)
                result = client.query(create_query)
                
                # 캐시 갱신
                self._clear_cache(db_name)
                
                logger.info(f"Created ontology '{ontology_id}' in database '{db_name}'")
                
                return {
                    "id": ontology_id,
                    "db_name": db_name,
                    "created": True,
                    "result": result
                }
                
        except Exception as e:
            logger.error(f"Failed to create ontology '{ontology_id}' in '{db_name}': {e}")
            raise DomainException(
                message=f"Failed to create ontology '{ontology_id}'",
                code="ONTOLOGY_CREATE_ERROR",
                details={"ontology_id": ontology_id, "db_name": db_name, "error": str(e)}
            )
    
    def get(self, db_name: str, ontology_id: str) -> Optional[Dict[str, Any]]:
        """
        온톨로지 조회
        
        Args:
            db_name: 데이터베이스 이름
            ontology_id: 온톨로지 ID
            
        Returns:
            온톨로지 정보 또는 None
        """
        try:
            with self.connection_manager.get_connection(db_name) as client:
                # 온톨로지 조회 쿼리
                get_query = self._build_get_query(ontology_id)
                result = client.query(get_query)
                
                if result and result.get("bindings"):
                    ontology_data = self._process_get_result(result["bindings"][0])
                    logger.debug(f"Retrieved ontology '{ontology_id}' from '{db_name}'")
                    return ontology_data
                
                return None
                
        except Exception as e:
            logger.error(f"Failed to get ontology '{ontology_id}' from '{db_name}': {e}")
            return None
    
    def update(self, db_name: str, ontology_id: str, 
               ontology_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        온톨로지 업데이트
        
        Args:
            db_name: 데이터베이스 이름
            ontology_id: 온톨로지 ID
            ontology_data: 업데이트할 데이터
            
        Returns:
            업데이트된 온톨로지 정보
            
        Raises:
            OntologyNotFoundError: 온톨로지를 찾을 수 없음
            OntologyValidationError: 유효성 검증 실패
            DomainException: 업데이트 실패
        """
        # 존재 확인
        if not self.get(db_name, ontology_id):
            raise OntologyNotFoundError(ontology_id, db_name)
        
        # ID 변경 방지
        if ontology_data.get("id") and ontology_data["id"] != ontology_id:
            raise OntologyValidationError(["Cannot change ontology ID"], ontology_id)
        
        # 유효성 검증
        validation_errors = self.validator.validate(ontology_data)
        if validation_errors:
            raise OntologyValidationError(validation_errors, ontology_id)
        
        try:
            with self.connection_manager.get_connection(db_name) as client:
                # 온톨로지 업데이트 쿼리
                update_query = self._build_update_query(ontology_id, ontology_data)
                result = client.query(update_query)
                
                # 캐시 갱신
                self._clear_cache(db_name)
                
                logger.info(f"Updated ontology '{ontology_id}' in database '{db_name}'")
                
                return {
                    "id": ontology_id,
                    "db_name": db_name,
                    "updated": True,
                    "result": result
                }
                
        except Exception as e:
            logger.error(f"Failed to update ontology '{ontology_id}' in '{db_name}': {e}")
            raise DomainException(
                message=f"Failed to update ontology '{ontology_id}'",
                code="ONTOLOGY_UPDATE_ERROR",
                details={"ontology_id": ontology_id, "db_name": db_name, "error": str(e)}
            )
    
    def delete(self, db_name: str, ontology_id: str) -> bool:
        """
        온톨로지 삭제
        
        Args:
            db_name: 데이터베이스 이름
            ontology_id: 온톨로지 ID
            
        Returns:
            삭제 성공 여부
            
        Raises:
            OntologyNotFoundError: 온톨로지를 찾을 수 없음
            DomainException: 삭제 실패
        """
        # 존재 확인
        if not self.get(db_name, ontology_id):
            raise OntologyNotFoundError(ontology_id, db_name)
        
        try:
            with self.connection_manager.get_connection(db_name) as client:
                # 온톨로지 삭제 쿼리
                delete_query = self._build_delete_query(ontology_id)
                result = client.query(delete_query)
                
                # 캐시 갱신
                self._clear_cache(db_name)
                
                logger.info(f"Deleted ontology '{ontology_id}' from database '{db_name}'")
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete ontology '{ontology_id}' from '{db_name}': {e}")
            raise DomainException(
                message=f"Failed to delete ontology '{ontology_id}'",
                code="ONTOLOGY_DELETE_ERROR",
                details={"ontology_id": ontology_id, "db_name": db_name, "error": str(e)}
            )
    
    def list(self, db_name: str, class_type: str = "sys:Class",
             limit: Optional[int] = None, offset: int = 0) -> List[Dict[str, Any]]:
        """
        온톨로지 목록 조회
        
        Args:
            db_name: 데이터베이스 이름
            class_type: 클래스 타입
            limit: 조회 개수 제한
            offset: 오프셋
            
        Returns:
            온톨로지 목록
        """
        try:
            with self.connection_manager.get_connection(db_name) as client:
                # 온톨로지 목록 조회 쿼리
                list_query = self._build_list_query(class_type, limit, offset)
                result = client.query(list_query)
                
                ontologies = []
                if result and result.get("bindings"):
                    for binding in result["bindings"]:
                        ontology_data = self._process_list_result(binding)
                        ontologies.append(ontology_data)
                
                logger.debug(f"Listed {len(ontologies)} ontologies from '{db_name}'")
                return ontologies
                
        except Exception as e:
            logger.error(f"Failed to list ontologies from '{db_name}': {e}")
            raise DomainException(
                message=f"Failed to list ontologies from '{db_name}'",
                code="ONTOLOGY_LIST_ERROR",
                details={"db_name": db_name, "error": str(e)}
            )
    
    def _build_create_query(self, ontology_data: Dict[str, Any]) -> Any:
        """온톨로지 생성 쿼리 빌드"""
        from terminusdb_client import WOQLQuery as WQ
        
        ontology_id = ontology_data["id"]
        
        # 기본 클래스 생성
        query = WQ().add_class(ontology_id)
        
        # 레이블 추가
        if "label" in ontology_data:
            label = ontology_data["label"]
            if isinstance(label, dict):
                for lang, text in label.items():
                    query = query.add_quad(ontology_id, "rdfs:label", f"{text}@{lang}")
            else:
                query = query.add_quad(ontology_id, "rdfs:label", label)
        
        # 설명 추가
        if "description" in ontology_data:
            description = ontology_data["description"]
            if isinstance(description, dict):
                for lang, text in description.items():
                    query = query.add_quad(ontology_id, "rdfs:comment", f"{text}@{lang}")
            else:
                query = query.add_quad(ontology_id, "rdfs:comment", description)
        
        return query
    
    def _build_get_query(self, ontology_id: str) -> Any:
        """온톨로지 조회 쿼리 빌드"""
        from terminusdb_client import WOQLQuery as WQ
        
        return WQ().select("v:Class", "v:Label", "v:Comment").where(
            WQ().quad("v:Class", "rdf:type", "sys:Class"),
            WQ().eq("v:Class", ontology_id),
            WQ().opt().quad("v:Class", "rdfs:label", "v:Label"),
            WQ().opt().quad("v:Class", "rdfs:comment", "v:Comment")
        )
    
    def _build_update_query(self, ontology_id: str, ontology_data: Dict[str, Any]) -> Any:
        """온톨로지 업데이트 쿼리 빌드"""
        from terminusdb_client import WOQLQuery as WQ
        
        # 기존 레이블/설명 삭제 후 새로 추가
        query = WQ().opt().delete_quad(ontology_id, "rdfs:label", "v:OldLabel")
        query = query.opt().delete_quad(ontology_id, "rdfs:comment", "v:OldComment")
        
        # 새 레이블 추가
        if "label" in ontology_data:
            label = ontology_data["label"]
            if isinstance(label, dict):
                for lang, text in label.items():
                    query = query.add_quad(ontology_id, "rdfs:label", f"{text}@{lang}")
            else:
                query = query.add_quad(ontology_id, "rdfs:label", label)
        
        # 새 설명 추가
        if "description" in ontology_data:
            description = ontology_data["description"]
            if isinstance(description, dict):
                for lang, text in description.items():
                    query = query.add_quad(ontology_id, "rdfs:comment", f"{text}@{lang}")
            else:
                query = query.add_quad(ontology_id, "rdfs:comment", description)
        
        return query
    
    def _build_delete_query(self, ontology_id: str) -> Any:
        """온톨로지 삭제 쿼리 빌드"""
        from terminusdb_client import WOQLQuery as WQ
        
        # TerminusDB에서 클래스 삭제는 delete_document 사용
        return WQ().delete_document(ontology_id)
    
    def _build_list_query(self, class_type: str, limit: Optional[int], offset: int) -> Any:
        """온톨로지 목록 조회 쿼리 빌드"""
        from terminusdb_client import WOQLQuery as WQ
        
        query = WQ().select("v:Class", "v:Label", "v:Comment").where(
            WQ().quad("v:Class", "rdf:type", class_type),
            WQ().opt().quad("v:Class", "rdfs:label", "v:Label"),
            WQ().opt().quad("v:Class", "rdfs:comment", "v:Comment")
        )
        
        if limit:
            query = query.limit(limit, offset)
        
        return query
    
    def _process_get_result(self, binding: Dict[str, Any]) -> Dict[str, Any]:
        """조회 결과 처리"""
        ontology_data = {
            "id": binding.get("Class", ""),
            "type": "Class"
        }
        
        # 레이블 처리
        if "Label" in binding:
            ontology_data["label"] = binding["Label"]
        
        # 설명 처리
        if "Comment" in binding:
            ontology_data["description"] = binding["Comment"]
        
        return ontology_data
    
    def _process_list_result(self, binding: Dict[str, Any]) -> Dict[str, Any]:
        """목록 결과 처리"""
        return self._process_get_result(binding)
    
    def _clear_cache(self, db_name: str) -> None:
        """캐시 삭제"""
        if db_name in self._class_cache:
            del self._class_cache[db_name]
        
        # LRU 캐시 삭제
        if hasattr(self, '_get_cached_classes'):
            self._get_cached_classes.cache_clear()
    
    @lru_cache(maxsize=32)
    def _get_cached_classes(self, db_name: str) -> set:
        """캐시된 클래스 목록 조회"""
        try:
            ontologies = self.list(db_name)
            return {ont["id"] for ont in ontologies}
        except Exception:
            return set()