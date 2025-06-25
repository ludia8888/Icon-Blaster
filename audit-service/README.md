# Audit Service MSA

## 개요

OMS에서 분리된 독립적인 감사 로그 서비스입니다. OMS의 MSA 경계를 명확히 하기 위해 조회/저장/관리 기능을 전담합니다.

## 🎯 Audit Service 핵심 책임

### ✅ Audit Service가 담당하는 기능
- **감사 로그 수집/저장** (OMS 이벤트 구독)
- **감사 로그 조회 API** (히스토리 목록, 커밋 상세 등)
- **SIEM 통합** (중앙 SIEM 전송)
- **규제 준수 리포트** (SOX, GDPR 등)
- **감사 로그 보존 정책** (7년 보관 등)
- **감사 로그 검색/필터링**
- **감사 데이터 분석/통계**

### ❌ OMS가 담당하는 기능 (분리됨)
- **스키마 변경 이벤트 발행** → OMS HistoryEventPublisher
- **스키마 복원** → OMS HistoryEventPublisher
- **스키마 메타데이터 관리** → OMS

## 📁 서비스 구조

```
audit-service/
├── README.md                    # 이 문서
├── main.py                      # FastAPI 앱 엔트리포인트
├── requirements.txt             # Python 의존성
├── Dockerfile                   # Docker 빌드 설정
├── docker-compose.yml           # 로컬 개발 환경
├── api/                         # API 레이어
│   ├── __init__.py
│   ├── routes/                  # API 라우트
│   │   ├── __init__.py
│   │   ├── history.py           # 히스토리 조회 API
│   │   ├── audit.py             # 감사 로그 API
│   │   ├── reports.py           # 리포트 API
│   │   └── health.py            # 헬스체크 API
│   └── middleware/              # API 미들웨어
│       ├── __init__.py
│       ├── auth.py              # 인증/인가
│       ├── cors.py              # CORS 설정
│       └── rate_limit.py        # 요청 제한
├── core/                        # 비즈니스 로직
│   ├── __init__.py
│   ├── services/                # 서비스 레이어
│   │   ├── __init__.py
│   │   ├── audit_service.py     # 감사 로그 서비스
│   │   ├── history_service.py   # 히스토리 서비스
│   │   ├── siem_service.py      # SIEM 통합 서비스
│   │   └── report_service.py    # 리포트 서비스
│   ├── repositories/            # 데이터 접근 레이어
│   │   ├── __init__.py
│   │   ├── audit_repository.py  # 감사 로그 저장소
│   │   └── history_repository.py # 히스토리 저장소
│   └── subscribers/             # 이벤트 구독
│       ├── __init__.py
│       ├── oms_subscriber.py    # OMS 이벤트 구독자
│       └── event_processor.py   # 이벤트 처리기
├── models/                      # 데이터 모델
│   ├── __init__.py
│   ├── audit.py                 # 감사 로그 모델
│   ├── history.py               # 히스토리 모델
│   ├── siem.py                  # SIEM 모델
│   └── reports.py               # 리포트 모델
├── database/                    # 데이터베이스 설정
│   ├── __init__.py
│   ├── connection.py            # DB 연결 관리
│   ├── migrations/              # 데이터베이스 마이그레이션
│   │   └── __init__.py
│   └── schemas.sql              # 테이블 스키마
├── utils/                       # 유틸리티
│   ├── __init__.py
│   ├── logger.py                # 구조화 로깅
│   ├── auth.py                  # 인증 유틸
│   └── validators.py            # 데이터 검증
├── config/                      # 설정
│   ├── __init__.py
│   ├── settings.py              # 앱 설정
│   ├── siem_config.py           # SIEM 설정
│   └── retention_policy.py      # 보존 정책
├── tests/                       # 테스트
│   ├── __init__.py
│   ├── conftest.py              # 테스트 설정
│   ├── unit/                    # 단위 테스트
│   ├── integration/             # 통합 테스트
│   └── e2e/                     # E2E 테스트
└── docs/                        # 문서
    ├── API.md                   # API 문서
    ├── DEPLOYMENT.md            # 배포 가이드
    └── SIEM_INTEGRATION.md      # SIEM 연동 가이드
```

## 🔄 OMS에서 이관된 기능

