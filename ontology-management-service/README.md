# 🚀 OMS (Ontology Management System)

> **엔터프라이즈급 온톨로지 관리 및 데이터 모델링 플랫폼**

OMS는 복잡한 데이터 모델과 온톨로지를 체계적으로 관리하기 위한 현대적인 엔터프라이즈 솔루션입니다. 하이브리드 아키텍처를 통해 모놀리스의 단순함과 마이크로서비스의 확장성을 모두 제공합니다.

## ✨ 주요 기능

### 🏗️ 온톨로지 관리
- **객체 타입(ObjectType)** 정의 및 관리
- **속성(Property)** 시스템 및 데이터 타입 지원  
- **링크 타입(LinkType)** 관계 모델링
- **인터페이스(Interface)** 및 공유 속성 지원

### 🔄 버전 관리
- **Git 스타일 브랜치** 시스템
- **변경 제안(Change Proposal)** 워크플로우
- **Time Travel** 쿼리 (AS OF, BETWEEN, ALL_VERSIONS)
- **감사 추적(Audit Trail)** 완전 지원

### 🌐 API 인터페이스
- **REST API** - 완전한 CRUD 작업 (Port: 8000)
- **GraphQL HTTP** - 실시간 쿼리 (Port: 8006)
- **GraphQL WebSocket** - 실시간 구독 (Port: 8004)
- **OpenAPI 문서** - 자동 생성된 API 문서

### 🔐 보안 및 인증
- **통합 JWT 기반 인증** - 단일 인증 소스
- **RBAC (Role-Based Access Control)** - 세밀한 권한 관리
- **보안 작성자 추적** - 모든 데이터 변경에 암호화 서명된 작성자 정보
- **서비스 계정 관리** - 자동화 및 통합을 위한 특별 계정
- **감사 필드 자동화** - _created_by, _updated_by 자동 추가

### 📊 모니터링 및 관찰성
- **Prometheus** 메트릭 수집 (Port: 9091)
- **Grafana** 대시보드 (Port: 3000)
- **Jaeger** 분산 트레이싱 (Port: 16686)
- **실시간 헬스 체크** + 보안 알림

## 🏛️ 아키텍처

OMS는 **하이브리드 아키텍처**를 채택하여 필요에 따라 모놀리스 또는 마이크로서비스로 운영할 수 있습니다.

### 배포 모드

#### 1. 모놀리스 모드 (기본)
모든 기능이 단일 애플리케이션으로 통합되어 운영되는 전통적인 방식입니다.

```bash
# 환경 설정 (모든 마이크로서비스 기능 비활성화)
USE_EMBEDDING_MS=false
USE_SCHEDULER_MS=false  
USE_EVENT_GATEWAY=false
USE_DATA_KERNEL_GATEWAY=false

# 실행
docker-compose up
```

#### 2. 마이크로서비스 모드
특정 기능들을 독립적인 서비스로 분리하여 운영하는 확장 가능한 방식입니다.

```bash
# 환경 설정 (선택적 마이크로서비스 활성화)
USE_EMBEDDING_MS=true      # Vector 임베딩 서비스
USE_SCHEDULER_MS=true      # 스케줄러 서비스
USE_EVENT_GATEWAY=true     # 이벤트 게이트웨이
USE_DATA_KERNEL_GATEWAY=true  # 데이터 커널 게이트웨이

# 실행
docker-compose up -d
docker-compose -f docker-compose.microservices.yml up -d
```

### 마이크로서비스 구성

| 서비스 | 포트 | 기능 | 상태 |
|--------|------|------|------|
| **Embedding Service** | 8001/50055 | 벡터 임베딩, 유사도 검색 | ✅ 구현 완료 |
| **Scheduler Service** | 8002/50056 | 작업 스케줄링, 백그라운드 작업 | ✅ 구현 완료 |
| **Event Gateway** | 8003/50057 | 이벤트 스트리밍, 웹훅 전달 | ✅ 구현 완료 |
| **Data-Kernel Gateway** | 8080/50051 | TerminusDB 추상화 계층 | ✅ 구현 완료 |

## 🚀 빠른 시작

### 필수 요구사항
- Docker & Docker Compose
- Python 3.9+ (로컬 개발 시)

### 설치 및 실행

```bash
# 1. 저장소 클론
git clone <repository-url>
cd oms-monolith

# 2. 환경 설정
cp .env.example .env
# .env 파일을 편집하여 필요한 설정 조정

# 3. 모놀리스 모드로 실행
docker-compose up

# 또는 마이크로서비스 모드로 실행
cp .env.microservices .env
docker-compose up -d
docker-compose -f docker-compose.microservices.yml up -d
```

