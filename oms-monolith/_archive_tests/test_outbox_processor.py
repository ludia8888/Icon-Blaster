#!/usr/bin/env python3
"""
Outbox Processor 실행 테스트
이벤트 발행이 실제로 작동하는지 확인
"""
import asyncio
import sys
import os

sys.path.append('/Users/sihyun/Desktop/ARRAKIS/SPICE/oms-monolith')

from database.simple_terminus_client import SimpleTerminusDBClient
from core.event_publisher.outbox_processor import OutboxProcessor
from shared.infrastructure.nats_client import NATSClient
from shared.infrastructure.metrics import MetricsCollector

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class MockTerminusDBClient:
    """TerminusDB 클라이언트 Mock"""
    def __init__(self):
        self.client = None
        
    async def connect(self):
        # SimpleTerminusDBClient 사용
        self.simple_client = SimpleTerminusDBClient(
            endpoint="http://localhost:6363",
            username="admin",
            password="root",
            database="oms"
        )
        await self.simple_client.connect()
        return True
        
    async def query(self, query, branch=None, bindings=None):
        """Outbox 이벤트 조회 Mock"""
        logger.info(f"Query called on branch: {branch}")
        
        # Outbox 이벤트 생성 (테스트용)
        if branch == "_outbox":
            # 테스트 이벤트 반환
            return [{
                "id": "test-event-1",
                "type": "schema.changed",
                "payload": '{"branch": "main", "resource_type": "object_type", "resource_id": "Customer", "operation": "update"}',
                "created_at": "2025-06-26T09:00:00Z"
            }]
        return []
        
    async def update(self, query, branch=None, bindings=None):
        """이벤트 상태 업데이트 Mock"""
        logger.info(f"Update called - marking event as published")
        return True


class MockNATSClient:
    """NATS 클라이언트 Mock"""
    def __init__(self):
        self.published_events = []
        
    async def connect(self):
        logger.info("Mock NATS connected")
        return True
        
    async def publish(self, subject, payload, headers=None):
        """이벤트 발행"""
        logger.info(f"📤 Publishing to NATS: {subject}")
        logger.info(f"   Payload size: {len(payload)} bytes")
        logger.info(f"   Headers: {headers}")
        
        self.published_events.append({
            "subject": subject,
            "payload": payload,
            "headers": headers
        })
        
        return True
        
    async def disconnect(self):
        logger.info("Mock NATS disconnected")


class MockMetricsCollector:
    """메트릭 수집기 Mock"""
    def record_events_processed(self, count):
        logger.info(f"📊 Metrics: {count} events processed")
        
    def record_processing_error(self):
        logger.error("📊 Metrics: Processing error recorded")
        
    def record_event_latency(self, event_type, latency):
        logger.info(f"📊 Metrics: {event_type} latency: {latency}s")


async def test_outbox_processing():
    """Outbox 처리 테스트"""
    logger.info("🚀 Outbox Processor 테스트 시작")
    
    # Mock 객체들 생성
    tdb_client = MockTerminusDBClient()
    await tdb_client.connect()
    
    nats_client = MockNATSClient()
    await nats_client.connect()
    
    metrics = MockMetricsCollector()
    
    # Outbox Processor 생성
    processor = OutboxProcessor(
        tdb_client=tdb_client,
        nats_client=nats_client,
        metrics=metrics,
        enable_multi_platform=False  # 단순 NATS만 사용
    )
    
    logger.info("✅ Outbox Processor 초기화 완료")
    
    # 한 번만 배치 처리 실행
    logger.info("\n📦 배치 처리 시작...")
    processed = await processor._process_batch()
    
    logger.info(f"\n✅ 처리 완료: {processed}개 이벤트")
    
    # 발행된 이벤트 확인
    if nats_client.published_events:
        logger.info(f"\n📨 발행된 이벤트: {len(nats_client.published_events)}개")
        for i, event in enumerate(nats_client.published_events):
            logger.info(f"\nEvent {i+1}:")
            logger.info(f"  Subject: {event['subject']}")
            logger.info(f"  Headers: {event['headers']}")
            
    # 실제 NATS 연결 테스트
    logger.info("\n🔄 실제 NATS 연결 테스트...")
    try:
        import nats
        nc = await nats.connect("nats://localhost:4222")
        logger.info("✅ 실제 NATS 서버 연결 성공!")
        
        # 테스트 메시지 발행
        test_subject = "oms.test.connection"
        test_payload = b'{"test": true}'
        await nc.publish(test_subject, test_payload)
        logger.info(f"✅ 테스트 메시지 발행 성공: {test_subject}")
        
        await nc.close()
        
    except Exception as e:
        logger.error(f"❌ NATS 연결 실패: {e}")


async def main():
    """메인 실행"""
    await test_outbox_processing()


if __name__ == "__main__":
    asyncio.run(main())