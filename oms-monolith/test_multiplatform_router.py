#!/usr/bin/env python3
"""
Multi-Platform Event Router 테스트 스크립트
"""
import asyncio
import json
import os
import sys
from datetime import datetime, timezone

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.event_publisher.cloudevents_enhanced import (
    EnhancedCloudEvent, EventType, CloudEventBuilder
)
from core.event_publisher.eventbridge_publisher import EventBridgeConfig
from core.event_publisher.multi_platform_router import (
    MultiPlatformEventRouter, Platform, RoutingRule, RoutingStrategy
)


class MockNATSPublisher:
    """Mock NATS Publisher for testing"""
    
    def __init__(self):
        self.published_events = []
    
    async def publish(self, subject: str, payload: bytes, headers: dict):
        """Mock publish method"""
        self.published_events.append({
            'subject': subject,
            'payload': payload.decode() if isinstance(payload, bytes) else payload,
            'headers': headers,
            'timestamp': datetime.now(timezone.utc)
        })
        print(f"📨 NATS: Published to {subject}")


async def test_basic_multi_platform_routing():
    """기본 Multi-Platform 라우팅 테스트"""
    print("=== Basic Multi-Platform Routing Test ===\n")
    
    # 1. Mock NATS Publisher 생성
    nats_publisher = MockNATSPublisher()
    
    # 2. EventBridge Config 생성 (LocalStack 사용)
    eventbridge_config = EventBridgeConfig(
        event_bus_name="test-oms-events",
        aws_region="us-east-1",
        endpoint_url="http://localhost:4566",  # LocalStack endpoint
        aws_access_key_id="test",
        aws_secret_access_key="test"
    )
    
    # 3. Multi-Platform Router 생성
    router = MultiPlatformEventRouter()
    
    # 4. 플랫폼 등록
    router.register_nats_platform(nats_publisher, is_primary=True)
    
    try:
        router.register_eventbridge_platform(eventbridge_config, is_primary=False)
        print("✅ EventBridge platform registered successfully")
    except Exception as e:
        print(f"⚠️  EventBridge registration failed (expected in test environment): {e}")
        # EventBridge 없이 계속 진행
    
    # 5. 기본 라우팅 규칙 추가
    router.add_default_oms_routing_rules()
    
    # 6. 테스트 이벤트들 생성
    test_events = [
        # Schema 변경 이벤트 (모든 플랫폼)
        CloudEventBuilder(EventType.SCHEMA_UPDATED, "/oms/main")
        .with_subject("object_type/User")
        .with_data({"operation": "update", "resource_id": "User"})
        .with_oms_context("main", "abc123", "developer@company.com")
        .build(),
        
        # Branch 이벤트 (NATS 우선, EventBridge 백업)
        CloudEventBuilder(EventType.BRANCH_CREATED, "/oms/feature")
        .with_subject("branch/feature-xyz")
        .with_data({"branch_name": "feature-xyz", "author": "developer@company.com"})
        .build(),
        
        # Action 이벤트 (NATS만)
        CloudEventBuilder(EventType.ACTION_STARTED, "/oms/actions")
        .with_subject("job/validate-123")
        .with_data({"job_id": "validate-123", "action_type": "validation"})
        .build(),
        
        # System 이벤트 (EventBridge로)
        CloudEventBuilder(EventType.SYSTEM_HEALTH_CHECK, "/oms/system")
        .with_subject("component/database")
        .with_data({"component": "database", "status": "healthy"})
        .build()
    ]
    
    # 7. 이벤트 발행 테스트
    print("📡 Publishing test events...\n")
    
    for i, event in enumerate(test_events, 1):
        print(f"Event {i}: {event.type}")
        results = await router.publish_event(event)
        
        # results는 {event_id: {platform: result}} 형태일 수 있음
        if isinstance(results, dict) and event.id in results:
            platform_results = results[event.id]
        else:
            platform_results = results
        
        for platform, result in platform_results.items():
            status = "✅ SUCCESS" if result.success else "❌ FAILED"
            print(f"  {platform.value}: {status}")
            if hasattr(result, 'error') and result.error:
                print(f"    Error: {result.error}")
        print()
    
    # 8. NATS 발행 결과 확인
    print(f"📊 NATS Published Events: {len(nats_publisher.published_events)}")
    for event in nats_publisher.published_events:
        print(f"  Subject: {event['subject']}")
        print(f"  Headers: {event['headers'].get('ce-type', 'unknown')}")
    print()
    
    # 9. 플랫폼 상태 확인
    status = router.get_platform_status()
    print("🔍 Platform Status:")
    print(json.dumps(status, indent=2, default=str))
    
    await router.shutdown()
    print("\n✅ Multi-Platform Router test completed!")


