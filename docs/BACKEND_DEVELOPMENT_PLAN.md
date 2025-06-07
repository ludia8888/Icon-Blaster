# Backend Development Plan

## 개발 원칙

- **TDD (Test-Driven Development)**: 모든 기능은 테스트 먼저 작성
- **작은 단위 개발**: 함수는 10-30줄, 단일 책임 원칙
- **즉각적 검증**: 각 단계마다 테스트 실행
- **문서화**: 모든 결정과 구현 내용 기록

## Phase 1: 기본 인프라 구축

### 1.1 Express 서버 초기 설정 ✅ TODO #17

**목표**: 최소한의 Express 서버 구동

- [x] package.json 생성
- [x] Express + TypeScript 설정
- [x] 기본 서버 부트스트랩 (server.ts, app.ts)
- [x] Health check 엔드포인트 (/health)
- [x] 테스트: 서버 시작/종료, health check 응답

### 1.2 TypeORM 설정 및 PostgreSQL 연결 ✅ TODO #18

**목표**: 데이터베이스 연결 확립

- [x] TypeORM 설정 (database/config.ts)
- [ ] Docker Compose로 로컬 PostgreSQL 설정
- [x] DataSource 싱글톤 패턴 구현
- [x] 연결 테스트 및 에러 처리
- [x] 테스트: DB 연결/해제

### 1.3 기본 미들웨어 구현 ✅ TODO #19

**목표**: 필수 미들웨어 계층 구축

- [x] 에러 핸들링 미들웨어
  - [x] 전역 에러 핸들러
  - [x] 커스텀 에러 클래스 (AppError)
  - [x] 에러 응답 포맷 (contracts 패키지 활용)
- [ ] 로깅 미들웨어 (Winston)
  - [ ] 구조화된 로그 포맷
  - [ ] Request ID 추가
  - [ ] 환경별 로그 레벨
- [x] CORS 설정
- [ ] 요청 검증 미들웨어
- [x] 테스트: 각 미들웨어 단위 테스트

### 1.4 JWT 검증 미들웨어 ✅ TODO #20

**목표**: 간단한 인증 계층 (Keycloak은 추후)

- [ ] JWT 토큰 검증 로직
- [ ] 인증 미들웨어
- [ ] 권한 검사 데코레이터
- [ ] Mock 사용자 정보
- [ ] 테스트: 유효/무효 토큰, 권한 검사

## Phase 2: ObjectType CRUD 구현

### 2.1 ObjectType 엔티티 정의 ✅ TODO #21

**목표**: TypeORM 엔티티 및 DB 스키마

- [x] ObjectType 엔티티 클래스
- [x] 인덱스 및 제약조건
- [ ] 마이그레이션 생성
- [ ] Seed 데이터
- [x] 테스트: 엔티티 검증

### 2.2 ObjectType Repository ✅ TODO #22

**목표**: 데이터 접근 계층

- [ ] Repository 인터페이스 정의
- [ ] TypeORM Repository 구현
- [ ] 페이징 및 필터링
- [ ] 트랜잭션 처리
- [ ] 테스트: CRUD 작업, 동시성

### 2.3 ObjectType Service ✅ TODO #23

**목표**: 비즈니스 로직 계층

- [ ] Service 인터페이스 정의
- [ ] 비즈니스 규칙 구현
  - [ ] 중복 검사
  - [ ] 버전 관리
  - [ ] 이벤트 발행 (추후 Kafka)
- [ ] DTO 변환
- [ ] 테스트: 모든 비즈니스 시나리오

### 2.4 ObjectType Controller ✅ TODO #24

**목표**: HTTP 엔드포인트

- [ ] Controller 클래스
- [ ] 라우트 정의 (/api/object-type)
- [ ] 요청/응답 처리
- [ ] OpenAPI 문서 연동
- [ ] 통합 테스트: 전체 API 흐름

## 검증 기준

각 단계 완료 시:

1. 단위 테스트 커버리지 90% 이상
2. 통합 테스트 통과
3. ESLint/Prettier 검사 통과
4. 문서 업데이트

## 진행 상황

- Phase 1: 50% 완료
  - Express 서버 초기 설정: ✅ 완료
  - TypeORM 설정: ✅ 완료 (Docker Compose 제외)
  - 기본 미들웨어: ✅ 부분 완료 (로깅 미들웨어 제외)
  - JWT 미들웨어: ⏳ 진행 예정
- Phase 2: 25% 완료
  - ObjectType 엔티티: ✅ 완료
  - Property 엔티티: ✅ 완료 (추가)
  - LinkType 엔티티: ✅ 완료 (추가)
  - Repository, Service, Controller: ⏳ 진행 예정

## 참고 문서

- [BackendSpec.md](../BackendSpec.md)
- [APISpec.md](../APISpec.md)
- [CLAUDE-RULES.md](../CLAUDE-RULES.md)
