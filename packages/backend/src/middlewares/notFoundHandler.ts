import { ErrorCode } from '@arrakis/contracts';
import { Request, Response, NextFunction } from 'express';

import { AppError } from './errorHandler';

/**
 * 404 Not Found handler
 */
export function notFoundHandler(req: Request, _res: Response, next: NextFunction): void {
  const error = new AppError(`Route ${req.method} ${req.path} not found`, 404, ErrorCode.NOT_FOUND);
  next(error);
}
