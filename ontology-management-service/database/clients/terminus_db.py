"""
Terminus DB 클라이언트 - 표준 httpx 클라이언트 기반으로 리팩토링됨
TerminusDB 내부 LRU 캐싱 활용 최적화 (섹션 8.6.1 참조)
mTLS 지원으로 보안 강화 (NFR-S2)

표준 `httpx.AsyncClient`와 `httpx.Limits`를 사용하여 안정적인 연결 관리를 수행합니다.
"""
import logging
import os
import ssl
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx
# from httpx_pool import AsyncConnectionPool, ConnectionConfig # 제거됨

# from database.clients.unified_http_client import ( # 제거됨
#     create_terminus_client, create_secure_client, HTTPClientConfig, ClientMode, UnifiedHTTPClient
# )
from utils.retry_strategy import with_retry, DB_WRITE_CONFIG, DB_READ_CONFIG, DB_CRITICAL_CONFIG
from common_logging.setup import get_logger
# from .base import BaseDatabaseClient, DatabaseError, NotFoundError # 삭제됨

logger = logging.getLogger(__name__)

# Simple trace_method decorator placeholder
def trace_method(name):
    def decorator(func):
        return func
    return decorator

# add_span_attributes placeholder
def add_span_attributes(attrs):
    pass


class TerminusDBClient:
    """TerminusDB 비동기 클라이언트 - 표준 httpx.AsyncClient 기반"""

    def __init__(self, endpoint: str = "http://localhost:6363",
                 username: str = "admin",
                 password: str = "changeme-admin-pass",
                 service_name: str = "schema-service"):
        self.endpoint = endpoint
        self.username = username
        self.password = password
        self.service_name = service_name
        self._client: Optional[httpx.AsyncClient] = None

        # TerminusDB 내부 캐싱 설정
        self.cache_size = int(os.getenv("TERMINUSDB_LRU_CACHE_SIZE", "500000000"))  # 500MB
        self.enable_internal_cache = os.getenv("TERMINUSDB_CACHE_ENABLED", "true").lower() == "true"

        # mTLS 설정
        self.use_mtls = os.getenv("TERMINUSDB_USE_MTLS", "false").lower() == "true"
        
        logger.info(f"TerminusDB client configured - service: {self.service_name}, mTLS: {self.use_mtls}")


    async def __aenter__(self):
        await self._initialize_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _initialize_client(self):
        """클라이언트 초기화 - mTLS 지원"""
        if self._client:
            return
            
        try:
            # Connection pool 설정을 httpx.Limits로 대체
            limits = httpx.Limits(
                max_connections=int(os.getenv("DB_MAX_CONNECTIONS", "20")),
                max_keepalive_connections=int(os.getenv("DB_MIN_CONNECTIONS", "5")),
                keepalive_expiry=int(os.getenv("DB_MAX_IDLE_TIME", "300")),
            )
            
            # mTLS 설정 준비
            ssl_context = None
            if self.use_mtls:
                cert_path = os.getenv("TERMINUSDB_CERT_PATH")
                key_path = os.getenv("TERMINUSDB_KEY_PATH")
                ca_path = os.getenv("TERMINUSDB_CA_PATH")
                
                if cert_path and key_path:
                    ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
                    if ca_path:
                        ssl_context.load_verify_locations(ca_path)
                    ssl_context.load_cert_chain(cert_path, key_path)
                    ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
                    
                    if self.endpoint.startswith("http://"):
                        self.endpoint = self.endpoint.replace("http://", "https://")
                    logger.info("TerminusDB mTLS configuration prepared")
                else:
                    logger.warning("mTLS certificates not found, falling back to standard TLS")
                    self.use_mtls = False

            self._client = httpx.AsyncClient(
                base_url=self.endpoint,
                auth=(self.username, self.password),
                verify=ssl_context if ssl_context else True,
                limits=limits,
                timeout=int(os.getenv("DB_CONNECTION_TIMEOUT", "30")),
            )
            logger.info(f"TerminusDB httpx.AsyncClient initialized - mTLS: {self.use_mtls}")
                
        except Exception as e:
            logger.error(f"Failed to initialize TerminusDB client: {e}")
            # 최후의 fallback - 기본 클라이언트
            self._client = httpx.AsyncClient(
                base_url=self.endpoint,
                auth=(self.username, self.password)
            )
            self.use_mtls = False
            logger.info("TerminusDB client initialized with basic httpx configuration")

    async def close(self):
        """클라이언트 종료"""
        if self._client:
            await self._client.aclose()

    async def ping(self):
        """TerminusDB 서버 연결 확인"""
        if not self._client: return False
        try:
            response = await self._client.get("/api/info")
            return response.status_code == 200
        except Exception:
            return False

    @with_retry("terminusdb_create_database", config=DB_WRITE_CONFIG)
    @trace_method("terminusdb.create_database")
    async def create_database(self, db_name: str, label: Optional[str] = None):
        """데이터베이스 생성 - 자동 재시도 포함"""
        if not self._client: raise ConnectionError("Client not initialized")
        add_span_attributes({"db.name": db_name, "db.operation": "create_database"})
        url = f"/api/db/admin/{db_name}"

        payload = {
            "organization": "admin",
            "database": db_name,
            "label": label or f"{db_name} Database",
            "comment": "OMS Database"
        }

        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            logger.info(f"Database {db_name} created successfully")
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400:
                logger.warning(f"Database {db_name} already exists")
                return False
            raise

    @with_retry("terminusdb_delete_database", config=DB_CRITICAL_CONFIG)
    async def delete_database(self, db_name: str):
        """데이터베이스 삭제 - 중요 작업을 위한 강화된 재시도"""
        if not self._client: raise ConnectionError("Client not initialized")
        url = f"/api/db/admin/{db_name}"

        response = await self._client.delete(url)
        response.raise_for_status()
        logger.info(f"Database {db_name} deleted successfully")

    @with_retry("terminusdb_query_branch", config=DB_READ_CONFIG)
    @trace_method("terminusdb.query_branch")
    async def query_branch(self, db_name: str, branch_name: str, query: str, commit_msg: Optional[str] = None):
        """특정 브랜치를 대상으로 WOQL 쿼리를 실행합니다."""
        if not self._client: raise ConnectionError("Client not initialized")
        add_span_attributes({"db.name": db_name, "db.branch": branch_name, "db.operation": "query"})
        # URL 형식: /api/woql/{organization}/{db}/{branch}
        url = f"/api/woql/admin/{db_name}/{branch_name}"

        payload = {
            "query": query,
            "commit_info": {"message": commit_msg or f"Query on branch {branch_name}"}
        }

        response = await self._client.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    @with_retry("terminusdb_query", config=DB_READ_CONFIG)
    @trace_method("terminusdb.query")
    async def query(self, db_name: str, query: str, commit_msg: Optional[str] = None):
        """WOQL 쿼리 실행 - 읽기 작업 최적화된 재시도"""
        if not self._client: raise ConnectionError("Client not initialized")
        add_span_attributes({"db.name": db_name, "db.operation": "query"})
        url = f"/api/woql/admin/{db_name}"

        payload = {
            "query": query,
            "commit_info": {"message": commit_msg or "Query execution"}
        }

        response = await self._client.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    @with_retry("terminusdb_get_branch_info", config=DB_READ_CONFIG)
    @trace_method("terminusdb.get_branch_info")
    async def get_branch_info(self, db_name: str, branch_name: str) -> Optional[Dict[str, Any]]:
        """특정 브랜치의 정보를 가져옵니다 (head commit 등). 브랜치가 없으면 None을 반환합니다."""
        if not self._client: raise ConnectionError("Client not initialized")
        add_span_attributes({"db.name": db_name, "db.branch": branch_name, "db.operation": "get_branch_info"})
        url = f"/api/branch/admin/{db_name}/{branch_name}"

        try:
            response = await self._client.get(url)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Branch '{branch_name}' not found in db '{db_name}'.")
                return None
            raise
    
    @with_retry("terminusdb_get_document", config=DB_READ_CONFIG)
    @trace_method("terminusdb.get_document")
    async def get_document(self, db_name: str, branch_name: str, document_id: str) -> Optional[Dict[str, Any]]:
        """특정 브랜치에서 ID로 문서를 가져옵니다. 문서가 없으면 None을 반환합니다."""
        if not self._client: raise ConnectionError("Client not initialized")
        add_span_attributes({"db.name": db_name, "db.branch": branch_name, "document.id": document_id})
        url = f"/api/document/admin/{db_name}/{branch_name}"
        
        try:
            response = await self._client.get(url, params={"id": document_id})
            response.raise_for_status()
            # TerminusDB는 문서가 없을 때 200 OK와 빈 객체 {}를 반환할 수 있습니다.
            result = response.json()
            if not result:
                 logger.warning(f"Document '{document_id}' not found or is empty in branch '{branch_name}'.")
                 return None
            return result
        except httpx.HTTPStatusError as e:
            # 404도 명시적으로 처리
            if e.response.status_code == 404:
                logger.warning(f"Document endpoint not found for branch '{branch_name}' or document '{document_id}' does not exist.")
                return None
            raise

    async def get_databases(self):
        """데이터베이스 목록 조회"""
        if not self._client: raise ConnectionError("Client not initialized")
        try:
            response = await self._client.get("/api/info")
            response.raise_for_status()
            # 실제 데이터베이스 목록을 반환하는 로직이 필요. 여기서는 info를 기반으로 단순화.
            info = response.json()
            if "databases" in info:
                return [{"name": db, "status": "available"} for db in info["databases"]]
            return [{"name": "admin", "status": "available"}]
        except Exception as e:
            logger.warning(f"Failed to get databases: {e}")
            return []

    async def get_schema(self, db_name: str):
        """스키마 조회"""
        if not self._client: raise ConnectionError("Client not initialized")
        url = f"/api/schema/admin/{db_name}"
        
        response = await self._client.get(url)
        response.raise_for_status()
        return response.json()

    async def update_schema(self, db_name: str, schema: Dict[str, Any], commit_msg: str = "Schema update"):
        """스키마 업데이트"""
        if not self._client: raise ConnectionError("Client not initialized")
        url = f"/api/schema/admin/{db_name}"
        
        payload = {
            "schema": schema,
            "commit_info": {"message": commit_msg}
        }
        
        response = await self._client.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    @with_retry("terminusdb_create_branch", config=DB_WRITE_CONFIG)
    @trace_method("terminusdb.create_branch")
    async def create_branch(self, db_name: str, new_branch_name: str, source_branch: str = "main") -> bool:
        """새로운 브랜치를 생성합니다. 성공 시 True, 이미 존재하면 False를 반환합니다."""
        if not self._client: raise ConnectionError("Client not initialized")
        add_span_attributes({
            "db.name": db_name,
            "db.operation": "create_branch",
            "branch.new": new_branch_name,
            "branch.source": source_branch
        })
        url = f"/api/branch/admin/{db_name}"
        payload = {"origin": source_branch, "new_branch": new_branch_name}

        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            logger.info(f"Branch '{new_branch_name}' created from '{source_branch}' in db '{db_name}'.")
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 400 and "already exists" in e.response.text:
                logger.warning(f"Branch '{new_branch_name}' already exists in db '{db_name}'.")
                return False
            logger.error(f"Failed to create branch '{new_branch_name}': {e.response.text}")
            raise
    
    @with_retry("terminusdb_insert_document", config=DB_WRITE_CONFIG)
    @trace_method("terminusdb.insert_document")
    async def insert_document(self, db_name: str, branch_name: str, document: Dict[str, Any], commit_msg: Optional[str] = None) -> Dict[str, Any]:
        """특정 브랜치에 문서를 삽입합니다."""
        if not self._client: raise ConnectionError("Client not initialized")
        add_span_attributes({
            "db.name": db_name,
            "db.branch": branch_name,
            "db.operation": "insert_document"
        })
        url = f"/api/document/admin/{db_name}/{branch_name}"
        
        payload = {
            "commit_info": {"message": commit_msg or f"Inserted document into {branch_name}"},
            "document": document
        }

        response = await self._client.post(url, json=payload)
        response.raise_for_status()
        logger.info(f"Document inserted into branch '{branch_name}' in db '{db_name}'.")
        return response.json()

    @with_retry("terminusdb_delete_branch", config=DB_CRITICAL_CONFIG)
    @trace_method("terminusdb.delete_branch")
    async def delete_branch(self, db_name: str, branch_name: str) -> bool:
        """네이티브 브랜치를 삭제합니다. 성공 시 True, 실패 시 예외가 발생합니다."""
        if not self._client: raise ConnectionError("Client not initialized")
        add_span_attributes({"db.name": db_name, "db.operation": "delete_branch", "branch.name": branch_name})
        url = f"/api/branch/admin/{db_name}/{branch_name}"

        try:
            response = await self._client.delete(url)
            response.raise_for_status()
            logger.info(f"Branch '{branch_name}' deleted successfully from db '{db_name}'.")
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Branch '{branch_name}' not found for deletion in db '{db_name}'.")
                return False # 찾을 수 없는 경우도 성공 처리의 일종으로 간주
            logger.error(f"Failed to delete branch '{branch_name}': {e.response.text}")
            raise

    @with_retry("terminusdb_delete_document", config=DB_CRITICAL_CONFIG)
    @trace_method("terminusdb.delete_document")
    async def delete_document(self, db_name: str, branch_name: str, document_id: str, commit_msg: Optional[str] = None) -> bool:
        """특정 브랜치에서 문서를 삭제합니다."""
        if not self._client: raise ConnectionError("Client not initialized")
        add_span_attributes({
            "db.name": db_name,
            "db.branch": branch_name,
            "db.operation": "delete_document",
            "document.id": document_id
        })
        url = f"/api/document/admin/{db_name}/{branch_name}"

        payload = {
            "commit_info": {"message": commit_msg or f"Deleted document {document_id}"},
            "id": document_id
        }

        try:
            # 린터가 delete+json 조합을 인식하지 못하는 문제 우회를 위해 request 메서드를 명시적으로 사용
            response = await self._client.request("DELETE", url, json=payload)
            response.raise_for_status()
            logger.info(f"Document '{document_id}' deleted from branch '{branch_name}'.")
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Document '{document_id}' not found for deletion in branch '{branch_name}'.")
                return False
            logger.error(f"Failed to delete document '{document_id}': {e.response.text}")
            raise

    @with_retry("terminusdb_update_document", config=DB_WRITE_CONFIG)
    @trace_method("terminusdb.update_document")
    async def update_document(self, db_name: str, branch_name: str, document: Dict[str, Any], commit_msg: Optional[str] = None) -> Dict[str, Any]:
        """특정 브랜치의 문서를 업데이트(덮어쓰기)합니다."""
        if not self._client: raise ConnectionError("Client not initialized")
        add_span_attributes({
            "db.name": db_name,
            "db.branch": branch_name,
            "db.operation": "update_document"
        })
        # TerminusDB의 문서 업데이트는 삽입과 동일한 엔드포인트를 사용하지만,
        # 문서에 @id가 포함되어 있으면 해당 문서를 덮어씁니다.
        url = f"/api/document/admin/{db_name}/{branch_name}"
        
        payload = {
            "commit_info": {"message": commit_msg or f"Updated document {document.get('@id', '')}"},
            "document": document
        }

        # 업데이트는 PUT과 유사하게 동작하지만 TerminusDB에서는 POST를 사용합니다.
        response = await self._client.post(url, json=payload)
        response.raise_for_status()
        logger.info(f"Document '{document.get('@id')}' updated in branch '{branch_name}'.")
        return response.json()