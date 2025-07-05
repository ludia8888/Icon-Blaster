"""
REQ-OMS-IF1-AC3: Outbox 패턴 구현
REQ-OMS-IF1-AC6: Event Bus 전달 보장
섹션 8.5.3의 Outbox Processor 구현
Enhanced CloudEvents 1.0 표준 완전 지원
"""
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Optional

from database.clients.terminus_db import TerminusDBClient
from shared.infrastructure.metrics import MetricsCollector
from shared.infrastructure.nats_client import NATSClient
from .cloudevents_enhanced import EnhancedCloudEvent, CloudEventValidator
from .cloudevents_adapter import CloudEventsAdapter
from .cloudevents_migration import EventSchemaMigrator
from .multi_platform_router import MultiPlatformEventRouter, create_oms_multi_platform_router
from .eventbridge_publisher import EventBridgeConfig

logger = logging.getLogger(__name__)


class OutboxProcessor:
    """
    REQ-OMS-IF1-AC3: Outbox 패턴 구현
    REQ-OMS-IF1-AC6: 트랜잭션 보장을 위한 Outbox 패턴
    """

    def __init__(
        self,
        tdb_client: TerminusDBClient,
        nats_client: NATSClient,
        metrics: MetricsCollector,
        eventbridge_config: Optional[EventBridgeConfig] = None,
        enable_multi_platform: bool = False
    ):
        self.tdb = tdb_client
        self.nats = nats_client
        self.metrics = metrics
        self.batch_size = 100
        self.process_interval = 0.5  # 500ms
        self.migrator = EventSchemaMigrator()  # 레거시 이벤트 마이그레이션용
        
        # Multi-Platform Router 설정
        self.enable_multi_platform = enable_multi_platform
        self.router = None
        
        if enable_multi_platform:
            self.router = create_oms_multi_platform_router(
                nats_publisher=nats_client,
                eventbridge_config=eventbridge_config
            )
            logger.info("Multi-platform event routing enabled")

    async def start_processing(self):
        """
        REQ-OMS-IF1-AC3: Outbox 처리 시작
        Event Bus로의 안전한 이벤트 전달
        """

        while True:
            try:
                processed = await self._process_batch()

                if processed > 0:
                    self.metrics.record_events_processed(processed)

            except Exception as e:
                logger.error(f"Outbox processing error: {e}")
                self.metrics.record_processing_error()

            await asyncio.sleep(self.process_interval)

    async def _process_batch(self) -> int:
        """배치 처리"""

        # 1. 미발행 이벤트 조회
        query = """
        SELECT ?event ?id ?type ?payload ?created_at
        WHERE {
            ?event a ont:OutboxEvent .
            ?event ont:status "pending" .
            ?event ont:id ?id .
            ?event ont:type ?type .
            ?event ont:payload ?payload .
            ?event ont:created_at ?created_at .
        }
        ORDER BY ?created_at
        LIMIT $limit
        """

        events = await self.tdb.query(
            query,
            branch="_outbox",
            bindings={"limit": self.batch_size}
        )

        if not events:
            return 0

        # 2. 각 이벤트 발행
        processed = 0

        for event in events:
            try:
                await self._publish_event(event)
                await self._mark_published(event["id"])
                processed += 1

            except Exception as e:
                logger.error(f"Failed to publish event {event['id']}: {e}")
                await self._mark_failed(event["id"], str(e))

        return processed

    async def _publish_event(self, event: Dict):
        """Enhanced CloudEvents를 Multi-Platform으로 발행"""

        try:
            # 1. OutboxEvent를 Enhanced CloudEvent로 변환
            payload = json.loads(event["payload"])
            
            # 레거시 이벤트 형식 감지 및 마이그레이션
            legacy_event = {
                "id": event["id"],
                "type": event["type"],
                "payload": event["payload"],
                "created_at": event["created_at"]
            }
            
            migrated_event = self.migrator._migrate_single_event(legacy_event)
            if migrated_event:
                cloud_event = migrated_event
            else:
                # 직접 변환
                cloud_event = EnhancedCloudEvent(
                    type=f"com.foundry.oms.{event['type']}",
                    source=f"/oms/{payload.get('branch', 'main')}",
                    id=event["id"],
                    data=payload
                )
            
            # 2. CloudEvent 유효성 검증
            validation_errors = CloudEventValidator.validate_cloudevent(cloud_event)
            if validation_errors:
                logger.warning(f"CloudEvent validation warnings for {event['id']}: {validation_errors}")
            
            # 3. Multi-Platform 라우팅 또는 NATS 직접 발행
            if self.enable_multi_platform and self.router:
                # Multi-Platform Router 사용
                platform_results = await self.router.publish_event(cloud_event)
                
                # 결과 처리
                success_count = sum(1 for result in platform_results.values() if result.success)
                total_platforms = len(platform_results)
                
                if success_count > 0:
                    logger.debug(f"Published CloudEvent {cloud_event.id} to {success_count}/{total_platforms} platforms")
                else:
                    logger.error(f"Failed to publish CloudEvent {cloud_event.id} to any platform")
                    # 전체 실패시 레거시 fallback
                    await self._publish_legacy_event(event)
                    return
                
                # 메트릭 기록 (첫 번째 성공한 플랫폼 기준)
                for platform, result in platform_results.items():
                    if result.success:
                        latency = result.latency_ms or (
                            (datetime.utcnow() - datetime.fromisoformat(event["created_at"])).total_seconds() * 1000
                        )
                        self.metrics.record_event_latency(str(cloud_event.type), latency / 1000)
                        break
            
            else:
                # 기존 NATS 직접 발행
                await self._publish_to_nats_directly(cloud_event, event)
            
        except Exception as e:
            logger.error(f"Failed to publish event {event['id']} as CloudEvent: {e}")
            # 레거시 형식으로 fallback
            await self._publish_legacy_event(event)
    
    async def _publish_to_nats_directly(self, cloud_event: EnhancedCloudEvent, original_event: Dict):
        """NATS에 직접 발행 (기존 로직)"""
        # 3. NATS subject 결정
        subject = cloud_event.get_nats_subject()
        
        # 4. Binary Content Mode로 발행
        headers = cloud_event.to_binary_headers()
        headers.update({
            "Nats-Msg-Id": original_event["id"],  # 중복 제거용
            "X-OMS-Event-Version": "2.0",  # Enhanced CloudEvents 버전
            "X-OMS-Router": "direct-nats"
        })
        
        # 데이터는 JSON으로 페이로드에
        payload_data = json.dumps(cloud_event.data or {}).encode()
        
        # NATS JetStream 발행
        await self.nats.publish(
            subject=subject,
            payload=payload_data,
            headers=headers
        )
        
        logger.debug(f"Published CloudEvent {cloud_event.id} directly to NATS subject {subject}")
        
        # 5. 메트릭 기록
        latency = (datetime.utcnow() -
                  datetime.fromisoformat(original_event["created_at"])).total_seconds()
        
        self.metrics.record_event_latency(str(cloud_event.type), latency)

    async def _publish_legacy_event(self, event: Dict):
        """레거시 형식으로 이벤트 발행 (fallback)"""
        
        event_type = event["type"]
        payload = json.loads(event["payload"])

        # 기존 CloudEvents 형식으로 변환
        cloud_event = {
            "specversion": "1.0",
            "type": f"com.oms.{event_type}",
            "source": f"/oms/{payload.get('branch', 'main')}",
            "id": event["id"],
            "time": event["created_at"],
            "datacontenttype": "application/json",
            "data": payload
        }

        # Subject 결정
        subject = self._get_subject(event_type, payload)

        # NATS JetStream 발행
        await self.nats.publish(
            subject=subject,
            payload=json.dumps(cloud_event).encode(),
            headers={
                "Nats-Msg-Id": event["id"],  # 중복 제거용
                "CE-Type": cloud_event["type"],
                "CE-Source": cloud_event["source"],
                "X-OMS-Event-Version": "1.0",  # 레거시 버전
                "X-OMS-Fallback": "true"
            }
        )

        logger.info(f"Published legacy event {event['id']} to subject {subject}")

    def _get_subject(self, event_type: str, payload: Dict) -> str:
        """이벤트 타입에 따른 NATS subject 결정"""

        branch = payload.get("branch", "main")

        if event_type == "schema.changed":
            # oms.schema.changed.{branch}.{resource_type}
            resource_type = payload.get("changed_resources", [""])[0].split(":")[0]
            return f"oms.schema.changed.{branch}.{resource_type}"

        elif event_type == "branch.merged":
            # oms.branch.merged.{target_branch}
            return f"oms.branch.merged.{payload.get('target_branch')}"

        elif event_type == "action.completed":
            # oms.action.completed.{action_type}
            return f"oms.action.completed.{payload.get('action_type')}"

        else:
            # 기본: oms.events.{event_type}
            return f"oms.events.{event_type}"

    async def _mark_published(self, event_id: str):
        """이벤트를 발행됨으로 표시"""

        update_query = """
        WOQL.and(
            WOQL.triple("v:Event", "ont:id", $event_id),
            WOQL.delete_triple("v:Event", "ont:status", "pending"),
            WOQL.add_triple("v:Event", "ont:status", "published"),
            WOQL.add_triple("v:Event", "ont:published_at", WOQL.datetime())
        )
        """

        await self.tdb.update(
            update_query,
            branch="_outbox",
            bindings={"event_id": event_id}
        )

    async def _mark_failed(self, event_id: str, error: str):
        """이벤트 발행 실패 처리"""

        # 재시도 횟수 증가
        retry_query = """
        WOQL.and(
            WOQL.triple("v:Event", "ont:id", $event_id),
            WOQL.opt(WOQL.triple("v:Event", "ont:retry_count", "v:Count")),
            WOQL.eval(WOQL.plus("v:Count", 1), "v:NewCount"),
            WOQL.delete_triple("v:Event", "ont:retry_count", "v:Count"),
            WOQL.add_triple("v:Event", "ont:retry_count", "v:NewCount"),
            WOQL.add_triple("v:Event", "ont:last_error", $error),
            WOQL.add_triple("v:Event", "ont:last_attempt", WOQL.datetime())
        )
        """

        await self.tdb.update(
            retry_query,
            branch="_outbox",
            bindings={
                "event_id": event_id,
                "error": error
            }
        )
