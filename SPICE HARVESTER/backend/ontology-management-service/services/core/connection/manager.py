"""
연결 관리자 구현
TerminusDB 연결 관리를 전담하는 서비스
SRP: 오직 연결 관리만 담당
"""

import logging
from typing import Optional, Any
from contextlib import contextmanager
from terminusdb_client import WOQLClient

from services.core.interfaces import IConnectionManager, ConnectionConfig
from domain.exceptions import ConnectionError

logger = logging.getLogger(__name__)


class TerminusConnectionManager(IConnectionManager):
    """
    TerminusDB 연결 관리자
    
    단일 책임: 연결 생성 및 관리만 담당
    """
    
    def __init__(self, config: ConnectionConfig):
        """
        초기화
        
        Args:
            config: 연결 설정
        """
        self.config = config
        self._connection_pool = None
        
        # 연결 풀 사용 시 초기화
        if config.use_pool:
            self._init_connection_pool()
    
    def _init_connection_pool(self) -> None:
        """연결 풀 초기화"""
        try:
            from .connection_pool import TerminusConnectionPool
            self._connection_pool = TerminusConnectionPool(self.config)
            logger.info("Connection pool initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize connection pool: {e}")
            self.config.use_pool = False
    
    @contextmanager
    def get_connection(self, db_name: Optional[str] = None,
                      branch: Optional[str] = None):
        """
        데이터베이스 연결 컨텍스트 매니저
        
        Args:
            db_name: 데이터베이스 이름
            branch: 브랜치 이름
            
        Yields:
            WOQLClient: 연결된 클라이언트
            
        Raises:
            ConnectionError: 연결 실패
        """
        # 연결 풀 사용
        if self.config.use_pool and self._connection_pool:
            try:
                with self._connection_pool.get_connection(db_name, branch) as client:
                    yield client
                return
            except Exception as e:
                logger.warning(f"Connection pool failed: {e}")
                # 폴백으로 직접 연결 시도
        
        # 직접 연결
        client = None
        try:
            client = self._create_client(db_name, branch)
            yield client
        except Exception as e:
            logger.error(f"Failed to create connection: {e}")
            raise ConnectionError(
                message=str(e),
                server_url=self.config.server_url
            )
        finally:
            # TerminusDB 클라이언트는 명시적 close가 없음
            pass
    
    def _create_client(self, db_name: Optional[str] = None,
                      branch: Optional[str] = None) -> WOQLClient:
        """
        새 클라이언트 생성
        
        Args:
            db_name: 데이터베이스 이름
            branch: 브랜치 이름
            
        Returns:
            WOQLClient: 연결된 클라이언트
            
        Raises:
            Exception: 연결 실패
        """
        client = WOQLClient(self.config.server_url)
        
        # 연결
        client.connect(
            user=self.config.user,
            account=self.config.account,
            key=self.config.key,
            db=db_name
        )
        
        # 브랜치 체크아웃
        if branch and db_name:
            client.checkout(branch)
        
        logger.debug(f"Created connection to {db_name or 'server'}"
                    f"{f' on branch {branch}' if branch else ''}")
        
        return client
    
    def check_connection(self) -> bool:
        """
        연결 상태 확인
        
        Returns:
            bool: 연결 가능 여부
        """
        try:
            with self.get_connection() as client:
                # 간단한 쿼리로 연결 테스트
                from terminusdb_client import WOQLQuery
                client.query(WOQLQuery().limit(1))
                return True
        except Exception as e:
            logger.warning(f"Connection check failed: {e}")
            return False
    
    def close(self) -> None:
        """연결 종료 및 리소스 정리"""
        if self._connection_pool:
            try:
                self._connection_pool.close_all()
                logger.info("Connection pool shut down")
            except Exception as e:
                logger.error(f"Error shutting down connection pool: {e}")
        
        self._connection_pool = None
        logger.info("Connection manager closed")
    
    def __enter__(self):
        """컨텍스트 매니저 진입"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """컨텍스트 매니저 종료"""
        self.close()