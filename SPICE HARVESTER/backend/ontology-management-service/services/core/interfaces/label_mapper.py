"""
레이블 매퍼 인터페이스 정의
레이블과 ID 간의 매핑을 담당하는 서비스의 추상화
DIP: 구체적인 구현이 아닌 추상화에 의존
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any


class ILabelMapperService(ABC):
    """
    레이블 매퍼 서비스 인터페이스
    
    사용자 친화적인 레이블과 내부 ID 간의 매핑을 관리
    """
    
    @abstractmethod
    def register_class(self, db_name: str, class_id: str, 
                      label: Any, description: Optional[Any] = None) -> None:
        """
        클래스 레이블 매핑 등록
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            label: 클래스 레이블 (문자열 또는 MultiLingualText)
            description: 클래스 설명
        """
        pass
    
    @abstractmethod
    def register_property(self, db_name: str, class_id: str, 
                         property_id: str, label: Any) -> None:
        """
        속성 레이블 매핑 등록
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            property_id: 속성 ID
            label: 속성 레이블
        """
        pass
    
    @abstractmethod
    def register_relationship(self, db_name: str, predicate: str, label: Any) -> None:
        """
        관계 레이블 매핑 등록
        
        Args:
            db_name: 데이터베이스 이름
            predicate: 관계 술어
            label: 관계 레이블
        """
        pass
    
    @abstractmethod
    def get_id_by_label(self, db_name: str, label: str, 
                       label_type: str = "class", class_id: Optional[str] = None,
                       lang: str = 'ko') -> Optional[str]:
        """
        레이블로 ID 조회 (통합 메서드)
        
        Args:
            db_name: 데이터베이스 이름
            label: 레이블
            label_type: 레이블 타입 ("class", "property", "relationship")
            class_id: 클래스 ID (property 조회 시 필요)
            lang: 언어 코드
            
        Returns:
            ID 또는 None
        """
        pass
    
    @abstractmethod
    def get_label_by_id(self, db_name: str, id_value: str,
                       label_type: str = "class", class_id: Optional[str] = None,
                       lang: str = 'ko') -> Optional[str]:
        """
        ID로 레이블 조회 (통합 메서드)
        
        Args:
            db_name: 데이터베이스 이름
            id_value: ID 값
            label_type: 레이블 타입 ("class", "property", "relationship")
            class_id: 클래스 ID (property 조회 시 필요)
            lang: 언어 코드
            
        Returns:
            레이블 또는 None
        """
        pass
    
    @abstractmethod
    def get_property_id_by_label(self, db_name: str, class_id: str,
                                label: str, lang: str = 'ko') -> Optional[str]:
        """
        속성 레이블로 ID 조회 (편의 메서드)
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
            label: 속성 레이블
            lang: 언어 코드
            
        Returns:
            속성 ID 또는 None
        """
        pass
    
    @abstractmethod
    def convert_query_to_internal(self, db_name: str, query: Dict[str, Any], 
                                 lang: str = 'ko') -> Dict[str, Any]:
        """
        레이블 기반 쿼리를 내부 ID 기반으로 변환
        
        Args:
            db_name: 데이터베이스 이름
            query: 레이블 기반 쿼리
            lang: 언어 코드
            
        Returns:
            내부 ID 기반 쿼리
            
        Raises:
            ValueError: 레이블을 찾을 수 없는 경우
        """
        pass
    
    @abstractmethod
    def convert_to_display(self, db_name: str, data: Dict[str, Any], 
                          lang: str = 'ko') -> Dict[str, Any]:
        """
        내부 ID 기반 데이터를 레이블 기반으로 변환
        
        Args:
            db_name: 데이터베이스 이름
            data: 내부 ID 기반 데이터
            lang: 언어 코드
            
        Returns:
            레이블 기반 데이터
        """
        pass
    
    @abstractmethod
    def update_mappings(self, db_name: str, ontology_data: Dict[str, Any]) -> None:
        """
        온톨로지 데이터로부터 모든 매핑 업데이트
        
        Args:
            db_name: 데이터베이스 이름
            ontology_data: 온톨로지 데이터
        """
        pass
    
    @abstractmethod
    def remove_class(self, db_name: str, class_id: str) -> None:
        """
        클래스 관련 모든 매핑 제거
        
        Args:
            db_name: 데이터베이스 이름
            class_id: 클래스 ID
        """
        pass
    
    @abstractmethod
    def export_mappings(self, db_name: str) -> Dict[str, Any]:
        """
        특정 데이터베이스의 모든 매핑 내보내기
        
        Args:
            db_name: 데이터베이스 이름
            
        Returns:
            매핑 데이터
        """
        pass
    
    @abstractmethod
    def import_mappings(self, data: Dict[str, Any]) -> None:
        """
        매핑 데이터 가져오기
        
        Args:
            data: 매핑 데이터
        """
        pass