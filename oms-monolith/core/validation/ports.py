"""
Validation Service Ports (Interfaces)
의존성 역전을 위한 Port 인터페이스 정의
순환 참조 해결을 위한 핵심 추상화 계층
"""
from typing import Protocol, Any, Dict, List, Optional, runtime_checkable

@runtime_checkable
class CachePort(Protocol):
    """캐시 인터페이스 - 외부 캐시 시스템과의 계약"""
    
    async def get(self, key: str) -> Any:
        """캐시에서 값 조회"""
        ...
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """캐시에 값 저장"""
        ...
    
    async def delete(self, key: str) -> None:
        """캐시에서 값 삭제"""
        ...
    
    async def exists(self, key: str) -> bool:
        """키 존재 여부 확인"""
        ...

@runtime_checkable
class TerminusPort(Protocol):
    """TerminusDB 인터페이스 - 데이터베이스와의 계약"""
    
    async def query(
        self, 
        sparql: str, 
        db: str = "oms", 
        branch: str = "main", 
        **opts
    ) -> List[Dict[str, Any]]:
        """SPARQL 쿼리 실행"""
        ...
    
    async def get_document(
        self, 
        doc_id: str, 
        db: str = "oms", 
        branch: str = "main"
    ) -> Optional[Dict[str, Any]]:
        """문서 조회"""
        ...
    
    async def insert_document(
        self, 
        document: Dict[str, Any], 
        db: str = "oms", 
        branch: str = "main",
        author: Optional[str] = None,
        message: Optional[str] = None
    ) -> str:
        """문서 삽입"""
        ...
    
    async def update_document(
        self, 
        document: Dict[str, Any], 
        db: str = "oms", 
        branch: str = "main",
        author: Optional[str] = None,
        message: Optional[str] = None
    ) -> bool:
        """문서 업데이트"""
        ...
    
    async def health_check(self) -> bool:
        """헬스 체크"""
        ...

@runtime_checkable
class EventPort(Protocol):
    """이벤트 발행 인터페이스 - 이벤트 시스템과의 계약"""
    
    async def publish(
        self, 
        event_type: str, 
        data: Dict[str, Any], 
        correlation_id: Optional[str] = None
    ) -> None:
        """이벤트 발행"""
        ...
    
    async def publish_batch(self, events: List[Dict[str, Any]]) -> None:
        """배치 이벤트 발행"""
        ...

class ValidationContext:
    """
    검증 컨텍스트 - 규칙 실행에 필요한 모든 정보를 담는 컨테이너
    의존성 주입을 통해 Port 구현체들을 전달받음
    """
    
    def __init__(
        self,
        source_branch: str,
        target_branch: str,
        user_id: Optional[str] = None,
        cache: Optional[CachePort] = None,
        terminus_client: Optional[TerminusPort] = None,
        event_publisher: Optional[EventPort] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.source_branch = source_branch
        self.target_branch = target_branch
        self.user_id = user_id
        self.cache = cache
        self.terminus_client = terminus_client
        self.event_publisher = event_publisher
        self.metadata = metadata or {}
        
    def with_metadata(self, **kwargs) -> 'ValidationContext':
        """메타데이터를 추가한 새 컨텍스트 생성"""
        new_metadata = {**self.metadata, **kwargs}
        return ValidationContext(
            source_branch=self.source_branch,
            target_branch=self.target_branch,
            user_id=self.user_id,
            cache=self.cache,
            terminus_client=self.terminus_client,
            event_publisher=self.event_publisher,
            metadata=new_metadata
        )

# Adapter implementations for testing
class InMemoryCacheAdapter:
    """테스트용 인메모리 캐시 어댑터"""
    
    def __init__(self):
        self._storage: Dict[str, Any] = {}
    
    async def get(self, key: str) -> Any:
        return self._storage.get(key)
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        self._storage[key] = value
    
    async def delete(self, key: str) -> None:
        self._storage.pop(key, None)
    
    async def exists(self, key: str) -> bool:
        return key in self._storage

class NoOpEventAdapter:
    """테스트용 이벤트 어댑터 (아무것도 하지 않음)"""
    
    async def publish(
        self, 
        event_type: str, 
        data: Dict[str, Any], 
        correlation_id: Optional[str] = None
    ) -> None:
        pass
    
    async def publish_batch(self, events: List[Dict[str, Any]]) -> None:
        pass