"""
온톨로지 관리 인터페이스 정의
CRUD 작업에 필요한 최소한의 메서드만 포함
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any


class IOntologyRepository(ABC):
    """온톨로지 저장소 인터페이스"""
    
    @abstractmethod
    def create(self, db_name: str, ontology_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        온톨로지 생성
        
        Args:
            db_name: 데이터베이스 이름
            ontology_data: 온톨로지 데이터
            
        Returns:
            생성된 온톨로지 정보
            
        Raises:
            DuplicateOntologyError: 중복된 ID
            ValidationError: 유효성 검증 실패
        """
        pass
    
    @abstractmethod
    def get(self, db_name: str, ontology_id: str) -> Optional[Dict[str, Any]]:
        """
        온톨로지 조회
        
        Args:
            db_name: 데이터베이스 이름
            ontology_id: 온톨로지 ID
            
        Returns:
            온톨로지 정보 또는 None
        """
        pass
    
    @abstractmethod
    def update(self, db_name: str, ontology_id: str, 
               ontology_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        온톨로지 업데이트
        
        Args:
            db_name: 데이터베이스 이름
            ontology_id: 온톨로지 ID
            ontology_data: 업데이트할 데이터
            
        Returns:
            업데이트된 온톨로지 정보
            
        Raises:
            OntologyNotFoundError: 온톨로지를 찾을 수 없음
            ValidationError: 유효성 검증 실패
        """
        pass
    
    @abstractmethod
    def delete(self, db_name: str, ontology_id: str) -> bool:
        """
        온톨로지 삭제
        
        Args:
            db_name: 데이터베이스 이름
            ontology_id: 온톨로지 ID
            
        Returns:
            삭제 성공 여부
            
        Raises:
            OntologyNotFoundError: 온톨로지를 찾을 수 없음
        """
        pass
    
    @abstractmethod
    def list(self, db_name: str, class_type: str = "sys:Class",
             limit: Optional[int] = None, offset: int = 0) -> List[Dict[str, Any]]:
        """
        온톨로지 목록 조회
        
        Args:
            db_name: 데이터베이스 이름
            class_type: 클래스 타입
            limit: 조회 개수 제한
            offset: 오프셋
            
        Returns:
            온톨로지 목록
        """
        pass


class IOntologyValidator(ABC):
    """온톨로지 유효성 검증 인터페이스"""
    
    @abstractmethod
    def validate(self, ontology_data: Dict[str, Any]) -> List[str]:
        """
        온톨로지 데이터 유효성 검증
        
        Args:
            ontology_data: 검증할 데이터
            
        Returns:
            오류 메시지 리스트 (빈 리스트면 유효함)
        """
        pass


class IOntologyMerger(ABC):
    """온톨로지 병합 인터페이스"""
    
    @abstractmethod
    def merge(self, db_name: str, ontology_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        온톨로지 병합 (존재하면 업데이트, 없으면 생성)
        
        Args:
            db_name: 데이터베이스 이름
            ontology_data: 온톨로지 데이터
            
        Returns:
            병합 결과
        """
        pass