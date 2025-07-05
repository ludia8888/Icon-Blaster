# ② Terminus Gateway gRPC Stub로 전환 ― “모든 서비스에서 TerminusDBClient 직접 호출 → Stub 호출”

(현재 코드베이스 기준·단계적 마이그레이션 전략 포함)

────────────────────────────
A. WHY?
────────────────────────────
• Step-1 FastAPI 게이트웨이만으로는 **Python 이외 서비스**(Rust, Go, 외부 Batch) 가 재사용하기 어렵고

• HTTP Round-trip + JSON 직렬화 → 대용량 쿼리에서 레이턴시 ↑

• gRPC 는

– 양방향 스트리밍(대형 WOQL 결과)

– Deadlines / Retries / mTLS / 헤더-메타데이터 전달(Otel Interceptor)

– Stub 코드 자동 생성 → “한 줄 DI 교체” 만으로 종속성 제거

────────────────────────────
B. WHAT? (타깃 아키텍처)
────────────────────────────

```
┌──────────────────────────────────────┐
│            Data-Kernel Pod           │
│  ┌──────────────┐   ┌─────────────┐ │
│  │ FastAPI REST │   │ gRPC Server │ │  <-- 같은 컨테이너/포트 50051
│  └──────────────┘   └─────────────┘ │
└────────────┬────────────────────────┘
             │
      gRPC Stub (protobuf)
             │
┌────────────▼──────────────┐   ┌───────────────────┐
│   OMS-Monolith (Python)   │   │ Embedding-Service │
│  +- TerminusGatewayClient │   │  +- TerminusStub  │
└───────────────────────────┘   └───────────────────┘

```

────────────────────────────
C. HOW? (구현 단계)
────────────────────────────

1. proto 정의 ( `data_kernel/proto/data_kernel.proto` )

```
syntax = "proto3";

package data_kernel;

message CommitMeta {
  string author      = 1;
  string commit_msg  = 2;
  string trace_id    = 3;
  string branch      = 4;
}

message DocumentId { string id = 1; }

message Document   { bytes json = 1; }

service DocumentService {
  rpc Get   (DocumentId) returns (Document);
  rpc Put   (Document)   returns (DocumentId);
  rpc Patch (Document)   returns (DocumentId);
}

message WOQL { string query = 1; CommitMeta meta = 2; }
service QueryService {
  rpc Execute (WOQL) returns (stream Document);
}

```

- **stream Document** 로 대용량 결과를 분할 전송

• CommitMeta → TraceID·Author 자동 주입

1. 서버 구현 (`data_kernel/grpc_server.py`)

```python
import grpc, asyncio
from opentelemetry.instrumentation.grpc import server_interceptor
from .service.terminus_service import TerminusService
from .proto import data_kernel_pb2_grpc as pb2_grpc, data_kernel_pb2 as pb2

class DocumentServicer(pb2_grpc.DocumentServiceServicer):
    def __init__(self, svc: TerminusService):
        self.svc = svc
    async def Get(self, request, context):
        doc = await self.svc.get_document("oms", request.id)
        return pb2.Document(json=json.dumps(doc).encode())

# ... Put, Patch 동일

async def serve():
    server = grpc.aio.server(
        interceptors=[server_interceptor()]
    )
    pb2_grpc.add_DocumentServiceServicer_to_server(
        DocumentServicer(TerminusService()), server)
    server.add_insecure_port("[::]:50051")
    await server.start()
    await server.wait_for_termination()

```

- 컨테이너 엔트리포인트에서 `uvicorn data_kernel.main:app & python -m data_kernel.grpc_server` 로 두 서버 동시 실행
1. Stub 생성 자동화

```bash
python -m grpc_tools.protoc -I data_kernel/proto \\
  --python_out=oms-monolith/sdk \\
  --grpc_python_out=oms-monolith/sdk \\
  data_kernel/proto/data_kernel.proto

```

- Makefile / CI workflow 에 추가
1. 공통 클라이언트 래퍼 (`shared/data_kernel_client.py`)

```python
class TerminusGatewayClient:
    def __init__(self, target="data-kernel:50051"):
        self.channel = grpc.aio.insecure_channel(target,
            interceptors=[client_otlp_interceptor()])
        self.stub = dk_pb2_grpc.DocumentServiceStub(self.channel)
    async def get_document(self, doc_id:str):
        resp = await self.stub.Get(dk_pb2.DocumentId(id=doc_id))
        return json.loads(resp.json)
    # put, patch 동일...

```

- 메서드 시그니처를 **기존 TerminusDBClient 와 동일** 하게 맞춰 리팩터링 비용 최소화
1. 단계적 DI 교체

```python
USE_GATEWAY = os.getenv("USE_GATEWAY", "false") == "true"

def get_db_client():
    if USE_GATEWAY:
        return TerminusGatewayClient()
    else:
        return TerminusDBClient(...)

```

모든 서비스의 `bootstrap` 또는 `providers/database.py` 한 곳만 수정 → 나머지 코드 변경 無.

1. Trace / Author 자동 주입
• gRPC client-interceptor 에서:

```python
def client_otlp_interceptor():
    class _Interceptor(grpc.aio.ClientInterceptor):
        async def intercept_unary_unary(self, cont, call, req, meta):
            meta = list(meta) + [
                ('traceparent', get_current_trace_parent()),
                ('author', get_current_user_id() or 'system')
            ]
            return await cont(req, meta)
    return _Interceptor()

```

1. TLS / mTLS
    
    • `server.add_secure_port("[::]:50051", grpc.ssl_server_credentials(...))`
    
    • `grpc.aio.secure_channel()` + Certificates 경로를 환경변수로 주입
    
2. 단위/통합 테스트

```
pytest -q tests/integration/test_gateway_stub.py
  - create, get, patch
  - trace_id round-trip
  - deadline=3s 미만 쿼리 timeout 동작

```

────────────────────────────
D. 마이그레이션·롤아웃 순서
────────────────────────────

1. 컨테이너에 gRPC 서버 추가 → `grpc_health_probe` 로 readiness 확인
2. **OMS Monolith** 환경변수 `USE_GATEWAY=true` 설정 → E2E Regression 실행
3. Embedding-Service, Scheduler … 순차적으로 클라이언트 교체
4. TerminusDB 6363 포트를 **네트워크 격리**(internal VPC only) → 직방 호출 불가 상태로 최종 전환

────────────────────────────
E. 성공 Criteria
────────────────────────────
• 95% 이상의 기존 단위 테스트 통과 (CRUD·WOQL)

• gRPC Round-trip 평균 레이턴시 ≤ HTTP 대비 40% 감소

• TerminusDB 연결 수: “서비스 수 × N” → “Data-Kernel 1개” 로 감소

• OTel Trace Tree 상, 서비스 ↔ Data-Kernel hop 이 부모-자식 Span 으로 정확히 연결

이제 Step-2가 완료되면, 이후 **Branch/Author 규칙 미들웨어**(Step-3) 를 Data-Kernel Stub 내 메타데이터로 밀어넣을 준비가 됩니다.