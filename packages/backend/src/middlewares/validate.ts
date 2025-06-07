import { Request, Response, NextFunction } from 'express';
import { ZodSchema } from 'zod';

import { ValidationError } from '../errors/ValidationError';

export function validateBody<T extends ZodSchema>(schema: T) {
  return <R extends Request>(req: R, _res: Response, next: NextFunction): void => {
    const result = schema.safeParse(req.body as unknown);

    if (!result.success) {
      next(new ValidationError(result.error));
      return;
    }

    // Direct assignment after validation - TypeScript can't track this but it's safe
    // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
    req.body = result.data;
    next();
  };
}

export function validateQuery<T extends ZodSchema>(schema: T) {
  return <R extends Request>(req: R, _res: Response, next: NextFunction): void => {
    const result = schema.safeParse(req.query as unknown);

    if (!result.success) {
      next(new ValidationError(result.error));
      return;
    }

    // Direct assignment after validation - TypeScript can't track this but it's safe
    // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
    req.query = result.data;
    next();
  };
}

export function validateParams<T extends ZodSchema>(schema: T) {
  return <R extends Request>(req: R, _res: Response, next: NextFunction): void => {
    const result = schema.safeParse(req.params as unknown);

    if (!result.success) {
      next(new ValidationError(result.error));
      return;
    }

    // Direct assignment after validation - TypeScript can't track this but it's safe
    // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
    req.params = result.data;
    next();
  };
}
