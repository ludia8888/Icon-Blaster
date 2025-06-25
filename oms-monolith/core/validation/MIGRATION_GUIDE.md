# Validation Service 순환 참조 해결 마이그레이션 가이드

## 개요
이 가이드는 `core.validation` 모듈의 순환 import 문제를 해결하기 위한 리팩토링 과정을 설명합니다.

## 문제점
기존 구조에서 발생한 순환 참조 체인:
```
service.py
 ├─> rules/*.py (직접 import)
 │     ├─> shared.cache.*
 │     └─> database.clients.*
 └─> models.py
```

## 해결 방법

### 1. Interface 계층 도입 (Ports)
- `ports.py`: CachePort, TerminusPort, EventPort 인터페이스 정의
- 규칙과 서비스가 구체적인 구현체가 아닌 인터페이스에 의존

### 2. 동적 규칙 로딩
- `rule_registry.py`: 규칙을 동적으로 로드하는 레지스트리
- 서비스가 규칙을 직접 import하지 않음

### 3. Adapter 패턴
- `adapters.py`: 실제 구현체를 Port 인터페이스에 맞게 변환
- 런타임에만 실제 모듈을 import하여 순환 방지

### 4. DI Container
- `container.py`: 모든 의존성을 중앙에서 관리
- 테스트와 프로덕션 환경 분리 지원

## 마이그레이션 단계

### Step 1: 새로운 서비스로 전환
```python
# 기존 코드
from core.validation.service import ValidationService
from shared.cache.smart_cache import SmartCacheManager
from database.clients.terminus_db import TerminusDBClient
from shared.events import EventPublisher

service = ValidationService(tdb_client, cache, event_publisher)

# 새로운 코드
from core.validation.container import get_validation_service

service = get_validation_service()
```

### Step 2: 규칙 수정 (필요한 경우)
```python
# 기존 규칙
from shared.cache.smart_cache import SmartCacheManager

class MyRule(BreakingChangeRule):
    def __init__(self):
        self.cache = SmartCacheManager(...)

# 새로운 규칙
from core.validation.ports import CachePort

class MyRule(BreakingChangeRule):
    def __init__(self, cache: CachePort = None, tdb: TerminusPort = None):
        self.cache = cache
        self.tdb = tdb
```

### Step 3: FastAPI 통합
```python
from fastapi import Depends
from core.validation.container import get_validation_service_dependency

@router.post("/validate")
async def validate(
    request: ValidationRequest,
    service = Depends(get_validation_service_dependency)
):
    return await service.validate_breaking_changes(request)
```

### Step 4: 테스트 업데이트
```python
# 테스트에서 Mock 사용
from core.validation.container import ValidationContainer

def test_validation():
    container = ValidationContainer(test_mode=True)
    service = container.get_validation_service()
    # Mock 어댑터가 자동으로 주입됨
```

## 기존 코드 호환성

레거시 코드를 위한 호환성 레이어:
```python
from core.validation.container import create_validation_service_with_legacy_interface

# 기존 방식으로 서비스 생성
service = create_validation_service_with_legacy_interface(
    tdb_client=existing_tdb,
    cache=existing_cache,
    event_publisher=existing_publisher
)
```

## 이점
1. **순환 참조 제거**: 컴파일 타임에 순환 import 없음
2. **테스트 용이성**: Mock 어댑터로 빠른 단위 테스트
3. **확장성**: 새로운 규칙 추가 시 서비스 수정 불필요
4. **유연성**: 런타임에 어댑터 교체 가능

## 주의사항
- 모든 규칙이 동적으로 로드되므로 규칙 파일의 이름과 위치가 중요
- 규칙 클래스는 `rule_id` 속성과 `check` 메서드를 반드시 구현해야 함
- Port 인터페이스 변경 시 모든 어댑터 업데이트 필요

## 문제 해결
- ImportError 발생 시: 규칙 모듈이 외부 의존성을 직접 import하는지 확인
- 규칙이 로드되지 않을 때: 규칙 클래스가 BreakingChangeRule을 상속하는지 확인
- 테스트 실패 시: Mock 어댑터의 메서드 시그니처가 Port와 일치하는지 확인