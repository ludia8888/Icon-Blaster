"""
EventPublisher - 간단한 이벤트 퍼블리셔 구현
"""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

class EventPublisher:
    """이벤트 퍼블리셔 더미 구현"""
    
    def __init__(self, *args, **kwargs):
        pass
    
    async def publish(self, event_type: str, data: Dict[str, Any]):
        """이벤트 발행 (로깅만)"""
        logger.info(f"Event published: {event_type} - {data}")
    
    async def publish_batch(self, events: list):
        """여러 이벤트 발행"""
        for event in events:
            await self.publish(event.get('type', 'unknown'), event.get('data', {}))
    
    def close(self):
        """리소스 정리"""
        pass