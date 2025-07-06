"""
Schema Repository
스키마 데이터에 대한 데이터베이스 CRUD(Create, Read, Update, Delete) 작업을 담당합니다.
서비스 계층(SchemaService)은 이 리포지토리를 통해 데이터베이스와 상호작용합니다.
이를 통해 비즈니스 로직과 데이터 접근 로직을 분리합니다.
"""
import logging
from typing import Any, Dict, List, Optional

from database.clients.terminus_db import TerminusDBClient
from models.domain import ObjectType, ObjectTypeCreate
from shared.terminus_context import get_author

logger = logging.getLogger(__name__)


class SchemaRepository:
    """스키마 데이터베이스 작업을 위한 리포지토리"""

    def __init__(self, tdb_client: TerminusDBClient, db_name: str):
        """
        리포지토리 초기화
        Args:
            tdb_client (TerminusDBClient): TerminusDB 클라이언트 인스턴스
            db_name (str): 데이터베이스 이름
        """
        self.tdb = tdb_client
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
            documents = await self.tdb.get_documents(
                database=self.db_name,
                branch=branch,
                doc_type="ObjectType"
            )
            return documents if documents else []
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
            
            result = await self.tdb.insert_documents(
                database=self.db_name,
                branch=branch,
                documents=[doc],
                author=author,
                message=f"Create ObjectType: {data.name}"
            )
            return bool(result)
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
            # 현재 TerminusDBClient는 ID로만 조회를 지원하므로,
            # 전체 목록에서 필터링하는 방식으로 구현합니다.
            # 추후 클라이언트가 이름 조회를 지원하면 최적화가 필요합니다.
            all_types = await self.list_all_object_types(branch)
            for obj_type in all_types:
                if obj_type.get("name") == name:
                    return obj_type
            return None
        except Exception as e:
            logger.error(f"Error getting object type by name '{name}': {e}")
            raise 