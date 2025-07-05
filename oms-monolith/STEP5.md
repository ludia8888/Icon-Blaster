# ⑤ 외부 무거운 컴포넌트의 단계적 MSA 분리

(현재 코드베이스를 그대로 활용하면서 “Embedding → Scheduler → Event-Gateway” 순으로 떼어내는 실천 가이드)

──────────────────────────────────
0. 공통 전제

• Step-1~4 로 **Data-Kernel 게이트웨이 + gRPC Stub + CommitHook** 가 이미 안정화.

• 모든 서비스가 TerminusDB 직접 접근 대신 Stub 사용.

• OTel, Author, Branch 메타데이터가 header/metadata 로 전파됨.

──────────────────────────────────
A. Vector-Embedding Service 분리
──────────────────────────────────

1. 코드 이동
    
    ```
    mkdir services/embedding-service
    cp -r core/embeddings services/embedding-service/app
    
    ```
    
    – `providers.py`, `service.py` 그대로 사용하되 `TerminusGatewayClient` 로교체
    
    – ML 모델( `sentence-transformers`, `torch`) 의존성만 포함하는 `requirements.txt` 작성
    
2. FastAPI + gRPC Dual 서버
    
    ```
    uvicorn app.api:fastapi_app  # /embedding, /similarity, /health
    python -m grpc_server        # EmbeddingServiceStub
    
    ```
    
    – gRPC 는 대량 벡터 전송 시 효율적, HTTP 엔드포인트는 간편 테스트용
    
3. 캐시·DB 연결
    
    – Redis 주소를 ENV 로 주입 (`REDIS_URL=redis://redis:6379/5`)
    
    – Terminus 브랜치: `${ENV}/embedding/main`
    
4. OMS 호출부 교체
    
    ```python
    if USE_EMBEDDING_MS:
        from sdk.embedding_stub import EmbeddingStub
        embedding_client = EmbeddingStub("embedding-service:50055")
    else:
        from core.embeddings.service import VectorEmbeddingService
    
    ```
    
5. Dockerfile & Compose
    
    ```
    FROM python:3.11-slim
    RUN pip install -r requirements.txt
    CMD ["bash", "-c", "uvicorn ... & python -m grpc_server"]
    
    ```
    
6. 프로덕션 검증
    
    – Cold-start 시간 측정 (모델 preload)
    
    – CPU/GPU 자원 설정, HPA 기준은 **GPU 메모리 사용률** 또는 **RQ per second**
    

──────────────────────────────────
B. Advanced-Scheduler Service 분리
──────────────────────────────────

1. 코드 이동
    
    ```
    services/scheduler-service/app/
      ├─ scheduler/   # core/scheduler/advanced_scheduler.py 그대로
      ├─ api.py       # REST: /jobs, /executions
      └─ worker.py    # Job Executor
    
    ```
    
2. Terminus 의존성
    
    – Job 메타·체크포인트는 TerminusDB `prod/scheduler/main` 브랜치에 저장
    
    – Gateway Stub 사용
    
3. 시스템 아키텍처
    
    • “Scheduler API” 컨테이너: FastAPI + gRPC → Job Spec 등록, 조회
    
    • “Scheduler Worker” 컨테이너: 동일 이미지, `worker.py run` 로 실행 → 실질 작업 수행 + 결과 Commit
    
4. OMS 연동
    
    – 기존 `core/scheduler/advanced_scheduler.py` import 부분을
    
    `from sdk.scheduler_stub import SchedulerStub` 로 교체
    
    – 스케줄 등록/취소만 Stub RPC 호출
    
5. 장애 격리
    
    – APScheduler JobStore 는 Redis → Redis Sentinel 로 전환하여 HA 확보
    
    – Worker 컨테이너가 죽어도 API 컨테이너는 살아있도록 Deployment 분리
    

──────────────────────────────────
C. Event-Gateway Service 분리
──────────────────────────────────

1. 현황 문제
    
    – `core/event_publisher/` 와 `event_subscriber/` 모듈이 직접 NATS 연결; `connect()` 미구현 → 실패 로그
    
    – 여러 마이크로서비스가 NATS / CloudEvents 연동을 반복 구현
    
