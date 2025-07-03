# 🚀 OMS (Ontology Management System) - 온톨로지 관리 시스템

> **엔터프라이즈급 온톨로지 관리 및 데이터 모델링 플랫폼**

## 📋 개요

OMS는 복잡한 데이터 모델과 온톨로지를 체계적으로 관리하기 위한 현대적인 엔터프라이즈 솔루션입니다. 그래프 데이터베이스, 실시간 API, 그리고 고급 보안 기능을 통합하여 대규모 조직의 데이터 구조를 효율적으로 관리할 수 있습니다.

## ✨ 주요 기능

### 🏗️ 온톨로지 관리
- **객체 타입(ObjectType)** 정의 및 관리
- **속성(Property)** 시스템 및 데이터 타입 지원
- **링크 타입(LinkType)** 관계 모델링
- **인터페이스(Interface)** 및 공유 속성 지원

### 🔄 버전 관리
- **Git 스타일 브랜치** 시스템
- **변경 제안(Change Proposal)** 워크플로우
- **머지 및 충돌 해결** 기능
- **감사 추적(Audit Trail)** 완전 지원

### 🌐 API 인터페이스
- **REST API** - 완전한 CRUD 작업
- **GraphQL API** - 실시간 쿼리 및 구독
- **WebSocket** - 실시간 이벤트 스트리밍
- **OpenAPI 문서** - 자동 생성된 API 문서

### 🔐 보안 및 인증
- **JWT 기반 인증** 시스템
- **RBAC (Role-Based Access Control)**
- **스코프 기반 권한 관리**
- **API 키 및 토큰 관리**

### 📊 모니터링 및 관찰성
- **Prometheus** 메트릭 수집
- **Grafana** 대시보드
- **Jaeger** 분산 트레이싱 (OpenTelemetry 통합)
- **실시간 헬스 체크**

### 🚀 고급 기능 (TerminusDB 확장)
- **Vector Embeddings** - 7개 프로바이더 지원 (OpenAI, Cohere, HuggingFace, Azure, Google Vertex, Anthropic, Local)
- **GraphQL Deep Linking** - Repository/Service/Resolver 아키텍처
- **Redis SmartCache** - 3-tier 캐싱 (Local → Redis → TerminusDB)
- **Time Travel Queries** - AS OF, BETWEEN, ALL_VERSIONS 연산자
- **Delta Encoding** - 압축 전략을 통한 스토리지 효율성
- **@unfoldable Documents** - 선택적 콘텐츠 로딩
- **@metadata Frames** - Markdown 문서 메타데이터

## 🏛️ 시스템 아키텍처

