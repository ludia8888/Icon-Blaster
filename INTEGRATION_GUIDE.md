# 🏗️ OMS + User Service 통합 가이드

## 📋 개요

이 가이드는 OMS-Monolith와 User-Service를 완전히 통합하여 엔터프라이즈 레벨의 인증/인가 시스템을 구축하는 방법을 설명합니다.

## 🎯 아키텍처 개요

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │  NGINX Gateway  │    │   Monitoring    │
│   (React/Vue)   │◄───┤  (Port 8090)    │───►│  (Prometheus)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │
                        ┌───────┴───────┐
                        │               │
                        ▼               ▼
              ┌─────────────────┐  ┌─────────────────┐
              │  User Service   │  │  OMS Monolith   │
              │  (Port 8000)    │  │  (Port 8000)    │
              │                 │  │                 │
              │ • JWT Auth      │  │ • Business      │
              │ • User Mgmt     │  │   Logic         │
              │ • IAM Adapter   │  │ • RBAC          │
              │ • RBAC          │  │ • Audit         │
              └─────────────────┘  └─────────────────┘
                        │                  │
                        ▼                  ▼
              ┌─────────────────┐  ┌─────────────────┐
              │   User DB       │  │    OMS DB       │
              │  (PostgreSQL)   │  │  (PostgreSQL)   │
              └─────────────────┘  └─────────────────┘
                        │                  │
                        ▼                  ▼
              ┌─────────────────┐  ┌─────────────────┐
              │  User Redis     │  │   OMS Redis     │
              │  (Session)      │  │  (Cache)        │
              └─────────────────┘  └─────────────────┘
```

## 🚀 빠른 시작

### 1. 환경 설정

```bash
# 프로젝트 루트 디렉토리로 이동
cd /Users/isihyeon/Desktop/Arrakis-Project

# 환경 변수 설정
cp .env.shared .env

# JWT 시크릿 업데이트 (필수!)
sed -i 's/your-super-secret-key-change-in-production-environment/YOUR_ACTUAL_SECRET_KEY/' .env
```

### 2. 서비스 시작

```bash
# 모든 서비스 시작
docker-compose -f docker-compose.integrated.yml up -d

# 로그 확인
docker-compose -f docker-compose.integrated.yml logs -f

# 서비스 상태 확인
docker-compose -f docker-compose.integrated.yml ps
```

### 3. 통합 테스트 실행

```bash
# 테스트 스크립트 실행
./integration-test.sh

# 수동 테스트
curl http://localhost:8090/health
```

## 🔧 상세 설정

### 인증 플로우

1. **사용자 로그인**
   ```bash
   curl -X POST http://localhost:8090/auth/login \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=testuser&password=Test123!"
   ```

2. **JWT 토큰 검증**
   ```bash
   curl -X POST http://localhost:8090/api/v1/auth/validate \
     -H "Content-Type: application/json" \
     -d '{"token":"YOUR_JWT_TOKEN"}'
   ```

3. **OMS API 접근**
   ```bash
   curl -X GET http://localhost:8090/api/v1/schemas \
     -H "Authorization: Bearer YOUR_JWT_TOKEN"
   ```

### 환경 변수 설정

#### 필수 설정
```bash
# JWT 설정 (모든 서비스에서 동일해야 함)
JWT_SECRET=your-secret-key
JWT_ALGORITHM=HS256

# IAM 통합 활성화
USE_IAM_VALIDATION=true
IAM_SERVICE_URL=http://user-service:8000
```

#### 선택 설정
```bash
# 토큰 만료 시간
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# 로깅 레벨
LOG_LEVEL=INFO

# CORS 설정
CORS_ORIGINS=http://localhost:8090,http://localhost:3000
```

## 🔍 서비스 엔드포인트

### NGINX Gateway (Port 8090)
- **Base URL**: `http://localhost:8090`
- **Health Check**: `GET /health`

### User Service
- **Login**: `POST /auth/login`
- **User Info**: `GET /auth/userinfo`
- **Token Refresh**: `POST /auth/refresh`
- **Documentation**: `GET /docs`

### IAM Adapter (User Service)
- **Token Validation**: `POST /api/v1/auth/validate`
- **User Info**: `POST /api/v1/users/info`
- **Scope Check**: `POST /api/v1/auth/check-scopes`
- **Service Auth**: `POST /api/v1/auth/service`

### OMS Monolith
- **Schemas**: `GET /api/v1/schemas`
- **Ontologies**: `GET /api/v1/ontologies`
- **Branches**: `GET /api/v1/branches`
- **Audit**: `GET /api/v1/audit`

## 🔐 보안 고려사항

### JWT 토큰 관리
- **시크릿 키**: 모든 서비스에서 동일한 `JWT_SECRET` 사용
- **알고리즘**: `HS256` 또는 `RS256` 지원
- **만료 시간**: 적절한 토큰 만료 시간 설정

