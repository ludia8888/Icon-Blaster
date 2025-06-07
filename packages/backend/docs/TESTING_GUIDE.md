# 테스트 가이드

## 개요

이 프로젝트는 여러 레벨의 테스트를 통해 코드 품질을 보장합니다:

- **Unit Tests**: 개별 함수/클래스 테스트
- **Integration Tests**: 실제 DB를 사용한 API 통합 테스트
- **Type Tests**: 컴파일 타임 타입 안전성 검증

## 테스트 실행 명령

### 모든 테스트 실행

```bash
npm test
```

### Unit 테스트만 실행

```bash
npm run test:unit
```

### Integration 테스트 실행

```bash
npm run test:integration
```

이 명령은:

- TestContainers로 PostgreSQL 컨테이너 자동 시작
- 실제 DB 환경에서 API 엔드투엔드 테스트
- 테스트 후 컨테이너 자동 정리

### 테스트 커버리지 확인

```bash
npm run test:coverage
```

### Watch 모드로 개발

```bash
npm run test:watch              # 모든 테스트
npm run test:integration:watch  # 통합 테스트만
```

## Integration 테스트 작성 가이드

### 1. 테스트 환경 설정

```typescript
import { testEnvironment } from './test-db-setup';

beforeAll(async () => {
  // DB 컨테이너 시작
  const dbConfig = await testEnvironment.start();

  // DataSource 초기화
  dataSource = await testEnvironment.createDataSource(dbConfig);

  // 시드 데이터 생성
  await testEnvironment.seedTestData(dataSource);
});

afterAll(async () => {
  // 자원 정리
  await testEnvironment.cleanup();
});
```

### 2. API 테스트 작성

```typescript
it('should create a resource', async () => {
  const response = await request(app)
    .post('/api/resources')
    .set('Authorization', `Bearer ${authToken}`)
    .send(validData)
    .expect(201);

  // 명시적 검증
  expect(response.body).toMatchObject({
    id: expect.stringMatching(/^[0-9a-f-]{36}$/),
    ...validData,
  });

  // DB 검증
  const saved = await repository.findOne({ where: { id: response.body.id } });
  expect(saved).toBeDefined();
});
```

### 3. 에러 케이스 테스트

```typescript
it('should handle validation errors', async () => {
  const response = await request(app).post('/api/resources').send(invalidData).expect(400);

  expect(response.body).toMatchObject({
    error: 'Validation failed',
    details: expect.arrayContaining([expect.stringContaining('field')]),
  });
});
```

## 명시적 코드 작성 원칙

### 1. 명확한 테스트 이름

```typescript
// ❌ 나쁜 예
it('should work', () => {});

// ✅ 좋은 예
it('should return 404 when updating non-existent resource', () => {});
```

### 2. 구체적인 검증

```typescript
// ❌ 나쁜 예
expect(response.body).toBeDefined();

// ✅ 좋은 예
expect(response.body).toMatchObject({
  id: expect.stringMatching(/^[0-9a-f-]{36}$/),
  status: 'active',
  createdAt: expect.any(String),
});
```

### 3. 에러 상황 명시

```typescript
// 모든 에러 케이스를 명시적으로 테스트
describe('Error Handling', () => {
  it('should return 400 for invalid input');
  it('should return 401 for missing authentication');
  it('should return 403 for insufficient permissions');
  it('should return 404 for non-existent resource');
  it('should return 409 for duplicate resource');
  it('should return 500 for database errors');
});
```

## CI/CD 통합

GitHub Actions에서 자동으로 테스트 실행:

```yaml
- name: Run Unit Tests
  run: npm run test:unit

- name: Run Integration Tests
  run: npm run test:integration

- name: Upload Coverage
  run: npm run test:coverage
```

## 문제 해결

### PostgreSQL 컨테이너 시작 실패

- Docker가 실행 중인지 확인
- 포트 충돌 확인 (5432)
- 디스크 공간 확인

### 테스트 타임아웃

- `testTimeout` 값 증가 (package.json)
- 네트워크 연결 확인
- 컨테이너 리소스 제한 확인

### 테스트 데이터 충돌

- 각 테스트는 독립적이어야 함
- `afterEach`에서 생성한 데이터 정리
- 트랜잭션 롤백 활용
