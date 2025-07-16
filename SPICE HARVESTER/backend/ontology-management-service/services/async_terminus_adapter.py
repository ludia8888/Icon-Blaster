"""
AsyncTerminusService와 기존 TerminusService 인터페이스 어댑터
기존 동기 코드와의 호환성을 위한 어댑터 패턴 구현
"""

import asyncio
from typing import Dict, List, Optional, Any, Union
from functools import wraps
from services.async_terminus import AsyncTerminusService, AsyncConnectionInfo
from services.terminus import ConnectionInfo, OntologyNotFoundError, DuplicateOntologyError, ValidationError


def async_to_sync(func):
    """비동기 함수를 동기 함수로 변환하는 데코레이터"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 이미 실행 중인 루프가 있으면 새 태스크 생성
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, func(*args, **kwargs))
                    return future.result()
            else:
                return loop.run_until_complete(func(*args, **kwargs))
        except RuntimeError:
            # 새 이벤트 루프 생성
            return asyncio.run(func(*args, **kwargs))
    return wrapper


class TerminusServiceAdapter:
    """
    AsyncTerminusService를 동기 인터페이스로 감싸는 어댑터
    기존 코드와의 호환성 유지
    """
    
    def __init__(self, connection_info: Optional[ConnectionInfo] = None):
        """
        초기화
        
        Args:
            connection_info: 기존 ConnectionInfo 객체
        """
        # ConnectionInfo를 AsyncConnectionInfo로 변환
        if connection_info:
            async_connection_info = AsyncConnectionInfo(
                server_url=connection_info.server_url,
                user=connection_info.user,
                account=connection_info.account,
                key=connection_info.key
            )
        else:
            async_connection_info = None
        
        self._async_service = AsyncTerminusService(async_connection_info)
        self._loop = None
    
    def _get_or_create_loop(self):
        """이벤트 루프 가져오기 또는 생성"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            return loop
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop
    
    def _run_async(self, coro):
        """비동기 함수 실행"""
        loop = self._get_or_create_loop()
        try:
            if loop.is_running():
                # 이미 실행 중인 루프에서는 태스크 생성 후 대기
                task = asyncio.create_task(coro)
                return loop.run_until_complete(task)
            else:
                return loop.run_until_complete(coro)
        except RuntimeError:
            # 새 루프에서 실행
            return asyncio.run(coro)
    
    def connect(self, db_name: Optional[str] = None) -> None:
        """TerminusDB 연결 테스트"""
        return self._run_async(self._async_service.connect(db_name))
    
    def disconnect(self) -> None:
        """연결 해제"""
        return self._run_async(self._async_service.disconnect())
    
    def check_connection(self) -> bool:
        """연결 상태 확인"""
        return self._run_async(self._async_service.check_connection())
    
    def ensure_db_exists(self, db_name: str, description: Optional[str] = None) -> None:
        """데이터베이스가 존재하는지 확인하고 없으면 생성"""
        return self._run_async(self._async_service.ensure_db_exists(db_name, description))
    
    def create_database(self, db_name: str, description: Optional[str] = None) -> Dict[str, Any]:
        """새 데이터베이스 생성"""
        return self._run_async(self._async_service.create_database(db_name, description))
    
    def list_databases(self) -> List[Dict[str, Any]]:
        """사용 가능한 데이터베이스 목록 조회"""
        return self._run_async(self._async_service.list_databases())
    
    def create_ontology(self, db_name: str, jsonld_data: Dict[str, Any]) -> Dict[str, Any]:
        """온톨로지 클래스 생성"""
        try:
            return self._run_async(self._async_service.create_ontology(db_name, jsonld_data))
        except Exception as e:
            # 비동기 예외를 동기 예외로 변환
            if "already exists" in str(e):
                raise DuplicateOntologyError(str(e))
            elif "validation" in str(e).lower():
                raise ValidationError(str(e))
            else:
                raise e
    
    def get_ontology(self, db_name: str, class_id: str, 
                    raise_if_missing: bool = True) -> Optional[Dict[str, Any]]:
        """온톨로지 클래스 조회"""
        try:
            return self._run_async(self._async_service.get_ontology(db_name, class_id, raise_if_missing))
        except Exception as e:
            if "not found" in str(e).lower() and raise_if_missing:
                raise OntologyNotFoundError(str(e))
            elif raise_if_missing:
                raise e
            return None
    
    def update_ontology(self, db_name: str, class_id: str, 
                       jsonld_data: Dict[str, Any]) -> Dict[str, Any]:
        """온톨로지 클래스 업데이트"""
        try:
            return self._run_async(self._async_service.update_ontology(db_name, class_id, jsonld_data))
        except Exception as e:
            if "not found" in str(e).lower():
                raise OntologyNotFoundError(str(e))
            elif "validation" in str(e).lower():
                raise ValidationError(str(e))
            else:
                raise e
    
    def delete_ontology(self, db_name: str, class_id: str) -> bool:
        """온톨로지 클래스 삭제"""
        try:
            return self._run_async(self._async_service.delete_ontology(db_name, class_id))
        except Exception as e:
            if "not found" in str(e).lower():
                raise OntologyNotFoundError(str(e))
            else:
                raise e
    
    def list_ontologies(self, db_name: str, class_type: str = "sys:Class",
                       limit: Optional[int] = None, offset: int = 0) -> List[Dict[str, Any]]:
        """온톨로지 클래스 목록 조회"""
        return self._run_async(self._async_service.list_ontologies(db_name, class_type, limit, offset))
    
    def execute_query(self, db_name: str, query_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """WOQL 쿼리 실행"""
        return self._run_async(self._async_service.execute_query(db_name, query_dict))
    
    def merge_ontology(self, db_name: str, jsonld_data: Dict[str, Any]) -> Dict[str, Any]:
        """온톨로지 병합 (존재하면 업데이트, 없으면 생성)"""
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
            raise e
    
    def get_property_schema(self, db_name: str, class_id: str) -> Dict[str, Any]:
        """클래스의 속성 스키마 조회"""
        # 간단한 구현 - 실제로는 더 복잡한 스키마 분석이 필요
        ontology = self.get_ontology(db_name, class_id)
        if ontology:
            return {
                "class_id": class_id,
                "properties": ontology.get("properties", {})
            }
        else:
            return {
                "class_id": class_id,
                "properties": {}
            }
    
    # 기존 TerminusService의 다른 메서드들도 필요에 따라 구현
    def list_branches(self, db_name: str) -> List[Dict[str, Any]]:
        """브랜치 목록 조회 (미구현)"""
        return [{"name": "main", "head": "main", "is_current": True}]
    
    def create_branch(self, db_name: str, branch_name: str, 
                     from_branch: Optional[str] = None) -> Dict[str, Any]:
        """브랜치 생성 (미구현)"""
        return {"name": branch_name, "created_at": "now"}
    
    def commit_changes(self, db_name: str, message: str, 
                      author: str, branch: Optional[str] = None) -> Dict[str, Any]:
        """변경사항 커밋 (미구현)"""
        return {"message": message, "author": author}
    
    def get_commit_history(self, db_name: str, branch: Optional[str] = None,
                          limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """커밋 히스토리 조회 (미구현)"""
        return []
    
    def __enter__(self):
        """컨텍스트 매니저 진입"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료"""
        self.disconnect()