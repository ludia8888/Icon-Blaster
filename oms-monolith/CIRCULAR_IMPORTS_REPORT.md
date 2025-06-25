# 순환 참조 분석 보고서

## 요약
전체 프로젝트 분석 결과 2개의 순환 참조가 발견되었습니다.

## 발견된 순환 참조

### 1. tampering_detection ↔ siem_integration
```
core.validation.tampering_detection → core.validation.siem_integration
core.validation.siem_integration → core.validation.tampering_detection
```

**원인:**
- `tampering_detection.py`: SIEM으로 이벤트를 보내기 위해 `get_siem_manager` import
- `siem_integration.py`: `TamperingEvent` 클래스를 알아야 SIEM 포맷으로 변환 가능

### 2. validation_logging ↔ siem_integration
```
core.validation.validation_logging → core.validation.siem_integration
core.validation.siem_integration → core.validation.validation_logging
```

**원인:**
- `validation_logging.py`: SIEM으로 로그를 보내기 위해 `get_siem_manager` import
- `siem_integration.py`: `ValidationLogEntry` 클래스를 알아야 SIEM 포맷으로 변환 가능

## 현재 완화 방법
두 모듈 모두 lazy loading을 사용하여 런타임 오류는 방지하고 있습니다:
```python
def _get_siem_manager():
    from core.validation.siem_integration import get_siem_manager
    return get_siem_manager()
```

## 권장 해결 방법

### 방법 1: 데이터 클래스 분리 (추천)
```python
# core/validation/models/siem_models.py
class TamperingEvent:
    ...

class ValidationLogEntry:
    ...
```

### 방법 2: 이벤트 기반 아키텍처
```python
# core/validation/events.py
class EventBus:
    def publish(self, event: Any):
        # SIEM이 구독하여 처리
```

### 방법 3: Protocol/Interface 사용
```python
# core/validation/protocols.py
from typing import Protocol

class SIEMSerializable(Protocol):
    def to_siem_format(self) -> dict:
        ...
```

## 기타 발견사항

### 의심스러운 패턴
1. **하위 모듈이 상위 모듈을 import:**
   - `core.user.routes` → `core.user`
   - `core.event_publisher.secure_publisher` → `core.event_publisher`

2. **양방향 import 가능성:**
   - 위에서 언급한 SIEM 관련 모듈들

## 결론
- 전체 91개 모듈 중 2개의 순환 참조만 존재
- 모두 SIEM 통합 관련 모듈에 집중
- Lazy loading으로 당장의 문제는 없으나 구조 개선 필요
- 나머지 코드베이스는 순환 참조 없이 깔끔함