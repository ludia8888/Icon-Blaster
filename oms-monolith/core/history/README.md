# OMS History Event Publisher

## 개요

OMS의 핵심 책임에 맞게 리팩토링된 History 모듈입니다. **감사 로그 조회/관리 기능을 제거**하고 **이벤트 발행 기능만 유지**하여 MSA 경계를 명확히 했습니다.

## 🎯 OMS 핵심 책임

### ✅ OMS가 담당하는 기능
- **스키마 변경 이벤트 발행** (CloudEvents 표준)
- **스키마 복원** (메타데이터만)
- **감사 이벤트 생성** (발행만, 저장/조회는 별도 MSA)

### ❌ 다른 MSA로 분리된 기능
- **감사 로그 조회/서빙** → **Audit Service MSA**
- **SIEM 통합** → **Audit Service MSA**
- **규제 준수 리포트** → **Audit Service MSA**
- **데이터 복원** → **OSv2 Service**
- **파이프라인 복원** → **Funnel Service**

## 📁 파일 구조

```
core/history/
├── README.md                    # 이 문서
├── __init__.py
├── models.py                    # 이벤트 모델 (간소화)
├── service.py                   # HistoryEventPublisher (리팩토링됨)
└── routes.py                    # 이벤트 발행 API만 유지
```

## 🔄 주요 변경사항

### 1. Service Layer 변경
```python
# Before: HistoryService (조회/관리 포함)
class HistoryService:
    async def list_history()        # ❌ 제거됨 → Audit Service MSA
    async def get_commit_detail()   # ❌ 제거됨 → Audit Service MSA
    async def export_audit_logs()   # ❌ 제거됨 → Audit Service MSA
    async def revert_to_commit()    # ✅ 스키마 복원으로 축소

# After: HistoryEventPublisher (이벤트 발행만)
class HistoryEventPublisher:
    async def publish_schema_change_event()    # ✅ 핵심 기능
    async def publish_audit_event()            # ✅ 핵심 기능
    async def revert_schema_to_commit()        # ✅ 스키마만 복원
```

### 2. API Endpoints 변경
```python
# Before: 조회/관리 API (제거됨)
GET    /api/v1/history/                    # ❌ → Audit Service MSA
GET    /api/v1/history/{commit_hash}       # ❌ → Audit Service MSA
GET    /api/v1/history/audit/export        # ❌ → Audit Service MSA

# After: 이벤트 발행 API만 유지
POST   /api/v1/schema/revert               # ✅ 스키마 복원
POST   /api/v1/schema/events/audit         # ✅ 감사 이벤트 발행
```

### 3. Model 변경
```python
# Before: 복잡한 히스토리 모델들 (제거됨)
class HistoryEntry         # ❌ → Audit Service MSA
class HistoryListResponse  # ❌ → Audit Service MSA
class CommitDetail         # ❌ → Audit Service MSA
class AuditLogEntry        # ❌ → Audit Service MSA

# After: 이벤트 모델만 유지
class AuditEvent          # ✅ 이벤트 발행용
class ChangeDetail        # ✅ 변경 상세
class RevertRequest       # ✅ 스키마 복원 요청
class RevertResult        # ✅ 스키마 복원 결과
```

## 🚀 사용법

### 1. 스키마 변경 이벤트 발행
```python
from core.history.service import HistoryEventPublisher

publisher = HistoryEventPublisher(terminus_client, event_publisher)

# 스키마 변경 시 이벤트 발행
event_id = await publisher.publish_schema_change_event(
    operation=ChangeOperation.UPDATE,
    resource_type=ResourceType.OBJECT_TYPE,
    resource_id="Product",
    resource_name="Product Object Type",
    changes=[...],
    branch="main",
    commit_hash="abc123",
    user_context=user_context
)
```

### 2. 스키마 복원
```python
# 스키마를 특정 커밋으로 복원 (메타데이터만)
result = await publisher.revert_schema_to_commit(
    branch="main",
    request=RevertRequest(
        target_commit="def456",
        strategy="soft",
        message="Revert breaking change"
    ),
    user_context=user_context
)
```

