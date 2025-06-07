/**
 * 타입 안전한 Handler 패턴
 *
 * Specification-Driven Coding 원칙 적용:
 * Input → Process → Output 계약을 타입 레벨에서 보장
 */

import { Request, Response, NextFunction } from 'express';
import { ZodSchema, z } from 'zod';

/**
 * 1️⃣ 입력 계약 정의
 */
export interface RequestValidation {
  body?: ZodSchema;
  query?: ZodSchema;
  params?: ZodSchema;
}

/**
 * 2️⃣ 검증된 요청 타입 생성
 */
export type ValidatedRequest<T extends RequestValidation> = Request & {
  body: T['body'] extends ZodSchema ? z.infer<T['body']> : unknown;
  query: T['query'] extends ZodSchema ? z.infer<T['query']> : Record<string, string>;
  params: T['params'] extends ZodSchema ? z.infer<T['params']> : Record<string, string>;
};

/**
 * 3️⃣ 타입 안전한 핸들러 정의
 */
export type SafeHandler<TValidation extends RequestValidation, TResponse = unknown> = (
  req: ValidatedRequest<TValidation>,
  res: Response<TResponse>,
  next: NextFunction
) => Promise<void> | void;

/**
 * 4️⃣ 검증 미들웨어 생성기
 */
export function createValidatedHandler<TValidation extends RequestValidation, TResponse = unknown>(
  validation: TValidation,
  handler: SafeHandler<TValidation, TResponse>
) {
  return [
    // 검증 미들웨어들
    ...(validation.body ? [validateBodyMiddleware(validation.body)] : []),
    ...(validation.query ? [validateQueryMiddleware(validation.query)] : []),
    ...(validation.params ? [validateParamsMiddleware(validation.params)] : []),

    // 타입 안전한 핸들러
    async (req: Request, res: Response, next: NextFunction) => {
      try {
        // 이 시점에서 req는 검증된 상태이므로 안전한 캐스팅
        await handler(req as ValidatedRequest<TValidation>, res, next);
      } catch (error) {
        next(error);
      }
    },
  ];
}

/**
 * 5️⃣ 미들웨어 구현부 (기존 validate.ts 활용)
 */
function validateBodyMiddleware(schema: ZodSchema) {
  return (req: Request, _res: Response, next: NextFunction) => {
    const result = schema.safeParse(req.body as unknown);
    if (!result.success) {
      throw new ValidationError(result.error);
    }
    req.body = result.data;
    next();
  };
}

function validateQueryMiddleware(schema: ZodSchema) {
  return (req: Request, _res: Response, next: NextFunction) => {
    const result = schema.safeParse(req.query as unknown);
    if (!result.success) {
      throw new ValidationError(result.error);
    }
    req.query = result.data;
    next();
  };
}

function validateParamsMiddleware(schema: ZodSchema) {
  return (req: Request, _res: Response, next: NextFunction) => {
    const result = schema.safeParse(req.params as unknown);
    if (!result.success) {
      throw new ValidationError(result.error);
    }
    req.params = result.data;
    next();
  };
}

// ValidationError는 기존 구현 사용
import { ValidationError } from '../errors/ValidationError';

/**
 * 6️⃣ 사용 예제 (타입 안전성 보장)
 */
const exampleValidation = {
  body: z.object({
    name: z.string(),
    email: z.string().email(),
  }),
  params: z.object({
    id: z.string().uuid(),
  }),
} as const;

export const exampleUsage = {
  // 스키마 정의
  validation: exampleValidation,

  // 타입 안전한 핸들러
  handler: async (req: ValidatedRequest<typeof exampleValidation>, res: Response) => {
    // ✅ TypeScript가 이 타입들을 정확히 추론함
    const { name, email } = req.body; // string 타입들
    const { id } = req.params; // string (UUID) 타입

    res.json({ id, name, email });
  },
} as const;
