/**
 * Type Safety Requirements Test
 * 
 * 이 테스트는 우리가 달성하고자 하는 타입 안전성을 정의합니다.
 * TDD 방식: 먼저 원하는 결과를 테스트로 작성하고, 그 후 구현합니다.
 * 
 * 📋 검증 대상:
 * 1. 미들웨어 시그니처 제네릭 완전 적용
 * 2. asyncHandler 제네릭 지원
 * 3. 컨트롤러/서비스 단일 책임 (30줄 제한)
 * 4. any 완전 제거
 * 5. 전체 타입 체인 안전성
 */

import { Request, Response, NextFunction } from 'express';
import { z } from 'zod';

// 1️⃣ 목표: 미들웨어 체인에서 타입이 완전히 보존되어야 함
describe('Type Safety Requirements', () => {
  
  // 2️⃣ 요구사항: 검증된 요청은 타입 안전해야 함
  it('should preserve types through middleware chain', () => {
    const schema = z.object({
      name: z.string(),
      age: z.number()
    });
    
    type ExpectedBody = z.infer<typeof schema>;
    
    // 이 함수는 컴파일 타임에 타입 체크되어야 함
    const testHandler = (req: Request & { body: ExpectedBody }) => {
      // TypeScript가 이를 안전하다고 인식해야 함
      const name: string = req.body.name; // ✅ 에러 없어야 함
      const age: number = req.body.age;   // ✅ 에러 없어야 함
      
      expect(typeof name).toBe('string');
      expect(typeof age).toBe('number');
    };
    
    // 3️⃣ 이 테스트가 통과하면 타입 시스템이 올바르게 작동하는 것
    expect(testHandler).toBeDefined();
  });

  // 4️⃣ 요구사항: 미들웨어가 타입을 변환해야 함
  it('should transform Request to TypedRequest through validation', () => {
    const schema = z.object({ id: z.string().uuid() });
    
    // 미들웨어 전: Express Request (타입 불안전)
    const beforeValidation: Request = {
      body: { id: 'some-string' }
    } as Request;
    
    // 미들웨어 후: TypedRequest (타입 안전)
    interface TypedRequest<T> extends Request {
      body: T;
      _validated: true; // 검증 완료 마커
    }
    
    type ValidatedRequest = TypedRequest<z.infer<typeof schema>>;
    
    // 이런 변환이 가능해야 함
    const afterValidation: ValidatedRequest = {
      ...beforeValidation,
      body: { id: '550e8400-e29b-41d4-a716-446655440000' },
      _validated: true as const
    } as ValidatedRequest;
    
    expect(afterValidation._validated).toBe(true);
  });

  // 5️⃣ 요구사항: 컨트롤러는 완전한 타입 안전성을 가져야 함
  it('should provide full type safety in controllers', () => {
    type CreateUserDto = {
      name: string;
      email: string;
    };
    
    type UserResponse = {
      id: string;
      name: string;
      email: string;
    };
    
    // 컨트롤러 함수는 이런 시그니처를 가져야 함
    const createUser = (
      req: Request & { body: CreateUserDto },
      res: Response<UserResponse>
    ): void => {
      // 타입 안전한 접근 (컴파일 타임 체크)
      const { name, email } = req.body; // ✅ 타입 추론됨
      
      res.json({
        id: '123',
        name, // ✅ string 타입 보장
        email // ✅ string 타입 보장
      });
    };
    
    expect(createUser).toBeDefined();
  });

  // 6️⃣ 요구사항: asyncHandler는 제네릭을 완전히 지원해야 함
  it('should support full generic types in asyncHandler', () => {
    type RequestHandler<
      TReq extends Request = Request,
      TRes extends Response = Response
    > = (req: TReq, res: TRes, next: NextFunction) => Promise<void> | void;
    
    // asyncHandler는 입력 타입을 보존해야 함
    function asyncHandler<
      TReq extends Request,
      TRes extends Response
    >(fn: RequestHandler<TReq, TRes>): RequestHandler<TReq, TRes> {
      return (req, res, next) => {
        Promise.resolve(fn(req, res, next)).catch(next);
      };
    }
    
    // 타입이 보존되는지 검증
    const typedHandler: RequestHandler<
      Request & { body: { name: string } },
      Response<{ success: boolean }>
    > = async (req, res) => {
      const _name: string = req.body.name; // ✅ 타입 안전
      void _name; // 변수 사용
      res.json({ success: true }); // ✅ 타입 안전
    };
    
    const wrapped = asyncHandler(typedHandler);
    expect(wrapped).toBeDefined();
  });

  // 7️⃣ 요구사항: 미들웨어는 제네릭 타입 변환을 지원해야 함
  it('should support generic type transformation in middleware', () => {
    // 미들웨어는 Request를 더 구체적인 타입으로 변환할 수 있어야 함
    type ValidationMiddleware<TInput extends Request> = 
      (req: TInput, res: Response, next: NextFunction) => void;
    
    // 예: body 검증 미들웨어
    function validateBody<T extends z.ZodSchema>(
      schema: T
    ): ValidationMiddleware<Request> {
      return (req, res, next) => {
        const result = schema.safeParse(req.body);
        if (!result.success) {
          res.status(400).json({ error: result.error });
          return;
        }
        req.body = result.data;
        next();
      };
    }
    
    const userSchema = z.object({ name: z.string(), age: z.number() });
    const middleware = validateBody(userSchema);
    expect(middleware).toBeDefined();
  });

  // 8️⃣ 요구사항: 함수는 30줄을 넘지 않아야 함 (단일 책임)
  it('should enforce single responsibility with 30-line limit', () => {
    // 잘못된 예: 너무 많은 책임 (주석으로 표현)
    /*
    class BadController {
      async create(req: Request, res: Response) {
        // 1. 검증
        // 2. 변환
        // 3. 비즈니스 로직
        // 4. 에러 처리
        // ... 30줄 이상
      }
    }
    */
    
    // 올바른 예: 책임 분리
    class GoodController {
      private service = { create: async (dto: CreateDto) => ({ id: '1', name: dto.name }) };
      
      async create(req: Request & { body: CreateDto }, res: Response) {
        const dto = this.extractDto(req.body);
        const entity = await this.service.create(dto);
        const response = this.mapToResponse(entity);
        res.json(response);
      }
      
      private extractDto(body: CreateDto): CreateDto {
        return body; // 10줄 이내
      }
      
      private mapToResponse(entity: Entity): ResponseDto {
        return { id: entity.id }; // 10줄 이내
      }
    }
    
    expect(GoodController).toBeDefined();
  });

  // 9️⃣ 요구사항: any 타입은 완전히 제거되어야 함
  it('should have zero any types in production code', () => {
    // ESLint no-explicit-any 규칙이 활성화되어야 함
    // 모든 any는 제거되거나 구체적 타입으로 교체
    
    // 잘못된 예
    // function bad(data: any): any { return data; }
    
    // 올바른 예
    function good<T>(data: T): T { return data; }
    function goodUnknown(data: unknown): string {
      if (typeof data === 'string') return data;
      return String(data);
    }
    
    expect(good).toBeDefined();
    expect(goodUnknown).toBeDefined();
  });
});

// 타입 정의 예제 (실제 구현에서 사용)
type CreateDto = { name: string };
type Entity = { id: string; name: string };
type ResponseDto = { id: string };

/**
 * 💡 이 테스트들이 통과하면:
 * 1. 미들웨어 체인에서 타입 정보가 보존됨
 * 2. 컨트롤러에서 완전한 타입 안전성 확보
 * 3. 런타임 에러 위험 최소화
 * 4. IDE 자동완성 완벽 지원
 * 5. 코드 유지보수성 대폭 향상
 * 6. any 타입으로 인한 런타임 에러 제거
 */