# ① Data-Kernel 게이트웨이 구현 ― “FastAPI ↔ TerminusDB HTTP”

(현재 코드베이스를 그대로 활용해 **하루 안에 PoC** 를 올릴 수 있는 수준으로 기술 상세를 적었습니다.)

────────────────────────────
A. WHY? (현재 구조의 한계)
────────────────────────────
• 거의 모든 모듈이 `database/clients/terminus_db.py::TerminusDBClient` 를 **직접 인스턴스화** →

– 커넥션 풀 난립, mTLS 재협상 다중 발생

– Trace / Author / Commit-msg 규칙을 **모듈별로 중복** 구현

• TerminusDB REST 엔드포인트가 외부 네트워크에 그대로 노출 → IAM 없이 접근 가능

→ “Gateway-패턴” 으로 중앙화해 **보안·성능·운영 일관성** 확보가 1단계 목표

────────────────────────────
B. WHAT? (구성 그림)
────────────────────────────

```
         +--------------+       HTTP(S)
[OMS] ---| Data-Kernel  |------------------> TerminusDB 6363/tcp
         |   Gateway    |  (1) Health
         |  FastAPI     |  (2) CRUD /db/:db/doc
         +--------------+  (3) Query /db/:db/woql
             ▲   ▲
             |   └── OpenTelemetry, RBAC, Author-Injector
             └───── gRPC Server (internal) – Step-2 에서 활용

```

────────────────────────────
C. HOW? (구현 단계)
────────────────────────────

1. 디렉터리/파일 스캐폴딩

```
oms-monolith/
└─ data_kernel/
   ├─ api/
   │   ├─ __init__.py
   │   ├─ router.py          # FastAPI Router
   │   └─ deps.py            # Depends( get_db_client, get_commit_meta )
   ├─ service/
   │   └─ terminus_service.py # Thin Wrapper(현 TerminusDBClient 재사용)
   ├─ main.py                # create_app()
   └─ proto/
       └─ data_kernel.proto  # (gRPC 정의 – Step-2 대비)

```

1. 서비스 레이어 (`terminus_service.py`)
    
    • `class TerminusService` — 내부에 **싱글턴** `TerminusDBClient` 보관
    
    • 메소드: `get_document`, `insert_document`, `update_document`, `query`, `branch_switch` …
    
    • 모든 메소드에 `@trace_method` + 커스텀 `@commit_author` 데코레이터 부착
    
    - Author 값은 **Request State** (`request.state.user_id`) 에서 자동 취득
2. FastAPI 라우터 (`router.py`)

```python
router = APIRouter(prefix="/db/{db_name}", tags=["data-kernel"])

@router.get("/doc/{doc_id}")
async def read_doc(db_name: str, doc_id: str,
                   svc: TerminusService = Depends(get_service)):
    return await svc.get_document(db_name, doc_id)

@router.post("/doc")
async def create_doc(db_name: str, payload: Dict[str, Any],
                     svc: TerminusService = Depends(get_service),
                     meta: CommitMeta = Depends(get_commit_meta)):
    return await svc.insert_document(db_name, payload, meta.commit_msg)

```

- **Query / Vector Search / Branch-Revision** 는 `?branch=` `?rev=` `?vector=true` 쿼리 파라미터로 분기
1. 공통 Dependency (`deps.py`)

```python
async def get_service() -> TerminusService:
    return GatewayContext.service_singleton   # 애플리케이션 시작 시 한 번 생성

async def get_commit_meta(request: Request) -> CommitMeta:
    return CommitMeta(
        author=request.state.user_id or "anonymous",
        trace_id=request.headers.get("traceparent"),
        commit_msg=request.headers.get("X-Commit-Msg", "OMS-Gateway write")
    )

```

1. 미들웨어 체인 (FastAPI `main.py`)

```python
app = FastAPI()
FastAPIInstrumentor().instrument_app(app)     # OTel
app.add_middleware(AuthMiddleware)            # JWT → request.state.user_id
app.add_middleware(RBACMiddleware)            # DB-단위 권한
app.include_router(router)

```

1. 현재 코드와의 연결
① **단계적 전환 플래그**

```python
USE_DATA_KERNEL_GATEWAY = os.getenv("USE_DATA_KERNEL_GATEWAY", "false") == "true"

```

② `core/...` 모듈에서

```python
if USE_DATA_KERNEL_GATEWAY:
    from data_kernel.client import DataKernelStub  # gRPC Stub (Step-2)
else:
    from database.clients.terminus_db import TerminusDBClient

```

→ Step-1 에서는 `USE_DATA_KERNEL_GATEWAY=false` 로 두고 **Gateway 기능 검증** 먼저 진행

1. Docker / Compose 추가

```yaml
services:
  data-kernel:
    build: ./oms-monolith/data_kernel
    environment:
      TERMINUSDB_ENDPOINT: <http://terminusdb:6363>
      TERMINUSDB_USER: admin
      TERMINUSDB_PASS: ${TERMINUSDB_PASS}
    depends_on:
      - terminusdb
    networks:
      - oms_net

```

────────────────────────────
D. 검증 체크리스트
────────────────────────────

1. `curl <http://data-kernel:8080/health`> → 200 & TerminusDB ping 성공
2. CRUD Round-trip : Create → Read → Update → Branch Switch → Read (검증 시 Revision 결과 다름)
3. OTel Trace ID 가 TerminusDB HTTP 헤더로 전파되는지 (`unified_http_client` 자동 주입 확인)
4. Commit Meta 의 `author`, `message` 가 TerminusDB `_commits` 레이어에 기록되는지 확인

────────────────────────────
E. 예상 코드 변경 범위
────────────────────────────
• **신규** `data_kernel/` 폴더: ≈ 500 LOC

• 기존 `bootstrp/app.py` 수정량: 5 라인 (router mount)

• 기존 비즈니스 모듈 수정 없음 (환경변수 플래그만)

이렇게 하면 **현재 코드베이스를 크게 건드리지 않고** TerminusDB 접근을 중앙 게이트웨이로 우회시켜, 이후 단계(Stub 치환·Commit Hook 통합·MSA 분리)를 안전하게 진행할 수 있습니다.