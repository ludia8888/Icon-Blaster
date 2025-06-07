import { ErrorCode } from '@arrakis/contracts';
import { ZodError } from 'zod';

import { AppError } from '../middlewares/errorHandler';

export interface ValidationDetail {
  path: string;
  message: string;
}

export class ValidationError extends AppError {
  public readonly validationDetails: ValidationDetail[];

  constructor(zodError: ZodError) {
    const validationDetails: ValidationDetail[] = zodError.errors.map((err) => ({
      path: err.path.join('.'),
      message: err.message,
    }));

    const detailMessages = validationDetails.map(
      (detail) => `${detail.path}: ${detail.message}`
    );

    super('Validation failed', 400, ErrorCode.VALIDATION_ERROR, detailMessages);
    this.validationDetails = validationDetails;
  }
}