```mermaid
graph TB
    subgraph "클라이언트 레이어"
        WebUI[웹 UI]
        MobileApp[모바일 앱]
        ThirdParty[써드파티 앱]
    end

    subgraph "API 게이트웨이"
        APIGateway[API Gateway<br/>포트: 8090]
        LoadBalancer[로드 밸런서]
    end

    subgraph "애플리케이션 레이어"
        MainAPI[메인 API 서버<br/>FastAPI<br/>포트: 8000]
        GraphQLHTTP[GraphQL HTTP<br/>포트: 8006]
        GraphQLWS[GraphQL WebSocket<br/>포트: 8004]
    end

    subgraph "미들웨어 레이어"
        AuthMiddleware[인증 미들웨어<br/>JWT 토큰 검증]
        RBACMiddleware[RBAC 미들웨어<br/>권한 관리]
        AuditMiddleware[감사 미들웨어<br/>로그 수집]
        CacheMiddleware[캐시 미들웨어<br/>Redis 통합]
    end

    subgraph "비즈니스 로직 레이어"
        SchemaService[스키마 서비스<br/>온톨로지 관리]
        ValidationService[검증 서비스<br/>데이터 유효성]
        VersionService[버전 서비스<br/>브랜치 관리]
        AuditService[감사 서비스<br/>변경 추적]
        IAMService[IAM 서비스<br/>인증/인가]
        EmbeddingService[임베딩 서비스<br/>벡터 검색]
        TimeTravelService[시간 여행 서비스<br/>시점 쿼리]
        GraphAnalysisService[그래프 분석<br/>Deep Linking]
    end

    subgraph "데이터 저장소"
        TerminusDB[(TerminusDB<br/>그래프 DB<br/>포트: 6363)]
        PostgreSQL[(PostgreSQL<br/>관계형 DB<br/>포트: 5432)]
        Redis[(Redis<br/>SmartCache/세션<br/>포트: 6379)]
        SQLite[(SQLite<br/>감사 로그)]
    end

    subgraph "이벤트 스트리밍"
        NATS[NATS<br/>메시지 브로커<br/>포트: 4222]
        EventPublisher[이벤트 발행자]
        EventConsumer[이벤트 소비자]
    end

    subgraph "모니터링 스택"
        Prometheus[Prometheus<br/>메트릭 수집<br/>포트: 9091]
        Grafana[Grafana<br/>대시보드<br/>포트: 3000]
        Jaeger[Jaeger<br/>트레이싱<br/>포트: 16686]
    end

    %% 연결 관계
    WebUI --> APIGateway
    MobileApp --> APIGateway
    ThirdParty --> APIGateway

    APIGateway --> LoadBalancer
    LoadBalancer --> MainAPI
    LoadBalancer --> GraphQLHTTP
    LoadBalancer --> GraphQLWS

    MainAPI --> AuthMiddleware
    GraphQLHTTP --> AuthMiddleware
    GraphQLWS --> AuthMiddleware

    AuthMiddleware --> RBACMiddleware
    RBACMiddleware --> AuditMiddleware
    AuditMiddleware --> CacheMiddleware

    CacheMiddleware --> SchemaService
    CacheMiddleware --> ValidationService
    CacheMiddleware --> VersionService
    CacheMiddleware --> AuditService
    CacheMiddleware --> IAMService
    CacheMiddleware --> EmbeddingService
    CacheMiddleware --> TimeTravelService
    CacheMiddleware --> GraphAnalysisService

    SchemaService --> TerminusDB
    ValidationService --> TerminusDB
    VersionService --> TerminusDB
    AuditService --> PostgreSQL
    AuditService --> SQLite
    IAMService --> PostgreSQL
    IAMService --> Redis

    CacheMiddleware --> Redis
    
    SchemaService --> EventPublisher
    VersionService --> EventPublisher
    TimeTravelService --> EventPublisher
    GraphAnalysisService --> EventPublisher
    EventPublisher --> NATS
    NATS --> EventConsumer

    MainAPI --> Prometheus
    GraphQLHTTP --> Prometheus
    GraphQLWS --> Prometheus
    Prometheus --> Grafana

    SchemaService --> Jaeger
    ValidationService --> Jaeger
    EmbeddingService --> Jaeger
    TimeTravelService --> Jaeger
    GraphAnalysisService --> Jaeger

    classDef apiLayer fill:#e1f5fe
    classDef dataLayer fill:#f3e5f5
    classDef monitoringLayer fill:#e8f5e8
    classDef middlewareLayer fill:#fff3e0

    class MainAPI,GraphQLHTTP,GraphQLWS apiLayer
    class TerminusDB,PostgreSQL,Redis,SQLite dataLayer
    class Prometheus,Grafana,Jaeger monitoringLayer
    class AuthMiddleware,RBACMiddleware,AuditMiddleware,CacheMiddleware middlewareLayer
```

## 🚀 빠른 시작

### 사전 요구사항
- Docker & Docker Compose
- Python 3.11+
- Node.js 18+ (프론트엔드 개발시)

### 1. 저장소 클론
```bash
git clone https://github.com/your-username/oms-monolith.git
cd oms-monolith
```

### 2. 환경 설정
```bash
cp .env.example .env
# .env 파일을 수정하여 필요한 설정값 입력
```

### 3. Docker로 전체 시스템 실행
```bash
# 모든 서비스 시작
docker-compose up -d

# 서비스 상태 확인
docker-compose ps
```

### 4. 서비스 접속
| 서비스 | URL | 설명 |
|--------|-----|------|
| 메인 API | http://localhost:8000 | REST API 엔드포인트 |
| API 문서 | http://localhost:8000/docs | Swagger UI 문서 |
| GraphQL HTTP | http://localhost:8006/graphql | GraphQL HTTP API |
| GraphQL WebSocket | http://localhost:8004/graphql | GraphQL 실시간 구독 |
| PostgreSQL | localhost:5432 | 관계형 데이터베이스 |
| TerminusDB | http://localhost:6363 | 그래프 데이터베이스 |
| Redis | localhost:6379 | 캐시 및 세션 스토어 |
| Grafana | http://localhost:3000 | 모니터링 대시보드 |
| Jaeger | http://localhost:16686 | 분산 트레이싱 |

## 📖 상세 가이드

### 온톨로지 모델링

#### 1. 객체 타입 생성
```python
from models.domain import ObjectTypeCreate

# 새로운 객체 타입 정의
user_type = ObjectTypeCreate(
    name="User",
    display_name="사용자",
    description="시스템 사용자 정보",
    properties=[
        {
            "name": "username",
            "display_name": "사용자명",
            "data_type": "string",
            "is_required": True,
            "is_unique": True
        },
        {
            "name": "email",
            "display_name": "이메일",
            "data_type": "string",
            "is_required": True,
            "validation_rules": {
                "pattern": "^[\\w\\.-]+@[\\w\\.-]+\\.[a-zA-Z]{2,}$"
            }
        }
    ]
)
```

