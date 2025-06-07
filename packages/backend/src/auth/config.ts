import { JwtConfig } from './types';

/**
 * Get JWT configuration from environment
 */
export function getJwtConfig(): JwtConfig {
  const secret = process.env['JWT_SECRET'];
  if (secret === undefined || secret === '') {
    throw new Error('JWT_SECRET environment variable is required');
  }

  return {
    secret,
    expiresIn: process.env['JWT_EXPIRES_IN'] ?? '1h',
  };
}

/**
 * Validate JWT configuration
 */
export function validateJwtConfig(config: JwtConfig): void {
  if (config.secret.length < 32) {
    throw new Error('JWT secret must be at least 32 characters long');
  }

  // Validate expiresIn format (basic check)
  const validFormats = /^\d+[smhdwy]$/;
  if (!validFormats.test(config.expiresIn)) {
    throw new Error('Invalid JWT expiration format');
  }
}
