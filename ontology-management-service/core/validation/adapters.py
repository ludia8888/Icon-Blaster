"""
Port Adapters - 실제 구현체들을 Port 인터페이스에 맞게 연결
순환 참조 해결의 핵심: 인프라 레이어의 구현체를 Core 레이어의 인터페이스에 맞춤
"""
from typing import Any, Dict, List, Optional
import logging

from core.validation.ports import CachePort, TerminusPort, EventPort

logger = logging.getLogger(__name__)


class SmartCacheAdapter:
    """
    shared.cache.smart_cache.SmartCacheManager를 CachePort로 변환하는 어댑터
    실제 import는 생성자에서만 수행하여 순환 참조 방지
    """
    
    def __init__(self, cache_manager=None):
        if cache_manager is None:
            # 런타임에만 import하여 순환 참조 방지
            from shared.cache.smart_cache import SmartCacheManager
            from database.clients.terminus_db import TerminusDBClient
            tdb = TerminusDBClient()
            self.cache = SmartCacheManager(tdb)
        else:
            self.cache = cache_manager
    
    async def get(self, key: str) -> Any:
        """캐시에서 값 조회"""
        try:
            return await self.cache.get(key)
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """캐시에 값 저장"""
        try:
            await self.cache.set(key, value, ttl=ttl)
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
    
    async def delete(self, key: str) -> None:
        """캐시에서 값 삭제"""
        try:
            await self.cache.delete(key)
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
    
    async def exists(self, key: str) -> bool:
        """키 존재 여부 확인"""
        try:
            return await self.cache.exists(key)
        except Exception as e:
            logger.error(f"Cache exists error for key {key}: {e}")
            return False


class TerminusDBAdapter:
    """
    database.clients.terminus_db.TerminusDBClient를 TerminusPort로 변환하는 어댑터
    """
    
    def __init__(self, tdb_client=None):
        if tdb_client is None:
            # 런타임에만 import
            from database.clients.terminus_db import TerminusDBClient
            self.tdb = TerminusDBClient()
        else:
            self.tdb = tdb_client
    
    async def query(
        self, 
        sparql: str, 
        db: str = "oms", 
        branch: str = "main", 
        **opts
    ) -> List[Dict[str, Any]]:
        """SPARQL 쿼리 실행"""
        try:
            return await self.tdb.query(sparql, db=db, branch=branch)
        except Exception as e:
            logger.error(f"TerminusDB query error: {e}")
            return []
    
    async def get_document(
        self, 
        doc_id: str, 
        db: str = "oms", 
        branch: str = "main"
    ) -> Optional[Dict[str, Any]]:
        """문서 조회"""
        try:
            return await self.tdb.get_document(doc_id, db=db, branch=branch)
        except Exception as e:
            logger.error(f"TerminusDB get_document error: {e}")
            return None
    
    async def insert_document(
        self, 
        document: Dict[str, Any], 
        db: str = "oms", 
        branch: str = "main",
        author: Optional[str] = None,
        message: Optional[str] = None
    ) -> str:
        """문서 삽입"""
        try:
            return await self.tdb.insert_document(
                document, 
                db=db, 
                branch=branch,
                author=author,
                message=message
            )
        except Exception as e:
            logger.error(f"TerminusDB insert_document error: {e}")
            raise
    
    async def update_document(
        self, 
        document: Dict[str, Any], 
        db: str = "oms", 
        branch: str = "main",
        author: Optional[str] = None,
        message: Optional[str] = None
    ) -> bool:
        """문서 업데이트"""
        try:
            return await self.tdb.update_document(
                document, 
                db=db, 
                branch=branch,
                author=author,
                message=message
            )
        except Exception as e:
            logger.error(f"TerminusDB update_document error: {e}")
            return False
    
    async def health_check(self) -> bool:
        """헬스 체크"""
        try:
            return await self.tdb.health_check()
        except Exception as e:
            logger.error(f"TerminusDB health_check error: {e}")
            return False


