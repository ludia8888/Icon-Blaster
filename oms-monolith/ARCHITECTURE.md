# 🏛️ OMS 시스템 아키텍처 상세 문서

## 📊 전체 시스템 아키텍처

```mermaid
C4Context
    title OMS (Ontology Management System) - 시스템 컨텍스트

    Person(user, "사용자", "데이터 모델링 담당자")
    Person(admin, "관리자", "시스템 관리자")
    Person(developer, "개발자", "API 사용자")

    System(oms, "OMS 플랫폼", "온톨로지 관리 시스템")
    
    System_Ext(iam, "IAM 시스템", "인증/인가 서비스")
    System_Ext(monitoring, "모니터링", "Grafana/Prometheus")
    System_Ext(backup, "백업 시스템", "데이터 백업")

    Rel(user, oms, "온톨로지 관리", "HTTPS/WebSocket")
    Rel(admin, oms, "시스템 관리", "HTTPS")
    Rel(developer, oms, "API 호출", "REST/GraphQL")
    
    Rel(oms, iam, "인증 요청", "HTTPS")
    Rel(oms, monitoring, "메트릭 전송", "HTTP")
    Rel(oms, backup, "데이터 백업", "HTTPS")
```

## 🔧 컨테이너 아키텍처

```mermaid
C4Container
    title OMS 컨테이너 다이어그램

    Container(web, "웹 UI", "React/TypeScript", "사용자 인터페이스")
    Container(api_gateway, "API Gateway", "NGINX", "라우팅 및 로드밸런싱")
    
    Container(main_api, "메인 API", "FastAPI/Python", "핵심 비즈니스 로직")
    Container(graphql_http, "GraphQL HTTP", "Strawberry", "GraphQL 쿼리 처리")
    Container(graphql_ws, "GraphQL WebSocket", "Strawberry", "실시간 구독")
    
    ContainerDb(terminusdb, "TerminusDB", "그래프 데이터베이스", "온톨로지 데이터 저장")
    ContainerDb(redis, "Redis", "인메모리 캐시", "세션 및 캐시")
    ContainerDb(sqlite, "SQLite", "관계형 DB", "메타데이터")
    
    Container(nats, "NATS", "메시지 브로커", "이벤트 스트리밍")
    Container(prometheus, "Prometheus", "메트릭 DB", "모니터링 데이터")
    Container(grafana, "Grafana", "대시보드", "시각화")

    Rel(web, api_gateway, "HTTPS")
    Rel(api_gateway, main_api, "HTTP")
    Rel(api_gateway, graphql_http, "HTTP")
    Rel(api_gateway, graphql_ws, "WebSocket")
    
    Rel(main_api, terminusdb, "TCP")
    Rel(main_api, redis, "TCP")
    Rel(main_api, sqlite, "File")
    Rel(main_api, nats, "TCP")
    
    Rel(graphql_http, terminusdb, "TCP")
    Rel(graphql_ws, terminusdb, "TCP")
    Rel(graphql_ws, nats, "TCP")
    
    Rel(main_api, prometheus, "HTTP")
    Rel(prometheus, grafana, "HTTP")
```

## 🔄 데이터 플로우

```mermaid
flowchart TD
    subgraph "클라이언트 요청"
        A[사용자 요청]
        B[API 클라이언트]
        C[GraphQL 클라이언트]
    end

    subgraph "인증/인가 레이어"
        D[JWT 토큰 검증]
        E[RBAC 권한 확인]
        F[스코프 검증]
    end

    subgraph "비즈니스 로직"
        G[스키마 서비스]
        H[검증 서비스]
        I[버전 서비스]
        J[감사 서비스]
    end

    subgraph "데이터 접근"
        K[TerminusDB 쿼리]
        L[Redis 캐시]
        M[SQLite 메타데이터]
    end

    subgraph "이벤트 처리"
        N[이벤트 발행]
        O[NATS 메시지]
        P[이벤트 소비]
    end

    A --> D
    B --> D
    C --> D
    
    D --> E
    E --> F
    
    F --> G
    F --> H
    F --> I
    F --> J
    
    G --> K
    G --> L
    H --> K
    I --> K
    J --> M
    
    G --> N
    I --> N
    N --> O
    O --> P
```