async def test_custom_routing_rules():
    """커스텀 라우팅 규칙 테스트"""
    print("\n=== Custom Routing Rules Test ===\n")
    
    router = MultiPlatformEventRouter()
    nats_publisher = MockNATSPublisher()
    
    # NATS만 등록
    router.register_nats_platform(nats_publisher, is_primary=True)
    
    # 커스텀 라우팅 규칙 추가
    router.add_routing_rule(RoutingRule(
        event_type_pattern=r".*\.test\..*",
        platforms={Platform.NATS},
        strategy=RoutingStrategy.ALL,
        priority=100
    ))
    
    # 조건부 라우팅 (특정 브랜치만)
    router.add_routing_rule(RoutingRule(
        event_type_pattern=r".*\.branch\..*",
        platforms={Platform.NATS},
        strategy=RoutingStrategy.CONDITIONAL,
        priority=90,
        conditions={"branch": "main"}
    ))
    
    # 테스트 이벤트
    test_event = CloudEventBuilder("com.oms.test.custom", "/oms/test") \
        .with_data({"test": "custom_routing"}) \
        .with_oms_context("main", "test123", "tester@company.com") \
        .build()
    
    results = await router.publish_event(test_event)
    
    print("Custom routing test results:")
    # Handle different result format
    if isinstance(results, dict) and test_event.id in results:
        platform_results = results[test_event.id]
    else:
        platform_results = results
        
    for platform, result in platform_results.items():
        status = "✅ SUCCESS" if result.success else "❌ FAILED"
        print(f"  {platform.value}: {status}")
    
    await router.shutdown()
    print("✅ Custom routing test completed!")


async def test_failover_scenario():
    """Failover 시나리오 테스트"""
    print("\n=== Failover Scenario Test ===\n")
    
    router = MultiPlatformEventRouter()
    
    # 실패하는 Mock Publisher
    class FailingPublisher:
        async def publish_event(self, event):
            from core.event_publisher.models import PublishResult
            return PublishResult(
                event_id=event.id,
                success=False,
                subject="",
                error="Simulated failure"
            )
        
        def get_health_status(self):
            return {'status': 'unhealthy'}
    
    # 성공하는 Mock Publisher
    nats_publisher = MockNATSPublisher()
    
    # 플랫폼 등록 (실패하는 것을 primary로)
    from core.event_publisher.multi_platform_router import PlatformConfig
    
    router.register_platform(
        Platform.EVENTBRIDGE,
        FailingPublisher(),
        PlatformConfig(platform=Platform.EVENTBRIDGE, is_primary=True)
    )
    
    router.register_nats_platform(nats_publisher, is_primary=False)
    
    # Failover 라우팅 규칙
    router.add_routing_rule(RoutingRule(
        event_type_pattern=r".*",
        platforms={Platform.EVENTBRIDGE, Platform.NATS},
        strategy=RoutingStrategy.FAILOVER,
        priority=100
    ))
    
    # 테스트 이벤트
    event = CloudEventBuilder(EventType.SCHEMA_UPDATED, "/oms/test") \
        .with_data({"failover": "test"}) \
        .build()
    
    results = await router.publish_event(event)
    
    print("Failover test results:")
    # Handle different result format
    if isinstance(results, dict) and event.id in results:
        platform_results = results[event.id]
    else:
        platform_results = results
        
    for platform, result in platform_results.items():
        status = "✅ SUCCESS" if result.success else "❌ FAILED"
        print(f"  {platform.value}: {status}")
        if hasattr(result, 'error') and result.error:
            print(f"    Error: {result.error}")
    
    await router.shutdown()
    print("✅ Failover test completed!")


async def main():
    """모든 테스트 실행"""
    print("🚀 Multi-Platform Event Router Test Suite")
    print("=" * 50)
    
    try:
        await test_basic_multi_platform_routing()
        await test_custom_routing_rules()
        await test_failover_scenario()
        
        print("\n🎉 All tests completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())