### 1. 이관된 모델들
```python
# From: oms-monolith/core/history/models.py
class HistoryQuery          # 히스토리 조회 파라미터
class HistoryListResponse   # 히스토리 목록 응답
class CommitDetail          # 커밋 상세 정보
class AuditLogEntry         # SIEM 전송용 감사 로그
```

### 2. 이관된 API들
```python
# From: oms-monolith/core/history/routes.py
GET    /api/v1/history/                    # 히스토리 목록
GET    /api/v1/history/{commit_hash}       # 커밋 상세
GET    /api/v1/history/audit/export        # 감사 로그 내보내기
```

### 3. 이관된 서비스 로직
```python
# From: oms-monolith/core/history/service.py
async def list_history()        # 히스토리 조회
async def get_commit_detail()   # 커밋 상세 조회
async def export_audit_logs()   # 감사 로그 내보내기
```

## 🔗 OMS와의 연동

### Event-Driven 아키텍처
```yaml
# OMS → Audit Service 이벤트 스트림
events:
  - schema.changed           # 스키마 변경 이벤트
  - schema.reverted          # 스키마 복원 이벤트
  - audit.event              # 감사 이벤트

# 이벤트 구독 방식
subscriber:
  type: NATS/Kafka/EventBridge
  topics: 
    - oms.schema.*
    - oms.audit.*
```

### API 연동
```python
# Frontend → Audit Service 직접 호출
GET /api/v1/audit/history          # 히스토리 조회
GET /api/v1/audit/commits/{hash}   # 커밋 상세
GET /api/v1/audit/reports/sox      # SOX 리포트
```

## 🚀 시작하기

### 1. 개발 환경 설정
```bash
cd audit-service
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 데이터베이스 설정
```bash
# PostgreSQL 설정
docker-compose up -d postgres

# 마이그레이션 실행
alembic upgrade head
```

### 3. 서비스 실행
```bash
# 개발 모드
uvicorn main:app --reload --port 8001

# 프로덕션 모드
gunicorn main:app -k uvicorn.workers.UvicornWorker
```

## 📊 모니터링

### 메트릭스
- 이벤트 처리 속도 (events/sec)
- 감사 로그 저장 지연시간
- SIEM 전송 성공률
- API 응답 시간

### 로깅
- 구조화 JSON 로깅
- ELK Stack 연동
- 감사 추적 (Audit Trail)

## 🔒 보안

### 인증/인가
- JWT 토큰 인증
- RBAC 권한 관리
- API 키 관리

### 데이터 보호
- 데이터 암호화 (저장/전송)
- 개인정보 마스킹
- 접근 로그 기록

## 🏗️ 배포

### Docker
```bash
docker build -t audit-service:latest .
docker run -p 8001:8001 audit-service:latest
```

### Kubernetes
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: audit-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: audit-service
  template:
    metadata:
      labels:
        app: audit-service
    spec:
      containers:
      - name: audit-service
        image: audit-service:latest
        ports:
        - containerPort: 8001
```

## 🔧 설정

### 환경 변수
```bash
DATABASE_URL=postgresql://user:pass@localhost/audit
REDIS_URL=redis://localhost:6379
SIEM_ENDPOINT=https://siem.company.com/api
EVENT_BROKER_URL=nats://localhost:4222
LOG_LEVEL=INFO
```

## 📈 확장성

### 수평 확장
- 무상태(Stateless) 서비스 설계
- 로드 밸런서 지원
- 데이터베이스 읽기 복제본

### 성능 최적화
- Redis 캐싱
- 데이터베이스 인덱싱
- 배치 처리 최적화

## 🎉 이관 효과

### 1. MSA 경계 명확화
- ✅ 단일 책임 원칙 준수
- ✅ 독립적인 배포/확장
- ✅ 장애 격리 (Blast Radius 축소)

### 2. 성능 향상
- ✅ 전용 데이터베이스
- ✅ 캐싱 최적화
- ✅ 인덱스 전략

### 3. 보안 강화
- ✅ 감사 데이터 분리
- ✅ 전용 인증/인가
- ✅ 규제 준수 특화

### 4. 운영 효율성
- ✅ 독립적인 모니터링
- ✅ 전용 SLA 관리
- ✅ 특화된 백업/복구