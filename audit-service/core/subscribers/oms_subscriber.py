"""
OMS Event Subscriber
OMS에서 발행되는 이벤트를 구독하고 Audit Service로 처리
"""
import asyncio
import json
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from utils.logger import get_logger, log_operation_start, log_operation_end
from .event_processor import EventProcessor


logger = get_logger(__name__)


class OMSEventSubscriber:
    """
    OMS 이벤트 구독자
    OMS HistoryEventPublisher에서 발행되는 이벤트를 구독
    """
    
    def __init__(self):
        self.event_processor = EventProcessor()
        self.is_running = False
        self.subscriber_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """이벤트 구독 시작"""
        if self.is_running:
            logger.warning("OMS event subscriber is already running")
            return
            
        log_operation_start(logger, "oms_event_subscription")
        
        try:
            # 이벤트 브로커 연결
            await self._connect_to_event_broker()
            
            # 구독 작업 시작
            self.subscriber_task = asyncio.create_task(self._subscribe_loop())
            self.is_running = True
            
            log_operation_end(logger, "oms_event_subscription", success=True)
            logger.info("OMS event subscriber started successfully")
            
        except Exception as e:
            log_operation_end(logger, "oms_event_subscription", success=False, error=str(e))
            logger.error(f"Failed to start OMS event subscriber: {str(e)}")
            raise
    
    async def stop(self):
        """이벤트 구독 중지"""
        if not self.is_running:
            return
            
        logger.info("Stopping OMS event subscriber...")
        
        self.is_running = False
        
        if self.subscriber_task:
            self.subscriber_task.cancel()
            try:
                await self.subscriber_task
            except asyncio.CancelledError:
                pass
        
        await self._disconnect_from_event_broker()
        
        logger.info("OMS event subscriber stopped")
    
    async def _connect_to_event_broker(self):
        """이벤트 브로커 연결"""
        # TODO: 실제 이벤트 브로커 (NATS, Kafka 등) 연결
        logger.info("Connecting to event broker...")
        
        # 실제 구현에서는 여기서 NATS/Kafka 클라이언트 초기화
        # 예시:
        # import nats
        # self.nc = await nats.connect("nats://localhost:4222")
        # self.js = self.nc.jetstream()
        
        await asyncio.sleep(0.1)  # 더미 연결 지연
        logger.info("Connected to event broker")
    
    async def _disconnect_from_event_broker(self):
        """이벤트 브로커 연결 해제"""
        logger.info("Disconnecting from event broker...")
        
        # 실제 구현에서는 여기서 연결 정리
        # if hasattr(self, 'nc'):
        #     await self.nc.close()
        
        await asyncio.sleep(0.1)  # 더미 해제 지연
        logger.info("Disconnected from event broker")
    
    async def _subscribe_loop(self):
        """이벤트 구독 루프"""
        logger.info("Starting event subscription loop")
        
        try:
            while self.is_running:
                try:
                    # 실제 구현에서는 이벤트 브로커에서 메시지 수신
                    # 현재는 더미 이벤트 생성
                    await self._process_dummy_events()
                    
                    # 실제 NATS 구현 예시:
                    # async for msg in self.js.subscribe("oms.schema.*"):
                    #     await self._handle_message(msg)
                    
                    await asyncio.sleep(1)  # 더미 지연
                    
                except Exception as e:
                    logger.error(f"Error in subscription loop: {str(e)}")
                    await asyncio.sleep(5)  # 에러 시 잠시 대기
                    
        except asyncio.CancelledError:
            logger.info("Subscription loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Subscription loop failed: {str(e)}")
            raise
    
    async def _process_dummy_events(self):
        """더미 이벤트 처리 (개발/테스트용)"""
        # 실제 환경에서는 이 메서드 제거
        
        # 더미 스키마 변경 이벤트
        schema_event = {
            "specversion": "1.0",
            "type": "com.oms.schema.changed",
            "source": "oms.history",
            "id": f"audit_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "time": datetime.now(timezone.utc).isoformat(),
            "datacontenttype": "application/json",
            "data": {
                "operation": "update",
                "resource_type": "objectType",
                "resource_id": "Product",
                "resource_name": "Product Object Type",
                "branch": "main",
                "commit_hash": "abc123def456",
                "author": "user123",
                "changes": [
                    {
                        "field": "description",
                        "operation": "update",
                        "old_value": "Old description",
                        "new_value": "New description",
                        "path": "object_types.Product.description",
                        "breaking_change": False
                    }
                ]
            }
        }
        
        # 이벤트 처리
        await self._handle_event(schema_event)
    
    async def _handle_message(self, message):
        """메시지 처리 (실제 브로커용)"""
        try:
            # 메시지 데이터 파싱
            data = json.loads(message.data.decode())
            
            # CloudEvents 형식 검증
            if not self._is_valid_cloudevent(data):
                logger.warning(f"Invalid CloudEvent format: {data}")
                return
            
            # 이벤트 처리
            await self._handle_event(data)
            
            # 메시지 ACK (NATS 예시)
            # await message.ack()
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message JSON: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to handle message: {str(e)}")
    
    async def _handle_event(self, event: Dict[str, Any]):
        """이벤트 처리"""
        event_type = event.get("type")
        event_id = event.get("id")
        
        logger.info(f"Processing event: {event_type} ({event_id})")
        
        try:
            # 이벤트 타입별 처리
            if event_type == "com.oms.schema.changed":
                await self._handle_schema_changed_event(event)
            elif event_type == "com.oms.schema.reverted":
                await self._handle_schema_reverted_event(event)
            elif event_type == "com.oms.audit.event":
                await self._handle_audit_event(event)
            else:
                logger.warning(f"Unknown event type: {event_type}")
                return
            
            # 이벤트 처리 성공 로그
            logger.info(f"Successfully processed event: {event_id}")
            
        except Exception as e:
            logger.error(f"Failed to process event {event_id}: {str(e)}")
            # 실제 구현에서는 DLQ(Dead Letter Queue)로 전송
            await self._send_to_dlq(event, str(e))
    
    async def _handle_schema_changed_event(self, event: Dict[str, Any]):
        """스키마 변경 이벤트 처리"""
        data = event.get("data", {})
        
        # 히스토리 엔트리 생성
        await self.event_processor.create_history_entry(event)
        
        # 감사 로그 생성
        await self.event_processor.create_audit_log(event)
        
        # SIEM 전송
        await self.event_processor.send_to_siem(event)
        
        logger.info(f"Schema change event processed: {data.get('resource_id')}")
    
    async def _handle_schema_reverted_event(self, event: Dict[str, Any]):
        """스키마 복원 이벤트 처리"""
        data = event.get("data", {})
        
        # 복원 히스토리 엔트리 생성
        await self.event_processor.create_revert_history_entry(event)
        
        # 감사 로그 생성
        await self.event_processor.create_audit_log(event)
        
        # SIEM 전송
        await self.event_processor.send_to_siem(event)
        
        logger.info(f"Schema revert event processed: {data.get('reverted_to')}")
    
    async def _handle_audit_event(self, event: Dict[str, Any]):
        """감사 이벤트 처리"""
        data = event.get("data", {})
        
        # 감사 로그 생성
        await self.event_processor.create_audit_log(event)
        
        # SIEM 전송
        await self.event_processor.send_to_siem(event)
        
        logger.info(f"Audit event processed: {data.get('event_type')}")
    
    def _is_valid_cloudevent(self, data: Dict[str, Any]) -> bool:
        """CloudEvents 형식 검증"""
        required_fields = ["specversion", "type", "source", "id"]
        return all(field in data for field in required_fields)
    
    async def _send_to_dlq(self, event: Dict[str, Any], error: str):
        """실패한 이벤트를 DLQ로 전송"""
        dlq_event = {
            "original_event": event,
            "error": error,
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "retry_count": 0
        }
        
        logger.error(f"Sending event to DLQ: {event.get('id')}")
        
        # TODO: 실제 DLQ 구현
        # await self.dlq_publisher.publish(dlq_event)


# 전역 구독자 인스턴스
_oms_subscriber: Optional[OMSEventSubscriber] = None


async def start_oms_subscriber():
    """OMS 이벤트 구독자 시작"""
    global _oms_subscriber
    
    if _oms_subscriber is None:
        _oms_subscriber = OMSEventSubscriber()
    
    await _oms_subscriber.start()


async def stop_oms_subscriber():
    """OMS 이벤트 구독자 중지"""
    global _oms_subscriber
    
    if _oms_subscriber:
        await _oms_subscriber.stop()


def get_oms_subscriber() -> Optional[OMSEventSubscriber]:
    """OMS 이벤트 구독자 인스턴스 반환"""
    return _oms_subscriber