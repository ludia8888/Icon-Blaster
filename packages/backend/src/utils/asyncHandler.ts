import { Request, Response, NextFunction } from 'express';

/**
 * Generic request handler type that preserves request and response types
 * 
 * @template TReq - The request type (must extend Express Request)
 * @template TRes - The response type (must extend Express Response)
 */
export type TypedRequestHandler<
  TReq extends Request = Request,
  TRes extends Response = Response
> = (req: TReq, res: TRes, next: NextFunction) => Promise<void> | void;

/**
 * Wraps async route handlers to properly catch errors while preserving types
 * 
 * @template TReq - The request type (must extend Express Request)
 * @template TRes - The response type (must extend Express Response)
 * @param fn - The async handler function to wrap
 * @returns A wrapped handler that catches and forwards errors
 * 
 * @example
 * ```typescript
 * // With typed request and response
 * const handler = asyncHandler<
 *   Request & { body: { name: string } },
 *   Response<{ success: boolean }>
 * >(async (req, res) => {
 *   const name = req.body.name; // ✅ TypeScript knows this is string
 *   res.json({ success: true }); // ✅ TypeScript validates response shape
 * });
 * ```
 */
export function asyncHandler<
  TReq extends Request = Request,
  TRes extends Response = Response
>(
  fn: TypedRequestHandler<TReq, TRes>
): TypedRequestHandler<TReq, TRes> {
  return (req: TReq, res: TRes, next: NextFunction) => {
    Promise.resolve(fn(req, res, next)).catch(next);
  };
}