import { z } from 'zod';

/**
 * Error codes enum
 */
export enum ErrorCode {
  VALIDATION_ERROR = 'VALIDATION_ERROR',
  NOT_FOUND = 'NOT_FOUND',
  CONFLICT = 'CONFLICT',
  UNAUTHORIZED = 'UNAUTHORIZED',
  FORBIDDEN = 'FORBIDDEN',
  INTERNAL_ERROR = 'INTERNAL_ERROR',
  BAD_REQUEST = 'BAD_REQUEST',
}

/**
 * Error response schema
 */
export const ErrorResponseSchema = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.array(z.string()).optional(),
  }),
  timestamp: z.string().datetime(),
  path: z.string(),
  requestId: z.string(),
});

/**
 * Success response wrapper
 */
export const SuccessResponseSchema = <T extends z.ZodTypeAny>(
  dataSchema: T
): z.ZodObject<{
  success: z.ZodLiteral<true>;
  data: T;
  timestamp: z.ZodString;
}> =>
  z.object({
    success: z.literal(true),
    data: dataSchema,
    timestamp: z.string().datetime(),
  });

/**
 * Pagination schema
 */
export const PaginationSchema = z.object({
  page: z.number().int().positive().default(1),
  limit: z.number().int().positive().max(100).default(20),
  sortBy: z.string().optional(),
  sortOrder: z.enum(['asc', 'desc']).default('asc'),
});

/**
 * Common query parameters
 */
export const QueryParamsSchema = PaginationSchema.extend({
  q: z.string().optional(),
  status: z.string().optional(),
  visibility: z.string().optional(),
  groups: z.array(z.string()).or(z.string()).optional(),
});

/**
 * Common ID parameter schema
 */
export const IdParamSchema = z.object({
  id: z.string().uuid('ID must be a valid UUID'),
});

/**
 * Type exports
 */
export type ErrorResponse = z.infer<typeof ErrorResponseSchema>;
export type Pagination = z.infer<typeof PaginationSchema>;
export type QueryParams = z.infer<typeof QueryParamsSchema>;
export type IdParam = z.infer<typeof IdParamSchema>;

/**
 * Create error response helper
 */
export function createErrorResponse(params: {
  code: string;
  message: string;
  details?: string[];
  path: string;
  requestId: string;
}): ErrorResponse {
  return {
    error: {
      code: params.code,
      message: params.message,
      details: params.details,
    },
    timestamp: new Date().toISOString(),
    path: params.path,
    requestId: params.requestId,
  };
}

/**
 * Create success response helper
 */
export function createSuccessResponse<T>(data: T): {
  success: true;
  data: T;
  timestamp: string;
} {
  return {
    success: true,
    data,
    timestamp: new Date().toISOString(),
  };
}
