# JWT Authentication Implementation Plan

## 목표

간단한 JWT 기반 인증 미들웨어를 구현하여 API 엔드포인트를 보호합니다.
(Keycloak 통합은 추후 진행)

## 구현 범위

### 1. JWT 토큰 구조

```typescript
interface JwtPayload {
  sub: string; // User ID (subject)
  email: string; // User email
  name: string; // User display name
  roles: string[]; // User roles
  iat: number; // Issued at
  exp: number; // Expiration time
}
```

### 2. 인증 미들웨어

- Bearer 토큰 추출
- JWT 검증 (서명, 만료시간)
- 사용자 정보를 Request 객체에 추가
- 인증 실패 시 401 응답

### 3. 권한 검사 미들웨어

- 역할 기반 접근 제어 (RBAC)
- 특정 역할이 필요한 엔드포인트 보호
- 권한 부족 시 403 응답

### 4. Mock 사용자 서비스

- 개발/테스트용 임시 토큰 생성
- 하드코딩된 사용자 정보

## 구현 계획

### Step 1: JWT 유틸리티 함수 (TDD)

**파일**: `src/auth/jwt.ts`

테스트 케이스:

- [ ] 유효한 토큰 생성
- [ ] 토큰 검증 성공
- [ ] 만료된 토큰 검증 실패
- [ ] 잘못된 서명 검증 실패
- [ ] 토큰 디코딩

### Step 2: 인증 미들웨어 (TDD)

**파일**: `src/middlewares/auth.ts`

테스트 케이스:

- [ ] Bearer 토큰 추출
- [ ] 유효한 토큰으로 인증 성공
- [ ] 토큰 없음 - 401 응답
- [ ] 잘못된 토큰 형식 - 401 응답
- [ ] 만료된 토큰 - 401 응답

### Step 3: 권한 검사 미들웨어 (TDD)

**파일**: `src/middlewares/authorize.ts`

테스트 케이스:

- [ ] 필요한 역할 보유 시 통과
- [ ] 역할 부족 시 403 응답
- [ ] 인증되지 않은 사용자 - 401 응답
- [ ] 복수 역할 중 하나 보유 시 통과

### Step 4: Express Request 타입 확장

**파일**: `src/types/express.d.ts` (업데이트)

```typescript
declare namespace Express {
  interface Request {
    user?: {
      id: string;
      email: string;
      name: string;
      roles: string[];
    };
  }
}
```

### Step 5: Mock 토큰 생성 엔드포인트

**파일**: `src/routes/auth.ts` (개발용)

- `POST /auth/mock-token` - 테스트용 토큰 생성
- 프로덕션에서는 비활성화

## 사용 예시

```typescript
// 인증이 필요한 라우트
router.get('/api/object-types', authenticate, async (req, res) => {
  // req.user 사용 가능
});

// 특정 역할이 필요한 라우트
router.post('/api/object-types', authenticate, authorize(['admin', 'editor']), async (req, res) => {
  // admin 또는 editor 역할을 가진 사용자만 접근 가능
});
```

## 환경 변수

```
JWT_SECRET=your-secret-key-for-development
JWT_EXPIRES_IN=1h
```

## 보안 고려사항

1. JWT_SECRET은 환경별로 다르게 설정
2. 프로덕션에서는 RS256 알고리즘 사용 고려
3. Refresh 토큰은 현재 범위에서 제외
4. 토큰 블랙리스트는 현재 범위에서 제외

## 테스트 전략

1. 단위 테스트: JWT 유틸리티, 미들웨어
2. 통합 테스트: 실제 Express 앱에서 인증 플로우
3. Mock 데이터로 다양한 사용자 시나리오 테스트

## 다음 단계 (향후)

- Keycloak 통합으로 실제 인증 시스템 연결
- Refresh 토큰 구현
- 토큰 블랙리스트/로그아웃 기능
- 권한 계층 구조 구현
