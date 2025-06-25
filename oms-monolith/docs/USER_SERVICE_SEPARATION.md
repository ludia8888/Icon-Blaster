# User Service MSA 분리 가이드

## 개요

OMS의 User Service를 별도의 마이크로서비스(IdP - Identity Provider)로 분리하여 스키마 관리와 보안이 독립적으로 진화할 수 있도록 합니다.

## 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                        Client Apps                          │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    API Gateway                               │
│                 (Auth Middleware)                            │
└──────┬──────────────┴───────────────────┬───────────────────┘
       │                                  │
       │ JWT Token                        │ Permission Check
       ▼                                  ▼
┌──────────────────┐              ┌───────────────────┐
│   OMS Service    │              │   IdP Service     │
│                  │◄─────────────│                   │
│ - Schema Mgmt    │   Optional   │ - Authentication  │
│ - Validation     │   IdP Call   │ - User Mgmt       │
│ - Branch Mgmt    │              │ - MFA             │
│ - Min Auth Check │              │ - Session Mgmt    │
└──────────────────┘              └───────────────────┘
       │                                  │
       ▼                                  ▼
┌──────────────────┐              ┌───────────────────┐
│  TerminusDB      │              │   PostgreSQL      │
└──────────────────┘              └───────────────────┘
```

## OMS 변경사항

### 1. 최소 권한 체크 모듈

**`core/auth/resource_permission_checker.py`**
- JWT 토큰 검증
- 리소스별 권한 체크
- Role 기반 권한 매핑
- IdP 연동 (선택적)

### 2. 인증 미들웨어

**`middleware/auth_middleware.py`**
- JWT 토큰에서 사용자 정보 추출
- Request context에 사용자 정보 주입
- 공개 경로 처리

### 3. 권한 체크 통합

```python
# Before (모놀리식)
from core.user.service import UserService
user = await user_service.get_current_user(token)
if not user.has_permission("schema:create"):
    raise PermissionError()

# After (MSA)
from core.auth import check_permission, ResourceType, Action
if not check_permission(token, ResourceType.SCHEMA, "*", Action.CREATE):
    raise HTTPException(status_code=403)
```

## IdP Service 스펙

### 필수 엔드포인트

1. **POST /auth/login**
   ```json
   Request: {
     "username": "string",
     "password": "string",
     "mfa_code": "string (optional)"
   }
   Response: {
     "access_token": "JWT",
     "refresh_token": "JWT",
     "token_type": "Bearer"
   }
   ```

2. **POST /auth/refresh**
   ```json
   Request: {
     "refresh_token": "string"
   }
   Response: {
     "access_token": "JWT"
   }
   ```

3. **GET /auth/userinfo**
   ```json
   Headers: {
     "Authorization": "Bearer {token}"
   }
   Response: {
     "user_id": "string",
     "username": "string",
     "email": "string",
     "roles": ["admin", "developer"],
     "permissions": ["schema:*:*"],
     "teams": ["team-1", "team-2"]
   }
   ```

4. **POST /auth/check-permission** (선택적)
   ```json
   Request: {
     "user_id": "string",
     "resource_type": "schema",
     "resource_id": "schema-123",
     "action": "update"
   }
   Response: {
     "allowed": true
   }
   ```

### JWT 토큰 구조

```json
{
  "sub": "user-123",
  "username": "john.doe",
  "email": "john@example.com",
  "roles": ["developer", "reviewer"],
  "permissions": [
    "schema:*:read",
    "schema:*:create",
    "branch:*:create"
  ],
  "teams": ["backend", "platform"],
  "exp": 1234567890,
  "iat": 1234567890
}
```

## 권한 모델

### Role 기반 권한

| Role | 권한 |
|------|------|
| admin | 모든 권한 (`*:*:*`) |
| developer | 스키마 CRUD, 검증, 브랜치 생성/머지 |
| reviewer | 읽기 권한, 브랜치 승인 |
| viewer | 모든 리소스 읽기 권한 |

### 권한 문자열 형식

```
{resource_type}:{resource_id}:{action}

예시:
- schema:*:create       # 모든 스키마 생성
- schema:123:update     # 특정 스키마 수정
- branch:*:merge        # 모든 브랜치 머지
- *:*:read             # 모든 리소스 읽기
```

## 마이그레이션 가이드

### 1단계: IdP 서비스 구축
1. User Service 코드를 별도 저장소로 이동
2. REST API 엔드포인트 구현
3. JWT 토큰 발급 로직 구현

### 2단계: OMS 업데이트
1. `core/auth` 모듈 추가
2. `AuthMiddleware` 적용
3. 각 엔드포인트에 권한 체크 추가

### 3단계: 점진적 전환
1. 새 엔드포인트부터 새로운 인증 방식 적용
2. 기존 엔드포인트 점진적 마이그레이션
3. User Service 제거

## 환경 변수

```bash
# OMS 환경 변수
JWT_SECRET=your-secret-key
JWT_ALGORITHM=HS256
IDP_ENDPOINT=https://idp.example.com  # 선택적

# IdP 환경 변수
DATABASE_URL=postgresql://user:pass@localhost/idp
REDIS_URL=redis://localhost:6379
JWT_SECRET=your-secret-key
MFA_ISSUER=YourCompany
```

## 보안 고려사항

1. **JWT 보안**
   - 짧은 만료 시간 (30분)
   - Refresh Token 사용
   - 강력한 Secret Key

2. **네트워크 보안**
   - HTTPS 필수
   - mTLS (선택적)
   - API Gateway에서 Rate Limiting

3. **권한 캐싱**
   - 5분 TTL
   - Redis 캐시 사용 권장

## 장점

1. **독립적 진화**
   - 스키마 변경과 보안 정책 독립
   - 각 팀이 독립적으로 배포

2. **확장성**
   - IdP 서비스 별도 스케일링
   - 다른 서비스에서도 재사용 가능

3. **운영 단순화**
   - 보안 이슈와 비즈니스 로직 분리
   - 각 서비스별 전문 팀 운영

4. **표준 준수**
   - OAuth2/OIDC 표준 적용 가능
   - 기존 IdP 솔루션 통합 가능