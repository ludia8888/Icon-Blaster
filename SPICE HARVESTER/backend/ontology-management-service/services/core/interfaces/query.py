"""
쿼리 실행 인터페이스 정의
WOQL 쿼리 실행 및 스키마 조회 기능 정의
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Union


class IQueryService(ABC):
    """쿼리 실행 서비스 인터페이스"""
    
    @abstractmethod
    def execute_query(self, db_name: str, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        쿼리 실행
        
        Args:
            db_name: 데이터베이스 이름
            query: 쿼리 정보 (클래스, 필터, 정렬 등)
            
        Returns:
            쿼리 결과
        """
        pass
    
    @abstractmethod
    def get_schema(self, db_name: str, class_id: str) -> Dict[str, Any]:
        """
        클래스 스키마 조회
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            
        Returns:
            스키마 정보
        """
        pass


class IQueryBuilder(ABC):
    """쿼리 빌더 인터페이스"""
    
    @abstractmethod
    def build_select_query(self, class_id: str, 
                          filters: Optional[List[Dict[str, Any]]] = None,
                          fields: Optional[List[str]] = None,
                          order_by: Optional[str] = None,
                          limit: Optional[int] = None,
                          offset: Optional[int] = None) -> Any:
        """
        SELECT 쿼리 생성
        
        Args:
            class_id: 클래스 ID
            filters: 필터 조건들
            fields: 선택할 필드들
            order_by: 정렬 필드
            limit: 결과 개수 제한
            offset: 오프셋
            
        Returns:
            WOQL 쿼리 객체
        """
        pass
    
    @abstractmethod
    def build_filter(self, field: str, operator: str, 
                    value: Union[str, int, float, List]) -> Any:
        """
        필터 조건 생성
        
        Args:
            field: 필드명
            operator: 연산자
            value: 값
            
        Returns:
            필터 조건
        """
        pass


class IQueryTransformer(ABC):
    """쿼리 변환 인터페이스"""
    
    @abstractmethod
    def transform_label_query(self, db_name: str, label_query: Dict[str, Any],
                            language: str = "ko") -> Dict[str, Any]:
        """
        레이블 기반 쿼리를 내부 ID 기반으로 변환
        
        Args:
            db_name: 데이터베이스 이름
            label_query: 레이블 기반 쿼리
            language: 언어 코드
            
        Returns:
            ID 기반 쿼리
        """
        pass
    
    @abstractmethod
    def transform_result(self, db_name: str, result: List[Dict[str, Any]],
                        language: str = "ko") -> List[Dict[str, Any]]:
        """
        쿼리 결과를 레이블 기반으로 변환
        
        Args:
            db_name: 데이터베이스 이름
            result: 쿼리 결과
            language: 언어 코드
            
        Returns:
            레이블 기반 결과
        """
        pass