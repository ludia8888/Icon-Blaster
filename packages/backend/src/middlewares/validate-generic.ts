import { Request, Response, NextFunction } from 'express';
import { ZodSchema, z } from 'zod';

import { ValidationError } from '../errors/ValidationError';

/**
 * Type-safe validation middleware that transforms request types
 *
 * This implementation uses generic type constraints to ensure
 * type safety through the middleware chain
 */

/**
 * Generic middleware type that transforms request types
 * @template TReq - Request type
 * @template TRes - Response type
 */
export type TransformingMiddleware<TReq extends Request, TRes extends Response = Response> = (
  req: TReq,
  res: TRes,
  next: NextFunction
) => void;

/**
 * Creates a type-safe body validation middleware
 * @template T - The Zod schema type
 * @param schema - Zod schema for validation
 * @returns Middleware that validates and transforms request body
 */
export function validateBody<T extends ZodSchema>(schema: T): TransformingMiddleware<Request> {
  return (req, _res, next) => {
    const result = schema.safeParse(req.body as unknown);

    if (!result.success) {
      next(new ValidationError(result.error));
      return;
    }

    // Type assertion is safe after validation
    (req as Request & { body: z.infer<T> }).body = result.data;
    next();
  };
}

/**
 * Creates a type-safe query validation middleware
 * @template T - The Zod schema type
 * @param schema - Zod schema for validation
 * @returns Middleware that validates and transforms request query
 */
export function validateQuery<T extends ZodSchema>(schema: T): TransformingMiddleware<Request> {
  return (req, _res, next) => {
    const result = schema.safeParse(req.query as unknown);

    if (!result.success) {
      next(new ValidationError(result.error));
      return;
    }

    // Type assertion is safe after validation
    (req as Request & { query: z.infer<T> }).query = result.data;
    next();
  };
}

/**
 * Creates a type-safe params validation middleware
 * @template T - The Zod schema type
 * @param schema - Zod schema for validation
 * @returns Middleware that validates and transforms request params
 */
export function validateParams<T extends ZodSchema>(schema: T): TransformingMiddleware<Request> {
  return (req, _res, next) => {
    const result = schema.safeParse(req.params as unknown);

    if (!result.success) {
      next(new ValidationError(result.error));
      return;
    }

    // Type assertion is safe after validation
    (req as Request & { params: z.infer<T> }).params = result.data;
    next();
  };
}

/**
 * Combined validation builder for multiple parts of the request
 *
 * @example
 * ```typescript
 * const validation = createValidation({
 *   body: CreateUserSchema,
 *   params: IdParamSchema
 * });
 *
 * router.post('/:id', ...validation.middleware, validation.handler(async (req, res) => {
 *   // req.body is typed as CreateUserDto
 *   // req.params.id is typed as string
 * }));
 * ```
 */
export interface ValidationConfig {
  body?: ZodSchema;
  query?: ZodSchema;
  params?: ZodSchema;
}

export function createValidation<T extends ValidationConfig>(config: T) {
  // Define default types for unvalidated parts
  type DefaultBody = Record<string, never>; // Empty object
  type DefaultQuery = Record<string, string | string[] | undefined>; // Express default query type
  type DefaultParams = Record<string, string>; // Express default params type
  
  type ValidatedReq = Request & {
    body: T['body'] extends ZodSchema ? z.infer<T['body']> : DefaultBody;
    query: T['query'] extends ZodSchema ? z.infer<T['query']> : DefaultQuery;
    params: T['params'] extends ZodSchema ? z.infer<T['params']> : DefaultParams;
  };

  const middleware: Array<TransformingMiddleware<Request>> = [];

  if (config.body) {
    middleware.push(validateBody(config.body));
  }
  if (config.query) {
    middleware.push(validateQuery(config.query));
  }
  if (config.params) {
    middleware.push(validateParams(config.params));
  }

  return {
    middleware,
    handler: <TRes = Record<string, unknown>>(
      fn: (req: ValidatedReq, res: Response<TRes>, next: NextFunction) => Promise<void> | void
    ) => fn,
  };
}
