import { Request } from 'express';
import { z } from 'zod';
import * as qs from 'qs';

/**
 * Type-safe request with validated body
 * Note: We can't override Express types directly, so we use type assertions in controllers
 */
export type TypedRequestBody<T> = Request & {
  body: T;
};

/**
 * Type-safe request with validated query
 */
export type TypedRequestQuery<T> = Request & {
  query: T;
};

/**
 * Type-safe request with validated params
 */
export type TypedRequestParams<T extends Record<string, string>> = Request & {
  params: T;
};

/**
 * Type-safe request with validated body, params, and query
 *
 * @template B - Body type (defaults to unknown for safety)
 * @template P - Params type (must be string record)
 * @template Q - Query type (defaults to ParsedQs from Express)
 */
export type TypedRequest<
  B = unknown,
  P extends Record<string, string> = Record<string, string>,
  Q = qs.ParsedQs,
> = Request & {
  body: B;
  params: P;
  query: Q;
};

/**
 * Extract the inferred type from a Zod schema
 */
export type InferSchema<T extends z.ZodSchema> = z.infer<T>;
