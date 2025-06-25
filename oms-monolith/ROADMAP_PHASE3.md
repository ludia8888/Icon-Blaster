# Phase 3: 이벤트 시스템 통합 로드맵

## 3.1 CloudEvents 구현 단순화 (2일)

### 현재 상태
- 복잡한 이벤트 발행 시스템
- 여러 어댑터 (EventBridge, NATS 등)

### 목표 아키텍처
```python
# events/simple_publisher.py
from cloudevents.http import CloudEvent

class SimpleEventPublisher:
    def __init__(self, mode="local"):
        self.mode = mode  # local, aws, nats
        
    async def publish(self, event_type: str, data: dict):
        event = CloudEvent({
            "type": f"com.spice.oms.{event_type}",
            "source": "oms-monolith",
            "data": data
        })
        
        if self.mode == "local":
            await self._publish_local(event)
        elif self.mode == "aws":
            await self._publish_eventbridge(event)
```

## 3.2 이벤트 주도 통합 (3일)

### 핵심 이벤트 정의
```python
# events/core_events.py
SCHEMA_CREATED = "schema.created"
SCHEMA_UPDATED = "schema.updated"
BREAKING_CHANGE_DETECTED = "validation.breaking-change"
BRANCH_MERGED = "branch.merged"
```

### 서비스 통합
```python
class SchemaServiceV4:
    def __init__(self, event_publisher=None):
        self.events = event_publisher or DummyPublisher()
    
    async def create_object_type(self, obj_type):
        # 비즈니스 로직
        result = await self._create(obj_type)
        
        # 이벤트 발행
        await self.events.publish(SCHEMA_CREATED, {
            "objectType": result.dict(),
            "branch": result.branch
        })
```

## 3.3 이벤트 구독자 (2일)

### 자동화 워크플로우
```python
# subscribers/auto_validation.py
@event_handler(SCHEMA_UPDATED)
async def auto_validate_changes(event):
    # 스키마 변경 시 자동 검증
    validation_result = await validation_service.check(
        event.data["before"],
        event.data["after"]
    )
    
    if validation_result.has_breaking_changes:
        await notify_team(validation_result)
```

## 예상 결과물
- 이벤트 기반 아키텍처
- 느슨한 결합
- 확장 가능한 워크플로우