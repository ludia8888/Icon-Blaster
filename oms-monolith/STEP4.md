# ④ Commit Hook 통합
― “Validation + Event Hook” 을 TerminusDB 커밋 시점에 자동 실행

(현재 코드베이스 기준 + Data-Kernel Gateway(REST/gRPC) 가 이미 존재한다는 전제)

──────────────────────────────────
A. WHY?

──────────────────────────────────
• 지금은 `core/validation/*` 모듈이 **API 로직 안**에서 호출될 때도 있고, 빠지는 곳도 많음 → 규칙 누락 위험

• `core/event_publisher/` · `core/audit/` 등이 **각각** “entity 수정 → 이벤트 발행” 코드를 반복

→ TerminusDB 커밋 레이어에서 **한 번**에 Validation + Event Emit 을 처리하면

① 스키마/정책 위반을 *Write Path* 상에서 차단

② 이벤트·감사 로직을 “중앙 집전”

③ MSA 로 분리되는 서비스도 추가코딩 無

──────────────────────────────────
B. WHAT? (타깃 흐름)

──────────────────────────────────

```
Service (OMS 등)
      │  Put/Patch via gRPC
      ▼
Data-Kernel Gateway
 ├─ TerminusService.put()
 │    └─ TerminusDB HTTP /api/document
 │          ├─ ✔︎ commit_id
 │          └─ ✔︎ layer diff
 └─ CommitHookPipeline  ← (Step-4 신규)
      ① ValidationPipeline
      ② EventPipeline
      ③ AuditLogPipeline

```

──────────────────────────────────
C. HOW? (구현 단계)

──────────────────────────────────

1. **Diff 획득**
    
    TerminusDB HTTP `/api/document/*?t=true` 옵션으로 `before/after` 레이어 diff (json patch) 반환 가능.
    
    TerminusService.put() 내부에서 커밋 성공 후
    
    ```python
    diff = response.json()["transaction"]["patch"]
    await CommitHookPipeline.run(meta, diff)
    
    ```
    
2. CommitHookPipeline 골격 (`data_kernel/hook/pipeline.py`)

```python
class CommitHookPipeline:
    _validators: List[BaseValidator] = []
    _event_sinks: List[BaseSink] = []
    _audit_sink:  Optional[AuditSink] = None

    @classmethod
    async def run(cls, meta: CommitMeta, diff: Dict):
        # Ⅰ. Validation 단계 (모두 통과해야 계속)
        for v in cls._validators:
            await v.validate(meta, diff)  # raise ValidationError ⇒ 커밋 롤백

        # Ⅱ. Audit 기록  (비동기 fire-and-forget)
        if cls._audit_sink:
            asyncio.create_task(cls._audit_sink.record(meta, diff))

        # Ⅲ. Event Fan-out
        for s in cls._event_sinks:
            asyncio.create_task(s.publish(meta, diff))

```

1. Validation 어댑터 – 기존 코드 재사용

```
from core.validation.service import ValidationService
class RuleValidator(BaseValidator):
    async def validate(self, meta, diff):
        result = await ValidationService().validate_patch(diff)
        if not result.is_valid:
            raise HTTPException(422, detail=result.errors)

```

- `tampering_detection`, `input_sanitization` 등도 같은 방식으로 여러 Validator 클래스로 래핑
1. Event Sink 연결

```
from core.event_publisher.unified_publisher import UnifiedPublisher
class NATSSink(BaseSink):
    async def publish(self, meta, diff):
        await UnifiedPublisher.publish("doc.modified", diff, headers={
            "trace-id": meta.trace_id, "author": meta.author
        })

```

- Kafka / Webhook 추후 확장: `BaseSink` 인터페이스만 추가
1. Audit Sink ― 이미 존재`core/audit/audit_middleware.py` 안의 `publish_audit_event` 함수 → 클래스로 분리하여 등록

```python
CommitHookPipeline._audit_sink = AuditSink()

```

1. **Pipeline 등록** (Data-Kernel start-up)

```python
CommitHookPipeline._validators = [RuleValidator(), TamperValidator()]
CommitHookPipeline._event_sinks = [NATSSink()]

```

- CI 단계에서 diff → validator 테스트를 “플러그인 방식” 으로 주입 가능
1. TerminusDB Roll-back 처리
    - ValidationError 발생 시 TerminusDB `/api/branch/{branch}/reset/{prev_commit}` 호출로 자동 되돌림
    (TerminusDB 는 soft-fail rollback API 제공)
2. **옵션 플래그 & 성능**
    
    • `VALIDATION_ASYNC=true` 이면 Validator 를 Task 로 fire-and-forget 하게 하여 레이턴시 완화
    
    • Diff 크기 > 10 MB 면 Validation skip 후 배치 Validator 큐에 적재
    

──────────────────────────────────
D. 코드베이스 수정 범위

──────────────────────────────────
• `data_kernel/hook/` 새 디렉터리 ≈ 250 LOC

• 기존 서비스에서 개별 `ValidationService.validate()` 직접 호출하고 있는 부분 **삭제** → 통합

• `UnifiedPublisher` 내 `connect()` 미구현 문제 (#NATS) → 이 단계에서 동시에 마무리 필요

──────────────────────────────────
E. 테스트 시나리오

1. 유효 패치: POST → 200, CommitHookPipeline 통과, NATS 메시지 수신
2. PII 규칙 위반 패치: POST → 422, DB 롤백 확인, 이벤트 발행 없음
3. 네트워크 오류로 EventSink 실패: 커밋은 유지, Retry Queue(일명 Outbox) 로 전송
4. Trace-ID 헤더가 Audit 이벤트와 NATS 메시지 양쪽에 동일하게 기록

──────────────────────────────────
F. 성공 지표

• Validation 누락률 0 % (모든 write path가 Pipeline 통해간다)

• 서비스별 소스코드에서 TerminusDB diff / 이벤트 발행 로직 **99 % 제거**

• Audit, Metrics 대시보드에서 Commit-ID ↔ Trace-ID 매핑 확인 가능

[STEP4.md]가 끝나면 **데이터 무결성과 이벤트 일원화** 가 확보되어, 이어질 [STEP5.md](무거운 기능 MSA 분리) 를 진행하더라도 공통 파이프라인이 그대로 재사용됩니다.