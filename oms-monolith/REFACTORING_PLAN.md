# OMS 모놀리스 리팩토링 계획

## 현황 분석

### 1. GraphQL Resolvers (api/graphql/resolvers.py - 1,800+ lines)

**문제점:**
- 단일 파일에 Query 19개, Mutation 11개가 집중
- 중복된 변환 로직 (Query용/Mutation용 별도)
- 도메인 경계가 불명확

**도메인 분석:**
- Object Types & Properties (스키마 관리)
- Relationships & Links (관계 관리)
- Actions & Transformations (비즈니스 로직)
- Functions & Data Types (타입 시스템)
- Branch Management (버전 관리)
- Validation & Search (유틸리티)

### 2. Middleware (700-800 lines 파일 다수)

**주요 파일:**
- component_health.py (838 lines, 12 classes)
- service_discovery.py (799 lines, 12 classes)
- rate_limiter.py (841 lines, 11 classes)
- dlq_handler.py (822 lines, 12 classes)
- component_middleware.py (750 lines, 15 classes)

**공통 문제점:**
- 단일 파일에 다중 책임
- Redis 통합 패턴 중복
- 메트릭 수집 로직 중복
- 재시도 로직 중복

## 개선 방안

### 1. GraphQL Resolvers 도메인별 분할

```
api/graphql/
├── __init__.py
├── resolvers/
│   ├── __init__.py
│   ├── base.py              # BaseResolver, ServiceClient
│   ├── schema/              
│   │   ├── __init__.py
│   │   ├── object_types.py  # ObjectTypeResolver
│   │   ├── properties.py    # PropertyResolver
│   │   └── converters.py    # 공통 변환 로직
│   ├── relationships/
│   │   ├── __init__.py
│   │   ├── links.py         # LinkTypeResolver
│   │   └── interfaces.py    # InterfaceResolver
│   ├── actions/
│   │   ├── __init__.py
│   │   └── action_types.py  # ActionTypeResolver
│   ├── types/
│   │   ├── __init__.py
│   │   ├── functions.py     # FunctionTypeResolver
│   │   └── data_types.py    # DataTypeResolver
│   ├── versioning/
│   │   ├── __init__.py
│   │   ├── branches.py      # BranchResolver
│   │   └── history.py       # HistoryResolver
│   └── utilities/
│       ├── __init__.py
│       ├── validation.py    # ValidationResolver
│       └── search.py        # SearchResolver
└── coordinator.py           # GraphQL Coordinator/Facade
```

### 2. Middleware 모듈화

```
middleware/
├── __init__.py
├── health/
│   ├── __init__.py
│   ├── checks/              # 개별 헬스체크 구현
│   ├── monitor.py           # 모니터링 로직
│   └── models.py            # 데이터 모델
├── discovery/
│   ├── __init__.py
│   ├── providers/           # 서비스 디스커버리 프로바이더
│   ├── balancer.py          # 로드 밸런싱
│   └── models.py
├── rate_limiting/
│   ├── __init__.py
│   ├── strategies/          # 알고리즘별 구현
│   ├── adaptive.py          # 적응형 제한
│   └── models.py
├── dlq/
│   ├── __init__.py
│   ├── storage/             # 메시지 저장소
│   ├── handler.py           # 핸들러 로직
│   └── detector.py          # 포이즌 메시지 감지
└── common/
    ├── redis_utils.py       # 공통 Redis 유틸
    ├── metrics.py           # 공통 메트릭
    └── retry.py             # 공통 재시도 로직
```

### 3. Facade/Coordinator 패턴 적용

#### GraphQL Coordinator
```python
# api/graphql/coordinator.py
class GraphQLCoordinator:
    """도메인 리졸버들을 조율하는 Facade"""
    
    def __init__(self):
        self.schema_resolver = SchemaResolver()
        self.relationship_resolver = RelationshipResolver()
        self.action_resolver = ActionResolver()
        # ...
    
    async def resolve_with_context(self, domain, operation, **kwargs):
        """컨텍스트를 고려한 도메인 간 조율"""
        # 도메인 간 의존성 처리
        # 트랜잭션 경계 관리
        # 공통 관심사 처리
```

#### Middleware Coordinator
```python
# middleware/coordinator.py
class MiddlewareCoordinator:
    """미들웨어 컴포넌트들을 조율하는 Facade"""
    
    def __init__(self):
        self.health = HealthCoordinator()
        self.discovery = DiscoveryCoordinator()
        self.rate_limiter = RateLimitCoordinator()
        # ...
    
    async def process_request(self, request):
        """요청 처리 파이프라인 조율"""
        # 미들웨어 실행 순서 관리
        # 컴포넌트 간 데이터 공유
        # 에러 처리 통합
```

## 구현 단계

### Phase 1: GraphQL Resolvers 분할 (1-2주)
1. 도메인별 resolver 클래스 생성
2. 공통 로직 추출 (converters, base resolver)
3. Coordinator 패턴 구현
4. 기존 resolver 대체 및 테스트

### Phase 2: Middleware 모듈화 (2-3주)
1. 공통 유틸리티 추출
2. 각 미들웨어를 서브패키지로 분할
3. 인터페이스 표준화
4. 통합 테스트

### Phase 3: 통합 및 최적화 (1주)
1. 성능 프로파일링
2. 메모리 사용량 최적화
3. 문서화
4. 마이그레이션 가이드 작성

## 기대 효과

1. **가독성 향상**: 파일당 200-300줄로 감소
2. **유지보수성**: 도메인별 독립적 수정 가능
3. **테스트 용이성**: 유닛 테스트 작성 간소화
4. **재사용성**: 공통 로직 중앙화
5. **확장성**: 새 도메인/미들웨어 추가 용이