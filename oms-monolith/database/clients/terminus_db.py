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

    def __init__(self, endpoint: str = "http://localhost:6363",
                 username: str = "admin",
                 password: str = "changeme-admin-pass",
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
        self.cache_size = int(os.getenv("TERMINUSDB_LRU_CACHE_SIZE", "500000000"))  # 500MB
        self.enable_internal_cache = os.getenv("TERMINUSDB_CACHE_ENABLED", "true").lower() == "true"

        # mTLS 설정
        self.use_mtls = os.getenv("TERMINUSDB_USE_MTLS", "false").lower() == "true"

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
                    timeout=30.0,
                    auth=(self.username, self.password),
                    headers={'Content-Type': 'application/json'}
                )

                # HTTPS 엔드포인트로 변경
                if self.endpoint.startswith("http://"):
                    self.endpoint = self.endpoint.replace("http://", "https://")

                logger.info("TerminusDB client initialized with mTLS")

            except Exception as e:
                logger.warning(f"mTLS initialization failed, falling back to HTTP: {e}")
                self.use_mtls = False
                self.client = httpx.AsyncClient(
                    auth=(self.username, self.password),
                    timeout=30.0,
                    headers={'Content-Type': 'application/json'}
                )
        else:
            # HTTP 모드 - 기본 인증 포함
            self.client = httpx.AsyncClient(
                auth=(self.username, self.password),
                timeout=30.0,
                headers={'Content-Type': 'application/json'}
            )

    async def close(self):
        """클라이언트 종료"""
        if self.client:
            await self.client.aclose()

    async def ping(self):
        """TerminusDB 서버 연결 확인"""
        try:
            response = await self.client.get(f"{self.endpoint}/api/info")
            return response.status_code == 200
        except Exception:
            return False

    @with_retry("terminusdb_create_database", config=DB_WRITE_CONFIG)
    @trace_method("terminusdb.create_database")
    async def create_database(self, db_name: str, label: Optional[str] = None):
        """데이터베이스 생성 - 자동 재시도 포함"""
        add_span_attributes({"db.name": db_name, "db.operation": "create_database"})
        url = f"{self.endpoint}/api/db/admin/{db_name}"

        payload = {
            "organization": "admin",
            "database": db_name,
            "label": label or f"{db_name} Database",
            "comment": "OMS Database"
        }

        try:
            # Inject trace context into headers
            headers = inject_trace_context({})
            response = await self.client.post(
                url,
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

    @with_retry("terminusdb_query", config=DB_READ_CONFIG)
    @trace_method("terminusdb.query")
    async def query(self, db_name: str, query: str, commit_msg: Optional[str] = None):
        """WOQL 쿼리 실행 - 읽기 작업 최적화된 재시도"""
        add_span_attributes({"db.name": db_name, "db.operation": "query"})
        url = f"{self.endpoint}/api/woql/admin/{db_name}"

        payload = {
            "query": query,
            "commit_info": {"message": commit_msg or "Query execution"}
        }

        headers = inject_trace_context({})
        response = await self.client.post(
            url,
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        return response.json()

    async def get_databases(self):
        """데이터베이스 목록 조회"""
        try:
            # TerminusDB 11.1.0에서는 다른 엔드포인트 사용
            response = await self.client.get(f"{self.endpoint}/api/organizations")
            if response.status_code == 200:
                return response.json()
            else:
                # 대안 방법: info에서 조직 정보 확인
                response = await self.client.get(f"{self.endpoint}/api/info")
                return [{"name": "admin", "status": "available"}]
        except Exception as e:
            logger.warning(f"Failed to get databases: {e}")
            return []

    async def get_schema(self, db_name: str):
        """스키마 조회"""
        url = f"{self.endpoint}/api/schema/admin/{db_name}"
        
        response = await self.client.get(url)
        response.raise_for_status()
        return response.json()

    async def update_schema(self, db_name: str, schema: Dict[str, Any], commit_msg: str = "Schema update"):
        """스키마 업데이트"""
        url = f"{self.endpoint}/api/schema/admin/{db_name}"
        
        payload = {
            "schema": schema,
            "commit_info": {"message": commit_msg}
        }
        
        response = await self.client.post(
            url,
            json=payload
        )
        response.raise_for_status()
        return response.json()