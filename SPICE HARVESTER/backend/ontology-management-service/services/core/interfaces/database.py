"""
데이터베이스 관리 인터페이스 정의
데이터베이스 생성, 삭제, 목록 조회 등의 기능 정의
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any


class IDatabaseService(ABC):
    """데이터베이스 관리 서비스 인터페이스"""
    
    @abstractmethod
    def list_databases(self) -> List[Dict[str, Any]]:
        """
        데이터베이스 목록 조회
        
        Returns:
            데이터베이스 정보 목록
        """
        pass
    
    @abstractmethod
    def create_database(self, db_name: str, 
                       description: Optional[str] = None) -> Dict[str, Any]:
        """
        데이터베이스 생성
        
        Args:
            db_name: 데이터베이스 이름
            description: 설명
            
        Returns:
            생성된 데이터베이스 정보
        """
        pass
    
    @abstractmethod
    def delete_database(self, db_name: str) -> bool:
        """
        데이터베이스 삭제
        
        Args:
            db_name: 데이터베이스 이름
            
        Returns:
            삭제 성공 여부
        """
        pass
    
    @abstractmethod
    def database_exists(self, db_name: str) -> bool:
        """
        데이터베이스 존재 여부 확인
        
        Args:
            db_name: 데이터베이스 이름
            
        Returns:
            존재 여부
        """
        pass
    
    @abstractmethod
    def get_database_info(self, db_name: str) -> Optional[Dict[str, Any]]:
        """
        데이터베이스 정보 조회
        
        Args:
            db_name: 데이터베이스 이름
            
        Returns:
            데이터베이스 정보
        """
        pass
    
    @abstractmethod
    def ensure_database_exists(self, db_name: str, 
                             description: Optional[str] = None) -> None:
        """
        데이터베이스가 존재하는지 확인하고 없으면 생성
        
        Args:
            db_name: 데이터베이스 이름
            description: 설명 (생성시 사용)
        """
        pass