#### 2. 링크 타입 정의
```python
from models.domain import LinkTypeCreate, Cardinality, Directionality

# 사용자-조직 관계 정의
user_org_link = LinkTypeCreate(
    name="belongs_to",
    display_name="소속",
    description="사용자가 조직에 소속됨",
    fromTypeId="User",
    toTypeId="Organization",
    cardinality=Cardinality.MANY_TO_ONE,
    directionality=Directionality.UNIDIRECTIONAL
)
```

### API 사용 예제

#### REST API
```bash
# 객체 타입 목록 조회
curl -H "Authorization: Bearer YOUR_TOKEN" \
     http://localhost:8000/api/v1/schemas/main/object-types

# 새 객체 타입 생성
curl -X POST \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"name": "Product", "display_name": "제품"}' \
     http://localhost:8000/api/v1/schemas/main/object-types
```

#### GraphQL
```graphql
# 스키마 정보 조회
query {
  __schema {
    types {
      name
      kind
      description
    }
  }
}

# 객체 타입 조회
query GetObjectTypes($branch: String!) {
  objectTypes(branch: $branch) {
    edges {
      node {
        id
        name
        displayName
        properties {
          name
          dataType
          isRequired
        }
      }
    }
  }
}
```

## 🔧 개발 환경 설정

### 로컬 개발
```bash
# 가상환경 생성
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 개발 서버 실행
python main.py
```

### 테스트 실행
```bash
# 단위 테스트
pytest tests/unit/

# 통합 테스트
pytest tests/integration/

# 전체 테스트 (커버리지 포함)
pytest --cov=. tests/
```

### 코드 품질
```bash
# 코드 포맷팅
black .
isort .

# 타입 체킹
mypy .

# 린팅
flake8 .
```

## 🏗️ 하이브리드 데이터베이스 아키텍처

### 데이터베이스 역할 분담

#### TerminusDB (그래프 데이터베이스)
- **주요 비즈니스 데이터**: 온톨로지, 스키마, 객체 타입
- **복잡한 관계 모델링**: 링크 타입, 인터페이스, 상속 관계
- **버전 관리**: Git 스타일 브랜치 및 머지 지원
- **GraphQL 네이티브**: 실시간 쿼리 및 구독 지원

#### PostgreSQL (관계형 데이터베이스)
- **감사 로그**: 모든 변경사항 추적 (SQLite/PostgreSQL 선택 가능)
- **사용자 관리**: 인증, 인가, 세션 관리
- **분산 잠금**: Advisory Lock을 통한 동시성 제어
- **아웃박스 패턴**: 이벤트 기반 아키텍처의 트랜잭션 보장
- **운영 메타데이터**: 시스템 설정, 정책, 보고서
- **감사 Side-Car**: TerminusDB와 교차 검증

#### Redis (인메모리 캐시)
- **SmartCache**: 3-tier 캐싱 (Local → Redis → TerminusDB)
- **세션 스토어**: JWT 토큰 캐싱 및 관리
- **쿼리 캐싱**: GraphQL 결과 캐싱
- **분산 락**: 고성능 락 메커니즘
- **실시간 데이터**: WebSocket 연결 상태 관리
- **Vector 캐싱**: 임베딩 벡터 결과 캐싱

#### SQLite (로컬 저장소)
- **감사 로그 기본값**: 로컬 감사 이벤트 저장 (7년 보존)
- **로컬 캐싱**: 오프라인 작업 지원
- **임시 데이터**: 세션별 작업 데이터
- **개발 환경**: 로컬 개발용 경량 저장소

### 데이터 플로우 패턴
```mermaid
graph LR
    A[비즈니스 로직] --> B[TerminusDB]
    A --> C[PostgreSQL 감사]
    A --> D[Redis 캐시]
    
    B --> E[GraphQL 응답]
    C --> F[감사 보고서]
    D --> G[빠른 응답]
```

## 📊 성능 및 확장성

### 성능 최적화
- **연결 풀링**: PostgreSQL, TerminusDB, Redis 연결 최적화
- **쿼리 최적화**: N+1 문제 해결을 위한 DataLoader 패턴
- **캐싱 전략**: Redis 기반 다층 캐싱
- **인덱싱**: 그래프 DB 및 PostgreSQL 쿼리 최적화