## 🏗️ 마이크로서비스 분해도

```mermaid
graph TB
    subgraph "API 게이트웨이 레이어"
        Gateway[API Gateway<br/>포트: 8090]
        LB[Load Balancer]
    end

    subgraph "API 서비스들"
        MainAPI[메인 API 서비스<br/>포트: 8000<br/>- REST API<br/>- 헬스체크<br/>- 메트릭]
        
        GraphQLHTTP[GraphQL HTTP 서비스<br/>포트: 8006<br/>- 스키마 쿼리<br/>- 뮤테이션<br/>- 데이터로더]
        
        GraphQLWS[GraphQL WebSocket 서비스<br/>포트: 8004<br/>- 실시간 구독<br/>- 이벤트 스트리밍<br/>- 웹소켓 관리]
    end

    subgraph "핵심 비즈니스 서비스들"
        SchemaService[스키마 관리 서비스<br/>- ObjectType 관리<br/>- Property 관리<br/>- LinkType 관리<br/>- 인터페이스 관리]
        
        VersionService[버전 관리 서비스<br/>- 브랜치 관리<br/>- 머지 처리<br/>- 충돌 해결<br/>- 변경 제안]
        
        ValidationService[검증 서비스<br/>- 스키마 검증<br/>- 데이터 유효성<br/>- 비즈니스 규칙<br/>- 제약 조건]
        
        AuditService[감사 서비스<br/>- 변경 추적<br/>- 이벤트 로깅<br/>- 규정 준수<br/>- 보고서 생성]
        
        IAMService[IAM 서비스<br/>- 사용자 인증<br/>- 권한 관리<br/>- 토큰 발급<br/>- 세션 관리]
    end

    subgraph "데이터 서비스들"
        TerminusDB[(TerminusDB<br/>포트: 6363<br/>그래프 데이터베이스)]
        Redis[(Redis<br/>포트: 6379<br/>캐시/세션)]
        SQLite[(SQLite<br/>로컬 메타데이터)]
    end

    subgraph "이벤트/메시징"
        NATS[NATS 서버<br/>포트: 4222<br/>이벤트 스트리밍]
        EventBus[이벤트 버스<br/>발행/구독 패턴]
    end

    subgraph "모니터링 스택"
        Prometheus[Prometheus<br/>포트: 9091<br/>메트릭 수집]
        Grafana[Grafana<br/>포트: 3000<br/>대시보드]
        Jaeger[Jaeger<br/>포트: 16686<br/>분산 트레이싱]
        AlertManager[Alert Manager<br/>알림 관리]
    end

    Gateway --> LB
    LB --> MainAPI
    LB --> GraphQLHTTP
    LB --> GraphQLWS

    MainAPI --> SchemaService
    MainAPI --> VersionService
    MainAPI --> ValidationService
    MainAPI --> AuditService
    MainAPI --> IAMService

    GraphQLHTTP --> SchemaService
    GraphQLHTTP --> VersionService
    GraphQLWS --> SchemaService
    GraphQLWS --> EventBus

    SchemaService --> TerminusDB
    VersionService --> TerminusDB
    ValidationService --> TerminusDB
    AuditService --> SQLite
    IAMService --> Redis

    SchemaService --> EventBus
    VersionService --> EventBus
    EventBus --> NATS

    MainAPI --> Prometheus
    GraphQLHTTP --> Prometheus
    GraphQLWS --> Prometheus
    Prometheus --> Grafana
    Prometheus --> AlertManager

    SchemaService --> Jaeger
    VersionService --> Jaeger
```

## 🔒 보안 아키텍처

