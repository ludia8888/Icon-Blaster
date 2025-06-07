import { ErrorCode } from '@arrakis/contracts';
import { Request, Response, NextFunction } from 'express';

import { AppError } from './errorHandler';

type User = {
  id: string;
  email: string;
  name: string;
  roles: string[];
};

/**
 * Check if user has required roles
 */
function checkUserRoles(user: User | undefined, requiredRoles: string[]): void {
  if (user === undefined) {
    throw new AppError('Authentication required', 401, ErrorCode.UNAUTHORIZED);
  }

  if (requiredRoles.length === 0) {
    return;
  }

  const userRoles = user.roles ?? [];
  const hasRequiredRole = requiredRoles.some((role) => userRoles.includes(role));

  if (!hasRequiredRole) {
    throw new AppError('Insufficient permissions', 403, ErrorCode.FORBIDDEN, [
      `Required roles: ${requiredRoles.join(', ')}`,
    ]);
  }
}

/**
 * Authorization middleware factory
 * Creates middleware that checks if user has required roles
 */
export function authorize(
  roles: string | string[]
): (req: Request, res: Response, next: NextFunction) => void {
  const requiredRoles = Array.isArray(roles) ? roles : [roles];

  return (req: Request, _res: Response, next: NextFunction): void => {
    try {
      checkUserRoles(req.user, requiredRoles);
      next();
    } catch (error) {
      if (error instanceof AppError) {
        next(error);
      } else {
        next(new AppError('Authorization failed', 403, ErrorCode.FORBIDDEN));
      }
    }
  };
}
