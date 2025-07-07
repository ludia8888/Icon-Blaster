# OMS + User Service 통합 계획

## 🎯 목표
OMS의 인증/인가를 User Service로 완전히 위임하여 실제 프로덕션과 동일한 환경 구축

## 📋 Phase 1: User Service 준비 (30분)

### 1.1 User Service 설정
```bash
cd /Users/isihyeon/Desktop/Arrakis-Project/user-service

# requirements.txt 생성 (코드 분석 기반)
cat > requirements.txt << EOF
fastapi==0.104.1
uvicorn[standard]==0.24.0
asyncpg==0.29.0
sqlalchemy==2.0.23
alembic==1.12.1
redis==5.0.1
passlib[argon2,bcrypt]==1.7.4
python-jose[cryptography]==3.3.0
python-multipart==0.0.6
pydantic==2.5.0
pydantic-settings==2.1.0
python-json-logger==2.0.7
httpx==0.25.2
python-dotenv==1.0.0
EOF

# main.py 생성 (누락된 파일)
# .env 파일 생성
```

### 1.2 포트 충돌 해결
- User Service: 8000 → **8001**로 변경
- OMS: 8000 유지

## 📋 Phase 2: Docker Compose 통합 (45분)

### 2.1 통합 docker-compose.yml
```yaml
version: '3.8'

services:
  # User Service 추가
  user-service:
    build: ./user-service
    container_name: user-service
    ports:
      - "8001:8000"  # 내부는 8000, 외부는 8001
    environment:
      - DATABASE_URL=postgresql://user_service:password@user-db:5432/user_service
      - REDIS_URL=redis://user-redis:6379
      - JWT_SECRET_KEY=shared-secret-key-for-testing
      - API_GATEWAY_URL=http://localhost:8090
    depends_on:
      - user-db
      - user-redis
    networks:
      - oms-network

  # User Service 전용 DB
  user-db:
    image: postgres:15-alpine
    container_name: user-db
    environment:
      - POSTGRES_DB=user_service
      - POSTGRES_USER=user_service
      - POSTGRES_PASSWORD=password
    volumes:
      - user-db-data:/var/lib/postgresql/data
    networks:
      - oms-network

  # User Service 전용 Redis
  user-redis:
    image: redis:7-alpine
    container_name: user-redis
    networks:
      - oms-network

  # OMS 설정 업데이트
  oms-monolith:
    environment:
      - AUTH_MODE=iam_service  # local → iam_service로 변경
      - IAM_SERVICE_URL=http://user-service:8000  # 내부 통신
      - JWT_SECRET_KEY=shared-secret-key-for-testing  # 동일한 시크릿
```

### 2.2 네트워크 구성
- 모든 서비스가 `oms-network`를 공유
- 내부 통신: 서비스명과 내부 포트 사용
- 외부 접근: 호스트 포트 매핑

## 📋 Phase 3: OMS 코드 수정 (30분)

### 3.1 환경 변수 업데이트
```python
# .env
AUTH_MODE=iam_service
IAM_SERVICE_URL=http://localhost:8001  # 개발시
# Docker 내부: http://user-service:8000
```

### 3.2 인증 미들웨어 수정
```python
# middleware/auth_middleware.py
if settings.AUTH_MODE == "iam_service":
    # User Service의 /auth/userinfo 호출
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{settings.IAM_SERVICE_URL}/auth/userinfo",
            headers={"Authorization": f"Bearer {token}"}
        )
```

### 3.3 권한 검증 통합
```python
# User Service의 /auth/check-permission 활용
async def check_permission(user_id: str, permission: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.IAM_SERVICE_URL}/auth/check-permission",
            json={"permission": permission},
            headers={"Authorization": f"Bearer {token}"}
        )
```

## 📋 Phase 4: 테스트 시나리오 (30분)

### 4.1 통합 테스트 스크립트
```bash
#!/bin/bash
# 1. User Service에서 사용자 생성 및 로그인
TOKEN=$(curl -X POST http://localhost:8001/auth/login \
  -d "username=testuser&password=Test123!" \
  | jq -r '.access_token')

# 2. OMS API 호출 (User Service 토큰 사용)
curl -X POST http://localhost:8000/api/v1/schema \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{...}'

# 3. 감사 로그 확인 (작성자 추적)
# 4. 권한 검증 테스트
```

### 4.2 검증 항목
- [x] User Service 로그인 → JWT 토큰 발급
- [x] OMS가 User Service 토큰 검증
- [x] SecureDatabaseAdapter가 사용자 정보 추출
- [x] Audit 필드에 올바른 사용자 정보 기록
- [x] 권한 기반 접근 제어 작동

## 📋 Phase 5: 모니터링 설정 (15분)

### 5.1 Prometheus 메트릭 통합
- User Service 메트릭 수집 추가
- 인증 실패율 대시보드
- 토큰 검증 레이턴시 추적

### 5.2 로그 통합
- User Service 로그를 중앙 로깅으로 수집
- 인증 이벤트와 OMS 작업 연관 분석

## 🚨 주의사항

1. **시크릿 관리**
   - JWT_SECRET_KEY는 모든 서비스가 동일해야 함
   - 프로덕션에서는 환경 변수로 관리

2. **네트워크 보안**
   - User Service는 내부 네트워크에서만 접근
   - API Gateway를 통한 외부 노출 제한

3. **세션 동기화**
   - Redis를 공유하거나 별도 세션 동기화 메커니즘 필요

4. **버전 호환성**
   - User Service API 변경시 OMS 코드도 업데이트 필요

## 🎯 예상 결과

1. **완전한 인증/인가 분리**
   - OMS는 비즈니스 로직에만 집중
   - User Service가 모든 인증 처리

2. **실제 프로덕션 환경 시뮬레이션**
   - JWT 토큰 기반 인증
   - 마이크로서비스 간 통신
   - 분산 트랜잭션 및 감사

3. **확장 가능한 아키텍처**
   - 다른 서비스도 동일한 패턴으로 통합 가능
   - API Gateway 추가 용이

## 📊 성공 지표

- 모든 OMS API가 User Service 토큰으로 작동
- Audit 로그에 정확한 사용자 정보 기록
- 권한 기반 접근 제어 정상 작동
- 세션 관리 및 토큰 갱신 정상 작동