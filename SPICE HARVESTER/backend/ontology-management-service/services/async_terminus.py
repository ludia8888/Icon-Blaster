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
from models.config import ConnectionConfig
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
                return {"success": True}
            
        except httpx.HTTPStatusError as e:
            error_detail = ""
            try:
                error_detail = e.response.text
            except:
                pass
            
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
            
            databases = []
            # TerminusDB 응답 형식: [{"path": "admin/db_name"}]
            db_list = result if isinstance(result, list) else []
            
            for db_info in db_list:
                path = db_info.get("path", "")
                if "/" in path:
                    _, db_name = path.split("/", 1)
                    databases.append({
                        "name": db_name,
                        "label": db_name,
                        "comment": f"Database {db_name}",
                        "created": None,
                        "path": path
                    })
                    self._db_cache.add(db_name)
            
            return databases
            
        except Exception as e:
            logger.error(f"Failed to list databases: {e}")
            raise AsyncDatabaseError(f"데이터베이스 목록 조회 실패: {e}")
    
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
            return {"api:status": "api:success", "class_id": class_id, "result": result}
            
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
            return {"api:status": "api:success", "document_id": doc_id, "result": result}
            
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