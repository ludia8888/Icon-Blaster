## [BackendSpec.md]

### 1. 문서 개요

이 문서는 Ontology Editor의 백엔드 OMS API 서버 구현 사양을 엔터프라이즈 프로덕션 레벨로 심층 규격화합니다. 아키텍처, 모듈 간 데이터 흐름, 에러 처리, 보안 정책, 성능 최적화, 테스트 전략, 배포 파이프라인, 관측성 등을 포함하여, [FrontendSpec.md] 및 APISpec.md와 완벽히 연계됩니다.

**대상 독자:** 백엔드 개발자, DevOps 엔지니어, 아키텍트, QA 엔지니어

---

### 2. 시스템 아키텍처

### 2.1 컴포넌트 다이어그램

- **Client (React/App)** → **API Gateway / Ingress** → **OMS API Server**
- OMS API ↔ **PostgreSQL** (메타데이터 저장)
- OMS API → **Kafka** ─→ **IndexingService** → **ElasticSearch**
- OMS API → **Kafka** ─→ **GraphSyncService** → **Neo4j**
- OMS API ↔ **Redis** (락, 캐시)
- OMS API ↔ **Keycloak** (OIDC)
- OMS API → **Prometheus** Metrics
- OMS API → **Sentry** Error Tracking

### 2.2 데이터 흐름

1. **Create ObjectType**: Client → POST /api/object-type → Controller → Service (DB Transaction) → Kafka 이벤트 발행 → Response
2. **Indexing**: Kafka Consumer → IndexingService → ElasticSearch 인덱스 업데이트
3. **Graph Sync**: Kafka Consumer → GraphSyncService → Neo4j Cypher MERGE

---

### 3. 프로젝트 구조

```
server/
├─ src/
│   ├─ app.ts              # Express 앱 설정 (미들웨어, 라우트)
│   ├─ server.ts           # HTTP/S 서버 부트스트랩
│   ├─ config/
│   │   ├─ index.ts        # dotenv, Joi로 env 검증
│   │   ├─ db.ts           # TypeORM DataSource
│   │   └─ kafka.ts        # Kafka 클라이언트 설정
│   ├─ controllers/
│   │   ├─ authController.ts
│   │   ├─ metadataController.ts
│   │   ├─ versionController.ts
│   │   ├─ auditController.ts
│   │   └─ healthController.ts
│   ├─ services/
│   │   ├─ authService.ts
│   │   ├─ objectService.ts
│   │   ├─ propertyService.ts
│   │   ├─ linkService.ts
│   │   ├─ interfaceService.ts
│   │   ├─ actionService.ts
│   │   ├─ versionService.ts
│   │   ├─ auditService.ts
│   │   ├─ indexingService.ts
│   │   ├─ graphSyncService.ts
│   │   └─ notificationService.ts
│   ├─ repositories/
│   │   ├─ objectRepository.ts
│   │   ├─ propertyRepository.ts
│   │   └─ ... (Prisma 지원 가능)
│   ├─ entities/           # TypeORM @Entity 정의
│   ├─ middlewares/
│   │   ├─ authMiddleware.ts
│   │   ├─ errorHandler.ts
│   │   ├─ validationMiddleware.ts
│   │   └─ rateLimiter.ts
│   ├─ dto/                # class-validator, class-transformer DTO
│   │   ├─ createObject.dto.ts
│   │   └─ updateObject.dto.ts
│   ├─ utils/
│   │   ├─ logger.ts       # Winston 설정
│   │   ├─ tracer.ts       # OpenTelemetry 연동
│   │   └─ constants.ts
│   ├─ routes.ts           # API 라우트 맵핑
│   └─ migrations/         # TypeORM migration files
├─ test/
│   ├─ unit/               # Jest 단위 테스트
│   └─ integration/         # Supertest 통합 테스트
├─ Dockerfile
├─ helm/                   # Helm 차트 (values.yaml 포함)
├─ ormconfig.ts
└─ .env.example

```

---

### 4. 환경 구성

### 4.1 환경 변수

```
PORT=4000
NODE_ENV=production
DATABASE_URL=postgres://user:pass@host:5432/ontology
REDIS_URL=redis://host:6379/0
KAFKA_BROKER=broker1:9092,broker2:9092
KEYCLOAK_ISSUER=https://auth.company.com/auth/realms/onto
KEYCLOAK_CLIENT_ID=onto-client
JWT_PUBLIC_KEY=<PEM>
SENTRY_DSN=https://xxxxx@sentry.io/123

```

- Joi 스키마로 필수 변수 검증, 미설정 시 서버 부팅 실패

### 4.2 컨피그 레이어

- `config/index.ts`: `config.get('db')`, `config.get('kafka')`, `config.get('auth')`
- `config/db.ts`: `DataSource` 싱글톤, connection pool 설정(`max: 20`)

---

### 5. 주요 모듈 상세

### 5.1 AuthModule