```mermaid
graph TB
    subgraph "외부 요청"
        Client[클라이언트]
        Browser[브라우저]
        API_Client[API 클라이언트]
    end

    subgraph "보안 레이어"
        WAF[Web Application Firewall]
        RateLimit[요청 제한]
        CORS[CORS 정책]
    end

    subgraph "인증 레이어"
        JWT[JWT 토큰 검증]
        OAuth[OAuth 2.0]
        APIKey[API 키 인증]
    end

    subgraph "인가 레이어"
        RBAC[역할 기반 접근 제어]
        Scope[스코프 권한 검사]
        Resource[리소스 권한 검사]
    end

    subgraph "감사 레이어"
        AccessLog[접근 로그]
        AuditTrail[감사 추적]
        Compliance[규정 준수]
    end

    subgraph "데이터 보안"
        Encryption[데이터 암호화]
        Backup[보안 백업]
        Privacy[개인정보 보호]
    end

    Client --> WAF
    Browser --> WAF
    API_Client --> WAF

    WAF --> RateLimit
    RateLimit --> CORS

    CORS --> JWT
    CORS --> OAuth
    CORS --> APIKey

    JWT --> RBAC
    OAuth --> RBAC
    APIKey --> Scope

    RBAC --> Resource
    Scope --> Resource

    Resource --> AccessLog
    AccessLog --> AuditTrail
    AuditTrail --> Compliance

    RBAC --> Encryption
    Resource --> Backup
    Compliance --> Privacy
```

## 📊 데이터 모델 아키텍처

```mermaid
erDiagram
    ObjectType {
        string id PK
        string name UK
        string display_name
        string description
        enum status
        enum type_class
        string version_hash
        datetime created_at
        datetime modified_at
        string created_by
        string modified_by
    }

    Property {
        string id PK
        string object_type_id FK
        string name
        string display_name
        string data_type_id FK
        boolean is_required
        boolean is_unique
        boolean is_indexed
        json validation_rules
        string version_hash
    }

    LinkType {
        string id PK
        string name UK
        string display_name
        string from_type_id FK
        string to_type_id FK
        enum cardinality
        enum directionality
        boolean cascade_delete
        string version_hash
    }

    Interface {
        string id PK
        string name UK
        string display_name
        string description
        string version_hash
    }

    SharedProperty {
        string id PK
        string name UK
        string display_name
        string data_type_id FK
        string semantic_type_id FK
        json validation_rules
        string version_hash
    }

    Branch {
        string id PK
        string name UK
        string display_name
        string parent_branch FK
        boolean is_protected
        boolean is_active
        string head_commit
        datetime created_at
    }

    ChangeProposal {
        string id PK
        string title
        string source_branch FK
        string target_branch FK
        enum status
        string created_by
        datetime created_at
        json conflicts
        json validation_result
    }

    AuditEvent {
        string id PK
        string event_type
        string entity_type
        string entity_id
        string branch_id FK
        string user_id
        datetime timestamp
        json changes
        string version_before
        string version_after
    }

    ObjectType ||--o{ Property : "has"
    ObjectType ||--o{ LinkType : "from_type"
    ObjectType ||--o{ LinkType : "to_type"
    ObjectType }o--o{ Interface : "implements"
    Interface ||--o{ Property : "defines"
    Property }o--|| SharedProperty : "based_on"
    Branch ||--o{ ObjectType : "contains"
    Branch ||--o{ ChangeProposal : "source"
    Branch ||--o{ ChangeProposal : "target"
    AuditEvent }o--|| Branch : "tracked_in"
```

## 🔄 이벤트 아키텍처

```mermaid
sequenceDiagram
    participant Client as 클라이언트
    participant API as API 서버
    participant Schema as 스키마 서비스
    participant Event as 이벤트 발행자
    participant NATS as NATS 브로커
    participant Sub1 as 구독자 1 (GraphQL)
    participant Sub2 as 구독자 2 (감사)
    participant Sub3 as 구독자 3 (캐시)

    Client->>+API: POST /object-types
    API->>+Schema: 객체 타입 생성
    Schema->>Schema: 유효성 검증
    Schema->>Schema: TerminusDB 저장
    Schema->>+Event: 이벤트 발행
    Event->>+NATS: ObjectTypeCreated 이벤트
    
    NATS-->>Sub1: 실시간 알림
    NATS-->>Sub2: 감사 로그 기록
    NATS-->>Sub3: 캐시 무효화
    
    Sub1->>Sub1: WebSocket 클라이언트에 전송
    Sub2->>Sub2: 감사 DB에 저장
    Sub3->>Sub3: Redis 캐시 갱신
    
    Schema-->>-API: 생성 완료
    API-->>-Client: 201 Created
    
    Note over Client, Sub3: 이벤트 기반 아키텍처로<br/>느슨한 결합 달성
```

