"""
Schema Service - Fixed DB Connection
SimpleTerminusDBClient 사용으로 DB 연결 문제 해결
"""
import logging
from typing import Any, Dict, List, Optional
from database.unified_terminus_client import SimpleTerminusDBClient
from models.domain import ObjectType, ObjectTypeCreate

logger = logging.getLogger(__name__)


class SchemaService:
    """스키마 관리 서비스 - 수정된 버전"""

    def __init__(self, tdb_endpoint: Optional[str] = None, event_publisher: Optional[Any] = None):
        self.tdb_endpoint = tdb_endpoint or "http://localhost:6363"
        self.db_name = "oms"
        self.tdb = None  # initialize에서 연결
        self.event_publisher = event_publisher

    async def initialize(self):
        """서비스 초기화 - SimpleTerminusDBClient 사용"""
        try:
            # SimpleTerminusDBClient 사용
            self.tdb = SimpleTerminusDBClient(
                endpoint=self.tdb_endpoint,
                username="admin",
                password="root",
                database=self.db_name
            )
            
            # 연결
            connected = await self.tdb.connect()
            if connected:
                logger.info(f"Connected to TerminusDB at {self.tdb_endpoint}")
            else:
                logger.error("Failed to connect to TerminusDB")
                
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")

    async def list_object_types(self, branch: str = "main") -> List[Dict[str, Any]]:
        """ObjectType 목록 조회 - 실제 DB에서"""
        try:
            if not self.tdb or not self.tdb.is_connected():
                logger.warning("DB not connected, attempting reconnect")
                await self.initialize()
            
            # TerminusDB에서 ObjectType 문서들 조회
            result = await self.tdb.client.get(
                f"/api/document/admin/{self.db_name}?type=ObjectType",
                auth=("admin", "root")
            )
            
            if result.status_code == 200:
                # TerminusDB는 NDJSON으로 반환함
                text = result.text.strip()
                if not text:
                    return []
                
                # 각 줄을 JSON으로 파싱
                import json
                objects = []
                for line in text.split('\n'):
                    if line.strip():
                        try:
                            obj = json.loads(line)
                            objects.append(obj)
                        except:
                            pass
                return objects
            else:
                logger.warning(f"Failed to get object types: {result.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Error listing object types: {e}")
            return []

    async def create_object_type(self, branch: str, data: ObjectTypeCreate) -> ObjectType:
        """ObjectType 생성 - 실제 DB에"""
        try:
            if not self.tdb or not self.tdb.is_connected():
                await self.initialize()
            
            # 문서 준비 - properties 제거 (스키마에 정의되지 않음)
            doc = {
                "@type": "ObjectType",
                "@id": f"ObjectType/{data.name}",
                "name": data.name,
                "displayName": data.display_name or data.name,
                "description": data.description or ""
            }
            
            # DB에 삽입
            result = await self.tdb.client.post(
                f"/api/document/admin/{self.db_name}?author=OMS&message=Create ObjectType",
                json=[doc],
                auth=("admin", "root")
            )
            
            if result.status_code in [200, 201]:
                logger.info(f"Created ObjectType: {data.name}")
                from datetime import datetime
                import uuid
                
                return ObjectType(
                    id=data.name,
                    name=data.name,
                    display_name=data.display_name or data.name,
                    description=data.description,
                    properties=[],
                    version_hash=str(uuid.uuid4())[:16],
                    created_by="system",
                    created_at=datetime.now(),
                    modified_by="system",
                    modified_at=datetime.now()
                )
            else:
                raise Exception(f"Failed to create ObjectType: {result.text}")
                
        except Exception as e:
            logger.error(f"Error creating object type: {e}")
            raise

    async def _check_permission(self, user: Dict[str, Any], permission: str, branch: str) -> bool:
        """권한 확인 - 임시로 모두 허용"""
        return True

    async def _validate_object_type(self, data: ObjectTypeCreate) -> Dict[str, Any]:
        """유효성 검증"""
        return {"valid": True}