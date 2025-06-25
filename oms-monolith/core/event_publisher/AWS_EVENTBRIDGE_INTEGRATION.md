# AWS EventBridge Integration Guide

## 개요

OMS(Ontology Management System)에 AWS EventBridge 지원이 추가되어 NATS와 EventBridge를 동시에 사용할 수 있는 Multi-Platform Event Router가 구현되었습니다.

## 주요 기능

### ✅ 구현 완료
1. **AWS EventBridge Publisher** - CloudEvents 1.0 완전 준수
2. **Multi-Platform Event Router** - NATS + EventBridge 동시 지원
3. **Smart Routing Rules** - 이벤트 타입별 라우팅 전략
4. **Failover Support** - 플랫폼 장애시 자동 대체
5. **IAM & Security** - AWS 보안 설정 자동화
6. **CloudWatch Monitoring** - 대시보드 및 메트릭

## 아키텍처

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   OMS Events    │───▶│ Multi-Platform   │───▶│ NATS JetStream  │
│ (CloudEvents)   │    │   Event Router   │    │                 │
└─────────────────┘    │                  │    └─────────────────┘
                       │   ┌──────────────┤
                       │   │ Routing      │    ┌─────────────────┐
                       │   │ Rules        │───▶│ AWS EventBridge │
                       │   │ • Schema→All │    │                 │
                       │   │ • Action→NATS│    └─────────────────┘
                       │   │ • System→AWS │
                       └───┴──────────────┘
```

## 설치 및 설정

### 1. 의존성 설치

기존 `requirements.txt`에 이미 포함되어 있습니다:
```
boto3==1.28.84
botocore==1.31.84
```

### 2. AWS 설정

#### 환경 변수 설정
```bash
export AWS_REGION=us-east-1
export AWS_ACCESS_KEY_ID=your_access_key
export AWS_SECRET_ACCESS_KEY=your_secret_key

# 선택적 설정
export OMS_EVENTBRIDGE_BUS_NAME=oms-events
export OMS_ENABLE_EVENTBRIDGE=true
```

#### AWS 인프라 설정
```python
# 자동 설정 스크립트 실행
python infrastructure/aws/eventbridge_setup.py \
    --event-bus-name oms-events \
    --aws-region us-east-1
```

### 3. OMS 설정 업데이트

#### Outbox Processor 설정
```python
from core.event_publisher.eventbridge_publisher import EventBridgeConfig
from core.event_publisher.outbox_processor import OutboxProcessor

# EventBridge 설정
eventbridge_config = EventBridgeConfig(
    event_bus_name="oms-events",
    aws_region="us-east-1"
)

# Multi-Platform 지원 활성화
processor = OutboxProcessor(
    tdb_client=tdb_client,
    nats_client=nats_client,
    metrics=metrics,
    eventbridge_config=eventbridge_config,
    enable_multi_platform=True  # 🆕 Multi-Platform 활성화
)
```

## 사용법

### 1. 기본 이벤트 발행

기존 코드는 수정 없이 동작합니다:

```python
from core.event_publisher.enhanced_event_service import EnhancedEventService

service = EnhancedEventService()

# 스키마 변경 이벤트 (NATS + EventBridge 동시 발행)
event = service.create_schema_change_event(
    operation="create",
    resource_type="object_type",
    resource_id="User",
    branch="main",
    commit_id="abc123",
    author="developer@company.com"
)

await service.publish_event(event)
```

### 2. Direct Multi-Platform Router 사용

```python
from core.event_publisher.multi_platform_router import create_oms_multi_platform_router
from core.event_publisher.eventbridge_publisher import EventBridgeConfig

# Router 생성
router = create_oms_multi_platform_router(
    nats_publisher=nats_client,
    eventbridge_config=EventBridgeConfig(
        event_bus_name="oms-events",
        aws_region="us-east-1"
    )
)

# 이벤트 발행
results = await router.publish_event(cloud_event)

# 플랫폼별 결과 확인
for platform, result in results.items():
    print(f"{platform}: {'✅' if result.success else '❌'}")
```

### 3. 커스텀 라우팅 규칙

```python
from core.event_publisher.multi_platform_router import RoutingRule, RoutingStrategy, Platform

# 특정 브랜치의 이벤트만 EventBridge로
router.add_routing_rule(RoutingRule(
    event_type_pattern=r".*\.schema\..*",
    platforms={Platform.EVENTBRIDGE},
    strategy=RoutingStrategy.CONDITIONAL,
    conditions={"branch": "production"}
))

