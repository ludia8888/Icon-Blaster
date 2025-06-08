import jwt, { SignOptions } from 'jsonwebtoken';

import { JwtPayload } from './types';

/**
 * Generate a JWT token
 */
export function generateToken(
  payload: Partial<JwtPayload>,
  secret: string,
  expiresIn: string | number = '1h'
): string {
  const options = {
    expiresIn,
    issuer: 'arrakis-backend',
  };
  return jwt.sign(payload as object, secret, options as SignOptions);
}

/**
 * Verify and decode a JWT token
 */
export function verifyToken(token: string, secret: string): JwtPayload | null {
  try {
    return jwt.verify(token, secret, {
      issuer: 'arrakis-backend',
    }) as JwtPayload;
  } catch {
    return null;
  }
}

/**
 * Decode token without verification (useful for debugging)
 */
export function decodeToken(token: string): JwtPayload | null {
  try {
    return jwt.decode(token) as JwtPayload;
  } catch {
    return null;
  }
}

/**
 * Extract Bearer token from Authorization header
 */
export function extractBearerToken(authHeader: string): string | null {
  if (authHeader === '') {
    return null;
  }

  const parts = authHeader.split(' ');
  if (parts.length !== 2) {
    return null;
  }

  const [scheme, token] = parts;
  if (scheme === undefined || !/^Bearer$/i.test(scheme)) {
    return null;
  }

  if (token === undefined || token === '') {
    return null;
  }

  return token;
}

/**
 * Check if token is expired
 */
export function isTokenExpired(token: string): boolean {
  try {
    const decoded = decodeToken(token);
    if (decoded === null || decoded.exp === undefined) {
      return true;
    }

    const now = Math.floor(Date.now() / 1000);
    return decoded.exp < now;
  } catch {
    return true;
  }
}
