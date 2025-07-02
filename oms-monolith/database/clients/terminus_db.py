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

from database.clients.unified_http_client import (
    create_terminus_client, create_secure_client, HTTPClientConfig, ClientMode, UnifiedHTTPClient
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
        """클라이언트 초기화 - mTLS 지원 (UnifiedHTTPClient 사용)"""
        try:
            # Connection pool 설정을 UnifiedHTTPClient에 전달
            connection_pool_config = {}
            if self.use_connection_pool and self.pool_config:
                connection_pool_config = {
                    "max_connections": self.pool_config.max_connections,
                    "max_keepalive_connections": max(self.pool_config.min_connections, 5),
                }
            
            # mTLS 설정 준비
            ssl_context = None
            cert_path = None
            key_path = None
            ca_path = None
            
            if self.use_mtls:
                try:
                    # mTLS 설정 로드 (실제 구현에서는 get_mtls_config 사용)
                    # config = get_mtls_config(self.service_name)
                    # cert_path = config.cert_path
                    # key_path = config.key_path  
                    # ca_path = config.ca_cert_path
                    
                    # 임시로 환경변수에서 로드
                    cert_path = os.getenv("TERMINUSDB_CERT_PATH")
                    key_path = os.getenv("TERMINUSDB_KEY_PATH")
                    ca_path = os.getenv("TERMINUSDB_CA_PATH")
                    
                    if cert_path and key_path:
                        # SSL 컨텍스트 생성
                        ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
                        if ca_path:
                            ssl_context.load_verify_locations(ca_path)
                        ssl_context.load_cert_chain(cert_path, key_path)
                        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
                        
                        # HTTPS 엔드포인트로 변경
                        if self.endpoint.startswith("http://"):
                            self.endpoint = self.endpoint.replace("http://", "https://")
                        
                        logger.info("TerminusDB mTLS configuration prepared")
                    else:
                        logger.warning("mTLS certificates not found, falling back to standard TLS")
                        self.use_mtls = False
                        
                except Exception as e:
                    logger.warning(f"mTLS setup failed, will use fallback: {e}")
                    # UnifiedHTTPClient의 fallback 기능이 처리함
            
            # UnifiedHTTPClient로 클라이언트 생성
            self.client = create_terminus_client(
                endpoint=self.endpoint,
                username=self.username,
                password=self.password,
                enable_mtls=self.use_mtls,
                ssl_context=ssl_context,
                cert_path=cert_path,
                key_path=key_path,
                ca_path=ca_path,
                connection_pool_config=connection_pool_config,
                enable_mtls_fallback=True,
                enable_tracing=True,
            )
            
            logger.info(f"TerminusDB client initialized - mTLS: {self.use_mtls}, Pool: {self.use_connection_pool}")
                
        except Exception as e:
            logger.error(f"Failed to initialize TerminusDB client: {e}")
            # 최후의 fallback - 기본 클라이언트
            self.client = create_terminus_client(
                endpoint=self.endpoint,
                username=self.username,
                password=self.password,
                enable_mtls=False,
                enable_mtls_fallback=False,
            )
            self.use_mtls = False
            logger.info("TerminusDB client initialized with basic configuration")

    async def close(self):
        """클라이언트 종료"""
        if self.client:
            await self.client.close()

    async def ping(self):
        """TerminusDB 서버 연결 확인"""
        try:
            response = await self.client.get("/api/info")
            return response.status_code == 200
        except Exception:
            return False

    @with_retry("terminusdb_create_database", config=DB_WRITE_CONFIG)
    @trace_method("terminusdb.create_database")
    async def create_database(self, db_name: str, label: Optional[str] = None):
        """데이터베이스 생성 - 자동 재시도 포함"""
        add_span_attributes({"db.name": db_name, "db.operation": "create_database"})
        url = f"/api/db/admin/{db_name}"

        payload = {
            "organization": "admin",
            "database": db_name,
            "label": label or f"{db_name} Database",
            "comment": "OMS Database"
        }

        try:
            # Trace context is automatically injected by UnifiedHTTPClient if enabled
            response = await self.client.post(
                url,
                json=payload
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
        url = f"/api/db/admin/{db_name}"

        response = await self.client.delete(url)
        response.raise_for_status()
        logger.info(f"Database {db_name} deleted successfully")

    @with_retry("terminusdb_query", config=DB_READ_CONFIG)
    @trace_method("terminusdb.query")
    async def query(self, db_name: str, query: str, commit_msg: Optional[str] = None):
        """WOQL 쿼리 실행 - 읽기 작업 최적화된 재시도"""
        add_span_attributes({"db.name": db_name, "db.operation": "query"})
        url = f"/api/woql/admin/{db_name}"

        payload = {
            "query": query,
            "commit_info": {"message": commit_msg or "Query execution"}
        }

        response = await self.client.post(
            url,
            json=payload
        )
        response.raise_for_status()
        return response.json()

    async def get_databases(self):
        """데이터베이스 목록 조회"""
        try:
            # TerminusDB 11.1.0에서는 다른 엔드포인트 사용
            response = await self.client.get("/api/organizations")
            if response.status_code == 200:
                return response.json()
            else:
                # 대안 방법: info에서 조직 정보 확인
                response = await self.client.get("/api/info")
                return [{"name": "admin", "status": "available"}]
        except Exception as e:
            logger.warning(f"Failed to get databases: {e}")
            return []

    async def get_schema(self, db_name: str):
        """스키마 조회"""
        url = f"/api/schema/admin/{db_name}"
        
        response = await self.client.get(url)
        response.raise_for_status()
        return response.json()

    async def update_schema(self, db_name: str, schema: Dict[str, Any], commit_msg: str = "Schema update"):
        """스키마 업데이트"""
        url = f"/api/schema/admin/{db_name}"
        
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