# 긴급 이벤트는 모든 플랫폼으로
router.add_routing_rule(RoutingRule(
    event_type_pattern=r".*\.system\.error",
    platforms={Platform.NATS, Platform.EVENTBRIDGE},
    strategy=RoutingStrategy.ALL,
    priority=999
))
```

## 라우팅 전략

### 기본 라우팅 규칙

| 이벤트 타입 | 대상 플랫폼 | 전략 | 설명 |
|------------|------------|------|------|
| `*.schema.*` | NATS + EventBridge | ALL | 스키마 변경은 모든 곳에 알림 |
| `*.branch.*` | NATS → EventBridge | FAILOVER | 브랜치 이벤트는 NATS 우선 |
| `*.action.*` | NATS | PRIMARY_ONLY | 실시간 액션은 NATS만 |
| `*.system.*` | EventBridge | ALL | 시스템 모니터링은 AWS로 |

### 사용 가능한 전략

- **ALL**: 모든 플랫폼에 동시 발행
- **PRIMARY_ONLY**: 기본 플랫폼만 사용
- **FAILOVER**: 기본 실패시 백업 사용
- **CONDITIONAL**: 조건부 라우팅

## EventBridge 매핑

### CloudEvents → EventBridge 변환

```json
// CloudEvent
{
  "specversion": "1.0",
  "type": "com.foundry.oms.objecttype.created",
  "source": "/oms/main",
  "id": "abc-123",
  "data": {"name": "User"}
}

// EventBridge Event
{
  "Source": "oms.main",
  "DetailType": "Objecttype Created",
  "Detail": {
    "cloudEvents": { /* original CloudEvent */ },
    "omsContext": { /* OMS extensions */ },
    "eventBridgeMetadata": { /* conversion info */ }
  }
}
```

### EventBridge Rules 생성

각 OMS 이벤트 타입별로 자동 Rule 생성:

```json
{
  "Name": "oms_objecttype_created_rule",
  "EventPattern": {
    "source": ["oms"],
    "detail-type": ["Objecttype Created"],
    "detail": {
      "cloudEvents": {
        "type": ["com.foundry.oms.objecttype.created"]
      }
    }
  }
}
```

## 모니터링

### 플랫폼 상태 확인

```python
status = router.get_platform_status()
print(f"Healthy platforms: {status['health_summary']['healthy_platforms']}")
print(f"Primary platform healthy: {status['health_summary']['primary_platform_healthy']}")
```

### CloudWatch Metrics

자동 생성되는 메트릭:
- `AWS/Events/SuccessfulInvocations`
- `AWS/Events/FailedInvocations`  
- `AWS/Events/MatchedEvents`

### Custom Metrics

OMS 자체 메트릭:
- 플랫폼별 이벤트 발행 성공률
- 라우팅 규칙 매칭 통계
- Failover 발생 횟수

## 보안

### IAM 권한

최소 권한 원칙:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "events:PutEvents"
      ],
      "Resource": "arn:aws:events:*:*:event-bus/oms-events"
    },
    {
      "Effect": "Allow", 
      "Action": [
        "events:DescribeEventBus"
      ],
      "Resource": "*"
    }
  ]
}
```

### 네트워크 보안

- VPC Endpoints 지원
- Private EventBridge 접근
- mTLS 연결 지원

## 트러블슈팅

### 일반적인 문제

1. **EventBridge 연결 실패**
   ```
   Solution: AWS 자격증명 및 리전 설정 확인
   ```

2. **라우팅 규칙 미동작**
   ```
   Solution: 정규식 패턴 및 우선순위 확인
   ```

3. **Failover 미동작**
   ```
   Solution: 플랫폼 헬스체크 상태 확인
   ```

### 디버깅

```python
# 상세 로깅 활성화
import logging
logging.getLogger('core.event_publisher').setLevel(logging.DEBUG)

# 플랫폼별 결과 확인
for platform, result in results.items():
    if not result.success:
        print(f"{platform} error: {result.error}")
```

## 성능 고려사항

### 배치 크기
- EventBridge: 최대 10개 이벤트/배치
- NATS: 제한 없음

### 지연시간
- NATS: ~1-5ms
- EventBridge: ~100-500ms

### 처리량
- NATS: 10,000+ events/sec
- EventBridge: 1,000+ events/sec

## 다음 단계

1. **AsyncAPI 문서 생성** - 이벤트 스키마 자동 문서화
2. **Real-time Webhooks** - EventBridge → HTTP endpoints
3. **Cross-Region Replication** - 다중 리전 이벤트 복제
4. **Event Sourcing** - EventBridge 기반 이벤트 소싱

## 예제 코드

완전한 예제는 `test_multiplatform_router.py`를 참조하세요:

```bash
python test_multiplatform_router.py
```

이 통합으로 OMS는 클라우드 네이티브 이벤트 아키텍처를 지원하면서도 기존 NATS 기반 실시간 처리 성능을 유지합니다.