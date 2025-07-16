"""
브랜치 관리 인터페이스 정의
Git-like 브랜치 작업에 필요한 메서드 정의
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any


class IBranchService(ABC):
    """브랜치 관리 서비스 인터페이스"""
    
    @abstractmethod
    def list_branches(self, db_name: str) -> List[Dict[str, Any]]:
        """
        브랜치 목록 조회
        
        Args:
            db_name: 데이터베이스 이름
            
        Returns:
            브랜치 정보 목록
        """
        pass
    
    @abstractmethod
    def create_branch(self, db_name: str, branch_name: str,
                     from_branch: Optional[str] = None) -> Dict[str, Any]:
        """
        새 브랜치 생성
        
        Args:
            db_name: 데이터베이스 이름
            branch_name: 새 브랜치 이름
            from_branch: 기준 브랜치 (기본값: 현재 브랜치)
            
        Returns:
            생성된 브랜치 정보
        """
        pass
    
    @abstractmethod
    def delete_branch(self, db_name: str, branch_name: str) -> Dict[str, Any]:
        """
        브랜치 삭제
        
        Args:
            db_name: 데이터베이스 이름
            branch_name: 삭제할 브랜치 이름
            
        Returns:
            삭제 결과
        """
        pass
    
    @abstractmethod
    def checkout(self, db_name: str, target: str,
                target_type: str = "branch") -> Dict[str, Any]:
        """
        브랜치 또는 커밋으로 체크아웃
        
        Args:
            db_name: 데이터베이스 이름
            target: 브랜치 이름 또는 커밋 ID
            target_type: "branch" 또는 "commit"
            
        Returns:
            체크아웃 결과
        """
        pass
    
    @abstractmethod
    def get_current_branch(self, db_name: str) -> Optional[str]:
        """
        현재 브랜치 조회
        
        Args:
            db_name: 데이터베이스 이름
            
        Returns:
            현재 브랜치 이름
        """
        pass


class IBranchMerger(ABC):
    """브랜치 병합 인터페이스"""
    
    @abstractmethod
    def merge(self, db_name: str, source: str, target: str,
             strategy: str = "merge", message: Optional[str] = None,
             author: Optional[str] = None) -> Dict[str, Any]:
        """
        브랜치 병합
        
        Args:
            db_name: 데이터베이스 이름
            source: 소스 브랜치
            target: 타겟 브랜치
            strategy: "merge" 또는 "rebase"
            message: 병합 커밋 메시지
            author: 작성자
            
        Returns:
            병합 결과
        """
        pass
    
    @abstractmethod
    def check_conflicts(self, db_name: str, source: str, 
                       target: str) -> List[Dict[str, Any]]:
        """
        병합 충돌 검사
        
        Args:
            db_name: 데이터베이스 이름
            source: 소스 브랜치
            target: 타겟 브랜치
            
        Returns:
            충돌 목록
        """
        pass