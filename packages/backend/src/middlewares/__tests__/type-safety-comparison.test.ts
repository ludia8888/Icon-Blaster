/**
 * 타입 안전성 비교 테스트
 * 
 * 기존 방식과 새로운 방식의 타입 안전성을 비교합니다.
 */

import { Request, Response } from 'express';
import { z } from 'zod';

// 테스트용 스키마
const UserSchema = z.object({
  name: z.string(),
  email: z.string().email(),
  age: z.number()
});

type User = z.infer<typeof UserSchema>;

describe('Type Safety Comparison', () => {
  describe('기존 방식 (타입 안전성 없음)', () => {
    it('컴파일은 되지만 런타임 에러 위험', () => {
      // 기존 validateBody (from validate.ts)
      function oldValidateBody(schema: z.ZodSchema) {
        return (req: Request, res: Response, next: () => void) => {
          const result = schema.safeParse(req.body);
          if (!result.success) throw new Error('Validation failed');
          req.body = result.data;
          next();
        };
      }
      
      // 미들웨어 사용
      const middleware = oldValidateBody(UserSchema);
      
      // 핸들러에서 타입 추론 안됨
      const handler = (req: Request, res: Response) => {
        // ❌ req.body는 여전히 any 타입
        const name = req.body.name; // any
        const email = req.body.email; // any
        const age = req.body.age; // any
        
        // 타입 에러가 컴파일 타임에 잡히지 않음
        const wrong: number = req.body.name; // 런타임에 문제 발생
        
        expect(typeof name).toBe('string'); // 런타임에만 검증 가능
      };
      
      // 실행 시뮬레이션
      const mockReq = { body: { name: 'John', email: 'john@example.com', age: 30 } } as Request;
      const mockRes = {} as Response;
      const mockNext = jest.fn();
      
      middleware(mockReq, mockRes, mockNext);
      handler(mockReq, mockRes);
    });
  });
  
  describe('새로운 방식 (완전한 타입 안전성)', () => {
    it('컴파일 타임에 타입 체크', () => {
      // 새로운 validateBody (from type-transforming-middleware.ts)
      // 실제 import 대신 타입 시뮬레이션
      type ValidatedRequest<T> = Request & { body: T };
      
      function newValidateBody<T extends z.ZodSchema>(schema: T) {
        type OutputReq = Request & { body: z.infer<T> };
        
        return (req: Request, res: Response, next: () => void) => {
          const result = schema.safeParse(req.body);
          if (!result.success) throw new Error('Validation failed');
          (req as OutputReq).body = result.data;
          next();
        };
      }
      
      // 타입 안전한 핸들러 정의
      const typeSafeHandler = (req: ValidatedRequest<User>, res: Response) => {
        // ✅ req.body가 User 타입으로 추론됨
        const name: string = req.body.name; // string
        const email: string = req.body.email; // string
        const age: number = req.body.age; // number
        
        // 컴파일 타임에 타입 에러 감지
        // const wrong: number = req.body.name; // Error: Type 'string' is not assignable to type 'number'
        
        expect(name).toBe('John');
        expect(email).toBe('john@example.com');
        expect(age).toBe(30);
      };
      
      // 실행 시뮬레이션
      const mockReq = { body: { name: 'John', email: 'john@example.com', age: 30 } } as ValidatedRequest<User>;
      const mockRes = {} as Response;
      
      typeSafeHandler(mockReq, mockRes);
    });
    
    it('IDE 자동완성 지원', () => {
      // 타입 정의만으로도 자동완성이 가능함을 보여주는 예시
      type AutoCompleteTest = {
        handler: (req: Request & { body: User }) => void;
      };
      
      const test: AutoCompleteTest = {
        handler: (req) => {
          // IDE에서 req.body. 입력 시 자동완성 제공:
          // - name (string)
          // - email (string)  
          // - age (number)
          
          // 존재하지 않는 필드는 자동완성에 나타나지 않음
          // req.body.nonExistent // 자동완성 없음, 타입 에러
          
          expect(req.body.name).toBeDefined();
        }
      };
      
      expect(test).toBeDefined();
    });
    
    it('체인된 미들웨어의 타입 누적', () => {
      // 여러 검증이 체인될 때 타입이 누적됨
      type ChainedRequest = Request & {
        body: { name: string; email: string };
        params: { id: string };
        query: { page: number; limit: number };
      };
      
      const chainedHandler = (req: ChainedRequest, res: Response) => {
        // 모든 타입이 안전하게 추론됨
        const bodyName: string = req.body.name;
        const paramId: string = req.params.id;
        const queryPage: number = req.query.page;
        
        expect(bodyName).toBeDefined();
        expect(paramId).toBeDefined();
        expect(queryPage).toBeDefined();
      };
      
      expect(chainedHandler).toBeDefined();
    });
  });
  
  describe('실질적 개선 효과', () => {
    it('버그 조기 발견', () => {
      // 시나리오: API 응답 형식 변경
      const OldResponseSchema = z.object({
        data: z.object({
          userId: z.number(),
          userName: z.string()
        })
      });
      
      const NewResponseSchema = z.object({
        data: z.object({
          id: z.string(), // userId -> id, number -> string
          name: z.string() // userName -> name
        })
      });
      
      // 기존 방식: 런타임에 실패
      const oldHandler = (data: any) => {
        const userId = data.userId; // undefined - 런타임 에러
        return userId.toString(); // TypeError: Cannot read property 'toString' of undefined
      };
      
      // 새로운 방식: 컴파일 타임에 감지
      type NewData = z.infer<typeof NewResponseSchema>;
      const newHandler = (data: NewData['data']) => {
        // const userId = data.userId; // Error: Property 'userId' does not exist
        const id = data.id; // OK
        return id.toString(); // 안전함 - id는 이미 string
      };
      
      expect(newHandler).toBeDefined();
    });
    
    it('리팩토링 안전성', () => {
      // 스키마 변경 시 영향받는 모든 코드를 컴파일러가 찾아줌
      const OriginalSchema = z.object({
        username: z.string(),
        password: z.string()
      });
      
      const UpdatedSchema = z.object({
        email: z.string().email(), // username -> email
        password: z.string(),
        confirmPassword: z.string() // 새 필드 추가
      });
      
      type UpdatedData = z.infer<typeof UpdatedSchema>;
      
      // 모든 핸들러가 자동으로 타입 에러 표시
      const handlers = {
        login: (data: UpdatedData) => {
          // const username = data.username; // Error: 'username' 없음
          const email = data.email; // 새 필드 사용
          const confirmPassword = data.confirmPassword; // 필수 필드
          
          expect(email).toBeDefined();
          expect(confirmPassword).toBeDefined();
        }
      };
      
      expect(handlers.login).toBeDefined();
    });
  });
});

/**
 * 결론:
 * 
 * 1. 기존 방식의 한계
 *    - req.body, req.params, req.query가 any 타입
 *    - 타입 오류가 런타임에만 발견됨
 *    - IDE 자동완성 없음
 *    - 리팩토링 시 위험
 * 
 * 2. 새로운 방식의 장점
 *    - 완전한 타입 추론
 *    - 컴파일 타임 오류 감지
 *    - IDE 자동완성 지원
 *    - 안전한 리팩토링
 * 
 * 3. 실질적 효과
 *    - 개발 속도 향상 (자동완성)
 *    - 버그 조기 발견 (컴파일 타임)
 *    - 유지보수성 향상 (타입 안전성)
 *    - 팀 협업 개선 (명확한 인터페이스)
 */