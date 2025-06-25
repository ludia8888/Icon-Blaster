"""
Simple TerminusDB Client for OMS
Self-contained client without shared module dependencies
"""
import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional
import httpx

logger = logging.getLogger(__name__)


class SimpleTerminusDBClient:
    """
    간단한 TerminusDB 클라이언트 
    OMS 전용으로 shared 모듈 의존성 없음
    """
    
    def __init__(
        self,
        endpoint: str = None,
        username: str = "admin", 
        password: str = "admin",
        database: str = "oms",
        timeout: int = 30
    ):
        self.endpoint = endpoint or os.getenv("TERMINUS_DB_ENDPOINT", "http://terminusdb:6363")
        self.username = username
        self.password = password  
        self.database = database or "admin"  # 기본 admin 데이터베이스 사용
        self.timeout = timeout
        self.client = None
        self._connected = False
        
    async def connect(self) -> bool:
        """TerminusDB 연결"""
        try:
            # TerminusDB 11.1.0은 인증 없이도 접근 가능할 수 있음
            self.client = httpx.AsyncClient(
                base_url=self.endpoint,
                timeout=httpx.Timeout(self.timeout)
            )
            
            # 먼저 인증 없이 연결 테스트
            response = await self.client.get("/api/info")
            if response.status_code == 200:
                self._connected = True
                logger.info(f"Connected to TerminusDB at {self.endpoint} (no auth)")
                
                # admin 데이터베이스는 기본으로 존재하므로 생성 스킵
                if self.database != "admin":
                    await self._ensure_database_exists()
                return True
            elif response.status_code == 401:
                # 인증이 필요한 경우 Basic Auth 시도
                await self.client.aclose()
                self.client = httpx.AsyncClient(
                    base_url=self.endpoint,
                    timeout=httpx.Timeout(self.timeout),
                    auth=(self.username, self.password)
                )
                
                response = await self.client.get("/api/info")
                if response.status_code == 200:
                    self._connected = True
                    logger.info(f"Connected to TerminusDB at {self.endpoint} (with auth)")
                    
                    # admin 데이터베이스는 기본으로 존재하므로 생성 스킵
                    if self.database != "admin":
                        await self._ensure_database_exists()
                    return True
                else:
                    logger.error(f"Failed to connect to TerminusDB with auth: {response.status_code}")
                    return False
            else:
                logger.error(f"Failed to connect to TerminusDB: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"TerminusDB connection error: {e}")
            return False
    
    async def disconnect(self):
        """연결 종료"""
        if self.client:
            await self.client.aclose()
            self._connected = False
            logger.info("Disconnected from TerminusDB")
    
    async def _ensure_database_exists(self):
        """데이터베이스 존재 확인 및 생성"""
        try:
            # TerminusDB 11.1.0 스타일로 데이터베이스 확인
            response = await self.client.get(f"/api/db/admin/{self.database}")
            if response.status_code == 404:
                # 데이터베이스 생성 시도 (권한 없으면 스킵)
                await self._create_database()
            elif response.status_code == 200:
                logger.debug(f"Database {self.database} already exists")
            else:
                # 다른 상태 코드는 로그만 남기고 계속 진행
                logger.debug(f"Database check returned: {response.status_code}")
        except Exception as e:
            logger.debug(f"Database check failed: {e}")
            # 실패해도 계속 진행 - 메모리 모드로 fallback
    
    async def _create_database(self):
        """데이터베이스 생성"""
        try:
            # TerminusDB 11.1.0 API 스타일
            create_data = {
                "@type": "CreateDatabase",
                "organization": "admin",  # 기본 organization
                "database": self.database,
                "label": f"OMS Database - {self.database}",
                "comment": "OMS ActionType metadata storage"
            }
            
            response = await self.client.post(
                f"/api/db/admin/{self.database}",
                json=create_data
            )
            
            if response.status_code in [200, 201]:
                logger.info(f"Created database: {self.database}")
            else:
                logger.warning(f"Database creation failed: {response.status_code} - {response.text}")
                
        except Exception as e:
            logger.warning(f"Database creation error: {e}")
            # 생성 실패해도 계속 진행
    
    async def insert_document(
        self, 
        doc: Dict[str, Any], 
        doc_id: str = None,
        graph_type: str = "instance",
        branch: str = "main"
    ) -> bool:
        """문서 삽입"""
        if not self._connected:
            connected = await self.connect()
            if not connected:
                return False
            
        try:
            # TerminusDB 11.1.0 document API 스타일
            url = f"/api/document/admin/{self.database}/local/{branch}"
            
            # 문서 준비
            doc_copy = doc.copy()
            if doc_id:
                doc_copy["@id"] = doc_id
            
            # TerminusDB 11.1.0은 author 파라미터가 필요함
            payload = {
                "author": "OMS System",
                "message": f"Insert document {doc_id}",
                "documents": [doc_copy]
            }
            
            response = await self.client.post(url, json=payload)
            
            if response.status_code in [200, 201]:
                logger.debug(f"Inserted document: {doc_id}")
                return True
            else:
                logger.warning(f"Document insert failed: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.warning(f"Document insert error: {e}")
            return False
    
    async def get_document(
        self, 
        doc_id: str,
        graph_type: str = "instance", 
        branch: str = "main"
    ) -> Optional[Dict[str, Any]]:
        """문서 조회"""
        if not self._connected:
            connected = await self.connect()
            if not connected:
                return None
            
        try:
            # TerminusDB 11.1.0에서는 WOQL 쿼리로 문서 조회
            woql_query = {
                "@type": "Triple",
                "subject": {"@type": "Value", "@value": doc_id},
                "predicate": {"@type": "Variable", "@value": "Predicate"},
                "object": {"@type": "Variable", "@value": "Object"}
            }
            
            url = f"/api/woql/admin/{self.database}/local/{branch}"
            response = await self.client.post(url, json={"query": woql_query})
            
            if response.status_code == 200:
                result = response.json()
                bindings = result.get("bindings", [])
                if bindings:
                    # 바인딩 결과를 문서 형태로 재구성
                    doc = {"@id": doc_id}
                    for binding in bindings:
                        pred = binding.get("Predicate", {}).get("@value", "")
                        obj = binding.get("Object", {})
                        if pred and not pred.startswith("@"):
                            doc[pred] = obj.get("@value", obj)
                    return doc if len(doc) > 1 else None
                return None
            elif response.status_code == 404:
                return None
            else:
                logger.warning(f"Document get failed: {response.status_code}")
                return None
                
        except Exception as e:
            logger.warning(f"Document get error: {e}")
            return None
    
    async def update_document(
        self,
        doc: Dict[str, Any],
        doc_id: str,
        graph_type: str = "instance",
        branch: str = "main" 
    ) -> bool:
        """문서 업데이트"""
        if not self._connected:
            await self.connect()
            
        try:
            url = f"/api/document/{self.database}/{branch}"
            
            # 문서에 @id 설정
            doc["@id"] = doc_id
            
            response = await self.client.put(url, json=doc)
            
            if response.status_code in [200, 201]:
                logger.debug(f"Updated document: {doc_id}")
                return True
            else:
                logger.error(f"Document update failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Document update error: {e}")
            return False
    
    async def delete_document(
        self,
        doc_id: str,
        graph_type: str = "instance",
        branch: str = "main"
    ) -> bool:
        """문서 삭제"""
        if not self._connected:
            await self.connect()
            
        try:
            url = f"/api/document/{self.database}/{branch}/{doc_id}"
            response = await self.client.delete(url)
            
            if response.status_code in [200, 204]:
                logger.debug(f"Deleted document: {doc_id}")
                return True
            else:
                logger.error(f"Document delete failed: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Document delete error: {e}")
            return False
    
    async def query_documents(
        self,
        query: Dict[str, Any],
        branch: str = "main"
    ) -> List[Dict[str, Any]]:
        """WOQL 쿼리 실행"""
        if not self._connected:
            await self.connect()
            
        try:
            url = f"/api/woql/{self.database}/{branch}"
            response = await self.client.post(url, json={"query": query})
            
            if response.status_code == 200:
                result = response.json()
                return result.get("bindings", [])
            else:
                logger.error(f"Query failed: {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Query error: {e}")
            return []
    
    async def list_all_documents(
        self,
        doc_type: str = None,
        branch: str = "main"
    ) -> List[Dict[str, Any]]:
        """모든 문서 목록 조회"""
        if not self._connected:
            await self.connect()
            
        try:
            # 간단한 WOQL 쿼리로 모든 문서 조회
            if doc_type:
                query = {
                    "@type": "Triple",
                    "subject": {"@type": "Variable", "@value": "Doc"},
                    "predicate": {"@type": "Variable", "@value": "type"},
                    "object": {"@type": "Value", "@value": doc_type}
                }
            else:
                query = {
                    "@type": "Triple", 
                    "subject": {"@type": "Variable", "@value": "Doc"},
                    "predicate": {"@type": "Variable", "@value": "Prop"},
                    "object": {"@type": "Variable", "@value": "Value"}
                }
            
            return await self.query_documents(query, branch)
            
        except Exception as e:
            logger.error(f"List documents error: {e}")
            return []
    
    def is_connected(self) -> bool:
        """연결 상태 확인"""
        return self._connected
    
    async def health_check(self) -> bool:
        """헬스 체크"""
        try:
            if not self.client:
                return False
                
            response = await self.client.get("/api/info")
            return response.status_code == 200
            
        except Exception:
            return False


# 편의 함수들
async def create_simple_client(
    endpoint: str = None,
    database: str = "oms"
) -> SimpleTerminusDBClient:
    """간단한 클라이언트 생성 및 연결"""
    client = SimpleTerminusDBClient(
        endpoint=endpoint,
        database=database
    )
    
    await client.connect()
    return client


async def test_connection(endpoint: str = None) -> bool:
    """TerminusDB 연결 테스트"""
    client = SimpleTerminusDBClient(endpoint=endpoint)
    try:
        connected = await client.connect()
        if connected:
            health = await client.health_check()
            await client.disconnect()
            return health
        return False
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return False