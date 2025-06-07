/**
 * JWT Payload structure
 */
export interface JwtPayload {
  sub: string; // User ID (subject)
  email: string; // User email
  name: string; // User display name
  roles: string[]; // User roles
  iat?: number; // Issued at (added by JWT)
  exp?: number; // Expiration time (added by JWT)
}

/**
 * User information extracted from JWT
 */
export interface AuthUser {
  id: string;
  email: string;
  name: string;
  roles: string[];
}

/**
 * JWT configuration
 */
export interface JwtConfig {
  secret: string;
  expiresIn: string;
}
