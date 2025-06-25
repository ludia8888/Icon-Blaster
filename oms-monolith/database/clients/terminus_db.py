"""
Terminus DB 클라이언트 - Connection Pool 기반 프로덕션 안정성 보장
TerminusDB 내부 LRU 캐싱 활용 최적화 (섹션 8.6.1 참조)
mTLS 지원으로 보안 강화 (NFR-S2)

Connection Pool을 통한 안정적인 연결 관리와 TerminusDB의 TERMINUSDB_LRU_CACHE_SIZE
환경변수를 통한 내부 캐싱을 활용하여 높은 성능과 안정성을 달성합니다.
"""
import logging
import os
import ssl
from typing import Any, Dict, List, Optional

import httpx
from opentelemetry import trace

from shared.database.connection_pool import (
    ConnectionConfig,
    get_db_connection,
    pool_manager,
)
from shared.observability import add_span_attributes, inject_trace_context, trace_method
from shared.security.mtls_config import get_mtls_config
from shared.utils import (
    DB_CRITICAL_CONFIG,
    DB_READ_CONFIG,
    DB_WRITE_CONFIG,
    with_retry,
)

logger = logging.getLogger(__name__)


class TerminusDBClient:
    """TerminusDB 비동기 클라이언트 - Connection Pool 기반 + 내부 LRU 캐싱 활용"""

    def __init__(self, endpoint: str = "http://terminusdb:6363",
                 username: str = "admin",
                 password: str = "admin",
                 service_name: str = "schema-service",
                 use_connection_pool: bool = True):
        self.endpoint = endpoint
        self.username = username
        self.password = password
        self.service_name = service_name
        self.use_connection_pool = use_connection_pool
        self.client = None
        self.pool_config = None

        # TerminusDB 내부 캐싱 설정
        self.cache_size = int(os.getenv("TERMINUSDB_LRU_CACHE_SIZE", "500000000"))  # 500MB 기본값
        self.enable_internal_cache = True

        # mTLS 설정
        self.use_mtls = os.getenv("MTLS_ENABLED", "false").lower() == "true"

        # Connection Pool 설정
        if self.use_connection_pool:
            self.pool_config = ConnectionConfig(
                terminus_url=endpoint,
                max_connections=int(os.getenv("DB_MAX_CONNECTIONS", "20")),
                min_connections=int(os.getenv("DB_MIN_CONNECTIONS", "5")),
                max_idle_time=int(os.getenv("DB_MAX_IDLE_TIME", "300")),
                connection_timeout=int(os.getenv("DB_CONNECTION_TIMEOUT", "30")),
                database=os.getenv("DB_NAME", "oms"),
                service=service_name
            )

        logger.info(f"TerminusDB client initialized - service: {service_name}, "
                   f"connection pool: {use_connection_pool}, mTLS: {self.use_mtls}")

    async def __aenter__(self):
        await self._initialize_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _initialize_client(self):
        """클라이언트 초기화 - mTLS 지원"""
        if self.use_mtls:
            try:
                # mTLS 설정으로 클라이언트 생성
                config = get_mtls_config(self.service_name)

                ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
                ssl_context.load_verify_locations(config.ca_cert_path)
                ssl_context.load_cert_chain(config.cert_path, config.key_path)
                ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2

                self.client = httpx.AsyncClient(
                    verify=ssl_context,
                    timeout=30.0
                )

                # HTTPS 엔드포인트로 변경
                if self.endpoint.startswith("http://"):
                    self.endpoint = self.endpoint.replace("http://", "https://")

                logger.info("TerminusDB client initialized with mTLS")

            except Exception as e:
                logger.warning(f"mTLS initialization failed, falling back to HTTP: {e}")
                self.use_mtls = False
                self.client = httpx.AsyncClient(timeout=30.0)
        else:
            self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """클라이언트 종료"""
        if self.client:
            await self.client.aclose()

    @with_retry("terminusdb_create_database", config=DB_WRITE_CONFIG)
    @trace_method("terminusdb.create_database")
    async def create_database(self, db_name: str, label: Optional[str] = None):
        """데이터베이스 생성 - 자동 재시도 포함"""
        add_span_attributes({"db.name": db_name, "db.operation": "create_database"})
        url = f"{self.endpoint}/api/db/admin/{db_name}"

        payload = {
            "label": label or f"{db_name} Database",
            "comment": "OMS Database"
        }

        try:
            # Inject trace context into headers
            headers = inject_trace_context({})
            response = await self.client.put(
                url,
                auth=(self.username, self.password),
                json=payload,
                headers=headers
            )
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
        url = f"{self.endpoint}/api/db/admin/{db_name}"

        response = await self.client.delete(
            url,
            auth=(self.username, self.password)
        )
        response.raise_for_status()
        logger.info(f"Database {db_name} deleted successfully")

    @with_retry("terminusdb_create_branch", config=DB_WRITE_CONFIG)
    async def create_branch(self, db: str, branch_name: str,
                          from_branch: str = "main"):
        """브랜치 생성 - 자동 재시도 포함"""
        url = f"{self.endpoint}/api/branch/{db}/{from_branch}/{branch_name}"

        response = await self.client.post(
            url,
            auth=(self.username, self.password),
            json={"origin": f"{db}/{from_branch}"}
        )
        response.raise_for_status()
        logger.info(f"Branch {branch_name} created from {from_branch}")

    @with_retry("terminusdb_insert_document", config=DB_WRITE_CONFIG)
    async def insert_document(
        self,
        document: Dict[str, Any],
        db: str = "oms",
        branch: str = "main",
        author: Optional[str] = None,
        message: Optional[str] = None
    ) -> str:
        """문서 삽입 - 자동 재시도와 TerminusDB 내부 캐시 무효화"""
        url = f"{self.endpoint}/api/document/{db}/{branch}"

        # 커밋 정보 추가
        commit_info = {
            "author": author or "system",
            "message": message or "Insert document"
        }

        response = await self.client.post(
            url,
            auth=(self.username, self.password),
            json=document,
            params=commit_info
        )
        response.raise_for_status()

        # TerminusDB가 내부적으로 캐시 무효화 처리
        logger.debug(f"Document inserted in {db}/{branch}, internal cache updated")

        return document.get("@id", "")

    @with_retry("terminusdb_update_document", config=DB_WRITE_CONFIG)
    async def update_document(
        self,
        document: Dict[str, Any],
        db: str = "oms",
        branch: str = "main",
        author: Optional[str] = None,
        message: Optional[str] = None
    ) -> bool:
        """문서 업데이트 - 자동 재시도와 TerminusDB 내부 캐시 무효화"""
        url = f"{self.endpoint}/api/document/{db}/{branch}"

        commit_info = {
            "author": author or "system",
            "message": message or "Update document"
        }

        response = await self.client.put(
            url,
            auth=(self.username, self.password),
            json=document,
            params=commit_info
        )
        response.raise_for_status()

        # TerminusDB가 내부적으로 캐시 무효화 처리
        logger.debug(f"Document updated in {db}/{branch}, internal cache invalidated")

        return True

    @with_retry("terminusdb_get_document", config=DB_READ_CONFIG)
    @trace_method("terminusdb.get_document", kind=trace.SpanKind.CLIENT)
    async def get_document(
        self,
        doc_id: str,
        db: str = "oms",
        branch: str = "main"
    ) -> Optional[Dict[str, Any]]:
        """문서 조회 - 자동 재시도와 TerminusDB 내부 캐시 활용"""
        add_span_attributes({
            "db.name": db,
            "db.branch": branch,
            "db.document_id": doc_id,
            "db.operation": "get_document"
        })
        url = f"{self.endpoint}/api/document/{db}/{branch}/{doc_id}"

        try:
            # TerminusDB 내부 캐시에서 우선 조회
            response = await self.client.get(
                url,
                auth=(self.username, self.password)
            )

            if response.status_code == 404:
                return None

            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error getting document {doc_id}: {e}")
            return None

    async def delete_document(
        self,
        doc_id: str,
        db: str = "oms",
        branch: str = "main",
        author: Optional[str] = None,
        message: Optional[str] = None
    ) -> bool:
        """문서 삭제"""
        url = f"{self.endpoint}/api/document/{db}/{branch}/{doc_id}"

        commit_info = {
            "author": author or "system",
            "message": message or f"Delete document {doc_id}"
        }

        response = await self.client.delete(
            url,
            auth=(self.username, self.password),
            params=commit_info
        )
        response.raise_for_status()
        return True

    async def query(
        self,
        query: str,
        db: str = "oms",
        branch: str = "main"
    ) -> List[Dict[str, Any]]:
        """WOQL 쿼리 실행"""
        url = f"{self.endpoint}/api/woql/{db}/{branch}"

        response = await self.client.post(
            url,
            auth=(self.username, self.password),
            json={"query": query}
        )
        response.raise_for_status()

        result = response.json()
        return result.get("bindings", [])

    async def get_all_documents(
        self,
        doc_type: Optional[str] = None,
        db: str = "oms",
        branch: str = "main",
        limit: Optional[int] = None,
        offset: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """모든 문서 또는 특정 타입의 문서 조회"""
        params = {}
        if doc_type:
            params["type"] = doc_type
        if limit:
            params["limit"] = limit
        if offset:
            params["offset"] = offset

        url = f"{self.endpoint}/api/document/{db}/{branch}"

        response = await self.client.get(
            url,
            auth=(self.username, self.password),
            params=params
        )
        response.raise_for_status()

        return response.json()

    async def get_branch_info(
        self,
        db: str = "oms",
        branch: str = "main"
    ) -> Dict[str, Any]:
        """브랜치 정보 조회"""
        url = f"{self.endpoint}/api/branch/{db}/{branch}"

        response = await self.client.get(
            url,
            auth=(self.username, self.password)
        )
        response.raise_for_status()

        return response.json()

    async def merge_branches(
        self,
        db: str,
        source_branch: str,
        target_branch: str,
        author: Optional[str] = None,
        message: Optional[str] = None
    ) -> Dict[str, Any]:
        """브랜치 병합"""
        url = f"{self.endpoint}/api/merge/{db}/{source_branch}/{target_branch}"

        payload = {
            "author": author or "system",
            "message": message or f"Merge {source_branch} into {target_branch}"
        }

        response = await self.client.post(
            url,
            auth=(self.username, self.password),
            json=payload
        )
        response.raise_for_status()

        return response.json()

    async def get_commit_history(
        self,
        db: str = "oms",
        branch: str = "main",
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """커밋 히스토리 조회"""
        url = f"{self.endpoint}/api/log/{db}/{branch}"

        response = await self.client.get(
            url,
            auth=(self.username, self.password),
            params={"limit": limit}
        )
        response.raise_for_status()

        return response.json()

    async def health_check(self) -> bool:
        """헬스 체크"""
        try:
            if self.use_connection_pool:
                # Use connection pool for health check
                async with get_db_connection(self.service_name, self.pool_config) as conn:
                    return await conn.health_check()
            else:
                response = await self.client.get(f"{self.endpoint}/api/info")
                return response.status_code == 200
        except Exception:
            return False

    # Connection Pool based methods for production use
    async def query_with_pool(
        self,
        query: str,
        db: str = "oms",
        branch: str = "main"
    ) -> List[Dict[str, Any]]:
        """Connection Pool을 사용한 WOQL 쿼리 실행"""
        if not self.use_connection_pool:
            return await self.query(query, db, branch)

        async with get_db_connection(self.service_name, self.pool_config) as conn:
            result = await conn.execute_query(query, db, branch)
            return result.get("bindings", [])

    async def get_document_with_pool(
        self,
        doc_id: str,
        db: str = "oms",
        branch: str = "main"
    ) -> Optional[Dict[str, Any]]:
        """Connection Pool을 사용한 문서 조회"""
        if not self.use_connection_pool:
            return await self.get_document(doc_id, db, branch)

        try:
            async with get_db_connection(self.service_name, self.pool_config) as conn:
                response = await conn.client.get(
                    f"/api/document/{db}/{branch}/{doc_id}",
                    auth=(self.username, self.password)
                )

                if response.status_code == 404:
                    return None

                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Error getting document {doc_id}: {e}")
            return None

    async def insert_document_with_pool(
        self,
        document: Dict[str, Any],
        db: str = "oms",
        branch: str = "main",
        author: Optional[str] = None,
        message: Optional[str] = None
    ) -> str:
        """Connection Pool을 사용한 문서 삽입"""
        if not self.use_connection_pool:
            return await self.insert_document(document, db, branch, author, message)

        async with get_db_connection(self.service_name, self.pool_config) as conn:
            success = await conn.insert_document(document, db, branch)
            if success:
                return document.get("@id", "")
            else:
                raise Exception("Document insertion failed")

    async def get_schema_with_pool(
        self,
        db: str = "oms",
        branch: str = "main"
    ) -> Dict[str, Any]:
        """Connection Pool을 사용한 스키마 조회"""
        if not self.use_connection_pool:
            # Fallback to direct client method
            url = f"{self.endpoint}/api/schema/{db}/{branch}"
            response = await self.client.get(
                url,
                auth=(self.username, self.password)
            )
            response.raise_for_status()
            return response.json()

        async with get_db_connection(self.service_name, self.pool_config) as conn:
            return await conn.get_schema(db, branch)

    def get_pool_stats(self) -> Optional[Dict[str, Any]]:
        """Connection Pool 통계 조회"""
        if not self.use_connection_pool:
            return None

        pool = pool_manager.get_pool(self.service_name, self.pool_config)
        return pool.get_stats()

    async def initialize_pool(self):
        """Connection Pool 초기화"""
        if self.use_connection_pool:
            pool = pool_manager.get_pool(self.service_name, self.pool_config)
            await pool.start()

    async def close_pool(self):
        """Connection Pool 종료"""
        if self.use_connection_pool and self.service_name in pool_manager.pools:
            pool = pool_manager.pools[self.service_name]
            await pool.stop()
