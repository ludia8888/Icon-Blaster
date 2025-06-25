"""
Outbox 패턴 구현 - 데이터 일관성 보장
- Idempotency key로 중복 처리 방지
- 트랜잭션 보장
"""
import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class OutboxStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"

class OutboxEvent(BaseModel):
    """Outbox 이벤트 모델"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    idempotency_key: str  # 중복 방지 키
    aggregate_id: str  # 집계 ID (예: object_type_id)
    aggregate_type: str  # 집계 타입 (예: "ObjectType")
    event_type: str
    event_data: Dict[str, Any]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    status: OutboxStatus = OutboxStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.now)
    processed_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None

    def generate_idempotency_key(self) -> str:
        """이벤트 데이터 기반 idempotency key 생성"""
        data_str = f"{self.aggregate_type}:{self.aggregate_id}:{self.event_type}:{json.dumps(self.event_data, sort_keys=True)}"
        return hashlib.sha256(data_str.encode()).hexdigest()

class OutboxStore:
    """In-memory Outbox 저장소 (실제로는 DB 사용)"""

    def __init__(self):
        self.events: Dict[str, OutboxEvent] = {}
        self.idempotency_index: Dict[str, str] = {}  # idempotency_key -> event_id
        self.processing_events: set = set()  # 처리 중인 이벤트
        self._lock = asyncio.Lock()

    async def add_event(self, event: OutboxEvent) -> bool:
        """이벤트 추가 (중복 체크)"""
        async with self._lock:
            # Idempotency key 체크
            if event.idempotency_key in self.idempotency_index:
                existing_id = self.idempotency_index[event.idempotency_key]
                logger.warning(f"Duplicate event detected: {event.idempotency_key} -> {existing_id}")
                return False

            # 이벤트 저장
            self.events[event.id] = event
            self.idempotency_index[event.idempotency_key] = event.id

            logger.info(f"Outbox event added: {event.id} ({event.event_type})")
            return True

    async def get_pending_events(self, limit: int = 100) -> List[OutboxEvent]:
        """처리 대기 중인 이벤트 조회"""
        async with self._lock:
            pending_events = [
                event for event in self.events.values()
                if event.status == OutboxStatus.PENDING
                and event.id not in self.processing_events
                and event.retry_count < event.max_retries
            ]

            # 처리 중 표시
            for event in pending_events[:limit]:
                self.processing_events.add(event.id)
                event.status = OutboxStatus.PROCESSING

            return pending_events[:limit]

    async def mark_completed(self, event_id: str):
        """이벤트 처리 완료"""
        async with self._lock:
            if event_id in self.events:
                self.events[event_id].status = OutboxStatus.COMPLETED
                self.events[event_id].processed_at = datetime.now()
                self.processing_events.discard(event_id)
                logger.info(f"Outbox event completed: {event_id}")

    async def mark_failed(self, event_id: str, error_message: str):
        """이벤트 처리 실패"""
        async with self._lock:
            if event_id in self.events:
                event = self.events[event_id]
                event.retry_count += 1
                event.error_message = error_message

                if event.retry_count >= event.max_retries:
                    event.status = OutboxStatus.DEAD_LETTER
                    logger.error(f"Outbox event moved to dead letter: {event_id}")
                else:
                    event.status = OutboxStatus.FAILED
                    logger.warning(f"Outbox event failed (retry {event.retry_count}): {event_id}")

                self.processing_events.discard(event_id)

    async def cleanup_completed(self, older_than_hours: int = 24):
        """완료된 오래된 이벤트 정리"""
        async with self._lock:
            cutoff_time = datetime.now() - timedelta(hours=older_than_hours)

            to_remove = []
            for event_id, event in self.events.items():
                if event.status == OutboxStatus.COMPLETED and event.processed_at < cutoff_time:
                    to_remove.append(event_id)

            for event_id in to_remove:
                event = self.events.pop(event_id)
                self.idempotency_index.pop(event.idempotency_key, None)

            if to_remove:
                logger.info(f"Cleaned up {len(to_remove)} completed events")

class OutboxProcessor:
    """Outbox 이벤트 처리기"""

    def __init__(self, store: OutboxStore):
        self.store = store
        self.is_running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """처리기 시작"""
        if self.is_running:
            return

        self.is_running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("Outbox processor started")

    async def stop(self):
        """처리기 중지"""
        self.is_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Outbox processor stopped")

    async def _process_loop(self):
        """이벤트 처리 루프"""
        while self.is_running:
            try:
                # 대기 중인 이벤트 조회
                events = await self.store.get_pending_events()

                if events:
                    # 동시 처리
                    tasks = [self._process_event(event) for event in events]
                    await asyncio.gather(*tasks, return_exceptions=True)
                else:
                    # 이벤트가 없으면 잠시 대기
                    await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Outbox processing error: {e}")
                await asyncio.sleep(5)

    async def _process_event(self, event: OutboxEvent):
        """개별 이벤트 처리"""
        try:
            # 여기서 실제 이벤트 발행 (NATS, Redis, etc.)
            await self._publish_event(event)

            # 성공 표시
            await self.store.mark_completed(event.id)

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Failed to process event {event.id}: {error_msg}")
            await self.store.mark_failed(event.id, error_msg)

    async def _publish_event(self, event: OutboxEvent):
        """이벤트 발행 (구현 필요)"""
        # EventService.publish 호출
        from core.event_publisher.enhanced_event_service import EnhancedEventService
        from core.event_publisher import get_event_publisher
        
        event_service = get_event_publisher()

        # EnhancedEventService의 publish 메서드 호출
        await event_service.publish(
            subject=f"{event.aggregate_type}/{event.aggregate_id}",
            event_type=event.event_type,
            source=f"outbox-{event.aggregate_type}",
            data=event.event_data,
            user_id=event.metadata.get("user_id", "system"),
            metadata=event.metadata
        )

# 전역 인스턴스
outbox_store = OutboxStore()
outbox_processor = OutboxProcessor(outbox_store)

# 헬퍼 함수
async def publish_with_outbox(
    aggregate_type: str,
    aggregate_id: str,
    event_type: str,
    event_data: Dict[str, Any],
    user_id: str = "system",
    idempotency_key: Optional[str] = None
) -> bool:
    """Outbox 패턴으로 이벤트 발행"""
    event = OutboxEvent(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        event_data=event_data,
        metadata={"user_id": user_id}
    )

    # idempotency key 설정
    if idempotency_key:
        event.idempotency_key = idempotency_key
    else:
        event.idempotency_key = event.generate_idempotency_key()

    # 이벤트 저장
    return await outbox_store.add_event(event)
