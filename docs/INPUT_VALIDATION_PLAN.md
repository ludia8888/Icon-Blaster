# Input Validation Implementation Plan

## 목표

Zod 스키마를 활용한 입력 검증 미들웨어를 구현하여 API 보안과 안정성을 확보합니다.

## 구현 계획

### 1. 검증 미들웨어 구현 (TDD)

#### 1.1 테스트 작성

**파일**: `src/middlewares/__tests__/validate.test.ts`

```typescript
describe('Validation Middleware', () => {
  it('should pass valid data');
  it('should reject invalid data with 400');
  it('should provide detailed error messages');
  it('should handle nested object validation');
  it('should validate query parameters');
  it('should validate path parameters');
});
```

#### 1.2 미들웨어 구현

**파일**: `src/middlewares/validate.ts`

```typescript
export function validateBody(schema: ZodSchema) {
  return (req, res, next) => {
    const result = schema.safeParse(req.body);
    if (!result.success) {
      next(new ValidationError(result.error));
    }
    req.body = result.data; // 파싱된 데이터로 교체
    next();
  };
}
```

#### 1.3 ValidationError 클래스

**파일**: `src/errors/ValidationError.ts`

```typescript
export class ValidationError extends AppError {
  constructor(zodError: ZodError) {
    const details = zodError.errors.map((err) => ({
      path: err.path.join('.'),
      message: err.message,
    }));
    super('Validation failed', 400, ErrorCode.VALIDATION_ERROR, details);
  }
}
```

### 2. 적용 예시

```typescript
// routes/objectType.ts
import { CreateObjectTypeSchema } from '@arrakis/contracts';

router.post(
  '/',
  authenticate,
  authorize(['admin', 'editor']),
  validateBody(CreateObjectTypeSchema),
  objectTypeController.create
);
```

### 3. 검증 포인트

- [ ] Body 검증
- [ ] Query 검증
- [ ] Params 검증
- [ ] 에러 메시지 포맷
- [ ] 타입 변환 (string → number 등)

## 예상 효과

1. **보안**: 악의적인 입력 차단
2. **안정성**: 런타임 타입 에러 방지
3. **개발 경험**: 명확한 에러 메시지
4. **유지보수**: 스키마 기반 단일 진실 공급원
