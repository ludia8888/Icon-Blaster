"""
GraphQL Realtime Publisher
실시간 이벤트 발행 및 구독 관리
"""
import asyncio
import logging
from typing import Dict, Set, Optional, Any, AsyncIterator
from dataclasses import dataclass
from enum import Enum
import json
import time

logger = logging.getLogger(__name__)

class EventType(str, Enum):
    """실시간 이벤트 유형"""
    SCHEMA_CHANGED = "schema_changed"
    BRANCH_UPDATED = "branch_updated"
    ACTION_PROGRESS = "action_progress"
    PROPOSAL_UPDATED = "proposal_updated"
    USER_NOTIFICATION = "user_notification"

@dataclass
class RealtimeEvent:
    """실시간 이벤트"""
    event_type: EventType
    payload: Dict[str, Any]
    user_id: Optional[str] = None
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()

class RealtimeSubscription:
    """실시간 구독"""
    def __init__(self, subscription_id: str, user_id: str, event_types: Set[EventType]):
        self.subscription_id = subscription_id
        self.user_id = user_id
        self.event_types = event_types
        self.queue: asyncio.Queue = asyncio.Queue()
        self.created_at = time.time()
        self.last_activity = time.time()
    
    async def send_event(self, event: RealtimeEvent):
        """이벤트 전송"""
        if event.event_type in self.event_types:
            if event.user_id is None or event.user_id == self.user_id:
                await self.queue.put(event)
                self.last_activity = time.time()
    
    async def get_events(self) -> AsyncIterator[RealtimeEvent]:
        """이벤트 수신"""
        while True:
            try:
                event = await asyncio.wait_for(self.queue.get(), timeout=30.0)
                yield event
            except asyncio.TimeoutError:
                # Keepalive
                keepalive_event = RealtimeEvent(
                    event_type=EventType.USER_NOTIFICATION,
                    payload={"type": "keepalive"},
                    user_id=self.user_id
                )
                yield keepalive_event

class RealtimePublisher:
    """실시간 발행자"""
    
    def __init__(self):
        self.subscriptions: Dict[str, RealtimeSubscription] = {}
        self.user_subscriptions: Dict[str, Set[str]] = {}
        self._cleanup_task = None
        # Don't start cleanup task in __init__ to avoid event loop issues
    
    def _start_cleanup_task(self):
        """정리 작업 시작"""
        async def cleanup_stale_subscriptions():
            while True:
                try:
                    await asyncio.sleep(60)  # 1분마다 정리
                    current_time = time.time()
                    stale_subscriptions = []
                    
                    for sub_id, subscription in self.subscriptions.items():
                        if current_time - subscription.last_activity > 300:  # 5분 비활성
                            stale_subscriptions.append(sub_id)
                    
                    for sub_id in stale_subscriptions:
                        await self.unsubscribe(sub_id)
                        
                except Exception as e:
                    logger.error(f"Cleanup task error: {e}")
        
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(cleanup_stale_subscriptions())
    
    async def subscribe(self, user_id: str, event_types: Set[EventType]) -> str:
        """구독 등록"""
        # Start cleanup task on first subscription if not already started
        if self._cleanup_task is None:
            self._start_cleanup_task()
            
        subscription_id = f"{user_id}_{int(time.time() * 1000)}"
        subscription = RealtimeSubscription(subscription_id, user_id, event_types)
        
        self.subscriptions[subscription_id] = subscription
        
        if user_id not in self.user_subscriptions:
            self.user_subscriptions[user_id] = set()
        self.user_subscriptions[user_id].add(subscription_id)
        
        logger.info(f"Created subscription {subscription_id} for user {user_id}")
        return subscription_id
    
    async def unsubscribe(self, subscription_id: str):
        """구독 해제"""
        if subscription_id in self.subscriptions:
            subscription = self.subscriptions[subscription_id]
            user_id = subscription.user_id
            
            del self.subscriptions[subscription_id]
            
            if user_id in self.user_subscriptions:
                self.user_subscriptions[user_id].discard(subscription_id)
                if not self.user_subscriptions[user_id]:
                    del self.user_subscriptions[user_id]
            
            logger.info(f"Removed subscription {subscription_id}")
    
    async def publish(self, event: RealtimeEvent):
        """이벤트 발행"""
        logger.debug(f"Publishing event {event.event_type} to {len(self.subscriptions)} subscriptions")
        
        tasks = []
        for subscription in self.subscriptions.values():
            tasks.append(subscription.send_event(event))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def get_subscription_events(self, subscription_id: str) -> AsyncIterator[RealtimeEvent]:
        """구독 이벤트 스트림"""
        if subscription_id not in self.subscriptions:
            return
        
        subscription = self.subscriptions[subscription_id]
        async for event in subscription.get_events():
            yield event
    
    def get_subscription_count(self) -> int:
        """활성 구독 수"""
        return len(self.subscriptions)
    
    def get_user_subscription_count(self, user_id: str) -> int:
        """사용자별 구독 수"""
        return len(self.user_subscriptions.get(user_id, set()))

# 전역 실시간 발행자 인스턴스
realtime_publisher = RealtimePublisher()

# Convenience functions
async def publish_schema_change(schema_id: str, change_type: str, user_id: str = None):
    """스키마 변경 이벤트 발행"""
    event = RealtimeEvent(
        event_type=EventType.SCHEMA_CHANGED,
        payload={
            "schema_id": schema_id,
            "change_type": change_type,
            "timestamp": time.time()
        },
        user_id=user_id
    )
    await realtime_publisher.publish(event)

async def publish_branch_update(branch_name: str, operation: str, user_id: str = None):
    """브랜치 업데이트 이벤트 발행"""
    event = RealtimeEvent(
        event_type=EventType.BRANCH_UPDATED,
        payload={
            "branch_name": branch_name,
            "operation": operation,
            "timestamp": time.time()
        },
        user_id=user_id
    )
    await realtime_publisher.publish(event)

async def publish_action_progress(action_id: str, progress: float, status: str, user_id: str = None):
    """액션 진행상황 이벤트 발행"""
    event = RealtimeEvent(
        event_type=EventType.ACTION_PROGRESS,
        payload={
            "action_id": action_id,
            "progress": progress,
            "status": status,
            "timestamp": time.time()
        },
        user_id=user_id
    )
    await realtime_publisher.publish(event)