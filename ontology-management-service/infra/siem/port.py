"""
SIEM Port Interface (의존성 역전을 위한 Protocol)
Core 레이어가 의존하는 인터페이스 정의
"""
from typing import Protocol, Dict, Any, List, Optional
from abc import abstractmethod


class ISiemPort(Protocol):
    """SIEM 시스템과의 통신을 위한 포트 인터페이스"""
    
    @abstractmethod
    async def send(self, event_type: str, payload: Dict[str, Any]) -> None:
        """
        단일 이벤트를 SIEM으로 전송
        
        Args:
            event_type: 이벤트 타입 (예: "security.tampering")
            payload: 전송할 데이터 (dict 형태)
        """
        ...
    
    @abstractmethod
    async def send_batch(self, events: List[Dict[str, Any]]) -> None:
        """
        여러 이벤트를 배치로 전송
        
        Args:
            events: 이벤트 리스트, 각 이벤트는 'type'과 'payload' 키를 포함
        """
        ...
    
    @abstractmethod
    async def query(self, query_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        SIEM에서 이벤트 조회
        
        Args:
            query_params: 조회 조건
            
        Returns:
            조회된 이벤트 리스트
        """
        ...
    
    @abstractmethod
    async def health_check(self) -> bool:
        """SIEM 연결 상태 확인"""
        ...