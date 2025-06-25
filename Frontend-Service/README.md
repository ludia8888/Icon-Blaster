# Frontend Service

OMS 실시간 UI 업데이트 전담 MSA 서비스

## 개요

Frontend Service는 OMS (Ontology Metadata Service)에서 발생하는 이벤트를 구독하여 웹 UI에 실시간 업데이트를 제공하는 마이크로서비스입니다.

### 주요 기능

- **실시간 스키마 변경 알림**: 스키마 생성/수정/삭제 이벤트를 UI에 실시간 전달
- **브랜치 상태 업데이트**: Git 브랜치 변경사항을 대시보드에 반영
- **사용자 알림**: 중요한 변경사항 및 보안 이벤트 알림
- **WebSocket 연결 관리**: 다중 클라이언트 연결 및 구독 관리

## 아키텍처

```
OMS Core Service --> NATS JetStream --> Frontend Service --> WebSocket --> UI
```

### 컴포넌트

- **WebSocket Manager**: 클라이언트 연결 및 메시지 브로드캐스팅
- **Realtime Publisher**: OMS 이벤트 구독 및 UI 형식 변환
- **Authentication**: WebSocket 연결 인증 처리

## 실행 방법

### Docker Compose 사용

```bash
# 서비스 시작
docker-compose up -d

# 로그 확인
docker-compose logs -f frontend-service

# 서비스 중지
docker-compose down
```

### 개발 환경

```bash
# 의존성 설치
pip install -r requirements.txt

# 개발 서버 실행
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8080
```

## API 엔드포인트

### Health Check
```
GET /health
```

### WebSocket 연결
```
WS /ws?token=<jwt_token>
```

### 연결 상태 조회
```
GET /api/v1/connections
GET /api/v1/subscriptions
```

## WebSocket 메시지 형식

### 구독 요청
```json
{
  "type": "subscribe",
  "subscription_id": "schema_changes"
}
```

### 스키마 변경 알림
```json
{
  "type": "schema_change",
  "event": {
    "id": "uuid",
    "operation": "create",
    "resource": {
      "type": "ObjectType",
      "id": "Person",
      "name": "Person"
    },
    "user": "developer@company.com",
    "timestamp": "2024-01-01T12:00:00Z"
  }
}
```

## 환경 변수

| 변수명 | 설명 | 기본값 |
|--------|------|--------|
| `NATS_URL` | NATS 서버 URL | `nats://nats:4222` |
| `JWT_SECRET_KEY` | JWT 서명 키 | `frontend-service-secret` |
| `LOG_LEVEL` | 로그 레벨 | `INFO` |
| `CORS_ORIGINS` | CORS 허용 도메인 | `http://localhost:3000` |

## 구독 타입

- `schema_changes`: 스키마 변경 이벤트
- `branch_updates`: 브랜치 상태 변경
- `admin_notifications`: 관리자 알림
- `security_notifications`: 보안 이벤트 알림

## 모니터링

### 메트릭

- 활성 WebSocket 연결 수
- 구독별 연결 통계
- 메시지 전송/수신 카운터
- 연결 지속 시간

### 로깅

구조화된 JSON 로그를 통해 다음 정보 추적:
- WebSocket 연결/해제
- OMS 이벤트 처리
- 에러 및 예외 상황