### 3. 감사 이벤트 발행
```python
# 내부 서비스용 감사 이벤트 발행
event_id = await publisher.publish_audit_event(
    event_type="schema.validation",
    operation="validate",
    resource_type="objectType",
    resource_id="Product",
    user_context=user_context,
    result="success"
)
```

## 🔗 MSA 연동

### Audit Service MSA
```yaml
# OMS → Audit Service 이벤트 스트림
events:
  - schema.changed
  - schema.reverted
  - audit.event

# Audit Service 책임
responsibilities:
  - 감사 로그 수집/저장
  - 감사 로그 조회 API
  - SIEM 통합
  - 규제 준수 리포트
  - 로그 보존 정책 관리
```

### OSv2 Service
```yaml
# 데이터 복원 이벤트 수신
events:
  - schema.reverted

# OSv2 책임
responsibilities:
  - 객체 데이터 복원
  - 데이터 일관성 검증
  - 백업/복원 전략
```

### Funnel Service
```yaml
# 파이프라인 복원 이벤트 수신
events:
  - schema.reverted

# Funnel 책임
responsibilities:
  - 파이프라인 재빌드
  - 데이터 플로우 복원
  - 의존성 그래프 업데이트
```

## 📊 이벤트 스키마 (CloudEvents)

### Schema Changed Event
```json
{
  "specversion": "1.0",
  "type": "com.oms.schema.changed",
  "source": "oms.history",
  "id": "audit_abc123def456",
  "time": "2025-06-25T10:30:00Z",
  "datacontenttype": "application/json",
  "data": {
    "operation": "update",
    "resource_type": "objectType",
    "resource_id": "Product",
    "resource_name": "Product Object Type",
    "branch": "main",
    "commit_hash": "abc123def456",
    "author": "user123",
    "changes": [...]
  }
}
```

### Audit Event
```json
{
  "specversion": "1.0",
  "type": "com.oms.audit.event",
  "source": "oms.audit",
  "id": "audit_xyz789abc123",
  "time": "2025-06-25T10:30:00Z",
  "datacontenttype": "application/json",
  "data": {
    "event_type": "schema.validation",
    "operation": "validate",
    "resource_type": "objectType",
    "resource_id": "Product",
    "author": "user123",
    "result": "success",
    "ip_address": "192.168.1.100",
    "session_id": "sess_123"
  }
}
```

## 🎉 리팩토링 효과

### 1. MSA 경계 명확화
- ✅ OMS 핵심 책임에만 집중
- ✅ 감사 로그 서빙 기능 분리
- ✅ 단일 책임 원칙 준수

### 2. 성능 향상
- ✅ 불필요한 조회 로직 제거
- ✅ 이벤트 발행 최적화
- ✅ 메모리 사용량 감소

### 3. 유지보수성 향상
- ✅ 코드 복잡도 감소 (549줄 → 439줄)
- ✅ 테스트 범위 축소
- ✅ 의존성 최소화

### 4. 확장성 향상
- ✅ 독립적인 서비스 배포
- ✅ 장애 격리 (Blast Radius 축소)
- ✅ 수평 확장 가능

## 🔧 Migration Guide

### 기존 코드 마이그레이션
```python
# Before: 히스토리 조회 (제거됨)
history = await history_service.list_history(query)
# → Audit Service MSA API 호출로 변경 필요

# Before: 커밋 상세 조회 (제거됨) 
detail = await history_service.get_commit_detail(commit_hash)
# → Audit Service MSA API 호출로 변경 필요

# After: 이벤트 발행만 유지 (호환성 유지)
event_id = await publisher.publish_schema_change_event(...)  # ✅ 동일
```

## 📝 Next Steps

1. **Audit Service MSA 구현**
   - 감사 로그 조회 API 구현
   - SIEM 통합 구현
   - 규제 준수 리포트 구현

2. **Frontend 연동**
   - Audit Service API 연동
   - 히스토리 조회 UI 업데이트

3. **이벤트 스트림 최적화**
   - 배치 이벤트 발행
   - 실패 재시도 로직
   - 모니터링 강화