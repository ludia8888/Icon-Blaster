import { Request, Response, NextFunction } from 'express';
import { ZodSchema, z } from 'zod';

import { ValidationError } from '../errors/ValidationError';

/**
 * 타입 변환을 명시적으로 표현하는 미들웨어 시스템
 *
 * Express의 한계를 극복하고 진정한 타입 안전성을 구현
 */

/**
 * 미들웨어가 Request를 어떻게 변환하는지 타입으로 표현
 */
export interface TypeTransform<TIn extends Request, TOut extends TIn> {
  _input: TIn;
  _output: TOut;
}

/**
 * 타입을 변환하는 미들웨어의 시그니처
 * 입력 타입 TIn을 출력 타입 TOut으로 변환
 */
export type TransformingMiddleware<TIn extends Request, TOut extends TIn> = (
  req: TIn,
  res: Response,
  next: NextFunction
) => void | Promise<void>;

/**
 * Body를 검증하고 타입을 변환하는 미들웨어 생성
 *
 * @template T - Zod 스키마 타입
 * @param schema - 검증할 Zod 스키마
 * @returns Request의 body 타입을 변환하는 미들웨어
 */
export function validateBody<T extends ZodSchema>(
  schema: T
): TransformingMiddleware<Request, Request & { body: z.infer<T> }> {
  return (req, _res, next) => {
    const result = schema.safeParse(req.body as unknown);

    if (!result.success) {
      next(new ValidationError(result.error));
      return;
    }

    // 타입 단언이 안전함 - 검증을 통과했으므로
    const typedReq = req as Request & { body: z.infer<T> };
    typedReq.body = result.data;
    next();
  };
}

/**
 * Query를 검증하고 타입을 변환하는 미들웨어 생성
 */
export function validateQuery<T extends ZodSchema>(
  schema: T
): TransformingMiddleware<Request, Request & { query: z.infer<T> }> {
  return (req, _res, next) => {
    const result = schema.safeParse(req.query as unknown);

    if (!result.success) {
      next(new ValidationError(result.error));
      return;
    }

    const typedReq = req as Request & { query: z.infer<T> };
    typedReq.query = result.data;
    next();
  };
}

/**
 * Params를 검증하고 타입을 변환하는 미들웨어 생성
 */
export function validateParams<T extends ZodSchema>(
  schema: T
): TransformingMiddleware<Request, Request & { params: z.infer<T> }> {
  return (req, _res, next) => {
    const result = schema.safeParse(req.params as unknown);

    if (!result.success) {
      next(new ValidationError(result.error));
      return;
    }

    const typedReq = req as Request & { params: z.infer<T> };
    typedReq.params = result.data;
    next();
  };
}

/**
 * 미들웨어 체인을 통해 타입을 누적시키는 빌더
 *
 * @example
 * ```typescript
 * const chain = middlewareChain()
 *   .use(validateBody(CreateUserSchema))
 *   .use(validateParams(IdSchema))
 *   .build();
 *
 * // chain.handler는 이제 정확한 타입을 가짐
 * chain.handler(async (req, res) => {
 *   req.body.name; // string - 타입 추론됨
 *   req.params.id; // string - 타입 추론됨
 * });
 * ```
 */
export class MiddlewareChain<TReq extends Request = Request> {
  private middlewares: Array<(req: Request, res: Response, next: NextFunction) => void> = [];

  use<TOut extends TReq>(middleware: TransformingMiddleware<TReq, TOut>): MiddlewareChain<TOut> {
    this.middlewares.push(middleware as (req: Request, res: Response, next: NextFunction) => void);
    // 타입만 변환된 새 체인 반환 - 타입 시스템에게 변환을 알림
    return this as unknown as MiddlewareChain<TOut>;
  }

  build() {
    return {
      middlewares: this.middlewares,
      handler: <TRes = unknown>(
        fn: (req: TReq, res: Response<TRes>, next: NextFunction) => void | Promise<void>
      ) => [...this.middlewares, fn as (req: Request, res: Response, next: NextFunction) => void],
    };
  }
}

export function middlewareChain(): MiddlewareChain<Request> {
  return new MiddlewareChain();
}

/**
 * 타입 안전한 라우트 정의를 위한 헬퍼
 *
 * @example
 * ```typescript
 * defineRoute({
 *   body: CreateUserSchema,
 *   params: IdSchema,
 *   handler: async (req, res) => {
 *     // req.body와 req.params가 완전히 타입 안전함
 *     const user = await createUser(req.body);
 *     res.json({ id: req.params.id, ...user });
 *   }
 * });
 * ```
 */
interface RouteDefinition<
  TBody = unknown,
  TParams = Record<string, string>,
  TQuery = Record<string, string>,
  TRes = unknown,
> {
  body?: ZodSchema<TBody>;
  params?: ZodSchema<TParams>;
  query?: ZodSchema<TQuery>;
  handler: (
    req: Request & { body: TBody; params: TParams; query: TQuery },
    res: Response<TRes>,
    next: NextFunction
  ) => void | Promise<void>;
}

export function defineRoute<TBody, TParams, TQuery, TRes>(
  def: RouteDefinition<TBody, TParams, TQuery, TRes>
) {
  const middlewares: Array<TransformingMiddleware<any, any>> = [];

  if (def.body) {
    middlewares.push(validateBody(def.body));
  }
  if (def.params) {
    middlewares.push(validateParams(def.params));
  }
  if (def.query) {
    middlewares.push(validateQuery(def.query));
  }

  return [...middlewares, def.handler];
}
