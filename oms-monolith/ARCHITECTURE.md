# 🏛️ OMS 시스템 아키텍처 상세 문서

## 📋 목차
1. [전체 시스템 아키텍처](#전체-시스템-아키텍처)
2. [하이브리드 아키텍처 전략](#하이브리드-아키텍처-전략)
3. [마이크로서비스 아키텍처](#마이크로서비스-아키텍처)
4. [데이터 계층 설계](#데이터-계층-설계)
5. [인증 및 보안 아키텍처](#인증-및-보안-아키텍처)
6. [모니터링 및 관찰성](#모니터링-및-관찰성)
7. [성능 최적화](#성능-최적화)
8. [배포 아키텍처](#배포-아키텍처)

## 📊 전체 시스템 아키텍처

OMS(Ontology Management System)는 **하이브리드 아키텍처**를 기반으로 한 엔터프라이즈급 온톨로지 관리 플랫폼입니다. 모놀리스의 단순함과 마이크로서비스의 확장성을 모두 제공하며, 환경 변수를 통해 점진적 마이그레이션을 지원합니다.

```mermaid
graph TB
    subgraph "클라이언트 계층"
        WebUI[웹 UI<br/>React/TypeScript]
        APIClient[API 클라이언트<br/>REST/GraphQL]
        CLI[CLI 도구<br/>oms-cli]
    end

    subgraph "API 게이트웨이"
        Gateway[API Gateway<br/>NGINX 라우팅]
    end

    subgraph "애플리케이션 계층"
        MainAPI[메인 API 서버<br/>FastAPI:8000<br/>- REST 엔드포인트<br/>- 통합 인증<br/>- 보안 DB 접근]
        
        GraphQLHTTP[GraphQL HTTP<br/>Strawberry:8006<br/>- 스키마 쿼리<br/>- 뮤테이션 지원]
        
        GraphQLWS[GraphQL WebSocket<br/>Strawberry:8004<br/>- 실시간 구독<br/>- 세션 관리]
    end

    subgraph "마이크로서비스 계층 (선택적)"
        EmbeddingMS[Embedding Service<br/>:8001/:50055<br/>- 벡터 임베딩<br/>- 유사도 검색]
        
        SchedulerMS[Scheduler Service<br/>:8002/:50056<br/>- APScheduler<br/>- 백그라운드 작업]
        
        EventGateway[Event Gateway<br/>:8003/:50057<br/>- NATS JetStream<br/>- CloudEvents]
        
        DataKernel[Data-Kernel Gateway<br/>:8080/:50051<br/>- TerminusDB 추상화<br/>- gRPC 인터페이스]
    end

    subgraph "데이터 계층"
        TerminusDB[(TerminusDB:6363<br/>그래프 데이터베이스<br/>온톨로지 저장)]
        PostgreSQL[(PostgreSQL:5432<br/>관계형 데이터베이스<br/>감사 로그)]
        Redis[(Redis:6379<br/>인메모리 캐시<br/>세션 관리)]
    end

    subgraph "메시징"
        NATS[NATS:4222<br/>이벤트 스트리밍<br/>JetStream]
    end

    subgraph "모니터링"
        Prometheus[Prometheus:9091<br/>메트릭 수집]
        Grafana[Grafana:3000<br/>대시보드]
        Jaeger[Jaeger:16686<br/>분산 추적]
    end

    WebUI --> Gateway
    APIClient --> Gateway
    CLI --> Gateway
    
    Gateway --> MainAPI
    Gateway --> GraphQLHTTP
    Gateway --> GraphQLWS
    
    MainAPI -.->|USE_EMBEDDING_MS=true| EmbeddingMS
    MainAPI -.->|USE_SCHEDULER_MS=true| SchedulerMS
    MainAPI -.->|USE_EVENT_GATEWAY=true| EventGateway
    MainAPI -.->|USE_DATA_KERNEL_GATEWAY=true| DataKernel
    
    MainAPI --> TerminusDB
    MainAPI --> PostgreSQL
    MainAPI --> Redis
    
    EmbeddingMS --> TerminusDB
    SchedulerMS --> Redis
    EventGateway --> NATS
    DataKernel --> TerminusDB
    
    MainAPI --> Prometheus
    EmbeddingMS --> Prometheus
    SchedulerMS --> Prometheus
    EventGateway --> Prometheus
    
    Prometheus --> Grafana
    MainAPI --> Jaeger
```

## 🔄 하이브리드 아키텍처 전략

### 설계 철학

OMS는 **점진적 마이크로서비스 마이그레이션**을 지원하는 하이브리드 아키텍처를 채택했습니다. 이는 다음 원칙을 기반으로 합니다:

1. **Feature Flag 기반 라우팅**: 환경 변수로 서비스 분리 제어
2. **Stub Pattern**: 일관된 인터페이스로 구현 투명성 제공
3. **Backward Compatibility**: 기존 코드 변경 최소화
4. **Independent Scaling**: 서비스별 독립적 확장 가능

### 환경 변수 제어

```bash
# 모놀리스 모드 (기본)
USE_EMBEDDING_MS=false
USE_SCHEDULER_MS=false
USE_EVENT_GATEWAY=false
USE_DATA_KERNEL_GATEWAY=false

# 하이브리드 모드 (점진적 마이그레이션)
USE_EMBEDDING_MS=true      # 임베딩만 마이크로서비스로
USE_SCHEDULER_MS=false     # 나머지는 모놀리스에서 처리
USE_EVENT_GATEWAY=false
USE_DATA_KERNEL_GATEWAY=false

# 풀 마이크로서비스 모드
USE_EMBEDDING_MS=true
USE_SCHEDULER_MS=true
USE_EVENT_GATEWAY=true
USE_DATA_KERNEL_GATEWAY=true
```

### Stub Pattern 구현

```python
# shared/embedding_stub.py - 인터페이스 통일
class EmbeddingStub:
    def __init__(self):
        if os.getenv('USE_EMBEDDING_MS') == 'true':
            self.client = EmbeddingServiceClient()  # gRPC 클라이언트
        else:
            self.client = LocalEmbeddingService()   # 로컬 구현
    
    async def embed_text(self, text: str) -> List[float]:
        return await self.client.embed_text(text)

# bootstrap/providers/embedding.py - DI 컨테이너
class EmbeddingServiceProvider(Provider[EmbeddingStub]):
    def get(self) -> EmbeddingStub:
        return EmbeddingStub()
```

## 🏗️ 마이크로서비스 아키텍처

### 서비스 분해도

| 서비스 | 포트 | 역할 | 상태 | 환경 변수 |
|--------|------|------|------|-----------|
| **Main API** | 8000 | REST API, 인증, 핵심 로직 | ✅ 활성 | - |
| **GraphQL HTTP** | 8006 | HTTP 기반 GraphQL 쿼리 | ✅ 활성 | - |
| **GraphQL WebSocket** | 8004 | 실시간 구독 | ✅ 활성 | - |
| **Embedding Service** | 8001/50055 | 벡터 임베딩, 유사도 검색 | ✅ 구현 완료 | `USE_EMBEDDING_MS` |
| **Scheduler Service** | 8002/50056 | APScheduler, 백그라운드 작업 | ✅ 구현 완료 | `USE_SCHEDULER_MS` |
| **Event Gateway** | 8003/50057 | NATS 이벤트 스트리밍 | ✅ 구현 완료 | `USE_EVENT_GATEWAY` |
| **Data-Kernel Gateway** | 8080/50051 | TerminusDB 추상화 계층 | ✅ 구현 완료 | `USE_DATA_KERNEL_GATEWAY` |

### 1. Embedding Service

**위치**: `/services/embedding-service/`

```python
# 주요 기능
- 7개 임베딩 프로바이더 지원 (OpenAI, Cohere, HuggingFace 등)
- 폴백 체인 및 배치 처리
- GPU 가속 지원
- 벡터 유사도 검색

# 엔드포인트
POST /embed          # 단일 텍스트 임베딩
POST /embed_batch     # 배치 임베딩  
POST /similarity      # 유사도 검색
GET /health          # 헬스 체크
```

### 2. Scheduler Service

**위치**: `/services/scheduler-service/`

```python
# 주요 기능
- APScheduler 기반 작업 스케줄링
- Redis 영속성 지원
- 분산 워커 지원
- Cron 표현식 및 interval 스케줄링

# 엔드포인트
POST /jobs           # 작업 생성
GET /jobs            # 작업 목록
PUT /jobs/{id}       # 작업 수정
DELETE /jobs/{id}    # 작업 삭제
POST /jobs/{id}/run  # 즉시 실행
```

### 3. Event Gateway

**위치**: `/services/event-gateway/`

```python
# 주요 기능
- NATS JetStream 통합
- CloudEvents 1.0 표준 지원
- 웹훅 전달 및 재시도
- 이벤트 필터링 및 라우팅

# 엔드포인트
POST /events         # 이벤트 발행
POST /webhooks       # 웹훅 등록
GET /streams         # 스트림 목록
GET /health          # 헬스 체크
```

### 4. Data-Kernel Gateway

**위치**: `/data_kernel/`

```python
# 주요 기능
- TerminusDB REST API 추상화
- gRPC 인터페이스 제공
- 인증 미들웨어 통합
- 분산 추적 지원

# 엔드포인트
POST /query          # WOQL 쿼리 실행
POST /insert         # 데이터 삽입
PUT /update          # 데이터 업데이트
DELETE /delete       # 데이터 삭제
```

## 🗄️ 데이터 계층 설계

### 하이브리드 데이터베이스 전략

```mermaid
graph TB
    subgraph "애플리케이션 계층"
        API[API Server]
        Services[Microservices]
    end
    
    subgraph "데이터 접근 계층"
        SecureDB[SecureDatabaseAdapter<br/>자동 작성자 추적]
        UnifiedDB[UnifiedDatabaseClient<br/>데이터베이스 추상화]
    end
    
    subgraph "캐시 계층"
        LocalCache[Local Cache<br/>TTLCache]
        RedisCache[Redis Cache<br/>분산 캐시]
    end
    
    subgraph "영구 저장소"
        TerminusDB[(TerminusDB<br/>온톨로지 데이터)]
        PostgreSQL[(PostgreSQL<br/>감사 로그)]
        SQLite[(SQLite<br/>로컬 메타데이터)]
    end
    
    API --> SecureDB
    Services --> SecureDB
    SecureDB --> UnifiedDB
    
    UnifiedDB --> LocalCache
    LocalCache --> RedisCache
    RedisCache --> TerminusDB
    RedisCache --> PostgreSQL
    
    API --> SQLite
    
    TerminusDB -.->|감사 복제| PostgreSQL
```

### 데이터베이스 역할 분담

| 데이터베이스 | 주요 역할 | 데이터 유형 | 보안 기능 |
|-------------|-----------|-------------|-----------|
| **TerminusDB** | 비즈니스 로직 | 온톨로지, 스키마, 관계 | 감사 필드, 커밋 작성자 |
| **PostgreSQL** | 운영 메타데이터 | 감사 로그, 사용자, 정책 | 불변 감사 추적 |
| **Redis** | 고성능 캐시 | 세션, 캐시, 분산락 | 토큰 캐싱 |
| **SQLite** | 로컬 저장소 | 버전 추적, 메타데이터 | 로컬 감사 |

### 감사 필드 자동화

모든 데이터 변경에 자동으로 추가되는 보안 필드:

```json
{
  "_created_by": "사용자 ID",
  "_created_by_username": "사용자명", 
  "_created_at": "2025-07-05T12:00:00Z",
  "_updated_by": "마지막 수정자 ID",
  "_updated_by_username": "마지막 수정자명",
  "_updated_at": "2025-07-05T12:30:00Z",
  "_deleted": false,
  "_deleted_by": null,
  "_deleted_at": null
}
```

## 🔐 인증 및 보안 아키텍처

### 통합 인증 미들웨어 체인

```mermaid
flowchart TD
    A[HTTP Request + JWT Token] --> B[AuthMiddleware<br/>JWT 검증 & UserContext 생성]
    B --> C[DatabaseContextMiddleware<br/>사용자 컨텍스트 전파]
    C --> D[RBACMiddleware<br/>역할 기반 권한 검증]
    D --> E[AuditMiddleware<br/>보안 감사 로깅]
    E --> F[Route Handler<br/>UserContext + SecureDatabaseAdapter]
    F --> G[SecureDatabaseAdapter<br/>자동 작성자 추적]
    G --> H[TerminusDB/PostgreSQL<br/>보안 커밋]
```

### 보안 데이터베이스 작업 패턴

```python
# ✅ 올바른 패턴 - 자동 작성자 추적
from middleware.auth_middleware import get_current_user
from database.dependencies import get_secure_database

@router.post("/items")
async def create_item(
    item: ItemCreate,
    user: UserContext = Depends(get_current_user),
    db: SecureDatabaseAdapter = Depends(get_secure_database)
):
    # 작성자 정보가 자동으로 추가됨
    result = await db.create(
        user_context=user,
        collection="items", 
        document=item.dict()
    )
    return result
```

### 보안 작성자 문자열 형식

```
# 일반 사용자
alice.smith (alice123)|verified|ts:2025-07-05T12:00:00Z|sig:abc123...

# 서비스 계정
deployment-service (svc_deploy) [service]|verified|ts:2025-07-05T12:00:00Z|sig:def456...

# 위임된 작업
etl-service (svc_etl) [service] [delegated|on_behalf_of:john.doe|reason:scheduled import]|ts:2025-07-05T12:00:00Z
```

## 📊 모니터링 및 관찰성

### 모니터링 스택

**위치**: `/monitoring/`

```yaml
# docker-compose.monitoring.yml
services:
  prometheus:
    image: prom/prometheus:latest
    ports: ["9091:9090"]
    
  grafana:
    image: grafana/grafana:latest
    ports: ["3000:3000"]
    
  jaeger:
    image: jaegertracing/all-in-one:latest
    ports: ["16686:16686"]
    
  alertmanager:
    image: prom/alertmanager:latest
    ports: ["9093:9093"]
```

### Prometheus 메트릭

```yaml
# 애플리케이션 메트릭
- http_requests_total
- http_request_duration_seconds
- active_connections

# 마이크로서비스 메트릭  
- embedding_requests_total
- scheduler_jobs_executed_total
- event_gateway_messages_published_total

# 시스템 메트릭
- database_connections_active
- cache_hit_ratio
- memory_usage_bytes

# 보안 메트릭
- authentication_attempts_total
- authorization_failures_total
- audit_events_total
```

### 분산 추적 (Jaeger)

```python
# OpenTelemetry 통합
from opentelemetry import trace
from opentelemetry.exporter.jaeger.thrift import JaegerExporter

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("database_query")
async def query_database(query: str):
    with tracer.start_as_current_span("terminus_query"):
        result = await terminus_client.query(query)
    return result
```

### 헬스 체크 엔드포인트

모든 서비스에서 표준화된 헬스 체크:

```python
# 각 서비스의 헬스 체크
GET /health           # 기본 상태 확인
GET /health/detailed  # 상세 상태 (인증 필요)  
GET /health/live      # 라이브니스 프로브
GET /health/ready     # 레디니스 프로브
```

## 📈 성능 최적화

### 1. Cold Start 최적화

**위치**: `/bootstrap/startup_optimizer.py`

```python
class StartupOptimizer:
    """애플리케이션 시작 시간 최적화"""
    
    async def optimize_startup(self):
        # 병렬 초기화
        await asyncio.gather(
            self._init_database_connections(),
            self._warm_up_caches(),
            self._preload_models()
        )
        
        # 지연 초기화 (non-critical)
        asyncio.create_task(self._defer_metrics_setup())
```

### 2. 3-Tier 캐싱

```python
# Tier 1: Local Memory (TTLCache)
local_cache = TTLCache(maxsize=1000, ttl=60)

# Tier 2: Redis (분산 캐시)
redis_cache = Redis(host="redis", decode_responses=True)

# Tier 3: Database (영구 저장소)
database = TerminusDB()

# 캐시 체인
async def get_data(key: str):
    if data := local_cache.get(key):
        return data
    if data := await redis_cache.get(key):
        local_cache[key] = data
        return data
    data = await database.query(key)
    await redis_cache.set(key, data, ex=300)
    local_cache[key] = data
    return data
```

### 3. 연결 풀링

```python
# 데이터베이스 연결 풀 설정
TERMINUSDB_POOL_SIZE = 20
POSTGRESQL_POOL_SIZE = 50  
REDIS_POOL_SIZE = 100
```

## 🚀 배포 아키텍처

### Docker Compose 구성

```yaml
# docker-compose.yml (기본 인프라)
services:
  oms-monolith:
    build: .
    ports: ["8000:8000", "8004:8004", "8006:8006"]
    environment:
      - USE_EMBEDDING_MS=${USE_EMBEDDING_MS:-false}
      - USE_SCHEDULER_MS=${USE_SCHEDULER_MS:-false}
      - USE_EVENT_GATEWAY=${USE_EVENT_GATEWAY:-false}

# docker-compose.microservices.yml (마이크로서비스)
services:
  embedding-service:
    build: ./services/embedding-service
    ports: ["8001:8001", "50055:50055"]
    
  scheduler-service:
    build: ./services/scheduler-service 
    ports: ["8002:8002", "50056:50056"]
    
  event-gateway:
    build: ./services/event-gateway
    ports: ["8003:8003", "50057:50057"]

# monitoring/docker-compose.monitoring.yml (모니터링)
services:
  prometheus:
    ports: ["9091:9090"]
  grafana:
    ports: ["3000:3000"]
  jaeger:
    ports: ["16686:16686"]
```

### 배포 모드

#### 1. 모놀리스 모드 (기본)
```bash
docker-compose up
```

#### 2. 하이브리드 모드 (점진적)
```bash
# 특정 서비스만 활성화
export USE_EMBEDDING_MS=true
export USE_SCHEDULER_MS=false
docker-compose up -d
docker-compose -f docker-compose.microservices.yml up embedding-service
```

#### 3. 풀 마이크로서비스 모드
```bash
# 모든 서비스 활성화
cp .env.microservices .env
docker-compose up -d
docker-compose -f docker-compose.microservices.yml up -d
```

#### 4. 모니터링 포함 배포
```bash
# 완전한 스택 배포
docker-compose \
  -f docker-compose.yml \
  -f docker-compose.microservices.yml \
  -f monitoring/docker-compose.monitoring.yml \
  up -d
```

### 프로덕션 최적화

```dockerfile
# Multi-stage build for optimization
FROM python:3.9-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.9-slim as runtime
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 환경별 설정

```bash
# 개발 환경
cp .env.example .env

# 마이크로서비스 환경  
cp .env.microservices .env

# 프로덕션 환경
cp .env.production .env
```

## 🔮 확장성 및 미래 계획

### 스케일링 전략

1. **수평적 확장**
   - API 서버 레플리카 스케일링
   - 마이크로서비스 독립적 스케일링
   - 로드 밸런서 기반 트래픽 분산

2. **수직적 확장**
   - 리소스 기반 동적 할당
   - GPU 가속 (임베딩 서비스)
   - 메모리 최적화

3. **지역별 배포**
   - 멀티 리전 지원
   - 엣지 캐싱
   - 글로벌 분산

### 향후 로드맵

#### 단기 (3-6개월)
- [ ] 서비스 메시 (Istio) 도입
- [ ] API Gateway (Kong) 통합
- [ ] Kafka 이벤트 스트리밍
- [ ] AI 기반 스키마 추천

#### 중기 (6-12개월)
- [ ] Redis Cluster 구성
- [ ] ML Platform (Kubeflow) 통합
- [ ] 자동 스케일링 고도화
- [ ] 고급 분석 도구

#### 장기 (12개월+)
- [ ] 블록체인 통합 (불변 감사)
- [ ] 양자 내성 암호화
- [ ] 자율 시스템 관리
- [ ] 글로벌 분산 아키텍처

## 📚 참고 자료

### 프로젝트 구조
```
oms-monolith/
├── api/                     # REST API 및 GraphQL
├── bootstrap/               # DI 컨테이너 및 팩토리
├── core/                    # 핵심 비즈니스 로직  
├── data_kernel/             # TerminusDB 게이트웨이
├── services/                # 마이크로서비스 구현
│   ├── embedding-service/   # 벡터 임베딩 서비스
│   ├── scheduler-service/   # 스케줄러 서비스
│   └── event-gateway/       # 이벤트 게이트웨이
├── shared/                  # 공유 라이브러리 및 스텁
├── monitoring/              # 모니터링 설정
├── archive_*/               # 아카이브된 레거시 코드
└── tests/                   # 테스트 스위트
```

### 핵심 환경 변수
```bash
# 마이크로서비스 제어
USE_EMBEDDING_MS=false       # 임베딩 서비스 토글
USE_SCHEDULER_MS=false       # 스케줄러 서비스 토글
USE_EVENT_GATEWAY=false      # 이벤트 게이트웨이 토글
USE_DATA_KERNEL_GATEWAY=false # 데이터 커널 게이트웨이 토글

# 데이터베이스
TERMINUSDB_ENDPOINT=http://terminusdb:6363
DATABASE_URL=postgresql://oms_user:oms_password@postgres:5432/oms_db
REDIS_URL=redis://redis:6379

# 보안
JWT_SECRET=your-secret-key-here
JWT_ALGORITHM=HS256

# 모니터링
ENABLE_TELEMETRY=true
JAEGER_ENDPOINT=http://jaeger:14268/api/traces
PROMETHEUS_METRICS=true
```

---

*이 문서는 현재 구현된 시스템 상태를 정확히 반영하며, 지속적으로 업데이트됩니다.*