2. 새로운 구조
    
    ```
    services/event-gateway/
      ├─ main.py       # FastAPI + NATS connection pool
      ├─ subscriber.py # Subject → gRPC/Webhook fan-out
      ├─ schemas/      # CloudEvents JSON-Schema
      └─ proto/        # EventGateway.proto
    
    ```
    
    – API: gRPC `Publish(Event)` , `Subscribe(Subject)`
    
    – 내부적으로 NATS JetStream 사용, Durable consumer 제공
    
3. 기존 코드 제거/교체
    
    – `UnifiedPublisher.publish()` 구현을 “gRPC Publish 호출” 로 단순화
    
    – `EventSubscriber` 는 필요 시 gRPC 스트리밍 또는 Gateway 의 WebHook 기능 사용
    
4. Audit & CommitHook 연동
    
    – CommitHookPipeline 의 Event Sink 를 `EventGatewayClient` 로 변경 (NATS 세부 로직 삭제)
    
5. Observability
    
    – Event-Gateway 자체가 NATS latency·ack 실패를 Prometheus metric 으로 노출
    
    – Traceparent 헤더 → CloudEvents `traceparent` extension 필드에 주입
    

──────────────────────────────────
D. 롤아웃 순서
──────────────────────────────────

1. **Embedding-Service** 컨테이너 먼저 배포
– OMS `USE_EMBEDDING_MS=true` 전환 → E2E 통과 확인
2. **Scheduler-Service** 배포 및 OMS 연동
– Cron/Interval 잡 정상 실행 확인, Worker 스케일 테스트
3. **Event-Gateway** 배포
– CommitHook → Gateway → NATS 루프가 정상 동작 ↔ Jaeger Trace 트리 확인
4. TerminusDB 6363 포트를 VPC 내부 전용으로 변경 (직접 접근 완전 차단)
5. 기존 `core/embeddings`, `core/scheduler`, `core/event_*` 모듈 코드를 **deprecated** 표기 → 1개월 후 삭제

──────────────────────────────────
E. 체크리스트 / 성공 기준
──────────────────────────────────
• OMS 이미지 크기: 2.1 GB → 500 MB 이하

• Embedding-Service cold-start ≤ 25 s, 평균 응답 95-th ≤ 150 ms

• Scheduler 잡 실패 시 OMS API 영향 無 (격리)

• NATS 연결 실패해도 OMS 요청은 200 OK (Gateway 재시도 큐)

• 모든 Trace 가 “client-span → gateway-span → terminus-span” 구조로 연속

──────────────────────────────────
F. 추후 확장
──────────────────────────────────
• Embedding 모델 버전·A/B 테스트 → Gateway 에 `metadata.model_version` tag 추가

• Scheduler 가 Helm-Chart release/promotion 자동화에 포함되면 GitOps 완전 적용

• Event-Gateway 에 Kafka connector 추가, 이벤트 복제 가능

Step-5 까지 완료되면, OMS-Monolith 는 오로지 **경량 CRUD / GraphQL API** 역할만 남고, 리소스 헝거 서비스는 각각 독립 스케일링・배포가 가능해집니다.

---

## **총평**

- **장점** — TerminusDB 의 브랜치·타임트래블·온톨로지를 “단일 진실 소스(SSoT)”로 삼고, 나머지 MSA를 연산·인터페이스 전용으로 두는 구조는 Palantir Foundry의 핵심 철학(Asset-First, Strong Ontology, Immutable Log)을 가장 경제적으로 재현할 수 있는 노선입니다.
- **위험요소** — ① 단일 TerminusDB 인스턴스의 **단일 장애점(SPOF)**, ② 브랜치 난립에 따른 **스토리지·거버넌스 비용**, ③ Commit-Hook에 과도한 로직이 쌓일 때의 **레이턴시 급증**, ④ gRPC Gateway가 곧 **API 방화벽** 역할까지 떠안게 되는 **보안·운영 복잡도** 등은 초기 설계에서 반드시 관리 전략을 세워야 합니다.
- **핵심 조언** — ① TerminusDB 클러스터링·백업/복구 플랜을 PoC 단계에서 마련, ② 브랜치/Author 컨벤션을 **“제거 정책(garbage collection)까지 포함한 거버넌스 규칙”**으로 구체화, ③ Commit-Hook 파이프라인은 **“Sync-검증 / Async-파생작업”** 두 단계로 분리, ④ Gateway 컨테이너를 **이중화(활성-활성)** 하고 모든 서비스가 **Circuit Breaker** 를 기본 내장하도록 하십시오.