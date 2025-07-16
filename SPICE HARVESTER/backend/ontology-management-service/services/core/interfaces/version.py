"""
버전 관리 인터페이스 정의
커밋, 히스토리, 버전 비교 등의 기능 정의
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any


class IVersionService(ABC):
    """버전 관리 서비스 인터페이스"""
    
    @abstractmethod
    def commit(self, db_name: str, message: str, author: str,
              branch: Optional[str] = None) -> Dict[str, Any]:
        """
        변경사항 커밋
        
        Args:
            db_name: 데이터베이스 이름
            message: 커밋 메시지
            author: 작성자
            branch: 브랜치 이름 (기본값: 현재 브랜치)
            
        Returns:
            커밋 정보
        """
        pass
    
    @abstractmethod
    def get_history(self, db_name: str, branch: Optional[str] = None,
                   limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        커밋 히스토리 조회
        
        Args:
            db_name: 데이터베이스 이름
            branch: 브랜치 이름
            limit: 조회 개수
            offset: 오프셋
            
        Returns:
            커밋 목록
        """
        pass
    
    @abstractmethod
    def get_commit(self, db_name: str, commit_id: str) -> Optional[Dict[str, Any]]:
        """
        특정 커밋 정보 조회
        
        Args:
            db_name: 데이터베이스 이름
            commit_id: 커밋 ID
            
        Returns:
            커밋 정보
        """
        pass
    
    @abstractmethod
    def rollback(self, db_name: str, target_commit: str,
                create_branch: bool = True, 
                branch_name: Optional[str] = None) -> Dict[str, Any]:
        """
        특정 커밋으로 롤백
        
        Args:
            db_name: 데이터베이스 이름
            target_commit: 대상 커밋 ID
            create_branch: 새 브랜치 생성 여부
            branch_name: 새 브랜치 이름
            
        Returns:
            롤백 결과
        """
        pass


class IVersionComparator(ABC):
    """버전 비교 인터페이스"""
    
    @abstractmethod
    def compare(self, db_name: str, base: str, compare: str) -> Dict[str, Any]:
        """
        두 버전 간 차이 비교
        
        Args:
            db_name: 데이터베이스 이름
            base: 기준 버전 (브랜치/커밋)
            compare: 비교 버전 (브랜치/커밋)
            
        Returns:
            차이점 정보
        """
        pass
    
    @abstractmethod
    def get_changes_summary(self, db_name: str, base: str, 
                           compare: str) -> Dict[str, int]:
        """
        변경사항 요약 조회
        
        Args:
            db_name: 데이터베이스 이름
            base: 기준 버전
            compare: 비교 버전
            
        Returns:
            변경사항 통계 (added, modified, deleted 개수)
        """
        pass