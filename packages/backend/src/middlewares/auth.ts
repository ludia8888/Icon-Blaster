import { ErrorCode } from '@arrakis/contracts';
import { Request, Response, NextFunction } from 'express';

import { extractBearerToken, verifyToken } from '../auth/jwt';

import { AppError } from './errorHandler';

/**
 * Get JWT secret from environment
 */
function getJwtSecret(): string {
  const jwtSecret = process.env['JWT_SECRET'];
  if (jwtSecret === undefined || jwtSecret === '') {
    throw new AppError('JWT secret not configured', 500, ErrorCode.INTERNAL_ERROR);
  }
  return jwtSecret;
}

/**
 * Validate JWT payload structure
 */
function validatePayload(
  payload: ReturnType<typeof verifyToken>
): asserts payload is NonNullable<typeof payload> {
  if (payload === null) {
    throw new AppError('Invalid token', 401, ErrorCode.UNAUTHORIZED);
  }
  if (
    payload.sub === undefined ||
    payload.email === undefined ||
    payload.name === undefined ||
    payload.roles === undefined
  ) {
    throw new AppError('Invalid token payload', 401, ErrorCode.UNAUTHORIZED);
  }
}

/**
 * Authentication middleware
 * Extracts and verifies JWT token from Authorization header
 */
export function authenticate(req: Request, _res: Response, next: NextFunction): void {
  try {
    const jwtSecret = getJwtSecret();
    const authHeader = req.headers.authorization;
    if (authHeader === undefined) {
      throw new AppError('No authorization header provided', 401, ErrorCode.UNAUTHORIZED);
    }

    const token = extractBearerToken(authHeader);
    if (token === null) {
      throw new AppError('Invalid authorization header format', 401, ErrorCode.UNAUTHORIZED);
    }

    const payload = verifyToken(token, jwtSecret);
    validatePayload(payload);

    req.user = {
      id: payload.sub,
      email: payload.email,
      name: payload.name,
      roles: payload.roles,
    };

    next();
  } catch (error) {
    if (error instanceof AppError) {
      next(error);
    } else {
      next(new AppError('Authentication failed', 401, ErrorCode.UNAUTHORIZED));
    }
  }
}
