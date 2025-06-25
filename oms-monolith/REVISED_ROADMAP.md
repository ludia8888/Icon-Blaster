# OMS 수정된 로드맵 - 엔터프라이즈 코드 보존

## 핵심 원칙: "기존 고품질 코드 최대한 재사용"

### Phase 1: Import 문제만 해결 (3일)

#### 1.1 Import Fixer 스크립트 작성
```python
# scripts/fix_imports.py
import os
import re

def fix_service_imports(file_path):
    """services.validation_service.core.* → core.validation.*"""
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Import 패턴 수정
    content = re.sub(
        r'from services\.(\w+)_service\.core\.',
        r'from core.\1.',
        content
    )
    
    with open(file_path, 'w') as f:
        f.write(content)
```

#### 1.2 의존성 Stub 생성
```python
# shared/stubs.py
"""최소한의 스텁으로 실행 가능하게 만들기"""

class SmartCacheManager:
    """TerminusDB 내부 캐싱을 사용하므로 더미"""
    def __init__(self, *args, **kwargs):
        pass
    
    def get(self, key):
        return None
    
    def set(self, key, value, ttl=None):
        pass

class EventPublisher:
    """나중에 실제 구현으로 교체"""
    async def publish(self, event_type, data):
        print(f"Event: {event_type} - {data}")
```

### Phase 2: 기존 서비스 통합 (1주일)

#### 2.1 Service Wrapper 패턴
```python
# core/schema/service_wrapper.py
from core.schema.service import SchemaService  # 기존 코드
from shared.stubs import SmartCacheManager, EventPublisher

class SchemaServiceWrapper:
    """기존 SchemaService를 래핑하여 의존성 주입"""
    
    def __init__(self, db_client=None):
        # 스텁으로 초기화
        cache = SmartCacheManager()
        events = EventPublisher()
        
        # 기존 서비스 사용
        self.service = SchemaService(
            tdb_client=db_client or InMemoryClient(),
            cache=cache,
            event_publisher=events
        )
    
    # 기존 메서드들 그대로 노출
    async def create_object_type(self, *args, **kwargs):
        return await self.service.create_object_type(*args, **kwargs)
```

#### 2.2 통합 테스트
```python
# tests/integration/test_preserved_logic.py
async def test_breaking_change_detection():
    """기존 Breaking Change 로직이 그대로 작동하는지 확인"""
    
    # PrimaryKeyChangeRule 테스트
    rule = PrimaryKeyChangeRule()
    result = await rule.check(before, after)
    
    assert result.severity == Severity.CRITICAL
    assert "primary key change" in result.message
    
    # DataImpactAnalyzer 테스트
    analyzer = DataImpactAnalyzer()
    impact = await analyzer.analyze(schema_change)
    
    assert impact.affected_records > 0
    assert impact.migration_strategy == "COPY_THEN_DROP"
```

### Phase 3: 점진적 실제 구현 (2주일)

#### 3.1 스텁을 실제 구현으로 교체
```python
# 1단계: InMemoryClient → SimpleTerminusClient
# 2단계: EventPublisher stub → CloudEventsPublisher  
# 3단계: 로컬 캐시 → Redis/TerminusDB 캐시
```

#### 3.2 기존 코드 최적화
- 권한 시스템 TODO 완성
- 하드코딩된 값 설정으로 분리
- 메모리 효율성 개선

### Phase 4: 새로운 기능 추가 (1개월)

#### 4.1 기존 패턴을 따라 확장
```python
# 새로운 Breaking Change 규칙 추가
class NameConventionChangeRule(BreakingChangeRule):
    """기존 규칙 패턴을 따라 구현"""
    pass

# CloudEvents 확장
class EnhancedCloudEventV2(EnhancedCloudEvent):
    """기존 구현을 상속하여 확장"""
    pass
```

## 장점

1. **품질 보존**: 엔터프라이즈급 코드 그대로 유지
2. **빠른 실행**: Import만 고치면 바로 작동
3. **점진적 개선**: 스텁에서 실제 구현으로 천천히 전환
4. **확장성**: 기존 패턴을 따라 쉽게 확장

## 예상 일정

- **3일**: Import 수정 + 스텁으로 실행 가능
- **1주일**: 모든 서비스 통합 완료
- **2주일**: 실제 DB/이벤트 시스템 연결
- **1개월**: 프로덕션 준비 완료

## 핵심 차이점

### 이전 접근법 ❌
- 단순화를 위해 재작성
- 엔터프라이즈 기능 손실 위험
- 품질 저하 가능성

### 새로운 접근법 ✅
- 기존 코드 최대한 보존
- Import와 의존성만 해결
- 엔터프라이즈 품질 유지