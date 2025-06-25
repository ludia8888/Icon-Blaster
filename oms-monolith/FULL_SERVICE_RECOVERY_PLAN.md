# OMS 전체 서비스 복구 계획

## 발견된 엔터프라이즈급 자산들

### 🌟 최상급 서비스들 (재사용 가치 매우 높음)

#### 1. **User Service** (⭐⭐⭐⭐⭐)
- **완벽한 인증/인가 시스템**
  - MFA, JWT, 세션 관리
  - 비밀번호 정책 (복잡도, 히스토리, 만료)
  - 계정 잠금, 동시 세션 제한
  - SQLAlchemy 비동기 ORM
- **즉시 사용 가능한 수준**

#### 2. **Advanced Scheduler** (⭐⭐⭐⭐⭐)
- **엔터프라이즈급 작업 스케줄러**
  - APScheduler + Redis 분산 실행
  - 작업 우선순위 및 의존성 관리
  - 재시도 로직 (지수 백오프)
  - 체크포인트 및 진행률 추적
- **배치 작업 시스템의 핵심**

#### 3. **History Service** (⭐⭐⭐⭐⭐)
- **이벤트 기반 감사 로그**
  - CloudEvents 표준 준수
  - 보호된 브랜치 관리
  - Dry run 지원
  - 구조화된 로깅

#### 4. **Three-Way Merge** (⭐⭐⭐⭐⭐)
- **Git 수준의 병합 엔진**
  - 완전한 3-way 병합
  - 시맨틱 병합 지원
  - 확장 가능한 충돌 해결

### 🔥 우수한 서비스들

#### 5. **API Gateway** (⭐⭐⭐⭐)
- Circuit Breaker: 상태 머신, Redis 분산 지원
- Rate Limiter: Sliding window, 버스트 처리
- 모든 마이크로서비스에 필수

#### 6. **gRPC Services** (⭐⭐⭐⭐)
- OpenTelemetry 통합
- 엔터프라이즈급 인터셉터
- TLS, 우아한 종료

#### 7. **PII Handler** (⭐⭐⭐⭐)
- 한국 주민번호 포함 다양한 패턴
- 익명화, 암호화, 삭제 전략
- GDPR 규제 준수

## 복구 전략

### Phase 0: 즉시 실행 가능한 서비스 분리 (1일)

```bash
# 독립적으로 실행 가능한 서비스들을 별도 패키지로
oms-core/
├── user-service/        # 인증/인가 시스템
├── scheduler-service/   # 작업 스케줄러
├── merge-engine/       # 3-way merge
└── common/
    ├── circuit-breaker/
    ├── rate-limiter/
    └── pii-handler/
```

### Phase 1: Import 일괄 수정 (2일)

```python
# scripts/mass_import_fixer.py
import os
import re
from pathlib import Path

IMPORT_MAPPINGS = {
    r'from services\.(\w+)_service\.core\.': r'from core.\1.',
    r'from shared\.models\.': r'from models.',
    r'from shared\.clients\.': r'from database.clients.',
    r'from shared\.cache\.': r'from oms_core.cache.',
    r'from shared\.events': r'from oms_core.events',
}

def fix_all_imports():
    for py_file in Path('.').glob('**/*.py'):
        if 'venv' in str(py_file):
            continue
            
        content = py_file.read_text()
        for pattern, replacement in IMPORT_MAPPINGS.items():
            content = re.sub(pattern, replacement, content)
        py_file.write_text(content)
```

### Phase 2: 핵심 의존성 구현 (3일)

```python
# oms_core/cache.py
class SmartCacheManager:
    """TerminusDB 내부 캐싱 사용"""
    def __init__(self):
        # 실제로는 TerminusDB의 TERMINUSDB_LRU_CACHE_SIZE 활용
        pass

# oms_core/events.py
from core.event_publisher.enhanced_event_service import EnhancedEventService

class EventPublisher:
    """기존 CloudEvents 구현 재사용"""
    def __init__(self):
        self.service = EnhancedEventService()
    
    async def publish(self, event_type, data):
        # 기존 구현 활용
        await self.service.publish_event(event_type, data)
```

### Phase 3: 통합 실행 (1주일)

```python
# main_enterprise.py
from fastapi import FastAPI
from contextlib import asynccontextmanager

# 모든 서비스 import (수정된 경로)
from core.schema.service import SchemaService
from core.validation.service import ValidationService
from core.branch.service import BranchService
from core.user.service import UserService
from core.history.service import HistoryService
from core.scheduler.advanced_scheduler import AdvancedScheduler

# API 라우터들
from api.gateway.router import gateway_router
from api.graphql.main import graphql_app

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 서비스 초기화
    services = {
        'schema': SchemaService(),
        'validation': ValidationService(),
        'branch': BranchService(),
        'user': UserService(),
        'history': HistoryService(),
        'scheduler': AdvancedScheduler(),
    }
    
    # 스케줄러 시작
    services['scheduler'].start()
    
    yield services
    
    # 정리
    services['scheduler'].shutdown()

app = FastAPI(
    title="OMS Enterprise",
    version="2.0.0",
    lifespan=lifespan
)

# 모든 라우터 통합
app.mount("/graphql", graphql_app)
app.include_router(gateway_router)
```

## 예상 결과

### 1주일 내 달성 가능:
- ✅ 모든 엔터프라이즈 서비스 실행
- ✅ User Service로 완전한 인증/인가
- ✅ Advanced Scheduler로 배치 작업
- ✅ API Gateway로 보호된 엔드포인트
- ✅ GraphQL API 완전 작동

### 보존되는 기능들:
- Breaking Change Detection (Palantir Foundry 수준)
- CloudEvents 기반 이벤트 시스템
- 3-way Merge (Git 수준)
- 엔터프라이즈 보안 (MFA, JWT, PII 처리)
- 분산 작업 스케줄링
- Circuit Breaker & Rate Limiting
- 감사 로그 및 히스토리 추적

### 새로 얻는 것들:
- 검증된 엔터프라이즈 컴포넌트 라이브러리
- 재사용 가능한 보안 시스템
- 프로덕션 준비된 인프라 컴포넌트

## 결론

**모든 서비스를 살릴 수 있습니다!**

특히:
- User Service는 어떤 프로젝트에서도 바로 쓸 수 있는 완성도
- Advanced Scheduler는 Airflow 대체 가능한 수준
- Three-Way Merge는 협업 도구의 핵심 엔진
- API Gateway 컴포넌트들은 MSA 필수 요소

이 코드들을 버리는 것은 정말 아까운 일입니다. Import만 고쳐서 모두 살려내겠습니다!