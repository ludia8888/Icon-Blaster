"""
Async TerminusDB 서비스 모듈
httpx를 사용한 비동기 TerminusDB 클라이언트 구현
"""

import httpx
import json
import asyncio
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
import logging
from contextlib import asynccontextmanager
from functools import wraps

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))

from models.ontology import (
    OntologyCreateRequest,
    OntologyUpdateRequest,
    MultiLingualText,
    QueryOperator
)
from models.config import ConnectionConfig, AsyncConnectionInfo
from exceptions import (
    OntologyNotFoundError,
    DuplicateOntologyError,
    OntologyValidationError,
    ConnectionError,
    DatabaseNotFoundError
)

logger = logging.getLogger(__name__)

# 하위 호환성을 위한 별칭
AsyncOntologyNotFoundError = OntologyNotFoundError
AsyncDuplicateOntologyError = DuplicateOntologyError
AsyncValidationError = OntologyValidationError
AsyncDatabaseError = ConnectionError


def async_terminus_retry(max_retries: int = 3, delay: float = 1.0):
    """비동기 재시도 데코레이터"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except (httpx.RequestError, httpx.HTTPStatusError) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        await asyncio.sleep(delay * (2 ** attempt))
                        continue
                    raise
            raise last_exception
        return wrapper
    return decorator


class AsyncTerminusService:
    """
    비동기 TerminusDB 서비스 클래스
    httpx를 사용하여 TerminusDB API와 직접 통신
    """
    
    def __init__(self, connection_info: Optional[ConnectionConfig] = None):
        """
        초기화
        
        Args:
            connection_info: 연결 정보 객체
        """
        self.connection_info = connection_info or ConnectionConfig(
            server_url="http://localhost:6363",
            user="admin",
            account="admin",
            key="admin123"
        )
        
        self._client = None
        self._auth_token = None
        self._db_cache = set()
    
    async def _get_client(self) -> httpx.AsyncClient:
        """HTTP 클라이언트 생성/반환"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.connection_info.server_url,
                timeout=self.connection_info.timeout,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                }
            )
        return self._client
    
    async def _authenticate(self) -> str:
        """TerminusDB 인증 처리 - Basic Auth 사용"""
        # TerminusDB는 HTTP Basic Authentication을 사용
        import base64
        
        if self._auth_token:
            return self._auth_token
        
        # Basic Auth 헤더 생성
        credentials = f"{self.connection_info.user}:{self.connection_info.key}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        self._auth_token = f"Basic {encoded_credentials}"
        
        return self._auth_token
    
    async def _make_request(self, method: str, endpoint: str, 
                          data: Optional[Dict] = None, 
                          params: Optional[Dict] = None) -> Dict[str, Any]:
        """HTTP 요청 실행"""
        client = await self._get_client()
        token = await self._authenticate()
        
        headers = {
            "Authorization": token
        }
        
        try:
            response = await client.request(
                method=method,
                url=endpoint,
                json=data,
                params=params,
                headers=headers
            )
            response.raise_for_status()
            
            # TerminusDB 응답이 빈 경우 처리
            if response.text.strip():
                return response.json()
            else:
                # 빈 응답은 성공적인 작업을 의미할 수 있음 (예: DELETE)
                # 가짜 성공 응답 대신 빈 dict 반환
                return {}
            
        except httpx.HTTPStatusError as e:
            error_detail = ""
            try:
                error_detail = e.response.text
            except AttributeError:
                # response.text가 없을 수 있음
                pass
            except Exception as detail_error:
                logger.debug(f"Error extracting error detail: {detail_error}")
            
            if e.response.status_code == 404:
                raise AsyncOntologyNotFoundError(f"리소스를 찾을 수 없습니다: {endpoint}")
            elif e.response.status_code == 409:
                raise AsyncDuplicateOntologyError(f"중복된 리소스: {endpoint}")
            else:
                raise AsyncDatabaseError(f"HTTP 오류 {e.response.status_code}: {e}. 응답: {error_detail}")
        except httpx.RequestError as e:
            raise AsyncDatabaseError(f"요청 실패: {e}")
    
    async def connect(self, db_name: Optional[str] = None) -> None:
        """TerminusDB 연결 테스트"""
        try:
            # TerminusDB 연결 테스트 - 실제 엔드포인트 사용
            result = await self._make_request("GET", "/api/")
            
            if db_name:
                self._db_cache.add(db_name)
            
            logger.info(f"Connected to TerminusDB successfully")
            
        except Exception as e:
            logger.error(f"Failed to connect to TerminusDB: {e}")
            raise AsyncDatabaseError(f"TerminusDB 연결 실패: {e}")
    
    async def disconnect(self) -> None:
        """연결 해제"""
        if self._client:
            await self._client.aclose()
            self._client = None
        
        self._auth_token = None
        self._db_cache.clear()
        logger.info("Disconnected from TerminusDB")
    
    async def check_connection(self) -> bool:
        """연결 상태 확인"""
        try:
            await self._make_request("GET", "/api/")
            return True
        except Exception:
            return False
    
    @async_terminus_retry(max_retries=3)
    async def database_exists(self, db_name: str) -> bool:
        """데이터베이스 존재 여부 확인"""
        try:
            # TerminusDB 올바른 엔드포인트 사용
            endpoint = f"/api/db/{self.connection_info.account}/{db_name}"
            await self._make_request("GET", endpoint)
            return True
        except AsyncOntologyNotFoundError:
            return False
    
    async def ensure_db_exists(self, db_name: str, description: Optional[str] = None) -> None:
        """데이터베이스가 존재하는지 확인하고 없으면 생성"""
        if db_name in self._db_cache:
            return
        
        try:
            if await self.database_exists(db_name):
                self._db_cache.add(db_name)
                return
            
            # 데이터베이스 생성
            await self.create_database(db_name, description)
            self._db_cache.add(db_name)
            
        except Exception as e:
            logger.error(f"Error ensuring database exists: {e}")
            raise AsyncDatabaseError(f"데이터베이스 생성/확인 실패: {e}")
    
    async def create_database(self, db_name: str, description: Optional[str] = None) -> Dict[str, Any]:
        """새 데이터베이스 생성"""
        # 중복 검사 - 이미 존재하는 경우 예외 발생
        if await self.database_exists(db_name):
            raise AsyncDuplicateOntologyError(f"데이터베이스 '{db_name}'이(가) 이미 존재합니다")
        
        endpoint = f"/api/db/{self.connection_info.account}/{db_name}"
        
        # TerminusDB 데이터베이스 생성 요청 형식
        data = {
            "label": db_name,
            "comment": description or f"{db_name} database",
            "prefixes": {"@base": f"terminusdb:///{self.connection_info.account}/{db_name}/data/", "@schema": f"terminusdb:///{self.connection_info.account}/{db_name}/schema#"}
        }
        
        try:
            result = await self._make_request("POST", endpoint, data)
            self._db_cache.add(db_name)
            
            return {
                "name": db_name,
                "created_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to create database: {e}")
            raise AsyncDatabaseError(f"데이터베이스 생성 실패: {e}")
    
    async def list_databases(self) -> List[Dict[str, Any]]:
        """사용 가능한 데이터베이스 목록 조회"""
        try:
            endpoint = f"/api/db/{self.connection_info.account}"
            result = await self._make_request("GET", endpoint)
            
            # Debug logging to understand TerminusDB response format
            logger.debug(f"TerminusDB list response type: {type(result)}")
            if isinstance(result, dict):
                logger.debug(f"TerminusDB list response keys: {list(result.keys())}")
            
            databases = []
            # TerminusDB 응답 형식 처리 - 여러 형식 지원
            if isinstance(result, list):
                db_list = result
            elif isinstance(result, dict):
                # Check for common keys that might contain the database list
                if "@graph" in result:
                    db_list = result["@graph"]
                elif "databases" in result:
                    db_list = result["databases"]
                elif "dbs" in result:
                    db_list = result["dbs"]
                else:
                    # If no known keys, assume the dict contains database info directly
                    db_list = []
                    logger.warning(f"Unknown TerminusDB response format for database list: {result}")
            else:
                db_list = []
            
            for db_info in db_list:
                # 다양한 응답 형식 처리
                db_name = None
                
                if isinstance(db_info, str):
                    # 단순 문자열인 경우
                    db_name = db_info
                elif isinstance(db_info, dict):
                    # 딕셔너리인 경우 여러 키 시도
                    db_name = (db_info.get("name") or 
                              db_info.get("id") or
                              db_info.get("@id"))
                    
                    # path 형식 처리
                    if not db_name and "path" in db_info:
                        path = db_info.get("path", "")
                        if "/" in path:
                            _, db_name = path.split("/", 1)
                
                if db_name:
                    databases.append({
                        "name": db_name,
                        "label": db_info.get("label", db_name) if isinstance(db_info, dict) else db_name,
                        "comment": db_info.get("comment", f"Database {db_name}") if isinstance(db_info, dict) else f"Database {db_name}",
                        "created": db_info.get("created") if isinstance(db_info, dict) else None,
                        "path": db_info.get("path") if isinstance(db_info, dict) else f"{self.connection_info.account}/{db_name}"
                    })
                    self._db_cache.add(db_name)
            
            return databases
            
        except Exception as e:
            logger.error(f"Failed to list databases: {e}")
            raise AsyncDatabaseError(f"데이터베이스 목록 조회 실패: {e}")
    
    @async_terminus_retry(max_retries=3)
    async def delete_database(self, db_name: str) -> bool:
        """데이터베이스 삭제"""
        try:
            # 데이터베이스 존재 여부 확인
            if not await self.database_exists(db_name):
                raise AsyncOntologyNotFoundError(f"데이터베이스 '{db_name}'을(를) 찾을 수 없습니다")
            
            # TerminusDB 데이터베이스 삭제 엔드포인트 사용
            endpoint = f"/api/db/{self.connection_info.account}/{db_name}"
            await self._make_request("DELETE", endpoint)
            
            # 캐시에서 제거
            self._db_cache.discard(db_name)
            
            logger.info(f"Database '{db_name}' deleted successfully")
            return True
            
        except AsyncOntologyNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to delete database '{db_name}': {e}")
            raise AsyncDatabaseError(f"데이터베이스 삭제 실패: {e}")
    
    async def create_ontology(self, db_name: str, jsonld_data: Dict[str, Any]) -> Dict[str, Any]:
        """온톨로지 클래스 생성"""
        await self.ensure_db_exists(db_name)
        
        # TerminusDB 스키마 업데이트 엔드포인트
        endpoint = f"/api/schema/{self.connection_info.account}/{db_name}"
        
        # JSON-LD 형식으로 스키마 데이터 포맷팅
        schema_data = [{
            "@type": "Class",
            "@id": jsonld_data.get("@id"),
            "@documentation": jsonld_data.get("rdfs:comment", {}),
            "rdfs:label": jsonld_data.get("rdfs:label", {}),
            "@key": {
                "@type": "Lexical",
                "@fields": ["@id"]
            }
        }]
        
        try:
            result = await self._make_request("POST", endpoint, schema_data)
            
            return {
                "id": jsonld_data.get("@id"),
                "created_at": datetime.utcnow().isoformat(),
                "database": db_name
            }
            
        except Exception as e:
            logger.error(f"Failed to create ontology: {e}")
            if "already exists" in str(e):
                raise AsyncDuplicateOntologyError(str(e))
            elif "validation" in str(e).lower():
                raise AsyncValidationError(str(e))
            else:
                raise AsyncDatabaseError(f"온톨로지 생성 실패: {e}")
    
    async def get_ontology(self, db_name: str, class_id: str, 
                          raise_if_missing: bool = True) -> Optional[Dict[str, Any]]:
        """온톨로지 클래스 조회 - Document API 사용"""
        await self.ensure_db_exists(db_name)
        
        # Document API를 통한 스키마 조회
        endpoint = f"/api/document/{self.connection_info.account}/{db_name}"
        params = {
            "graph_type": "schema"
        }
        
        try:
            # JSON Lines 형식으로 응답 받기
            client = await self._get_client()
            token = await self._authenticate()
            
            headers = {
                "Authorization": token
            }
            
            response = await client.request(
                method="GET",
                url=endpoint,
                params=params,
                headers=headers
            )
            response.raise_for_status()
            
            # JSON Lines 형식 파싱
            response_text = response.text.strip()
            
            if response_text:
                for line in response_text.split('\n'):
                    try:
                        doc = json.loads(line)
                        if doc.get("@id") == class_id and doc.get("@type") == "Class":
                            return doc
                    except json.JSONDecodeError:
                        # 컨텍스트 줄 등은 무시
                        continue
            
            if raise_if_missing:
                raise AsyncOntologyNotFoundError(f"온톨로지를 찾을 수 없습니다: {class_id}")
            return None
            
        except AsyncOntologyNotFoundError:
            if raise_if_missing:
                raise
            return None
        except Exception as e:
            logger.error(f"온톨로지 조회 실패: {e}")
            if raise_if_missing:
                raise AsyncDatabaseError(f"온톨로지 조회 실패: {e}")
            return None
    
    async def update_ontology(self, db_name: str, class_id: str, 
                            jsonld_data: Dict[str, Any]) -> Dict[str, Any]:
        """온톨로지 클래스 업데이트 - Document API 사용"""
        await self.ensure_db_exists(db_name)
        
        # 먼저 기존 문서 조회
        existing_doc = await self.get_ontology(db_name, class_id, raise_if_missing=True)
        if not existing_doc:
            raise AsyncOntologyNotFoundError(f"온톨로지를 찾을 수 없습니다: {class_id}")
        
        # 기존 문서와 새 데이터 병합
        updated_doc = {**existing_doc, **jsonld_data}
        updated_doc["@id"] = class_id  # ID는 변경하지 않음
        updated_doc["@type"] = "Class"  # 타입 유지
        
        # Document API를 통한 업데이트 (replace)
        endpoint = f"/api/document/{self.connection_info.account}/{db_name}"
        
        # 먼저 삭제
        delete_params = {
            "graph_type": "schema",
            "author": self.connection_info.user,
            "message": f"Deleting {class_id} for update"
        }
        
        try:
            # ID로 삭제
            await self._make_request("DELETE", f"{endpoint}/{class_id}", None, delete_params)
        except Exception as e:
            logger.warning(f"삭제 중 오류 (무시됨): {e}")
        
        # 새로 생성
        create_params = {
            "graph_type": "schema",
            "author": self.connection_info.user,
            "message": f"Updating {class_id} schema"
        }
        
        try:
            result = await self._make_request("POST", endpoint, [updated_doc], create_params)
            
            return {
                "id": class_id,
                "updated_at": datetime.utcnow().isoformat(),
                "database": db_name,
                "result": result
            }
            
        except Exception as e:
            if "validation" in str(e).lower():
                raise AsyncValidationError(str(e))
            else:
                raise AsyncDatabaseError(f"온톨로지 업데이트 실패: {e}")
    
    async def delete_ontology(self, db_name: str, class_id: str) -> bool:
        """온톨로지 클래스 삭제 - Document API 사용"""
        await self.ensure_db_exists(db_name)
        
        # 먼저 문서가 존재하는지 확인
        existing_doc = await self.get_ontology(db_name, class_id, raise_if_missing=False)
        if not existing_doc:
            raise AsyncOntologyNotFoundError(f"온톨로지를 찾을 수 없습니다: {class_id}")
        
        # Document API를 통한 삭제
        endpoint = f"/api/document/{self.connection_info.account}/{db_name}/{class_id}"
        params = {
            "graph_type": "schema",
            "author": self.connection_info.user,
            "message": f"Deleting {class_id} schema"
        }
        
        try:
            await self._make_request("DELETE", endpoint, None, params)
            return True
            
        except Exception as e:
            raise AsyncDatabaseError(f"온톨로지 삭제 실패: {e}")
    
    async def list_ontologies(self, db_name: str, class_type: str = "sys:Class",
                            limit: Optional[int] = None, offset: int = 0) -> List[Dict[str, Any]]:
        """온톨로지 클래스 목록 조회 - Document API 사용"""
        # list_ontology_classes 메서드를 재사용
        classes_raw = await self.list_ontology_classes(db_name)
        
        # 응답 형식 변환
        classes = []
        for cls in classes_raw:
            if cls.get("type") == "Class" or class_type == "sys:Class":
                class_info = {
                    "id": cls.get("id"),
                    "type": cls.get("type", "Class"),
                    "label": cls.get("properties", {}).get("rdfs:label", {}),
                    "description": cls.get("properties", {}).get("rdfs:comment", {}),
                    "properties": cls.get("properties", {})
                }
                classes.append(class_info)
        
        # 페이징 처리
        if offset > 0:
            classes = classes[offset:]
        if limit:
            classes = classes[:limit]
        
        return classes
    
    async def execute_query(self, db_name: str, query_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """WOQL 쿼리 실행"""
        await self.ensure_db_exists(db_name)
        
        # TerminusDB WOQL 쿼리 엔드포인트
        endpoint = f"/api/woql/{self.connection_info.account}/{db_name}"
        
        # 쿼리 딕셔너리를 WOQL 형식으로 변환
        woql_query = self._convert_to_woql(query_dict)
        
        try:
            result = await self._make_request("POST", endpoint, woql_query)
            
            # 결과 파싱
            bindings = result.get("bindings", [])
            parsed_results = []
            
            for binding in bindings:
                parsed_result = {}
                for key, value in binding.items():
                    if isinstance(value, dict) and "@value" in value:
                        parsed_result[key] = value["@value"]
                    elif isinstance(value, dict) and "@id" in value:
                        parsed_result[key] = value["@id"]
                    else:
                        parsed_result[key] = value
                parsed_results.append(parsed_result)
            
            return {"results": parsed_results, "total": len(parsed_results)}
            
        except Exception as e:
            logger.error(f"Failed to execute query: {e}")
            raise AsyncDatabaseError(f"쿼리 실행 실패: {e}")
    
    async def delete_ontology(self, db_name: str, class_id: str) -> bool:
        """실제 TerminusDB 온톨로지 클래스 삭제"""
        try:
            await self.ensure_db_exists(db_name)
            
            # TerminusDB Document API를 통한 삭제: DELETE /api/document/<account>/<db>/<id>
            endpoint = f"/api/document/{self.connection_info.account}/{db_name}/{class_id}"
            params = {
                "graph_type": "schema"
            }
            
            # 실제 삭제 요청
            await self._make_request("DELETE", endpoint, params=params)
            
            logger.info(f"TerminusDB ontology '{class_id}' deleted successfully from database '{db_name}'")
            return True
            
        except Exception as e:
            logger.error(f"TerminusDB delete ontology API failed: {e}")
            if "not found" in str(e).lower():
                raise AsyncOntologyNotFoundError(f"온톨로지를 찾을 수 없습니다: {class_id}")
            else:
                raise AsyncDatabaseError(f"온톨로지 삭제 실패: {e}")
    
    async def list_ontology_classes(self, db_name: str) -> List[Dict[str, Any]]:
        """실제 TerminusDB 온톨로지 클래스 목록 조회"""
        try:
            await self.ensure_db_exists(db_name)
            
            # TerminusDB Document API로 모든 스키마 문서 조회: GET /api/document/<account>/<db>
            endpoint = f"/api/document/{self.connection_info.account}/{db_name}"
            params = {
                "graph_type": "schema",
                "type": "Class"
            }
            
            # 실제 API 요청
            client = await self._get_client()
            token = await self._authenticate()
            
            headers = {
                "Authorization": token
            }
            
            response = await client.request(
                method="GET",
                url=endpoint,
                params=params,
                headers=headers
            )
            response.raise_for_status()
            
            # JSON Lines 형식 파싱
            response_text = response.text.strip()
            ontologies = []
            
            if response_text:
                for line in response_text.split('\n'):
                    if line.strip():
                        try:
                            doc = json.loads(line.strip())
                            if isinstance(doc, dict) and doc.get("@type") == "Class":
                                ontologies.append(doc)
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse JSON line: {line}")
            
            logger.info(f"TerminusDB retrieved {len(ontologies)} ontology classes from database '{db_name}'")
            return ontologies
            
        except Exception as e:
            logger.error(f"TerminusDB list ontology classes API failed: {e}")
            raise AsyncDatabaseError(f"온톨로지 목록 조회 실패: {e}")
    
    # === BRANCH MANAGEMENT METHODS ===
    
    async def list_branches(self, db_name: str) -> List[str]:
        """실제 TerminusDB 브랜치 목록 조회"""
        try:
            # TerminusDB의 실제 브랜치 API: GET /api/db/<account>/<db>/branch
            endpoint = f"/api/db/{self.connection_info.account}/{db_name}/branch"
            
            # TerminusDB에 실제 요청
            result = await self._make_request("GET", endpoint)
            
            branches = []
            if isinstance(result, dict):
                # TerminusDB 브랜치 응답 구조: {"@type": "BranchList", "branch_name": [...]}
                if "branch_name" in result:
                    branches = result["branch_name"]
                elif "branches" in result:
                    branches = [branch.get("name", branch) for branch in result["branches"]]
            elif isinstance(result, list):
                # 직접 브랜치 목록인 경우
                branches = [branch if isinstance(branch, str) else branch.get("name", str(branch)) for branch in result]
            
            # 유효한 브랜치만 반환
            valid_branches = [b for b in branches if b and isinstance(b, str)]
            
            if not valid_branches:
                # TerminusDB 기본 브랜치는 'main'
                valid_branches = ['main']
            
            logger.info(f"Retrieved {len(valid_branches)} branches: {valid_branches}")
            return valid_branches
            
        except Exception as e:
            logger.error(f"TerminusDB branch API failed: {e}")
            raise AsyncDatabaseError(f"브랜치 목록 조회 실패: {e}")
    
    async def get_current_branch(self, db_name: str) -> str:
        """실제 TerminusDB 현재 브랜치 조회"""
        try:
            # TerminusDB의 실제 HEAD 정보 API
            endpoint = f"/api/db/{self.connection_info.account}/{db_name}/_meta"
            result = await self._make_request("GET", endpoint)
            
            # HEAD 정보에서 현재 브랜치 추출
            if isinstance(result, dict):
                current_branch = result.get("head", {}).get("branch", "main")
                if isinstance(current_branch, str):
                    return current_branch
            
            # 기본값으로 main 반환
            return "main"
            
        except Exception as e:
            logger.error(f"TerminusDB get current branch API failed: {e}")
            raise AsyncDatabaseError(f"현재 브랜치 조회 실패: {e}")
    
    async def create_branch(self, db_name: str, branch_name: str, from_branch: Optional[str] = None) -> bool:
        """실제 TerminusDB 브랜치 생성"""
        try:
            if not branch_name or not branch_name.strip():
                raise ValueError("브랜치 이름은 필수입니다")
            
            # 예약된 이름 확인
            reserved_names = {'HEAD', 'main', 'master', 'origin'}
            if branch_name.lower() in reserved_names:
                raise ValueError(f"'{branch_name}'은(는) 예약된 브랜치 이름입니다")
            
            # TerminusDB 실제 브랜치 생성 API: POST /api/db/<account>/<db>/branch/<branch_name>
            endpoint = f"/api/db/{self.connection_info.account}/{db_name}/branch/{branch_name}"
            
            # 브랜치 생성 요청 데이터
            data = {
                "origin": from_branch or "main"
            }
            
            # TerminusDB에 실제 브랜치 생성 요청
            await self._make_request("POST", endpoint, data)
            
            logger.info(f"TerminusDB branch '{branch_name}' created successfully from '{from_branch or 'main'}'")
            return True
            
        except Exception as e:
            logger.error(f"TerminusDB create branch API failed: {e}")
            raise ValueError(f"브랜치 생성 실패: {e}")
    
    async def delete_branch(self, db_name: str, branch_name: str) -> bool:
        """실제 TerminusDB 브랜치 삭제"""
        try:
            # 보호된 브랜치 확인
            protected_branches = {'main', 'master', 'HEAD'}
            if branch_name.lower() in protected_branches:
                raise ValueError(f"보호된 브랜치 '{branch_name}'은(는) 삭제할 수 없습니다")
            
            # TerminusDB 실제 브랜치 삭제 API: DELETE /api/db/<account>/<db>/branch/<branch_name>
            endpoint = f"/api/db/{self.connection_info.account}/{db_name}/branch/{branch_name}"
            
            # TerminusDB에 실제 브랜치 삭제 요청
            await self._make_request("DELETE", endpoint)
            
            logger.info(f"TerminusDB branch '{branch_name}' deleted successfully")
            return True
            
        except Exception as e:
            logger.error(f"TerminusDB delete branch API failed: {e}")
            raise ValueError(f"브랜치 삭제 실패: {e}")
    
    async def checkout(self, db_name: str, target: str, target_type: str = "branch") -> bool:
        """실제 TerminusDB 체크아웃"""
        try:
            if not target or not target.strip():
                raise ValueError(f"{target_type} 이름은 필수입니다")
            
            if target_type == "branch":
                # TerminusDB 브랜치 체크아웃 API: POST /api/db/<account>/<db>/_meta
                endpoint = f"/api/db/{self.connection_info.account}/{db_name}/_meta"
                data = {
                    "head": {
                        "branch": target
                    }
                }
            elif target_type == "commit":
                # TerminusDB 커밋 체크아웃 API
                endpoint = f"/api/db/{self.connection_info.account}/{db_name}/_meta"
                data = {
                    "head": {
                        "commit": target
                    }
                }
            else:
                raise ValueError(f"지원되지 않는 target_type: {target_type}")
            
            # TerminusDB에 실제 checkout 요청
            await self._make_request("PUT", endpoint, data)
            
            logger.info(f"TerminusDB checkout to {target_type} '{target}' completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"TerminusDB checkout API failed: {e}")
            raise ValueError(f"체크아웃 실패: {e}")
    
    # === VERSION CONTROL METHODS ===
    
    async def commit(self, db_name: str, message: str, author: str = "admin") -> str:
        """실제 TerminusDB 커밋 생성"""
        try:
            if not message or not message.strip():
                raise ValueError("커밋 메시지는 필수입니다")
            
            # TerminusDB 실제 커밋 API: POST /api/db/<account>/<db>/_commit
            endpoint = f"/api/db/{self.connection_info.account}/{db_name}/_commit"
            
            # 커밋 요청 데이터
            data = {
                "message": message,
                "author": author
            }
            
            # TerminusDB에 실제 커밋 요청
            result = await self._make_request("POST", endpoint, data)
            
            # 커밋 ID 추출
            commit_id = result.get("commit_id", result.get("id", f"commit_{int(__import__('time').time())}"))
            
            logger.info(f"TerminusDB commit '{commit_id}' created successfully with message: '{message}' by {author}")
            return str(commit_id)
            
        except Exception as e:
            logger.error(f"TerminusDB commit API failed: {e}")
            raise ValueError(f"커밋 생성 실패: {e}")
    
    async def get_commit_history(self, db_name: str, branch: Optional[str] = None, 
                          limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
        """실제 TerminusDB 커밋 히스토리 조회"""
        try:
            # TerminusDB 실제 로그 API: GET /api/db/<account>/<db>/_log
            endpoint = f"/api/db/{self.connection_info.account}/{db_name}/_log"
            
            # 쿼리 파라미터
            params = {
                "limit": limit,
                "offset": offset
            }
            if branch:
                params["branch"] = branch
            
            # TerminusDB에 실제 로그 요청
            result = await self._make_request("GET", endpoint, params=params)
            
            # 커밋 히스토리 추출
            history = []
            if isinstance(result, dict) and "commits" in result:
                history = result["commits"]
            elif isinstance(result, list):
                history = result
            
            # 형식 정규화
            normalized_history = []
            for commit in history:
                if isinstance(commit, dict):
                    normalized_commit = {
                        "id": commit.get("id", commit.get("commit_id", "unknown")),
                        "message": commit.get("message", ""),
                        "author": commit.get("author", "unknown"),
                        "timestamp": commit.get("timestamp", commit.get("time", 0)),
                        "branch": commit.get("branch", branch or "main")
                    }
                    normalized_history.append(normalized_commit)
            
            logger.info(f"TerminusDB retrieved {len(normalized_history)} commits for database '{db_name}'")
            return normalized_history
            
        except Exception as e:
            logger.error(f"TerminusDB get commit history API failed: {e}")
            raise AsyncDatabaseError(f"커밋 히스토리 조회 실패: {e}")
    
    async def diff(self, db_name: str, from_ref: str, to_ref: str) -> List[Dict[str, Any]]:
        """실제 TerminusDB diff 조회"""
        try:
            # TerminusDB 실제 diff API: GET /api/db/<account>/<db>/_diff
            endpoint = f"/api/db/{self.connection_info.account}/{db_name}/_diff"
            
            # diff 요청 파라미터
            params = {
                "from": from_ref,
                "to": to_ref
            }
            
            # TerminusDB에 실제 diff 요청
            result = await self._make_request("GET", endpoint, params=params)
            
            # diff 결과 추출
            changes = []
            if isinstance(result, dict) and "changes" in result:
                changes = result["changes"]
            elif isinstance(result, list):
                changes = result
            
            # 형식 정규화
            normalized_changes = []
            for change in changes:
                if isinstance(change, dict):
                    normalized_change = {
                        "type": change.get("type", "unknown"),
                        "path": change.get("path", change.get("id", "unknown")),
                        "old_value": change.get("old_value"),
                        "new_value": change.get("new_value")
                    }
                    normalized_changes.append(normalized_change)
            
            logger.info(f"TerminusDB found {len(normalized_changes)} changes between '{from_ref}' and '{to_ref}'")
            return normalized_changes
            
        except Exception as e:
            logger.error(f"TerminusDB diff API failed: {e}")
            raise AsyncDatabaseError(f"diff 조회 실패: {e}")
    
    async def merge(self, db_name: str, source_branch: str, target_branch: str, 
             strategy: str = "auto") -> Dict[str, Any]:
        """실제 TerminusDB 브랜치 머지"""
        try:
            if source_branch == target_branch:
                raise ValueError("소스와 대상 브랜치가 동일합니다")
            
            # TerminusDB 실제 머지 API: POST /api/db/<account>/<db>/_merge
            endpoint = f"/api/db/{self.connection_info.account}/{db_name}/_merge"
            
            # 머지 요청 데이터
            data = {
                "source_branch": source_branch,
                "target_branch": target_branch,
                "strategy": strategy
            }
            
            # TerminusDB에 실제 머지 요청
            result = await self._make_request("POST", endpoint, data)
            
            # 머지 결과 추출 및 정규화
            merge_result = {
                "merged": result.get("success", result.get("merged", True)),
                "conflicts": result.get("conflicts", []),
                "source_branch": source_branch,
                "target_branch": target_branch,
                "strategy": strategy,
                "commit_id": result.get("commit_id", result.get("id"))
            }
            
            logger.info(f"TerminusDB merge completed: {source_branch} -> {target_branch}")
            return merge_result
            
        except Exception as e:
            logger.error(f"TerminusDB merge API failed: {e}")
            raise ValueError(f"브랜치 머지 실패: {e}")
    
    async def rollback(self, db_name: str, target: str) -> bool:
        """실제 TerminusDB 롤백"""
        try:
            if not target or not target.strip():
                raise ValueError("롤백 대상은 필수입니다")
            
            # TerminusDB 실제 롤백 API: POST /api/db/<account>/<db>/_reset
            endpoint = f"/api/db/{self.connection_info.account}/{db_name}/_reset"
            
            # 롤백 요청 데이터
            data = {
                "target": target
            }
            
            # TerminusDB에 실제 롤백 요청
            await self._make_request("POST", endpoint, data)
            
            logger.info(f"TerminusDB rollback to '{target}' completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"TerminusDB rollback API failed: {e}")
            raise ValueError(f"롤백 실패: {e}")
    
    async def rebase(self, db_name: str, onto: str, branch: Optional[str] = None) -> Dict[str, Any]:
        """실제 TerminusDB 리베이스"""
        try:
            if not onto or not onto.strip():
                raise ValueError("리베이스 대상은 필수입니다")
            
            if branch and branch == onto:
                raise ValueError("리베이스 대상과 브랜치가 동일합니다")
            
            # TerminusDB 실제 리베이스 API: POST /api/db/<account>/<db>/_rebase
            endpoint = f"/api/db/{self.connection_info.account}/{db_name}/_rebase"
            
            # 리베이스 요청 데이터
            data = {
                "onto": onto
            }
            if branch:
                data["branch"] = branch
            
            # TerminusDB에 실제 리베이스 요청
            result = await self._make_request("POST", endpoint, data)
            
            # 리베이스 결과 정규화
            rebase_result = {
                "success": result.get("success", True),
                "branch": branch or result.get("branch", "current"),
                "onto": onto,
                "commit_id": result.get("commit_id", result.get("id"))
            }
            
            logger.info(f"TerminusDB rebase completed: {branch or 'current'} onto {onto}")
            return rebase_result
            
        except Exception as e:
            logger.error(f"TerminusDB rebase API failed: {e}")
            raise ValueError(f"리베이스 실패: {e}")
    
    def _convert_to_woql(self, query_dict: Dict[str, Any]) -> Dict[str, Any]:
        """쿼리 딕셔너리를 WOQL 형식으로 변환"""
        class_id = query_dict.get("class_id")
        filters = query_dict.get("filters", [])
        select_fields = query_dict.get("select", [])
        limit = query_dict.get("limit")
        offset = query_dict.get("offset", 0)
        
        # WOQL 쿼리 기본 구조
        and_clauses = []
        
        # 클래스 타입 조건
        if class_id:
            and_clauses.append({
                "@type": "Triple",
                "subject": {"@type": "NodeValue", "variable": "ID"},
                "predicate": {"@type": "NodeValue", "node": "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"},
                "object": {"@type": "Value", "node": f"http://www.w3.org/2002/07/owl#{class_id}"}
            })
        
        # 필터 조건들 추가
        for filter_item in filters:
            field = filter_item.get("field")
            operator = filter_item.get("operator")
            value = filter_item.get("value")
            
            if operator == "=":
                and_clauses.append({
                    "@type": "Triple",
                    "subject": {"@type": "NodeValue", "variable": "ID"},
                    "predicate": {"@type": "NodeValue", "node": field},
                    "object": {"@type": "Value", "data": {"@type": "xsd:string", "@value": value}}
                })
            elif operator == ">":
                and_clauses.append({
                    "@type": "Greater",
                    "left": {
                        "@type": "Triple",
                        "subject": {"@type": "NodeValue", "variable": "ID"},
                        "predicate": {"@type": "NodeValue", "node": field},
                        "object": {"@type": "Value", "variable": f"{field}_val"}
                    },
                    "right": {"@type": "Value", "data": {"@type": "xsd:string", "@value": value}}
                })
        
        # SELECT 필드 추가
        if select_fields:
            for field in select_fields:
                and_clauses.append({
                    "@type": "Triple",
                    "subject": {"@type": "NodeValue", "variable": "ID"},
                    "predicate": {"@type": "NodeValue", "node": field},
                    "object": {"@type": "Value", "variable": field}
                })
        
        # 기본 쿼리 구조
        woql_query = {
            "@type": "And",
            "and": and_clauses
        }
        
        # LIMIT 및 OFFSET 추가
        if limit:
            woql_query = {
                "@type": "Limit",
                "limit": limit,
                "query": woql_query
            }
        
        if offset > 0:
            woql_query = {
                "@type": "Start",
                "start": offset,
                "query": woql_query
            }
        
        return woql_query
    
    async def query_database(self, db_name: str, query: Dict[str, Any]) -> Dict[str, Any]:
        """WOQL 쿼리 실행"""
        await self.ensure_db_exists(db_name)
        
        # TerminusDB WOQL 엔드포인트
        endpoint = f"/api/woql/{self.connection_info.account}/{db_name}"
        
        # 쿼리를 올바른 형식으로 래핑
        woql_request = {
            "query": query,
            "author": self.connection_info.user,
            "message": "Creating ontology class"
        }
        
        try:
            result = await self._make_request("POST", endpoint, woql_request)
            return result
            
        except Exception as e:
            logger.error(f"WOQL 쿼리 실행 실패: {e}")
            raise AsyncDatabaseError(f"WOQL 쿼리 실행 실패: {e}")
    
    async def create_ontology_class(self, db_name: str, class_data: Dict[str, Any]) -> Dict[str, Any]:
        """온톨로지 클래스 생성 (Document API 사용)"""
        class_id = class_data.get("id")
        if not class_id:
            raise AsyncValidationError("클래스 ID가 필요합니다")
        
        # 스키마 문서 생성
        schema_doc = {
            "@type": "Class",
            "@id": class_id
        }
        
        # 속성 추가
        if "properties" in class_data:
            for prop in class_data["properties"]:
                prop_name = prop.get("name")
                prop_type = prop.get("type", "xsd:string")
                if prop_name:
                    schema_doc[prop_name] = prop_type
        
        # 기본 속성 추가 (optional로 설정)
        if "label" in class_data:
            schema_doc["rdfs:label"] = {"@type": "Optional", "@class": "xsd:string"}
        if "description" in class_data:
            schema_doc["rdfs:comment"] = {"@type": "Optional", "@class": "xsd:string"}
        
        # Document API를 통한 스키마 생성
        endpoint = f"/api/document/{self.connection_info.account}/{db_name}"
        params = {
            "graph_type": "schema",
            "author": self.connection_info.user,
            "message": f"Creating {class_id} schema"
        }
        
        try:
            result = await self._make_request("POST", endpoint, [schema_doc], params)
            # 실제 TerminusDB 응답을 그대로 반환
            return result
            
        except Exception as e:
            logger.error(f"스키마 생성 실패: {e}")
            raise AsyncDatabaseError(f"스키마 생성 실패: {e}")
    
    async def list_ontology_classes(self, db_name: str) -> List[Dict[str, Any]]:
        """온톨로지 클래스 목록 조회 (Document API 사용)"""
        endpoint = f"/api/document/{self.connection_info.account}/{db_name}"
        params = {
            "graph_type": "schema"
        }
        
        try:
            # 특별한 처리: TerminusDB는 JSON Lines 형식으로 응답
            client = await self._get_client()
            token = await self._authenticate()
            
            headers = {
                "Authorization": token
            }
            
            response = await client.request(
                method="GET",
                url=endpoint,
                params=params,
                headers=headers
            )
            response.raise_for_status()
            
            # JSON Lines 형식 파싱
            classes = []
            response_text = response.text.strip()
            
            if response_text:
                for line in response_text.split('\n'):
                    try:
                        doc = json.loads(line)
                        if doc.get("@type") == "Class":
                            classes.append({
                                "id": doc.get("@id"),
                                "type": "Class",
                                "properties": {k: v for k, v in doc.items() if k not in ["@type", "@id"]}
                            })
                    except json.JSONDecodeError:
                        # 컨텍스트 줄 등은 무시
                        continue
            
            return classes
            
        except Exception as e:
            logger.error(f"클래스 목록 조회 실패: {e}")
            import traceback
            traceback.print_exc()
            raise AsyncDatabaseError(f"클래스 목록 조회 실패: {e}")
    
    async def create_document(self, db_name: str, document_data: Dict[str, Any]) -> Dict[str, Any]:
        """문서 생성"""
        doc_type = document_data.get("@type")
        if not doc_type:
            raise AsyncValidationError("문서 타입이 필요합니다")
        
        # ID 프리픽스 확인 및 수정
        doc_id = document_data.get("@id")
        if doc_id and not doc_id.startswith(f"{doc_type}/"):
            document_data["@id"] = f"{doc_type}/{doc_id}"
        
        # Document API를 통한 문서 생성
        endpoint = f"/api/document/{self.connection_info.account}/{db_name}"
        params = {
            "author": self.connection_info.user,
            "message": f"Creating {doc_type} document"
        }
        
        try:
            result = await self._make_request("POST", endpoint, [document_data], params)
            # 실제 TerminusDB 응답을 그대로 반환
            return result
            
        except Exception as e:
            logger.error(f"문서 생성 실패: {e}")
            raise AsyncDatabaseError(f"문서 생성 실패: {e}")
    
    async def list_documents(self, db_name: str, doc_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """문서 목록 조회"""
        endpoint = f"/api/document/{self.connection_info.account}/{db_name}"
        params = {}
        
        if doc_type:
            params["type"] = doc_type
        
        try:
            result = await self._make_request("GET", endpoint, None, params)
            
            documents = []
            if isinstance(result, list):
                for doc in result:
                    documents.append(doc)
            
            return documents
            
        except Exception as e:
            logger.error(f"문서 목록 조회 실패: {e}")
            raise AsyncDatabaseError(f"문서 목록 조회 실패: {e}")

    async def __aenter__(self):
        """비동기 컨텍스트 매니저 진입"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """비동기 컨텍스트 매니저 종료"""
        await self.disconnect()