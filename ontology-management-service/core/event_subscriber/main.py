"""
Event Subscriber Service - NATS 이벤트 구독 및 처리
섹션 10.3의 Event Schemas 구현
"""
import asyncio
import logging
import os
import signal
import sys
from typing import Any, Dict

# shared 모듈 import를 위한 경로 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from shared.events import cleanup_nats, get_nats_client
from core.event_consumer.funnel_indexing_handler import get_funnel_indexing_handler

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EventSubscriber:
    """이벤트 구독자"""

    def __init__(self):
        self.running = False
        self.nats_client = None
        self.funnel_handler = get_funnel_indexing_handler()

    async def start(self):
        """구독자 시작"""
        logger.info("Event Subscriber starting...")

        # NATS 클라이언트 초기화
        self.nats_client = await get_nats_client()
        self.running = True

        # 이벤트 구독 설정
        await self._setup_subscriptions()

        logger.info("Event Subscriber started successfully")

    async def stop(self):
        """구독자 우아한 중지"""
        logger.info("Event Subscriber stopping gracefully...")

        try:
            # 1. 새로운 이벤트 처리 중단
            logger.info("Stopping new event processing...")
            self.running = False

            # 2. 진행 중인 이벤트 처리 완료 대기
            logger.info("Waiting for current events to finish processing...")
            await asyncio.sleep(2)  # 진행 중인 이벤트 처리를 위한 대기

            # 3. NATS 연결 정리
            logger.info("Cleaning up NATS connections...")
            await cleanup_nats()

            logger.info("Event Subscriber stopped gracefully")
        except Exception as e:
            logger.error(f"Error during graceful shutdown: {e}")
            raise

    async def _setup_subscriptions(self):
        """이벤트 구독 설정"""

        # 스키마 변경 이벤트 구독
        await self.nats_client.subscribe(
            "oms.schema.changed.>",
            self._handle_schema_changed,
            durable_name="schema-audit-consumer",
            queue_group="schema-consumers"
        )

        # 브랜치 이벤트 구독
        await self.nats_client.subscribe(
            "oms.branch.created",
            self._handle_branch_created,
            durable_name="branch-audit-consumer",
            queue_group="branch-consumers"
        )

        await self.nats_client.subscribe(
            "oms.branch.merged.>",
            self._handle_branch_merged,
            durable_name="merge-audit-consumer",
            queue_group="merge-consumers"
        )

        # 제안 이벤트 구독
        await self.nats_client.subscribe(
            "oms.proposal.>",
            self._handle_proposal_status_changed,
            durable_name="proposal-audit-consumer",
            queue_group="proposal-consumers"
        )

        # 액션 이벤트 구독
        await self.nats_client.subscribe(
            "oms.action.started",
            self._handle_action_started,
            durable_name="action-started-consumer",
            queue_group="action-consumers"
        )

        await self.nats_client.subscribe(
            "oms.action.completed",
            self._handle_action_completed,
            durable_name="action-completed-consumer",
            queue_group="action-consumers"
        )

        await self.nats_client.subscribe(
            "oms.action.failed",
            self._handle_action_failed,
            durable_name="action-failed-consumer",
            queue_group="action-consumers"
        )

        # 검증 이벤트 구독
        await self.nats_client.subscribe(
            "oms.validation.completed",
            self._handle_validation_completed,
            durable_name="validation-audit-consumer",
            queue_group="validation-consumers"
        )

        # Funnel Service 인덱싱 이벤트 구독
        await self.nats_client.subscribe(
            "funnel.indexing.completed",
            self._handle_funnel_indexing_completed,
            durable_name="funnel-indexing-consumer",
            queue_group="indexing-consumers"
        )

        await self.nats_client.subscribe(
            "funnel.indexing.failed",
            self._handle_funnel_indexing_completed,  # Same handler for both
            durable_name="funnel-indexing-failed-consumer",
            queue_group="indexing-consumers"
        )

        logger.info("All event subscriptions configured")

    async def _handle_schema_changed(self, event_data: Dict[str, Any]):
        """스키마 변경 이벤트 처리"""
        try:
            logger.info(f"Schema changed event received: {event_data}")

            # 감사 로그 저장
            await self._save_audit_log("schema_changed", event_data)

            # 캐시 무효화 알림 (필요시)
            await self._invalidate_cache(event_data)

            # 외부 시스템 알림 (필요시)
            await self._notify_external_systems("schema_changed", event_data)

        except Exception as e:
            logger.error(f"Error handling schema changed event: {e}")

    async def _handle_branch_created(self, event_data: Dict[str, Any]):
        """브랜치 생성 이벤트 처리"""
        try:
            logger.info(f"Branch created event received: {event_data}")

            # 감사 로그 저장
            await self._save_audit_log("branch_created", event_data)

            # 브랜치 보호 규칙 설정 (필요시)
            await self._setup_branch_protection(event_data)

        except Exception as e:
            logger.error(f"Error handling branch created event: {e}")

    async def _handle_branch_merged(self, event_data: Dict[str, Any]):
        """브랜치 병합 이벤트 처리"""
        try:
            logger.info(f"Branch merged event received: {event_data}")

            # 감사 로그 저장
            await self._save_audit_log("branch_merged", event_data)

            # 배포 트리거 (필요시)
            await self._trigger_deployment(event_data)

        except Exception as e:
            logger.error(f"Error handling branch merged event: {e}")

    async def _handle_proposal_status_changed(self, event_data: Dict[str, Any]):
        """제안 상태 변경 이벤트 처리"""
        try:
            logger.info(f"Proposal status changed event received: {event_data}")

            # 감사 로그 저장
            await self._save_audit_log("proposal_status_changed", event_data)

            # 알림 발송 (필요시)
            await self._send_notifications(event_data)

        except Exception as e:
            logger.error(f"Error handling proposal status changed event: {e}")

    async def _handle_action_started(self, event_data: Dict[str, Any]):
        """액션 시작 이벤트 처리"""
        try:
            logger.info(f"Action started event received: {event_data}")

            # 액션 상태 추적 시작
            await self._track_action_execution(event_data)

        except Exception as e:
            logger.error(f"Error handling action started event: {e}")

    async def _handle_action_completed(self, event_data: Dict[str, Any]):
        """액션 완료 이벤트 처리"""
        try:
            logger.info(f"Action completed event received: {event_data}")

            # 성공 메트릭 업데이트
            await self._update_action_metrics("completed", event_data)

        except Exception as e:
            logger.error(f"Error handling action completed event: {e}")

    async def _handle_action_failed(self, event_data: Dict[str, Any]):
        """액션 실패 이벤트 처리"""
        try:
            logger.error(f"Action failed event received: {event_data}")

            # 실패 메트릭 업데이트
            await self._update_action_metrics("failed", event_data)

            # 알람 발송 (중요한 액션의 경우)
            await self._send_failure_alert(event_data)

        except Exception as e:
            logger.error(f"Error handling action failed event: {e}")

    async def _handle_validation_completed(self, event_data: Dict[str, Any]):
        """검증 완료 이벤트 처리"""
        try:
            logger.info(f"Validation completed event received: {event_data}")

            # 검증 결과 통계 업데이트
            await self._update_validation_stats(event_data)

        except Exception as e:
            logger.error(f"Error handling validation completed event: {e}")

    async def _save_audit_log(self, event_type: str, event_data: Dict[str, Any]):
        """감사 로그 저장"""
        # TODO: 실제 감사 로그 저장소에 저장
        logger.debug(f"Saving audit log for {event_type}: {event_data}")

    async def _invalidate_cache(self, event_data: Dict[str, Any]):
        """캐시 무효화"""
        # TODO: 관련 캐시 무효화 로직
        logger.debug(f"Invalidating cache for: {event_data}")

    async def _notify_external_systems(self, event_type: str, event_data: Dict[str, Any]):
        """외부 시스템 알림"""
        # TODO: 외부 시스템 웹훅 호출
        logger.debug(f"Notifying external systems about {event_type}: {event_data}")

    async def _setup_branch_protection(self, event_data: Dict[str, Any]):
        """브랜치 보호 규칙 설정"""
        # TODO: 브랜치 보호 규칙 자동 설정
        logger.debug(f"Setting up branch protection: {event_data}")

    async def _trigger_deployment(self, event_data: Dict[str, Any]):
        """배포 트리거"""
        # TODO: CI/CD 파이프라인 트리거
        logger.debug(f"Triggering deployment: {event_data}")

    async def _send_notifications(self, event_data: Dict[str, Any]):
        """알림 발송"""
        # TODO: 이메일/슬랙 알림 발송
        logger.debug(f"Sending notifications: {event_data}")

    async def _track_action_execution(self, event_data: Dict[str, Any]):
        """액션 실행 추적"""
        # TODO: 액션 실행 상태 추적
        logger.debug(f"Tracking action execution: {event_data}")

    async def _update_action_metrics(self, status: str, event_data: Dict[str, Any]):
        """액션 메트릭 업데이트"""
        # TODO: 메트릭 저장소에 업데이트
        logger.debug(f"Updating action metrics ({status}): {event_data}")

    async def _send_failure_alert(self, event_data: Dict[str, Any]):
        """실패 알람 발송"""
        # TODO: 중요한 액션 실패시 즉시 알람
        logger.warning(f"Sending failure alert: {event_data}")

    async def _update_validation_stats(self, event_data: Dict[str, Any]):
        """검증 통계 업데이트"""
        # TODO: 검증 통계 업데이트
        logger.debug(f"Updating validation stats: {event_data}")

    async def _handle_funnel_indexing_completed(self, event_data: Dict[str, Any]):
        """Funnel Service 인덱싱 완료/실패 이벤트 처리"""
        try:
            logger.info(f"Funnel indexing event received: {event_data}")
            
            # Delegate to specialized handler
            success = await self.funnel_handler.handle_indexing_completed(event_data)
            
            if success:
                logger.info(f"Successfully processed indexing event: {event_data.get('id')}")
            else:
                logger.error(f"Failed to process indexing event: {event_data.get('id')}")
            
        except Exception as e:
            logger.error(f"Error handling funnel indexing event: {e}")
            # Don't re-raise - we don't want to break the entire event processing


async def main():
    """메인 실행 함수"""
    subscriber = EventSubscriber()

    # 시그널 핸들러 설정
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        asyncio.create_task(subscriber.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await subscriber.start()

        # 무한 대기
        while subscriber.running:
            await asyncio.sleep(1)

    except Exception as e:
        logger.error(f"Event Subscriber error: {e}")
    finally:
        await subscriber.stop()


if __name__ == "__main__":
    asyncio.run(main())
