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

    def __init__(self, db: UnifiedDatabaseClient):
        """
        Initializes the SchemaRepository.

        Args:
            db: An instance of UnifiedDatabaseClient.
        """
        self.db = db
        # self.db = db.get_client("terminus") # Legacy: This was incorrect. UDC is used directly.
        logger.debug("SchemaRepository initialized with UnifiedDatabaseClient.")

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
            result = await self.db.create(collection="ObjectType", document=doc)
            return result
        except Exception as e:
            logger.error(f"Error creating new object type '{data.name}': {e}")
            raise

    async def get_object_type_by_name(self, name: str, branch: str) -> Optional[Dict[str, Any]]:
        """
        이름과 브랜치로 특정 ObjectType을 조회합니다.
        현재 UDC는 브랜치를 직접 지원하지 않으므로, 쿼리 필터로 처리합니다.
        """
        try:
            query = {"name": name, "branch": branch} # UDC가 처리할 쿼리
            # `read`는 리스트를 반환하므로 첫 번째 항목을 가져옵니다.
            results = await self.db.read(collection="ObjectType", query=query, limit=1)
            if results:
                logger.debug(f"Found ObjectType '{name}' in branch '{branch}'.")
                return results[0]
            logger.warning(f"ObjectType '{name}' not found in branch '{branch}'.")
            return None
        except Exception as e:
            logger.error(f"Error getting object type by name '{name}': {e}", exc_info=True)
            return None

    async def update_object_type(self, schema_id: str, branch: str, schema_def: Dict[str, Any], updated_by: str) -> bool:
        """
        주어진 ID와 브랜치에 해당하는 ObjectType 문서를 업데이트합니다.
        """
        try:
            # UDC의 update는 doc_id를 필요로 합니다.
            # schema_id가 여기서 doc_id 역할을 합니다.
            affected_rows = await self.db.update(
                collection="ObjectType",
                doc_id=schema_id,
                updates=schema_def,
                author=updated_by,
                message=f"Update ObjectType {schema_id}"
            )
            logger.info(f"Updated ObjectType '{schema_id}' in branch '{branch}'. Affected rows: {affected_rows}")
            # UDC의 update가 bool을 반환하지 않으면, 영향 받은 행의 수로 성공 여부 판단
            return affected_rows > 0 if isinstance(affected_rows, int) else bool(affected_rows)
        except Exception as e:
            logger.error(f"Error updating object type '{schema_id}': {e}", exc_info=True)
            return False 