import { ErrorCode, createErrorResponse } from '@arrakis/contracts';
import { Request, Response, NextFunction } from 'express';

/**
 * Custom application error
 */
export class AppError extends Error {
  public readonly statusCode: number;
  public readonly code: ErrorCode | string;
  public readonly details?: string[];

  constructor(message: string, statusCode: number, code: ErrorCode | string, details?: string[]) {
    super(message);
    this.statusCode = statusCode;
    this.code = code;
    this.details = details;
    Error.captureStackTrace(this, this.constructor);
  }
}

interface ErrorInfo {
  statusCode: number;
  code: string;
  message: string;
  details?: string[];
}

/**
 * Extract error information from error object
 */
function getErrorInfo(err: Error | AppError): ErrorInfo {
  if (err instanceof AppError) {
    return {
      statusCode: err.statusCode,
      code: err.code,
      message: err.message,
      details: err.details,
    };
  }

  if (err instanceof SyntaxError && 'body' in err) {
    return {
      statusCode: 400,
      code: ErrorCode.BAD_REQUEST,
      message: 'Invalid JSON payload',
    };
  }

  return {
    statusCode: 500,
    code: ErrorCode.INTERNAL_ERROR,
    message: 'Internal server error',
  };
}

/**
 * Global error handler middleware
 */
export function errorHandler(
  err: Error | AppError,
  req: Request,
  res: Response,
  _next: NextFunction
): void {
  const { statusCode, code, message, details } = getErrorInfo(err);

  // Log error (in production, use proper logging)
  if (process.env['NODE_ENV'] !== 'test') {
    console.error('Error:', err);
  }

  // Send error response
  const errorResponse = createErrorResponse({
    code,
    message,
    details,
    path: req.path,
    requestId: (req as Request & { id?: string }).id ?? 'unknown',
  });

  res.status(statusCode).json(errorResponse);
}
