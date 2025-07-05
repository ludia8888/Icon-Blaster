# ③ Branch 네이밍·Author 규칙 확립 ＋ 미들웨어 자동 주입

(이미 Step-2 까지 완료되었다는 가정 하에, **현재 코드베이스** 에 구체적으로 적용하는 방법)

──────────────────────────────────
A. WHY?
──────────────────────────────────
• TerminusDB 는 Git-like 브랜치·커밋 메타를 갖지만, 지금은

– `db_name="oms"` 하나에 모든 서비스가 push

– `author="system"` 등 하드코딩 다수

– 브랜치 규칙이 없어 “임베딩 결과” 와 “비즈니스 데이터” 가 뒤섞임

→ 데이터 커플링·롤백 지점을 찾기 어렵고, 감사(Audit) 체인 단절

──────────────────────────────────
B. RULE 설계
──────────────────────────────────

1. 브랜치 네이밍 컨벤션

```
<env>/<service>/<purpose>
예) prod/embedding/main
     prod/oms/main
     dev/<git-sha>/scratch

```

- env : dev | staging | prod

• service : oms | embedding | scheduler …

• purpose : main | snapshot-YYYYMMDD | migration-<id> …

1. Author 규칙
    
    • JWT 의 `sub`(user id) + 서비스명 suffix
    
    • 백그라운드 잡 : `system@<service>`
    
    • 예) `alice@oms`, `system@scheduler`
    
2. Commit-msg 규칙 (자동)
    
    • `<HTTP_METHOD> <path> | trace=<trace-id>`
    
    • 예) `POST /documents | trace=4a1c…`
    

──────────────────────────────────
C. HOW? (구현 단계)
──────────────────────────────────

1. 컨벤션 상수 선언
    
    `shared/terminus_context/constants.py`
    
    ```python
    ENV = os.getenv("DEPLOY_ENV", "dev")
    DEFAULT_BRANCH = f"{ENV}/oms/main"
    
    ```
    
2. **Request ⇨ ContextVar**
    
    `middleware/terminus_context.py`
    
    ```python
    _author_ctx   = contextvars.ContextVar("author",  default="anonymous@unknown")
    _branch_ctx   = contextvars.ContextVar("branch",  default=DEFAULT_BRANCH)
    _trace_ctx    = contextvars.ContextVar("trace_id", default="")
    
    class TerminusContextMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):
            # 1) Trace-ID
            span_ctx = trace.get_current_span().get_span_context()
            _trace_ctx.set(span_ctx.trace_id.to_hex())
            # 2) Author
            user = getattr(request.state, "user", None)
            svc  = os.getenv("SERVICE_NAME", "oms")
            _author_ctx.set(f"{(user.id if user else 'anonymous')}@{svc}")
            # 3) Branch
            branch = request.headers.get("X-Branch") or DEFAULT_BRANCH
            _branch_ctx.set(branch)
            response = await call_next(request)
            return response
    
    ```
    
    - `bootstrap/app.py` 체인에 **AuthMiddleware → TerminusContextMiddleware → RBAC…** 순서로 삽입
3. **Data-Kernel Stub / TerminusGatewayClient 에서 자동 주입**
    
    `shared/data_kernel_client.py`
    
    ```python
    async def _meta() -> dk_pb2.CommitMeta:
        return dk_pb2.CommitMeta(
             author   = _author_ctx.get(),
             branch   = _branch_ctx.get(),
             trace_id = _trace_ctx.get(),
             commit_msg = build_commit_msg()
        )
    
    ```
    
    - 모든 `Put`, `Patch`, `WOQL` 호출 파라미터에 `_meta()` 주입
4. TerminusDB Commit-Hook (Data-Kernel 내부)
    
    `data_kernel/service/commit_hook.py`
    
    ```python
    async def validate_and_emit(meta: CommitMeta, diff: Dict):
        # ① Validation – schema, PII, tampering…
        await ValidationService.validate(diff, meta=meta)
        # ② Event – NATS / Audit
        await EventGateway.publish("commit", meta=meta, diff=diff)
    
    ```
    
    - Data-Kernel 서버의 `DocumentService.Put/Patch` 에서 커밋 직후 호출
5. **RBAC 미들웨어 확장**
    
    • 브랜치 명에 따라 읽기 전용/쓰기 금지 정책 적용
    
    • 예: `if branch.endswith("/snapshot-*"): raise HTTP_403`
    
6. 기존 코드 영향 최소화
    
    • 기존 모듈은 `from shared.terminus_context import get_branch` 식 으로 현재 브랜치만 조회
    
    • 직접 브랜치 지정이 필요하면 `with OverrideBranch("dev/embedding/tmp"):` 컨텍스트 헬퍼 제공
    

──────────────────────────────────
D. 테스트 시나리오
──────────────────────────────────

1. `POST /api/v1/documents` (JWT-user=alice)
    
    → Commit-meta: `author="alice@oms"`, `branch="dev/oms/main"`
    
    → `_commits` 레이어 검증
    
2. `curl -H "X-Branch: prod/embedding/main" ...`
    
    → 미들웨어가 브랜치 설정, 읽기/쓰기 모두 해당 브랜치 반영
    
3. Trace-ID 전파 검사
    
    • Jaeger 스팬 트리에서 “POST /db” → “TerminusDB PUT” 부모-자식 관계 확인
    
4. 권한 정책 검사
    
    • `prod/oms/snapshot-202405` 에 쓰기 요청 → 403
    

──────────────────────────────────
E. 완료 기준 (Definition of Done)
──────────────────────────────────
• 모든 단위·E2E 테스트 통과 (브랜치·author 검증 포함)

• `_commits` 를 조회했을 때 `author`·`branch` 필드가 규칙대로 일관성 있게 기록

• 서비스 코드에 `db_name`·`author` 관련 하드코딩이 **제거 or 무시**

• Audit & Event Gateway가 commit-meta 를 수신하고 downstream 에서 trace_id 연결

[STEP3.md] 를 마치면 **데이터 계층의 멀티-테넌시와 추적성**이 보장되므로, 이어지는 [STEP4.md](Commit Hook 통합) 에서 Validation·Event 를 완전 자동화할 토대가 마련됩니다.