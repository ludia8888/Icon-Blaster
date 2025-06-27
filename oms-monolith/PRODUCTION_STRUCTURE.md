# 프로덕션 파일 구조

## 정리 완료: 2025년 6월 27일

## 주요 진입점
- `main_secure.py` - 보안 강화된 프로덕션 서버
- `main.py` - 원본 참조용

## 핵심 디렉토리 구조

```
oms-monolith/
├── api/                        # API 엔드포인트
│   ├── gateway/               # API 게이트웨이
│   ├── graphql/              # GraphQL API
│   └── v1/                   # REST API v1
│       ├── schema_generation/
│       ├── semantic_types/
│       └── struct_types/
│
├── config/                     # 설정 파일
│   ├── circuit_breaker_secure.py  # 보안 회로 차단기 설정
│   └── msa_config.py              # MSA 설정
│
├── core/                       # 핵심 비즈니스 로직
│   ├── action/               # 액션 처리
│   ├── audit/                # 감사 로그
│   ├── auth/                 # 인증/인가
│   ├── branch/               # 브랜치 관리
│   ├── concurrency/          # 동시성 제어
│   ├── event_publisher/      # 이벤트 발행
│   ├── event_subscriber/     # 이벤트 구독
│   ├── iam/                  # IAM 통합
│   ├── idempotent/           # 멱등성 처리
│   ├── integrations/         # 외부 서비스 통합
│   ├── schema/               # 스키마 관리
│   └── validation/           # 데이터 검증
│
├── database/                   # 데이터베이스 관련
│   ├── clients/              # DB 클라이언트
│   └── migrations/           # DB 마이그레이션
│
├── middleware/                 # 미들웨어
│   ├── auth_secure.py        # 보안 강화 인증 미들웨어
│   ├── auth_msa.py           # MSA 인증 미들웨어
│   ├── auth_middleware.py    # 기본 인증 미들웨어
│   ├── circuit_breaker.py    # 회로 차단기
│   ├── etag_middleware.py    # ETag 처리
│   ├── issue_tracking_middleware.py  # 이슈 추적
│   ├── rbac_middleware.py    # RBAC
│   └── schema_freeze_middleware.py   # 스키마 동결
│
├── models/                     # 데이터 모델
│   ├── audit_events.py       # 감사 이벤트
│   ├── branch_state.py       # 브랜치 상태
│   ├── permissions.py        # 권한
│   └── shadow_index.py       # 섀도우 인덱스
│
├── scripts/                    # 유틸리티 스크립트
│   ├── dev/                  # 개발용 스크립트
│   ├── utils/                # 유틸리티
│   └── verify_deployment.py  # 배포 검증
│
├── shared/                     # 공통 모듈
│   ├── clients/              # 공통 클라이언트
│   ├── config.py             # 공통 설정
│   └── models/               # 공통 모델
│
└── utils/                      # 유틸리티 함수
    ├── audit_id_generator.py # 감사 ID 생성
    └── git_utils.py          # Git 유틸리티
```

## 프로덕션 배포 체크리스트

### 1. 환경 변수 설정
```bash
export ENVIRONMENT=production
export JWT_SECRET=<secure-secret>
export USER_SERVICE_URL=http://user-service:8001
export AUDIT_SERVICE_URL=http://audit-service:8003
```

### 2. 서비스 시작
```bash
python main_secure.py
```

### 3. 배포 검증
```bash
python scripts/verify_deployment.py
```

## 보안 기능

1. **인증/인가**
   - JWT 기반 인증 (auth_secure.py)
   - RBAC 미들웨어
   - 환경 변수 우회 불가

2. **회로 차단기**
   - 실패 임계값: 100
   - 성공 임계값: 50
   - 복구 검증: 10회

3. **감사 로깅**
   - 모든 요청 추적
   - 보안 이벤트 기록

## 제거된 항목

- 모든 테스트 파일 (`test_*.py`)
- 백업 파일 (`*.bak`)
- 임시 파일 (`*_pid.txt`)
- 디버그 파일 (`debug_*.py`)
- 개발 보고서 (docs/archive로 이동)

## 유지 관리

1. **코드 스타일**
   - Python PEP 8 준수
   - 명확한 함수/클래스 이름
   - 타입 힌트 사용

2. **보안 원칙**
   - 최소 권한 원칙
   - 실패 시 안전한 기본값
   - 모든 입력 검증

3. **문서화**
   - 주요 변경사항은 CHANGELOG 업데이트
   - API 변경은 문서 업데이트
   - 보안 변경은 SECURITY.md 업데이트