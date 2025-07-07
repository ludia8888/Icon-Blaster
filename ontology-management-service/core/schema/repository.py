"""
Schema Repository
스키마 데이터에 대한 데이터베이스 CRUD(Create, Read, Update, Delete) 작업을 담당합니다.
서비스 계층(SchemaService)은 이 리포지토리를 통해 데이터베이스와 상호작용합니다.
이를 통해 비즈니스 로직과 데이터 접근 로직을 분리합니다.
"""
import logging
from typing import Any, Dict, List, Optional

from database.clients.unified_database_client import UnifiedDatabaseClient
from models.domain import ObjectType, ObjectTypeCreate
from shared.terminus_context import get_author

logger = logging.getLogger(__name__)


class SchemaRepository:
    """스키마 데이터베이스 작업을 위한 리포지토리"""

    # TODO: 현재 UnifiedDatabaseClient를 직접 받고 있지만,
    # 이 리포지토리는 TerminusDB에 특화된 작업을 수행하므로,
    # 장기적으로는 TerminusDBClient나 관련 Port(Adapter)를 주입받아야 합니다.
    def __init__(self, db_client: UnifiedDatabaseClient, db_name: str):
        """
        리포지토리 초기화
        Args:
            db_client (UnifiedDatabaseClient): 데이터베이스 클라이언트 인스턴스
            db_name (str): 데이터베이스 이름
        """
        self.db = db_client
        self.db_name = db_name

    async def list_all_object_types(self, branch: str = "main") -> List[Dict[str, Any]]:
        """
        지정된 브랜치의 모든 ObjectType 문서를 조회합니다.
        
        Args:
            branch (str): 조회할 브랜치 이름

        Returns:
            List[Dict[str, Any]]: 조회된 ObjectType 문서 목록
        """
        try:
            documents = await self.db.read(collection="ObjectType", query={"branch": branch})
            return documents
        except Exception as e:
            logger.error(f"Error listing all object types from branch '{branch}': {e}")
            raise

    async def create_new_object_type(self, branch: str, data: ObjectTypeCreate, author: str) -> bool:
        """
        새로운 ObjectType 문서를 생성합니다.
        
        Args:
            branch (str): 생성할 브랜치 이름
            data (ObjectTypeCreate): 생성할 ObjectType 데이터
            author (str): 작업 수행자

        Returns:
            bool: 생성 성공 여부
        """
        try:
            doc = {
                "@type": "ObjectType",
                "@id": f"ObjectType/{data.name}",
                "name": data.name,
                "displayName": data.display_name or data.name,
                "description": data.description or ""
            }
            # TODO: Refactor this method to work with the UnifiedDatabaseClient interface.
            # result = await self.db.create(collection="ObjectType", document=doc)
            logger.warning(f"create_new_object_type is currently mocked for '{data.name}'.")
            return True
        except Exception as e:
            logger.error(f"Error creating new object type '{data.name}': {e}")
            raise

    async def get_object_type_by_name(self, name: str, branch: str = "main") -> Optional[Dict[str, Any]]:
        """
        이름으로 특정 ObjectType 문서를 조회합니다.
        
        Args:
            name (str): 조회할 ObjectType의 이름
            branch (str): 조회할 브랜치 이름

        Returns:
            Optional[Dict[str, Any]]: 조회된 ObjectType 문서 또는 None
        """
        try:
            # TODO: Refactor this method.
            logger.warning(f"get_object_type_by_name is currently mocked for '{name}'.")
            return None
        except Exception as e:
            logger.error(f"Error getting object type by name '{name}': {e}")
            raise 