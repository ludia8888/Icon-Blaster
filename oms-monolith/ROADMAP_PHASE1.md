# Phase 1: 코어 서비스 통합 로드맵

## 1.1 의존성 구조 단순화 (2일)

### 현재 문제점
```
services.validation_service.core.* (존재하지 않음)
↓
core.validation.* (실제 위치)
↓
shared.* (부분적으로 생성됨)
```

### 해결 방안
1. **Flat Import 구조로 변경**
   ```python
   # Before
   from services.validation_service.core.models import ValidationRequest
   
   # After
   from core.validation.models import ValidationRequest
   ```

2. **순환 의존성 제거**
   - Interface 정의를 별도 파일로 분리
   - 의존성 주입 패턴 적용

3. **shared 모듈 완성**
   ```
   shared/
   ├── __init__.py
   ├── interfaces.py      # 모든 인터페이스 정의
   ├── exceptions.py      # 공통 예외
   └── constants.py       # 공통 상수
   ```

## 1.2 서비스 레이어 통합 (3일)

### SchemaService 통합
```python
# core/schema/service_v2.py
class SchemaServiceV2:
    def __init__(self, db_client=None):
        # DB 클라이언트는 선택적 - 없으면 메모리 사용
        self.db_client = db_client or InMemoryStore()
```

### ValidationService 통합
- Rule 패턴은 유지 (잘 설계됨)
- 복잡한 의존성만 제거

### BranchService 통합
- Three-way merge 알고리즘 보존
- Git 스타일 브랜칭 로직 유지

## 1.3 통합 API 레이어 (2일)

```python
# main_integrated.py
from core.schema.service_v2 import SchemaServiceV2
from core.validation.service_v2 import ValidationServiceV2
from core.branch.service_v2 import BranchServiceV2

# 서비스 초기화
schema_service = SchemaServiceV2()
validation_service = ValidationServiceV2()
branch_service = BranchServiceV2()

# FastAPI 라우트에 연결
app.include_router(schema_router)
app.include_router(validation_router)
app.include_router(branch_router)
```

## 예상 결과물
- 모든 핵심 서비스가 실행 가능
- 메모리 기반으로 동작 (DB 없이도)
- 전체 API 테스트 가능