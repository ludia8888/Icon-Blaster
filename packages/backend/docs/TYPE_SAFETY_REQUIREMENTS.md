# Type Safety Requirements

이 문서는 `src/__tests__/type-safety.test.ts`에서 정의했던 타입 안전성 요구사항을 문서화합니다.

## 📋 검증 대상

### 1. 미들웨어 시그니처 제네릭 완전 적용

미들웨어 체인에서 타입 정보가 완전히 보존되어야 합니다.

```typescript
// Before: Express Request (타입 불안전)
const beforeValidation: Request = {
  body: { id: 'some-string' },
};

// After: TypedRequest (타입 안전)
interface TypedRequest<T> extends Request {
  body: T;
  _validated: true;
}
```

### 2. asyncHandler 제네릭 지원

asyncHandler는 입력 타입을 완전히 보존해야 합니다.

```typescript
function asyncHandler<TReq extends Request, TRes extends Response>(
  fn: RequestHandler<TReq, TRes>
): RequestHandler<TReq, TRes> {
  return (req, res, next) => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };
}
```

### 3. 컨트롤러/서비스 단일 책임 (30줄 제한)

각 함수는 단일 책임 원칙을 따라 30줄을 넘지 않아야 합니다.

**잘못된 예:**

```typescript
class BadController {
  async create(req: Request, res: Response) {
    // 1. 검증
    // 2. 변환
    // 3. 비즈니스 로직
    // 4. 에러 처리
    // ... 30줄 이상
  }
}
```

**올바른 예:**

```typescript
class GoodController {
  async create(req: Request & { body: CreateDto }, res: Response) {
    const dto = this.extractDto(req.body);
    const entity = await this.service.create(dto);
    const response = this.mapToResponse(entity);
    res.json(response);
  }
}
```

### 4. any 완전 제거

모든 `any` 타입은 제거되거나 구체적 타입으로 교체되어야 합니다.

**잘못된 예:**

```typescript
function bad(data: any): any {
  return data;
}
```

**올바른 예:**

```typescript
function good<T>(data: T): T {
  return data;
}

function goodUnknown(data: unknown): string {
  if (typeof data === 'string') return data;
  return String(data);
}
```

### 5. 전체 타입 체인 안전성

컨트롤러에서 완전한 타입 안전성을 제공해야 합니다.

```typescript
const createUser = (req: Request & { body: CreateUserDto }, res: Response<UserResponse>): void => {
  const { name, email } = req.body; // ✅ 타입 추론됨

  res.json({
    id: '123',
    name, // ✅ string 타입 보장
    email, // ✅ string 타입 보장
  });
};
```

## 💡 목표 달성 시 이점

1. **미들웨어 체인에서 타입 정보가 보존됨**
2. **컨트롤러에서 완전한 타입 안전성 확보**
3. **런타임 에러 위험 최소화**
4. **IDE 자동완성 완벽 지원**
5. **코드 유지보수성 대폭 향상**
6. **any 타입으로 인한 런타임 에러 제거**

## 검증 방법

1. TypeScript strict 모드 활성화
2. ESLint `@typescript-eslint/no-explicit-any` 규칙 적용
3. 컴파일 시 타입 에러 0개 유지
4. 코드 리뷰 시 타입 안전성 체크리스트 활용