## 🏗️ 배포 아키텍처

```mermaid
graph TB
    subgraph "로드밸런서"
        LB[NGINX Load Balancer]
        SSL[SSL Termination]
    end

    subgraph "애플리케이션 클러스터"
        API1[API 서버 1]
        API2[API 서버 2]
        API3[API 서버 3]
        
        GQL1[GraphQL 서버 1]
        GQL2[GraphQL 서버 2]
    end

    subgraph "데이터베이스 클러스터"
        TDB_Primary[(TerminusDB Primary)]
        TDB_Replica1[(TerminusDB Replica 1)]
        TDB_Replica2[(TerminusDB Replica 2)]
        
        Redis_Primary[(Redis Primary)]
        Redis_Replica[(Redis Replica)]
    end

    subgraph "모니터링 클러스터"
        Prom1[Prometheus 1]
        Prom2[Prometheus 2]
        Grafana_Cluster[Grafana Cluster]
    end

    subgraph "메시지 클러스터"
        NATS1[NATS Node 1]
        NATS2[NATS Node 2]
        NATS3[NATS Node 3]
    end

    SSL --> LB
    LB --> API1
    LB --> API2
    LB --> API3
    LB --> GQL1
    LB --> GQL2

    API1 --> TDB_Primary
    API2 --> TDB_Primary
    API3 --> TDB_Primary
    
    GQL1 --> TDB_Replica1
    GQL2 --> TDB_Replica2

    API1 --> Redis_Primary
    API2 --> Redis_Primary
    API3 --> Redis_Primary

    TDB_Primary --> TDB_Replica1
    TDB_Primary --> TDB_Replica2
    Redis_Primary --> Redis_Replica

    API1 --> NATS1
    API2 --> NATS2
    API3 --> NATS3

    API1 --> Prom1
    API2 --> Prom1
    GQL1 --> Prom2
    GQL2 --> Prom2

    Prom1 --> Grafana_Cluster
    Prom2 --> Grafana_Cluster
```

## 📈 성능 최적화 전략

### 1. 캐싱 전략
```mermaid
graph LR
    subgraph "캐시 계층"
        Browser[브라우저 캐시<br/>60분]
        CDN[CDN 캐시<br/>24시간]
        Redis[Redis 캐시<br/>1시간]
        AppCache[애플리케이션 캐시<br/>15분]
    end

    subgraph "데이터 소스"
        TerminusDB[(TerminusDB)]
        SQLite[(SQLite)]
    end

    Request[요청] --> Browser
    Browser --> CDN
    CDN --> Redis
    Redis --> AppCache
    AppCache --> TerminusDB
    AppCache --> SQLite
```

### 2. 쿼리 최적화
```mermaid
graph TD
    Query[GraphQL 쿼리]
    
    subgraph "쿼리 분석"
        Parse[쿼리 파싱]
        Validate[유효성 검증]
        Optimize[쿼리 최적화]
    end

    subgraph "실행 계획"
        DataLoader[DataLoader 배치]
        Cache[캐시 조회]
        DB[DB 쿼리]
    end

    subgraph "결과 처리"
        Transform[데이터 변환]
        Serialize[직렬화]
        Compress[압축]
    end

    Query --> Parse
    Parse --> Validate
    Validate --> Optimize
    
    Optimize --> DataLoader
    Optimize --> Cache
    Optimize --> DB
    
    DataLoader --> Transform
    Cache --> Transform
    DB --> Transform
    
    Transform --> Serialize
    Serialize --> Compress
```

이 아키텍처 문서는 OMS 시스템의 전체적인 구조와 각 컴포넌트 간의 관계를 상세히 설명합니다. 각 다이어그램은 시스템의 다른 측면을 보여주며, 개발자와 운영자가 시스템을 이해하고 확장하는 데 도움이 됩니다.