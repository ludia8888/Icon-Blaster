"""
OMS (Ontology Management Service) 클라이언트
BFF에서 OMS와 통신하기 위한 HTTP 클라이언트
"""

import httpx
from typing import Dict, List, Optional, Any
import logging
import sys
import os

# shared 모델 import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'shared'))
from models.ontology import (
    OntologyCreateRequest,
    OntologyUpdateRequest,
    QueryRequestInternal
)

logger = logging.getLogger(__name__)

class OMSClient:
    """OMS HTTP 클라이언트"""
    
    def __init__(self, base_url: str = "http://localhost:8001"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(
            base_url=base_url,
            timeout=30.0,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        )
    
    async def close(self):
        """클라이언트 연결 종료"""
        await self.client.aclose()
    
    async def check_health(self) -> bool:
        """OMS 서비스 상태 확인"""
        try:
            response = await self.client.get("/health")
            response.raise_for_status()
            data = response.json()
            return data.get("status") == "healthy"
        except Exception as e:
            logger.error(f"OMS 헬스 체크 실패: {e}")
            return False
    
    # 온톨로지 관리 메서드
    async def create_ontology(self, db_name: str, ontology: OntologyCreateRequest) -> Dict[str, Any]:
        """온톨로지 생성"""
        try:
            # OMS 요청 형태에 맞게 db_name을 JSON에 포함
            ontology_data = ontology.dict()
            ontology_data["db_name"] = db_name
            
            response = await self.client.post(
                "/api/v1/create",
                json=ontology_data
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"온톨로지 생성 실패: {e}")
            raise
    
    async def get_ontology(self, db_name: str, class_id: str) -> Optional[Dict[str, Any]]:
        """온톨로지 조회"""
        try:
            response = await self.client.get(
                f"/api/v1/get/{class_id}",
                params={"db_name": db_name}
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"온톨로지 조회 실패: {e}")
            raise
    
    async def update_ontology(self, db_name: str, class_id: str, 
                            update_data: OntologyUpdateRequest) -> Dict[str, Any]:
        """온톨로지 업데이트"""
        try:
            update_dict = update_data.dict()
            update_dict["db_name"] = db_name
            
            response = await self.client.put(
                f"/api/v1/update/{class_id}",
                json=update_dict
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"온톨로지 업데이트 실패: {e}")
            raise
    
    async def delete_ontology(self, db_name: str, class_id: str) -> bool:
        """온톨로지 삭제"""
        try:
            response = await self.client.delete(
                f"/api/v1/delete/{class_id}",
                params={"db_name": db_name}
            )
            response.raise_for_status()
            return True
        except httpx.HTTPError as e:
            logger.error(f"온톨로지 삭제 실패: {e}")
            raise
    
    async def list_ontologies(self, db_name: str, limit: Optional[int] = None, 
                            offset: int = 0) -> List[Dict[str, Any]]:
        """온톨로지 목록 조회"""
        try:
            params = {"db_name": db_name, "offset": offset}
            if limit:
                params["limit"] = limit
            
            response = await self.client.get("/api/v1/list", params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("data", {}).get("ontologies", [])
        except httpx.HTTPError as e:
            logger.error(f"온톨로지 목록 조회 실패: {e}")
            raise
    
    async def query_ontologies(self, db_name: str, query: QueryRequestInternal) -> Dict[str, Any]:
        """온톨로지 쿼리"""
        try:
            query_data = query.dict()
            query_data["db_name"] = db_name
            
            response = await self.client.post(
                "/api/v1/query",
                json=query_data
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"온톨로지 쿼리 실패: {e}")
            raise
    
    # 데이터베이스 관리 메서드
    async def create_database(self, db_name: str, description: Optional[str] = None) -> Dict[str, Any]:
        """데이터베이스 생성"""
        try:
            data = {"name": db_name}
            if description:
                data["description"] = description
            
            response = await self.client.post("/api/v1/database/create", json=data)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"데이터베이스 생성 실패: {e}")
            raise
    
    async def list_databases(self) -> List[Dict[str, Any]]:
        """데이터베이스 목록 조회"""
        try:
            response = await self.client.get("/api/v1/database/list")
            response.raise_for_status()
            data = response.json()
            return data.get("data", {}).get("databases", [])
        except httpx.HTTPError as e:
            logger.error(f"데이터베이스 목록 조회 실패: {e}")
            raise
    
    async def database_exists(self, db_name: str) -> bool:
        """데이터베이스 존재 여부 확인"""
        try:
            response = await self.client.get(f"/api/v1/database/exists/{db_name}")
            response.raise_for_status()
            data = response.json()
            return data.get("data", {}).get("exists", False)
        except httpx.HTTPError as e:
            logger.error(f"데이터베이스 존재 여부 확인 실패: {e}")
            raise
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()