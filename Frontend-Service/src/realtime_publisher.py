"""
Frontend Service - Real-time Event Publisher
OMS 이벤트를 구독하여 UI에 실시간 업데이트 제공
"""
import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import nats
from nats.js import JetStreamContext

from .websocket_manager import frontend_websocket_manager

logger = logging.getLogger(__name__)


class FrontendRealtimePublisher:
    """
    Frontend Service Real-time 이벤트 발행자
    
    OMS 이벤트를 구독하여 WebSocket으로 UI에 실시간 업데이트
    - 스키마 변경 사항을 대시보드에 반영
    - 브랜치 상태를 실시간으로 업데이트
    - 사용자 알림 및 진행 상황 표시
    """

    def __init__(self, nats_url: str = "nats://nats:4222"):
        self.nats_url = nats_url
        self.nc: Optional[nats.NATS] = None
        self.js: Optional[JetStreamContext] = None

        # Frontend 전용 구독 관리
        self.frontend_subscriptions: Dict[str, Set[str]] = {
            "ui_schema_updates": set(),
            "ui_branch_updates": set(),
            "ui_notifications": set(),
            "ui_progress_updates": set()
        }

        # OMS 이벤트 구독 설정
        self.oms_subscriptions = {
            "schema_changes": {
                "stream": "OMS_SCHEMA_EVENTS",
                "subject": "oms.schema.*",
                "consumer": "frontend_schema_consumer"
            },
            "branch_changes": {
                "stream": "OMS_BRANCH_EVENTS", 
                "subject": "oms.branch.*",
                "consumer": "frontend_branch_consumer"
            },
            "audit_events": {
                "stream": "OMS_AUDIT_EVENTS",
                "subject": "oms.audit.*", 
                "consumer": "frontend_audit_consumer"
            }
        }

    async def connect(self):
        """NATS 연결 및 OMS 이벤트 구독 시작"""
        try:
            self.nc = await nats.connect(self.nats_url)
            self.js = self.nc.jetstream()

            logger.info(f"Frontend Service connected to NATS at {self.nats_url}")

            # OMS 이벤트 구독 시작
            await self._subscribe_to_oms_events()

        except Exception as e:
            logger.error(f"Failed to connect to NATS: {e}")
            raise

    async def disconnect(self):
        """NATS 연결 해제"""
        if self.nc:
            await self.nc.close()
            logger.info("Frontend Service disconnected from NATS")

    @asynccontextmanager
    async def connection(self):
        """연결 컨텍스트 매니저"""
        await self.connect()
        try:
            yield self
        finally:
            await self.disconnect()

    async def _subscribe_to_oms_events(self):
        """OMS 이벤트 구독 설정"""
        for event_type, config in self.oms_subscriptions.items():
            try:
                handler = getattr(self, f"_handle_{event_type}")
                
                # 컨슈머 생성
                await self._create_frontend_consumer(
                    config["stream"],
                    config["consumer"], 
                    config["subject"]
                )
                
                # 구독 시작
                await self._start_subscription(
                    config["stream"],
                    config["consumer"],
                    config["subject"],
                    handler
                )
                
                logger.info(f"Frontend subscribed to OMS {event_type}")
                
            except Exception as e:
                logger.error(f"Failed to subscribe to OMS {event_type}: {e}")

    async def _handle_schema_changes(self, event: Dict[str, Any]):
        """OMS 스키마 변경 이벤트 처리"""
        try:
            # UI 친화적 형식으로 변환
            ui_event = {
                "id": event.get("event_id"),
                "type": "schema_change",
                "operation": event.get("event_type"),
                "resource": {
                    "type": event.get("resource_type"),
                    "id": event.get("resource_id"),
                    "name": event.get("resource_name")
                },
                "branch": event.get("branch"),
                "user": event.get("user_id"),
                "timestamp": event.get("timestamp"),
                "changes": event.get("changes", {}),
                "ui_message": self._generate_ui_message(event)
            }

            # WebSocket을 통해 UI에 브로드캐스트
            await frontend_websocket_manager.broadcast_schema_change(ui_event)
            
            # 중요한 변경사항인 경우 알림 전송
            if self._is_critical_change(event):
                await self._send_critical_change_notification(ui_event)

            logger.info(f"Processed schema change for UI: {event.get('resource_type')} {event.get('resource_id')}")

        except Exception as e:
            logger.error(f"Error handling schema change event: {e}")

    async def _handle_branch_changes(self, event: Dict[str, Any]):
        """OMS 브랜치 변경 이벤트 처리"""
        try:
            # UI 친화적 형식으로 변환
            ui_event = {
                "id": event.get("event_id"),
                "type": "branch_change",
                "operation": event.get("event_type"),
                "branch": event.get("branch_name"),
                "commit": {
                    "hash": event.get("commit_hash"),
                    "message": event.get("commit_message"),
                    "author": event.get("author")
                },
                "timestamp": event.get("timestamp"),
                "affected_resources": event.get("affected_resources", []),
                "ui_message": self._generate_branch_ui_message(event)
            }

            # WebSocket을 통해 UI에 브로드캐스트
            await frontend_websocket_manager.broadcast_branch_update(ui_event)

            logger.info(f"Processed branch change for UI: {event.get('event_type')} {event.get('branch_name')}")

        except Exception as e:
            logger.error(f"Error handling branch change event: {e}")

    async def _handle_audit_events(self, event: Dict[str, Any]):
        """OMS 감사 이벤트 처리"""
        try:
            # 보안 관련 이벤트만 UI에 표시
            if self._is_security_relevant(event):
                ui_notification = {
                    "id": event.get("event_id"),
                    "type": "security_alert",
                    "title": "Security Event Detected",
                    "message": f"Security event: {event.get('operation')} on {event.get('resource_type')}",
                    "severity": self._get_severity_level(event),
                    "timestamp": event.get("timestamp"),
                    "details": {
                        "operation": event.get("operation"),
                        "resource": event.get("resource_type"),
                        "user": event.get("author")
                    }
                }

                # 보안 관리자에게 알림 전송
                await self._send_security_notification(ui_notification)

            logger.debug(f"Processed audit event: {event.get('event_type')}")

        except Exception as e:
            logger.error(f"Error handling audit event: {e}")

    def _generate_ui_message(self, event: Dict[str, Any]) -> str:
        """UI용 메시지 생성"""
        operation = event.get("event_type", "updated")
        resource_type = event.get("resource_type", "resource")
        resource_name = event.get("resource_name", "unknown")
        user = event.get("user_id", "unknown user")

        return f"{user} {operation} {resource_type} '{resource_name}'"

    def _generate_branch_ui_message(self, event: Dict[str, Any]) -> str:
        """브랜치 UI용 메시지 생성"""
        operation = event.get("event_type", "updated")
        branch = event.get("branch_name", "unknown")
        author = event.get("author", "unknown user")

        return f"{author} {operation} branch '{branch}'"

    def _is_critical_change(self, event: Dict[str, Any]) -> bool:
        """중요한 변경사항 여부 판단"""
        critical_operations = ["delete", "deprecated", "breaking_change"]
        return event.get("event_type") in critical_operations

    def _is_security_relevant(self, event: Dict[str, Any]) -> bool:
        """보안 관련 이벤트 여부 판단"""
        security_operations = ["unauthorized_access", "permission_denied", "suspicious_activity"]
        return event.get("operation") in security_operations

    def _get_severity_level(self, event: Dict[str, Any]) -> str:
        """이벤트 심각도 레벨 결정"""
        operation = event.get("operation", "")
        if "critical" in operation or "unauthorized" in operation:
            return "critical"
        elif "warning" in operation or "suspicious" in operation:
            return "warning"
        else:
            return "info"

    async def _send_critical_change_notification(self, ui_event: Dict[str, Any]):
        """중요한 변경사항 알림 전송"""
        notification = {
            "id": str(uuid.uuid4()),
            "type": "critical_change",
            "title": "Critical Schema Change",
            "message": f"Critical change detected: {ui_event['ui_message']}",
            "severity": "warning",
            "timestamp": datetime.utcnow().isoformat(),
            "action_required": True,
            "details": ui_event
        }

        # 관리자들에게 알림 전송 (역할 기반)
        # TODO: 사용자 역할 서비스와 연동
        await frontend_websocket_manager.broadcast_to_subscription("admin_notifications", {
            "type": "notification",
            "notification": notification
        })

    async def _send_security_notification(self, notification: Dict[str, Any]):
        """보안 알림 전송"""
        # 보안 관리자들에게 알림 전송
        await frontend_websocket_manager.broadcast_to_subscription("security_notifications", {
            "type": "security_notification", 
            "notification": notification
        })

    async def _create_frontend_consumer(self, stream: str, consumer: str, subject: str):
        """Frontend 전용 컨슈머 생성"""
        try:
            consumer_config = {
                "durable_name": consumer,
                "filter_subject": subject,
                "deliver_policy": "new",  # 새 메시지부터
                "ack_policy": "explicit",
                "replay_policy": "instant",
                "max_deliver": 3,  # 최대 3번 재시도
                "ack_wait": 30  # 30초 ACK 대기
            }

            await self.js.add_consumer(stream, **consumer_config)
            logger.info(f"Created frontend consumer {consumer} for stream {stream}")

        except Exception as e:
            # 이미 존재하는 컨슈머는 무시
            if "already exists" not in str(e):
                logger.error(f"Failed to create consumer {consumer}: {e}")
                raise

    async def _start_subscription(self, stream: str, consumer: str, subject: str, handler):
        """구독 시작"""
        try:
            # Pull 기반 구독 생성
            psub = await self.js.pull_subscribe(
                subject,
                consumer=consumer,
                stream=stream
            )

            # 백그라운드에서 메시지 처리
            async def message_processor():
                while True:
                    try:
                        # 배치로 메시지 가져오기 (성능 최적화)
                        msgs = await psub.fetch(10, timeout=5.0)
                        
                        for msg in msgs:
                            try:
                                event_data = json.loads(msg.data.decode())
                                await handler(event_data)
                                await msg.ack()
                            except Exception as e:
                                logger.error(f"Error processing message: {e}")
                                await msg.nak()
                                
                    except TimeoutError:
                        continue  # 타임아웃은 정상
                    except Exception as e:
                        logger.error(f"Error in message processor for {consumer}: {e}")
                        await asyncio.sleep(5)

            # 백그라운드 태스크 시작
            asyncio.create_task(message_processor())
            logger.info(f"Started message processor for {consumer}")

        except Exception as e:
            logger.error(f"Failed to start subscription for {consumer}: {e}")
            raise

    def get_subscription_stats(self) -> Dict[str, Any]:
        """구독 통계 반환"""
        return {
            "frontend_subscriptions": {
                name: len(subs) for name, subs in self.frontend_subscriptions.items()
            },
            "oms_subscriptions": list(self.oms_subscriptions.keys()),
            "websocket_stats": frontend_websocket_manager.get_statistics()
        }


# Global Frontend realtime publisher instance
frontend_realtime_publisher = FrontendRealtimePublisher()