class EventPublisherAdapter:
    """
    shared.events.EventPublisher를 EventPort로 변환하는 어댑터
    """
    
    def __init__(self, event_publisher=None):
        if event_publisher is None:
            # 런타임에만 import
            from shared.events import EventPublisher
            self.publisher = EventPublisher()
        else:
            self.publisher = event_publisher
    
    async def publish(
        self, 
        event_type: str, 
        data: Dict[str, Any], 
        correlation_id: Optional[str] = None
    ) -> None:
        """이벤트 발행"""
        try:
            # EventPublisher의 실제 메서드에 맞게 호출
            if hasattr(self.publisher, 'publish_event'):
                await self.publisher.publish_event(
                    event_type=event_type,
                    data=data,
                    correlation_id=correlation_id
                )
            elif hasattr(self.publisher, 'publish'):
                await self.publisher.publish(
                    event_type,
                    data,
                    correlation_id=correlation_id
                )
            else:
                logger.warning(f"EventPublisher does not have publish method")
        except Exception as e:
            logger.error(f"Event publish error: {e}")
    
    async def publish_batch(self, events: List[Dict[str, Any]]) -> None:
        """배치 이벤트 발행"""
        try:
            if hasattr(self.publisher, 'publish_batch'):
                await self.publisher.publish_batch(events)
            else:
                # 배치 메서드가 없으면 개별 발행
                for event in events:
                    await self.publish(
                        event.get('event_type', 'unknown'),
                        event.get('data', {}),
                        event.get('correlation_id')
                    )
        except Exception as e:
            logger.error(f"Event publish_batch error: {e}")


# Factory functions for easy adapter creation
def create_cache_adapter(cache_manager=None) -> CachePort:
    """캐시 어댑터 생성"""
    return SmartCacheAdapter(cache_manager)


def create_terminus_adapter(tdb_client=None) -> TerminusPort:
    """TerminusDB 어댑터 생성"""
    return TerminusDBAdapter(tdb_client)


def create_event_adapter(event_publisher=None) -> EventPort:
    """이벤트 어댑터 생성"""
    return EventPublisherAdapter(event_publisher)


# Test adapters for unit testing
class MockCacheAdapter:
    """테스트용 Mock 캐시 어댑터"""
    
    def __init__(self):
        self.storage = {}
        self.call_count = {
            'get': 0,
            'set': 0,
            'delete': 0,
            'exists': 0
        }
    
    async def get(self, key: str) -> Any:
        self.call_count['get'] += 1
        return self.storage.get(key)
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        self.call_count['set'] += 1
        self.storage[key] = value
    
    async def delete(self, key: str) -> None:
        self.call_count['delete'] += 1
        self.storage.pop(key, None)
    
    async def exists(self, key: str) -> bool:
        self.call_count['exists'] += 1
        return key in self.storage


class MockTerminusAdapter:
    """테스트용 Mock TerminusDB 어댑터"""
    
    def __init__(self):
        self.documents = {}
        self.query_results = []
        self.call_count = {
            'query': 0,
            'get_document': 0,
            'insert_document': 0,
            'update_document': 0
        }
    
    async def query(
        self, 
        sparql: str, 
        db: str = "oms", 
        branch: str = "main", 
        **opts
    ) -> List[Dict[str, Any]]:
        self.call_count['query'] += 1
        return self.query_results
    
    async def get_document(
        self, 
        doc_id: str, 
        db: str = "oms", 
        branch: str = "main"
    ) -> Optional[Dict[str, Any]]:
        self.call_count['get_document'] += 1
        return self.documents.get(doc_id)
    
    async def insert_document(
        self, 
        document: Dict[str, Any], 
        db: str = "oms", 
        branch: str = "main",
        author: Optional[str] = None,
        message: Optional[str] = None
    ) -> str:
        self.call_count['insert_document'] += 1
        doc_id = document.get('@id', f'doc_{len(self.documents)}')
        self.documents[doc_id] = document
        return doc_id
    
    async def update_document(
        self, 
        document: Dict[str, Any], 
        db: str = "oms", 
        branch: str = "main",
        author: Optional[str] = None,
        message: Optional[str] = None
    ) -> bool:
        self.call_count['update_document'] += 1
        doc_id = document.get('@id')
        if doc_id and doc_id in self.documents:
            self.documents[doc_id] = document
            return True
        return False
    
    async def health_check(self) -> bool:
        return True


class MockEventAdapter:
    """테스트용 Mock 이벤트 어댑터"""
    
    def __init__(self):
        self.published_events = []
        self.call_count = {
            'publish': 0,
            'publish_batch': 0
        }
    
    async def publish(
        self, 
        event_type: str, 
        data: Dict[str, Any], 
        correlation_id: Optional[str] = None
    ) -> None:
        self.call_count['publish'] += 1
        self.published_events.append({
            'event_type': event_type,
            'data': data,
            'correlation_id': correlation_id
        })
    
    async def publish_batch(self, events: List[Dict[str, Any]]) -> None:
        self.call_count['publish_batch'] += 1
        self.published_events.extend(events)