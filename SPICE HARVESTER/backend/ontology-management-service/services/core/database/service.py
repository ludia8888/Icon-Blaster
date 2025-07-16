"""
데이터베이스 관리 서비스 구현
데이터베이스 생성, 삭제, 목록 조회 등을 담당
SRP: 오직 데이터베이스 관리만 담당
"""

import logging
from typing import Dict, List, Optional, Any
from functools import lru_cache

from services.core.interfaces import IDatabaseService, IConnectionManager
from domain.exceptions import (
    DatabaseNotFoundError,
    DatabaseAlreadyExistsError,
    DomainException
)

logger = logging.getLogger(__name__)


class TerminusDatabaseService(IDatabaseService):
    """
    TerminusDB 데이터베이스 관리 서비스
    
    단일 책임: 데이터베이스 생성, 삭제, 목록 조회만 담당
    """
    
    def __init__(self, connection_manager: IConnectionManager):
        """
        초기화
        
        Args:
            connection_manager: 연결 관리자
        """
        self.connection_manager = connection_manager
        self._db_cache: set = set()
    
    def list_databases(self) -> List[Dict[str, Any]]:
        """
        데이터베이스 목록 조회
        
        Returns:
            데이터베이스 정보 목록
            
        Raises:
            DomainException: 조회 실패
        """
        try:
            with self.connection_manager.get_connection() as client:
                databases = client.list_databases()
                
                # 캐시 업데이트
                self._db_cache.clear()
                for db in databases:
                    self._db_cache.add(db.get('name'))
                
                logger.info(f"Listed {len(databases)} databases")
                return databases
                
        except Exception as e:
            logger.error(f"Failed to list databases: {e}")
            raise DomainException(
                message="Failed to list databases",
                code="DATABASE_LIST_ERROR",
                details={"error": str(e)}
            )
    
    def create_database(self, db_name: str, 
                       description: Optional[str] = None) -> Dict[str, Any]:
        """
        데이터베이스 생성
        
        Args:
            db_name: 데이터베이스 이름
            description: 설명
            
        Returns:
            생성된 데이터베이스 정보
            
        Raises:
            DatabaseAlreadyExistsError: 이미 존재하는 경우
            DomainException: 생성 실패
        """
        # 존재 여부 확인
        if self.database_exists(db_name):
            raise DatabaseAlreadyExistsError(db_name)
        
        try:
            with self.connection_manager.get_connection() as client:
                client.create_database(
                    db_name,
                    label=db_name,
                    description=description or f"{db_name} database"
                )
                
                # 캐시 업데이트
                self._db_cache.add(db_name)
                self._database_exists.cache_clear()
                
                logger.info(f"Created database: {db_name}")
                
                return {
                    "name": db_name,
                    "label": db_name,
                    "description": description or f"{db_name} database"
                }
                
        except Exception as e:
            logger.error(f"Failed to create database '{db_name}': {e}")
            raise DomainException(
                message=f"Failed to create database '{db_name}'",
                code="DATABASE_CREATE_ERROR",
                details={"db_name": db_name, "error": str(e)}
            )
    
    def delete_database(self, db_name: str) -> bool:
        """
        데이터베이스 삭제
        
        Args:
            db_name: 데이터베이스 이름
            
        Returns:
            삭제 성공 여부
            
        Raises:
            DatabaseNotFoundError: 데이터베이스가 없는 경우
            DomainException: 삭제 실패
        """
        # 존재 여부 확인
        if not self.database_exists(db_name):
            raise DatabaseNotFoundError(db_name)
        
        try:
            with self.connection_manager.get_connection() as client:
                client.delete_database(db_name)
                
                # 캐시 업데이트
                self._db_cache.discard(db_name)
                self._database_exists.cache_clear()
                
                logger.info(f"Deleted database: {db_name}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete database '{db_name}': {e}")
            raise DomainException(
                message=f"Failed to delete database '{db_name}'",
                code="DATABASE_DELETE_ERROR",
                details={"db_name": db_name, "error": str(e)}
            )
    
    @lru_cache(maxsize=32)
    def _database_exists(self, db_name: str) -> bool:
        """
        데이터베이스 존재 여부 확인 (캐시됨)
        
        Args:
            db_name: 데이터베이스 이름
            
        Returns:
            존재 여부
        """
        try:
            with self.connection_manager.get_connection() as client:
                databases = client.list_databases()
                return any(db.get('name') == db_name for db in databases)
        except Exception:
            return False
    
    def database_exists(self, db_name: str) -> bool:
        """
        데이터베이스 존재 여부 확인
        
        Args:
            db_name: 데이터베이스 이름
            
        Returns:
            존재 여부
        """
        # 캐시 확인
        if db_name in self._db_cache:
            return True
        
        # 실제 확인
        return self._database_exists(db_name)
    
    def get_database_info(self, db_name: str) -> Optional[Dict[str, Any]]:
        """
        데이터베이스 정보 조회
        
        Args:
            db_name: 데이터베이스 이름
            
        Returns:
            데이터베이스 정보 또는 None
        """
        try:
            databases = self.list_databases()
            for db in databases:
                if db.get('name') == db_name:
                    return db
            return None
        except Exception:
            return None
    
    def ensure_database_exists(self, db_name: str, 
                             description: Optional[str] = None) -> None:
        """
        데이터베이스가 존재하는지 확인하고 없으면 생성
        
        Args:
            db_name: 데이터베이스 이름
            description: 설명
        """
        if not self.database_exists(db_name):
            self.create_database(db_name, description)