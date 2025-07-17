"""
연결 풀 구현
데이터베이스 연결을 효율적으로 관리하기 위한 연결 풀
SRP: 오직 연결 풀 관리만 담당
"""

import logging
import threading
from typing import Dict, Optional, Any
from queue import Queue, Empty
from contextlib import contextmanager
import time
from terminusdb_client import WOQLClient

from services.core.config import ConnectionConfig
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'shared'))
from exceptions.base import DomainException, ConnectionPoolError

logger = logging.getLogger(__name__)


class TerminusConnectionPool:
    """
    TerminusDB 연결 풀
    
    Thread-safe 연결 풀로 동시 접속 관리
    """
    
    def __init__(self, config: ConnectionConfig):
        """
        초기화
        
        Args:
            config: 연결 설정
        """
        self.config = config
        self._pools: Dict[str, Queue] = {}
        self._locks: Dict[str, threading.RLock] = {}
        self._pool_lock = threading.RLock()
        self._stats = {
            'created': 0,
            'active': 0,
            'idle': 0,
            'total_requests': 0,
            'pool_hits': 0,
            'pool_misses': 0
        }
        
        # 풀 초기화
        if config.use_pool:
            self._initialize_pool()
    
    def _initialize_pool(self) -> None:
        """연결 풀 초기화"""
        logger.info(f"Initializing connection pool with size {self.config.pool_size}")
        
    @contextmanager
    def get_connection(self, db_name: str, branch: Optional[str] = None):
        """
        연결 가져오기
        
        Args:
            db_name: 데이터베이스 이름
            branch: 브랜치 이름
            
        Yields:
            WOQLClient 인스턴스
        """
        if not self.config.use_pool:
            # 풀을 사용하지 않는 경우 직접 연결 생성
            client = self._create_connection(db_name, branch)
            try:
                yield client
            finally:
                self._close_connection(client)
            return
        
        # 풀에서 연결 가져오기
        pool_key = self._get_pool_key(db_name, branch)
        connection = self._acquire_connection(pool_key, db_name, branch)
        
        try:
            self._stats['active'] += 1
            self._stats['idle'] -= 1
            yield connection
        finally:
            # 연결을 풀에 반환
            self._release_connection(pool_key, connection)
            self._stats['active'] -= 1
            self._stats['idle'] += 1
    
    def _get_pool_key(self, db_name: str, branch: Optional[str]) -> str:
        """풀 키 생성"""
        if branch:
            return f"{db_name}:{branch}"
        return db_name
    
    def _acquire_connection(self, pool_key: str, db_name: str, branch: Optional[str]) -> Any:
        """
        풀에서 연결 획득
        
        Args:
            pool_key: 풀 키
            db_name: 데이터베이스 이름
            branch: 브랜치 이름
            
        Returns:
            연결 객체
        """
        with self._pool_lock:
            if pool_key not in self._pools:
                self._pools[pool_key] = Queue(maxsize=self.config.pool_size)
                self._locks[pool_key] = threading.RLock()
        
        pool = self._pools[pool_key]
        self._stats['total_requests'] += 1
        
        try:
            # 논블로킹으로 연결 시도
            connection = pool.get_nowait()
            self._stats['pool_hits'] += 1
            
            # 연결 상태 확인
            if self._is_connection_alive(connection):
                return connection
            else:
                # 죽은 연결은 폐기하고 새로 생성
                self._close_connection(connection)
                raise Empty()
                
        except Empty:
            # 풀이 비어있으면 새 연결 생성
            self._stats['pool_misses'] += 1
            
            # 풀 크기 제한 확인
            if pool.qsize() + self._stats['active'] >= self.config.pool_size:
                # 대기
                try:
                    connection = pool.get(timeout=self.config.pool_timeout)
                    if self._is_connection_alive(connection):
                        return connection
                    else:
                        self._close_connection(connection)
                except Empty:
                    raise ConnectionPoolError(
                        "Connection pool exhausted",
                        {"pool_key": pool_key, "pool_size": self.config.pool_size}
                    )
            
            # 새 연결 생성
            return self._create_connection(db_name, branch)
    
    def _release_connection(self, pool_key: str, connection: Any) -> None:
        """
        연결을 풀에 반환
        
        Args:
            pool_key: 풀 키
            connection: 연결 객체
        """
        pool = self._pools.get(pool_key)
        if pool is None:
            # 풀이 없으면 연결 닫기
            self._close_connection(connection)
            return
        
        try:
            # 연결 상태 확인
            if self._is_connection_alive(connection):
                pool.put_nowait(connection)
            else:
                # 죽은 연결은 폐기
                self._close_connection(connection)
                self._stats['created'] -= 1
        except queue.Full:
            # 풀이 가득 찬 경우 연결 닫기
            logger.warning(f"Connection pool for {db_name} is full, closing connection")
            self._close_connection(connection)
            self._stats['created'] -= 1
        except Exception as e:
            logger.error(f"Unexpected error returning connection to pool: {e}")
            self._close_connection(connection)
            self._stats['created'] -= 1
    
    def _create_connection(self, db_name: str, branch: Optional[str] = None) -> Any:
        """
        새 연결 생성
        
        Args:
            db_name: 데이터베이스 이름
            branch: 브랜치 이름
            
        Returns:
            WOQLClient 인스턴스
        """
        try:
            # 연결 URL 구성
            db_url = f"{self.config.server_url}/{self.config.account}/{db_name}"
            if branch:
                db_url = f"{db_url}/local/branch/{branch}"
            
            # 클라이언트 생성
            client = WOQLClient(
                db_url,
                user=self.config.user,
                key=self.config.key,
                account=self.config.account
            )
            
            # 연결 테스트
            client.connect()
            
            self._stats['created'] += 1
            self._stats['idle'] += 1
            
            logger.debug(f"Created new connection to {db_name}:{branch or 'main'}")
            return client
            
        except Exception as e:
            logger.error(f"Failed to create connection to {db_name}: {e}")
            raise ConnectionPoolError(
                f"Failed to create connection to {db_name}",
                {"db_name": db_name, "branch": branch, "error": str(e)}
            )
    
    def _close_connection(self, connection: Any) -> None:
        """
        연결 닫기
        
        Args:
            connection: 연결 객체
        """
        try:
            if hasattr(connection, 'close'):
                connection.close()
            logger.debug("Closed database connection")
        except Exception as e:
            logger.warning(f"Error closing connection: {e}")
    
    def _is_connection_alive(self, connection: Any) -> bool:
        """
        연결 상태 확인
        
        Args:
            connection: 연결 객체
            
        Returns:
            연결 활성 상태
        """
        try:
            # 간단한 쿼리로 연결 테스트
            if hasattr(connection, 'get_database'):
                connection.get_database()
                return True
            return False
        except Exception:
            return False
    
    def close_all(self) -> None:
        """모든 연결 닫기"""
        with self._pool_lock:
            for pool_key, pool in self._pools.items():
                while not pool.empty():
                    try:
                        connection = pool.get_nowait()
                        self._close_connection(connection)
                    except Empty:
                        break
            
            self._pools.clear()
            self._locks.clear()
            
            logger.info("Closed all connections in pool")
    
    def get_stats(self) -> Dict[str, int]:
        """
        풀 통계 조회
        
        Returns:
            통계 정보
        """
        return self._stats.copy()
    
    def resize_pool(self, new_size: int) -> None:
        """
        풀 크기 조정
        
        Args:
            new_size: 새 풀 크기
        """
        with self._pool_lock:
            old_size = self.config.pool_size
            self.config.pool_size = new_size
            
            # 크기가 줄어든 경우 초과 연결 제거
            if new_size < old_size:
                for pool in self._pools.values():
                    removed = 0
                    while pool.qsize() > new_size and removed < (old_size - new_size):
                        try:
                            connection = pool.get_nowait()
                            self._close_connection(connection)
                            removed += 1
                        except Empty:
                            break
            
            logger.info(f"Resized connection pool from {old_size} to {new_size}")
    
    def health_check(self) -> Dict[str, Any]:
        """
        풀 상태 확인
        
        Returns:
            상태 정보
        """
        health = {
            'status': 'healthy',
            'stats': self.get_stats(),
            'pools': {}
        }
        
        # 각 풀의 상태 확인
        for pool_key, pool in self._pools.items():
            health['pools'][pool_key] = {
                'size': pool.qsize(),
                'max_size': self.config.pool_size
            }
        
        # 건강 상태 판단
        if self._stats['active'] >= self.config.pool_size * 0.9:
            health['status'] = 'warning'
            health['message'] = 'Pool utilization is high'
        
        if self._stats['pool_misses'] > self._stats['pool_hits'] * 2:
            health['status'] = 'warning'
            health['message'] = 'High pool miss rate'
        
        return health