### 확장성 고려사항
- **수평 확장**: 마이크로서비스 아키텍처 지원
- **로드 밸런싱**: NGINX/HAProxy 통합
- **데이터 파티셔닝**: 대용량 데이터 처리
- **비동기 처리**: Celery/RQ 작업 큐

## 🔒 보안 가이드

### 인증 설정
```bash
# JWT 시크릿 키 생성
openssl rand -base64 32

# 환경 변수 설정
export JWT_SECRET="your-secret-key"
export JWT_ISSUER="your-issuer"
export JWT_AUDIENCE="oms"
```

### 권한 관리
```python
# 사용자 역할 정의
roles = {
    "admin": ["*"],  # 모든 권한
    "developer": ["schemas:read", "schemas:write", "ontologies:read", "ontologies:write"],
    "viewer": ["schemas:read", "ontologies:read"]
}
```

## 📈 모니터링 및 로깅

### 메트릭 수집
- **애플리케이션 메트릭**: 요청 수, 응답 시간, 에러율
- **비즈니스 메트릭**: 스키마 생성 수, 사용자 활동
- **인프라 메트릭**: CPU, 메모리, 디스크 사용률
- **TerminusDB 메트릭**: 쿼리 성능, 캐시 히트율
- **임베딩 메트릭**: 프로바이더별 성능, 토큰 사용량
- **시간 여행 메트릭**: 시점 쿼리 성능, 버전 스캔 효율

### 로그 관리
- **구조화된 로깅**: JSON 형태의 로그
- **로그 레벨**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **분산 트레이싱**: OpenTelemetry + Jaeger 통합
- **감사 로그**: 불변 이벤트 저장, 해시 기반 무결성
- **Side-Car 검증**: TerminusDB 교차 검증 리포트

## 🔄 배포 및 운영

### 배포 전략
```bash
# 프로덕션 빌드
docker build -t oms-monolith:latest .

# 컨테이너 실행
docker run -d \
  --name oms-prod \
  -p 8000:8000 \
  -e APP_ENV=production \
  -e JWT_SECRET=$JWT_SECRET \
  oms-monolith:latest
```

### 헬스 체크
```bash
# 서비스 상태 확인
curl http://localhost:8000/health

# 상세 헬스 체크
curl http://localhost:8000/health?detailed=true
```

## 🤝 기여 가이드

### 개발 워크플로우
1. **Fork** 저장소
2. **Feature 브랜치** 생성 (`git checkout -b feature/amazing-feature`)
3. **변경사항 커밋** (`git commit -m 'Add amazing feature'`)
4. **브랜치에 푸시** (`git push origin feature/amazing-feature`)
5. **Pull Request** 생성

### 코드 스타일
- **Python**: PEP 8 준수, Black 포맷터 사용
- **GraphQL**: 타입 정의는 파스칼 케이스, 필드명은 카멜 케이스
- **API**: RESTful 원칙 준수, OpenAPI 3.0 문서화

## 📄 라이선스

이 프로젝트는 [MIT 라이선스](LICENSE) 하에 배포됩니다.

## 🆘 지원 및 문의

- **문서**: [Wiki](https://github.com/your-username/oms-monolith/wiki)
- **이슈 리포트**: [GitHub Issues](https://github.com/your-username/oms-monolith/issues)
- **토론**: [GitHub Discussions](https://github.com/your-username/oms-monolith/discussions)

## 📚 추가 문서

- **[확장 아키텍처 문서](../ARCHITECTURE_EXTENDED.md)**: 시스템 아키텍처 상세 설명
- **[기능 가이드](../FEATURES.md)**: 9가지 TerminusDB 확장 기능 사용법
- **[통합 테스트 가이드](../INTEGRATION_TEST_README.md)**: 테스트 실행 방법
- **[API 문서](docs/api/)**: REST/GraphQL API 레퍼런스

## 🏆 주요 구현자

- **아키텍처 설계**: Claude AI Assistant
- **시스템 통합**: 이시현 (isihyeon)
- **보안 구현**: Claude & 이시현
- **모니터링 시스템**: Claude AI Assistant
- **TerminusDB 확장**: Claude & 이시현

---

**OMS - 차세대 온톨로지 관리 플랫폼** 🚀

> "*복잡한 데이터 모델을 간단하게, 확장 가능한 아키텍처로*"

## 🎯 최근 업데이트 (2024.12)

- ✅ Vector Embeddings 7개 프로바이더 통합
- ✅ GraphQL Deep Linking 최적화
- ✅ 3-tier SmartCache 구현
- ✅ OpenTelemetry + Jaeger 통합
- ✅ Time Travel Queries 지원
- ✅ Delta Encoding 압축 전략
- ✅ @unfoldable/@metadata 문서 기능
- ✅ 감사 서비스 PostgreSQL 지원