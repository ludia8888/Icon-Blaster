"""
연결 관리 인터페이스 정의
ISP에 따라 연결 관리에 필요한 최소한의 메서드만 포함
"""

from abc import ABC, abstractmethod
from typing import Optional, Any
from contextlib import contextmanager

from services.core.config import ConnectionConfig


class IConnectionManager(ABC):
    """연결 관리 인터페이스"""
    
    @abstractmethod
    @contextmanager
    def get_connection(self, db_name: Optional[str] = None, 
                      branch: Optional[str] = None):
        """
        데이터베이스 연결 컨텍스트 매니저
        
        Args:
            db_name: 데이터베이스 이름
            branch: 브랜치 이름
            
        Yields:
            연결된 클라이언트 객체
        """
        pass
    
    @abstractmethod
    def check_connection(self) -> bool:
        """연결 상태 확인"""
        pass
    
    @abstractmethod
    def close(self) -> None:
        """연결 종료 및 리소스 정리"""
        pass


class IConnectionPool(ABC):
    """연결 풀 인터페이스"""
    
    @abstractmethod
    @contextmanager
    def acquire_connection(self, db_name: Optional[str] = None,
                          branch: Optional[str] = None):
        """연결 풀에서 연결 획득"""
        pass
    
    @abstractmethod
    def get_pool_stats(self) -> dict:
        """연결 풀 통계 조회"""
        pass
    
    @abstractmethod
    def shutdown(self) -> None:
        """연결 풀 종료"""
        pass