- **Flow**: Access Token JWT → authMiddleware 검증 → req.user 주입
- **Keycloak**: `passport-keycloak` 또는 `openid-client`
- **Roles**: `Ontology Admin`, `Editor`, `Viewer`
- **RBAC**: `@Acl(['Admin', 'Editor'])` 데코레이터 적용
- **Refresh Token**: Redis에 저장, 만료 시 클라이언트 리프레시

### 5.2 MetadataModule

- **Controller**: `@UseGuards(Auth, Acl)` + `@ValidationPipe`
- **Service**: DB 트랜잭션 포함
    
    ```
    async createObject(dto) {
      return this.dataSource.transaction(async (manager) => {
        const obj = manager.create(ObjectEntity, dto);
        await manager.save(obj);
        await this.kafka.emit('ontology.object.created', obj);
        return obj;
      });
    }
    
    ```
    
- **Event Emit**: Kafka producer sends typed payload, key = `rid`

### 5.3 VersionModule

- **ChangeSet**: JSONB 워크플로우 기록, 상태(`open`, `merged`, `closed`)
- **Merge**: optimistic locking (version 필드) + 409 처리 → conflict payload 반환
- **Rollback**: historical JSON apply 역순

### 5.4 AuditModule

- **Interceptor**: 모든 mutating request 후 `auditService.log({entity, rid, action, user, before, after})`
- **Storage**: `audit_log` 테이블, JSONB 스냅샷
- **API**: `GET /api/audit-log?entity=object_type&rid=...&page=..`

### 5.5 IndexingService

- **Kafka Consumer**: 그룹 `indexing-service`
- **Error Handling**: 3회 재시도 후 `index_status='failed'` 업데이트 + Slack 알림 via `notificationService`
- **Bulk API**: Bulk index for fullSync

### 5.6 GraphSyncService

- **Full Sync**: Kubernetes CronJob 일일 실행 → `fullSync()`
- **Incremental**: Listen `version.changeset.merged` topic
- **Circuit Breaker**: `opossum` 라이브러리 적용 → Neo4j 장애 시 fallback

---

### 6. API 명세 연계

- APISpec.md에서 정의된 상세 OpenAPI 스펙 자동 생성 (Swagger UI `/docs`)
- Validation: `nestjs/swagger` 및 `class-validator` 로 매핑

---

### 7. DB 설계 & 마이그레이션

- TypeORM 엔티티 어노테이션 기반 설계
- `uuid_generate_v4()` 기본값, `created_at`, `updated_at` 자동 타임스탬프
- 마이그레이션 전략: 각 PR마다 `npm run typeorm:migration:generate`, 리뷰 후 `run`

---

### 8. 보안 정책

- **TLS**: Ingress 레벨에서 강제
- **CORS**: 화이트리스트(`frontend domains`)
- **Input Sanitization**: `class-sanitizer`, SQL Injection 방지
- **CSRF**: `csurf` 미들웨어(REST 경우 custom header로 토큰)
- **Secret Rotation**: Vault/KMS 연동

---

### 9. 성능 최적화

- **Connection Pool**: PostgreSQL max 20, Redis max 50
- **Batching**: Bulk endpoints, Kafka batch size 조정
- **Caching**: Redis LRU 캐시, TTL 5분
- **Profiling**: `clinic.js` 주기적 프로파일링

---

### 10. 관측성 & 로깅

- **Structured Logging**: JSON format, `requestId`, `userId`, `latency`
- **Correlation ID**: `X-Request-ID` 미들웨어
- **Metrics**: Prometheus Counter, Histogram 포함 (`http_requests_total`, `db_query_duration_seconds`)
- **Error Tracking**: Sentry integrated in `errorHandler`

---

### 11. 테스트 전략

- **Unit Tests**: Jest, Mock Repository/Service, 90% 커버리지
- **Integration Tests**: Supertest + Testcontainers(Postgres, Kafka, Redis)
- **Contract Tests**: Pact로 Frontend/Backend 계약 검증
- **Load Tests**: k6 스크립트, 목표 RPS 200, p95 <300ms
- **Security Tests**: OWASP ZAP 스캔, Snyk CI 연동

---

### 12. CI/CD & 배포

- **GitHub Actions**: lint, test, build, image push, helm chart 릴리스
- **Helm Chart**: values-production.yaml, values-staging.yaml
- **Rolling Update**: `maxSurge: 1`, `maxUnavailable: 0`
- **Canary Release**: Argo Rollouts 사용 검토

---

### 13. 백업 & DR

- **PostgreSQL**: pgBackRest 스냅샷, WAL 아카이브, 복구 테스트 주기적 수행
- **Kafka**: 토픽 보존 정책 7일, MirrorMaker2 설정
- **Neo4j**: Enterprise Hot Backup, Point-in-Time Recovery 테스트

---

### 14. 운영 및 유지보수

- **Alerts**: Prometheus Alertmanager (API 5xx >1%, DB connections >80%)
- **Dashboard**: Grafana (latency, error rate, consumer lag)
- **Runbooks**: 장애 대응, 롤백 절차, 데이터 복구 가이드 유지

---

### 15. 후속 문서 링크

- [APISpec.md]
- [InfraSpec.md]
- [CICDSpec.md]
- [QASpec.md]