### 네트워크 보안
- **내부 통신**: Docker 네트워크 내부에서만 통신
- **외부 접근**: NGINX Gateway를 통한 제어된 접근
- **SSL/TLS**: 프로덕션 환경에서는 HTTPS 사용

### 권한 관리
- **스코프 기반**: 세밀한 권한 제어
- **역할 기반**: 사용자 역할에 따른 접근 제어
- **감사 로깅**: 모든 인증/인가 이벤트 기록

## 📊 모니터링

### Prometheus + Grafana (선택사항)
```bash
# 모니터링 스택 시작
docker-compose -f docker-compose.integrated.yml --profile monitoring up -d

# Prometheus: http://localhost:9090
# Grafana: http://localhost:3000 (admin/admin)
```

### 로그 모니터링
```bash
# 실시간 로그 확인
docker-compose -f docker-compose.integrated.yml logs -f

# 특정 서비스 로그
docker-compose -f docker-compose.integrated.yml logs -f user-service
docker-compose -f docker-compose.integrated.yml logs -f oms-monolith
```

### 메트릭 수집
- **인증 성공/실패율**
- **토큰 검증 레이턴시**
- **API 응답 시간**
- **데이터베이스 연결 상태**

## 🐛 트러블슈팅

### 일반적인 문제

#### 1. 인증 실패 (401 Unauthorized)
```bash
# JWT 시크릿 확인
docker-compose -f docker-compose.integrated.yml exec user-service env | grep JWT_SECRET
docker-compose -f docker-compose.integrated.yml exec oms-monolith env | grep JWT_SECRET

# 토큰 유효성 확인
curl -X POST http://localhost:8090/api/v1/auth/validate \
  -H "Content-Type: application/json" \
  -d '{"token":"YOUR_TOKEN"}'
```

#### 2. 서비스 연결 실패
```bash
# 네트워크 확인
docker network ls | grep oms

# 서비스 상태 확인
docker-compose -f docker-compose.integrated.yml ps

# 로그 확인
docker-compose -f docker-compose.integrated.yml logs nginx-gateway
```

#### 3. 데이터베이스 연결 실패
```bash
# 데이터베이스 상태 확인
docker-compose -f docker-compose.integrated.yml exec user-db pg_isready
docker-compose -f docker-compose.integrated.yml exec oms-db pg_isready

# 연결 테스트
docker-compose -f docker-compose.integrated.yml exec user-service \
  python -c "import asyncio; from core.database import test_connection; asyncio.run(test_connection())"
```

### 디버깅 명령어

```bash
# 서비스 재시작
docker-compose -f docker-compose.integrated.yml restart user-service

# 컨테이너 내부 접근
docker-compose -f docker-compose.integrated.yml exec user-service bash

# 네트워크 테스트
docker-compose -f docker-compose.integrated.yml exec oms-monolith \
  curl -f http://user-service:8000/health

# 설정 확인
docker-compose -f docker-compose.integrated.yml config
```

## 🚢 프로덕션 배포

### 환경 변수 업데이트
```bash
# 프로덕션 환경 변수
JWT_SECRET=STRONG_RANDOM_SECRET_KEY_FOR_PRODUCTION
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=WARNING

# 데이터베이스 보안
POSTGRES_PASSWORD=STRONG_DATABASE_PASSWORD
REDIS_PASSWORD=STRONG_REDIS_PASSWORD

# SSL 설정
IAM_VERIFY_SSL=true
```

### 보안 강화
- **JWT 시크릿**: 강력한 랜덤 키 사용
- **데이터베이스**: 암호화된 연결
- **Redis**: 패스워드 인증 활성화
- **NGINX**: SSL/TLS 인증서 설정

### 스케일링
- **Load Balancer**: 여러 인스턴스 운영
- **Database**: 읽기 전용 복제본
- **Cache**: Redis 클러스터
- **Monitoring**: 전체 메트릭 수집

## 📚 추가 자료

### API 문서
- **User Service**: `http://localhost:8090/docs`
- **OMS API**: `http://localhost:8090/api/v1/docs`

### 설정 파일
- **Docker Compose**: `docker-compose.integrated.yml`
- **NGINX**: `nginx/nginx.conf`
- **Environment**: `.env.shared`

### 테스트 스크립트
- **통합 테스트**: `./integration-test.sh`
- **성능 테스트**: Apache Bench 사용

## 🤝 지원

문제가 발생하거나 추가 지원이 필요한 경우:

1. **로그 확인**: `docker-compose logs`
2. **통합 테스트 실행**: `./integration-test.sh`
3. **문서 검토**: 각 서비스의 README.md
4. **이슈 리포트**: 상세한 에러 메시지와 함께

---

**🎉 성공적인 통합을 위해 이 가이드를 단계별로 따라 진행하세요!**