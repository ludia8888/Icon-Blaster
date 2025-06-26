"""
Event Bus for MSA Integration

실제 마이크로서비스 간 이벤트 발행을 위한 이벤트 버스 구현
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, asdict
import uuid
from collections import defaultdict
import time

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DomainEvent:
    """도메인 이벤트 기본 클래스"""
    event_id: str
    event_type: str
    aggregate_id: str
    aggregate_type: str
    event_version: int
    occurred_at: datetime
    user_id: Optional[str]
    correlation_id: Optional[str]
    causation_id: Optional[str]
    metadata: Dict[str, Any]
    payload: Dict[str, Any]
    
    def to_json(self) -> str:
        """JSON 직렬화"""
        data = asdict(self)
        data['occurred_at'] = self.occurred_at.isoformat()
        return json.dumps(data)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'DomainEvent':
        """JSON 역직렬화"""
        data = json.loads(json_str)
        data['occurred_at'] = datetime.fromisoformat(data['occurred_at'])
        return cls(**data)


class EventBus:
    """
    이벤트 버스 구현
    
    실제 프로덕션에서는 Kafka, RabbitMQ, NATS 등을 사용하지만,
    테스트를 위해 인메모리 구현과 함께 실제 이벤트 발행 시뮬레이션
    """
    
    def __init__(self):
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self.event_store: List[DomainEvent] = []
        self.failed_events: List[Tuple[DomainEvent, str]] = []
        self.metrics = {
            "events_published": 0,
            "events_failed": 0,
            "events_retried": 0,
            "latency_ms": []
        }
        self._running = False
        self._background_tasks = set()
        
    async def start(self):
        """이벤트 버스 시작"""
        self._running = True
        logger.info("Event bus started")
        
    async def stop(self):
        """이벤트 버스 중지"""
        self._running = False
        # 모든 백그라운드 태스크 완료 대기
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
        logger.info("Event bus stopped")
    
    def subscribe(self, event_type: str, handler: Callable):
        """이벤트 구독"""
        self.subscribers[event_type].append(handler)
        logger.debug(f"Subscribed handler to {event_type}")
    
    async def publish(self, event_type: str, payload: Dict[str, Any], **kwargs) -> str:
        """
        이벤트 발행
        
        실제 MSA 환경에서의 이벤트 발행을 시뮬레이션
        """
        event_id = str(uuid.uuid4())
        
        event = DomainEvent(
            event_id=event_id,
            event_type=event_type,
            aggregate_id=payload.get("aggregate_id", ""),
            aggregate_type=payload.get("aggregate_type", ""),
            event_version=1,
            occurred_at=datetime.now(),
            user_id=kwargs.get("user_id"),
            correlation_id=kwargs.get("correlation_id", str(uuid.uuid4())),
            causation_id=kwargs.get("causation_id"),
            metadata=kwargs.get("metadata", {}),
            payload=payload
        )
        
        # 이벤트 저장
        self.event_store.append(event)
        self.metrics["events_published"] += 1
        
        # 비동기 이벤트 전파
        task = asyncio.create_task(self._propagate_event(event))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        
        return event_id
    
    async def _propagate_event(self, event: DomainEvent):
        """이벤트를 구독자들에게 전파"""
        start_time = time.time()
        
        handlers = self.subscribers.get(event.event_type, [])
        handlers.extend(self.subscribers.get("*", []))  # 모든 이벤트 구독자
        
        if not handlers:
            logger.warning(f"No handlers for event type: {event.event_type}")
            return
        
        # 각 핸들러에게 병렬로 전파
        tasks = []
        for handler in handlers:
            task = self._deliver_to_handler(event, handler)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 실패한 전달 추적
        failures = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failures += 1
                self.failed_events.append((event, str(result)))
                logger.error(f"Failed to deliver event {event.event_id} to handler: {result}")
        
        if failures > 0:
            self.metrics["events_failed"] += failures
        
        # 지연 시간 기록
        latency = (time.time() - start_time) * 1000
        self.metrics["latency_ms"].append(latency)
    
    async def _deliver_to_handler(self, event: DomainEvent, handler: Callable):
        """개별 핸들러에게 이벤트 전달"""
        try:
            # 네트워크 지연 시뮬레이션
            await asyncio.sleep(0.001)  # 1ms
            
            # 핸들러 실행
            if asyncio.iscoroutinefunction(handler):
                await handler(event)
            else:
                handler(event)
                
        except Exception as e:
            logger.error(f"Handler error for event {event.event_id}: {e}")
            
            # 재시도 로직
            if event.metadata.get("retry_count", 0) < 3:
                event.metadata["retry_count"] = event.metadata.get("retry_count", 0) + 1
                self.metrics["events_retried"] += 1
                
                # 지수 백오프로 재시도
                await asyncio.sleep(2 ** event.metadata["retry_count"])
                return await self._deliver_to_handler(event, handler)
            else:
                raise
    
    def get_events_by_aggregate(self, aggregate_id: str) -> List[DomainEvent]:
        """특정 집합체의 모든 이벤트 조회"""
        return [e for e in self.event_store if e.aggregate_id == aggregate_id]
    
    def get_events_by_correlation(self, correlation_id: str) -> List[DomainEvent]:
        """상관관계 ID로 이벤트 조회"""
        return [e for e in self.event_store if e.correlation_id == correlation_id]
    
    def get_metrics(self) -> Dict[str, Any]:
        """메트릭 조회"""
        if self.metrics["latency_ms"]:
            avg_latency = sum(self.metrics["latency_ms"]) / len(self.metrics["latency_ms"])
            p99_latency = sorted(self.metrics["latency_ms"])[int(len(self.metrics["latency_ms"]) * 0.99)]
        else:
            avg_latency = 0
            p99_latency = 0
            
        return {
            "events_published": self.metrics["events_published"],
            "events_failed": self.metrics["events_failed"],
            "events_retried": self.metrics["events_retried"],
            "avg_latency_ms": avg_latency,
            "p99_latency_ms": p99_latency,
            "failed_events_count": len(self.failed_events)
        }


class SchemaChangeEventPublisher:
    """스키마 변경 이벤트 발행기"""
    
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        
    async def publish_property_added(
        self,
        object_type: str,
        property_name: str,
        property_details: Dict[str, Any],
        user_id: str,
        correlation_id: Optional[str] = None
    ):
        """속성 추가 이벤트"""
        await self.event_bus.publish(
            event_type="schema.property.added",
            payload={
                "aggregate_id": object_type,
                "aggregate_type": "ObjectType",
                "object_type": object_type,
                "property_name": property_name,
                "property_details": property_details,
                "timestamp": datetime.now().isoformat()
            },
            user_id=user_id,
            correlation_id=correlation_id,
            metadata={
                "version": "1.0",
                "source": "oms"
            }
        )
    
    async def publish_link_created(
        self,
        link_id: str,
        from_type: str,
        to_type: str,
        cardinality: str,
        user_id: str,
        correlation_id: Optional[str] = None
    ):
        """링크 생성 이벤트"""
        await self.event_bus.publish(
            event_type="schema.link.created",
            payload={
                "aggregate_id": link_id,
                "aggregate_type": "LinkType",
                "link_id": link_id,
                "from_type": from_type,
                "to_type": to_type,
                "cardinality": cardinality,
                "timestamp": datetime.now().isoformat()
            },
            user_id=user_id,
            correlation_id=correlation_id,
            metadata={
                "version": "1.0",
                "source": "oms"
            }
        )
    
    async def publish_merge_completed(
        self,
        merge_id: str,
        source_branch: str,
        target_branch: str,
        conflicts_resolved: int,
        user_id: str,
        correlation_id: Optional[str] = None
    ):
        """머지 완료 이벤트"""
        await self.event_bus.publish(
            event_type="schema.merge.completed",
            payload={
                "aggregate_id": merge_id,
                "aggregate_type": "Merge",
                "merge_id": merge_id,
                "source_branch": source_branch,
                "target_branch": target_branch,
                "conflicts_resolved": conflicts_resolved,
                "timestamp": datetime.now().isoformat()
            },
            user_id=user_id,
            correlation_id=correlation_id,
            metadata={
                "version": "1.0",
                "source": "oms"
            }
        )
    
    async def publish_conflict_detected(
        self,
        conflict_id: str,
        conflict_type: str,
        severity: str,
        branches: List[str],
        user_id: str,
        correlation_id: Optional[str] = None
    ):
        """충돌 감지 이벤트"""
        await self.event_bus.publish(
            event_type="schema.conflict.detected",
            payload={
                "aggregate_id": conflict_id,
                "aggregate_type": "Conflict",
                "conflict_id": conflict_id,
                "conflict_type": conflict_type,
                "severity": severity,
                "branches": branches,
                "timestamp": datetime.now().isoformat()
            },
            user_id=user_id,
            correlation_id=correlation_id,
            metadata={
                "version": "1.0",
                "source": "oms",
                "requires_manual_resolution": severity in ["ERROR", "BLOCK"]
            }
        )


# 글로벌 이벤트 버스 인스턴스
event_bus = EventBus()
schema_event_publisher = SchemaChangeEventPublisher(event_bus)