### API 접근
- **REST API**: http://localhost:8000/docs
- **GraphQL Playground**: http://localhost:8006/graphql
- **WebSocket**: ws://localhost:8004/graphql
- **Prometheus**: http://localhost:9091
- **Grafana**: http://localhost:3000 (admin/admin)

## 🛠️ 개발 가이드

### 프로젝트 구조
```
oms-monolith/
├── api/                    # REST API 및 GraphQL 엔드포인트
├── bootstrap/              # 애플리케이션 팩토리 및 의존성 주입
├── core/                   # 핵심 비즈니스 로직
│   ├── audit/             # 감사 시스템
│   ├── auth_utils/        # 인증 유틸리티
│   ├── branch/            # 브랜치 관리
│   ├── schema/            # 스키마 관리
│   └── validation/        # 데이터 검증
├── data_kernel/           # TerminusDB 게이트웨이
├── middleware/            # 요청/응답 미들웨어
├── services/              # 마이크로서비스 구현
│   ├── embedding-service/ # 벡터 임베딩 서비스
│   ├── scheduler-service/ # 스케줄러 서비스
│   └── event-gateway/     # 이벤트 게이트웨이
├── shared/                # 공유 유틸리티 및 스텁
├── database/              # 데이터베이스 클라이언트
├── monitoring/            # 모니터링 설정
└── tests/                 # 테스트 스위트
```

### 환경 변수 설정

주요 환경 변수는 `.env.example`을 참조하세요. 핵심 설정:

```bash
# 데이터베이스
TERMINUSDB_ENDPOINT=http://terminusdb:6363
DATABASE_URL=postgresql://oms_user:oms_password@postgres:5432/oms_db
REDIS_URL=redis://redis:6379

# 마이크로서비스 토글
USE_EMBEDDING_MS=false      # 임베딩 마이크로서비스 사용 여부
USE_SCHEDULER_MS=false      # 스케줄러 마이크로서비스 사용 여부
USE_EVENT_GATEWAY=false     # 이벤트 게이트웨이 사용 여부

# 보안
JWT_SECRET=your-secret-key-here
```

### 개발 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# 개발 모드 실행
python main.py

# 테스트 실행
pytest tests/
```

## 📊 모니터링

### 헬스 체크
- **기본**: `GET /health`
- **상세**: `GET /health/detailed` (인증 필요)
- **라이브니스**: `GET /health/live`
- **레디니스**: `GET /health/ready`

### 메트릭 엔드포인트
- **Prometheus**: `GET /metrics`
- **서비스별 메트릭**: 각 마이크로서비스의 `/metrics`

### 모니터링 스택 실행
```bash
cd monitoring
./setup_monitoring.sh

# 완전한 모니터링 포함 실행
docker-compose -f docker-compose.yml \
               -f docker-compose.microservices.yml \
               -f monitoring/docker-compose.monitoring.yml up
```

## 🔐 인증 사용법

### JWT 토큰 기반 인증

```python
# 올바른 인증 패턴
from middleware.auth_middleware import get_current_user
from database.dependencies import get_secure_database

@router.post("/items")
async def create_item(
    item: ItemCreate,
    user: UserContext = Depends(get_current_user),
    db: SecureDatabaseAdapter = Depends(get_secure_database)
):
    # 자동으로 작성자 정보가 추가됨
    result = await db.create(
        user_context=user,
        collection="items",
        document=item.dict()
    )
    return result
```

### 감사 필드

모든 데이터베이스 쓰기 작업에 자동으로 추가되는 필드:
- `_created_by`: 작성자 ID
- `_created_by_username`: 작성자 이름
- `_created_at`: 생성 시간
- `_updated_by`: 수정자 ID
- `_updated_by_username`: 수정자 이름
- `_updated_at`: 수정 시간

## 🤝 기여하기

1. 이슈 생성 또는 기능 제안
2. 포크 및 브랜치 생성
3. 변경사항 커밋 (보안 가이드라인 준수)
4. 풀 리퀘스트 생성

## 📚 문서

- [아키텍처 상세](./ARCHITECTURE.md)
- [인증 마이그레이션 가이드](./docs/AUTHENTICATION_MIGRATION.md)
- [서비스 계정 정책](./docs/SERVICE_ACCOUNT_POLICY.md)
- [프로덕션 배포 가이드](./migrations/PRODUCTION_DEPLOYMENT_README.md)

## 📄 라이선스

이 프로젝트는 [MIT 라이선스](LICENSE)를 따릅니다.

---

**문의사항**: oms-team@company.com | **이슈 트래커**: [GitHub Issues](https://github.com/your-org/oms-monolith/issues)