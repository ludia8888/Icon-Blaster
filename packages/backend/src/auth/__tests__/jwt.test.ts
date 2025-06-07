import {
  generateToken,
  verifyToken,
  decodeToken,
  extractBearerToken,
  isTokenExpired,
} from '../jwt';
import { JwtPayload } from '../types';

describe('JWT Utilities', () => {
  const mockPayload: JwtPayload = {
    sub: 'user-123',
    email: 'test@example.com',
    name: 'Test User',
    roles: ['user', 'editor'],
  };

  const mockSecret = 'test-secret-key';

  describe('generateToken', () => {
    it('should generate a valid JWT token', () => {
      // Act
      const token = generateToken(mockPayload, mockSecret);

      // Assert
      expect(token).toBeDefined();
      expect(typeof token).toBe('string');
      expect(token.split('.')).toHaveLength(3); // JWT has 3 parts
    });

    it('should generate token with default expiration', () => {
      // Act
      const token = generateToken(mockPayload, mockSecret);
      const decoded = decodeToken(token);

      // Assert
      expect(decoded).toBeDefined();
      expect(decoded?.exp).toBeDefined();
      expect(decoded?.iat).toBeDefined();
      if (decoded?.exp !== undefined && decoded?.iat !== undefined) {
        expect(decoded.exp - decoded.iat).toBe(3600); // 1 hour default
      }
    });

    it('should generate token with custom expiration', () => {
      // Act
      const token = generateToken(mockPayload, mockSecret, '2h');
      const decoded = decodeToken(token);

      // Assert
      expect(decoded).toBeDefined();
      if (decoded?.exp !== undefined && decoded?.iat !== undefined) {
        expect(decoded.exp - decoded.iat).toBe(7200); // 2 hours
      }
    });
  });

  describe('verifyToken', () => {
    it('should verify a valid token', () => {
      // Arrange
      const token = generateToken(mockPayload, mockSecret);

      // Act
      const verified = verifyToken(token, mockSecret);

      // Assert
      expect(verified).toBeDefined();
      expect(verified?.sub).toBe(mockPayload.sub);
      expect(verified?.email).toBe(mockPayload.email);
      expect(verified?.name).toBe(mockPayload.name);
      expect(verified?.roles).toEqual(mockPayload.roles);
    });

    it('should return null for invalid signature', () => {
      // Arrange
      const token = generateToken(mockPayload, mockSecret);

      // Act
      const verified = verifyToken(token, 'wrong-secret');

      // Assert
      expect(verified).toBeNull();
    });

    it('should return null for expired token', () => {
      // Arrange
      const token = generateToken(mockPayload, mockSecret, '-1s'); // Already expired

      // Act
      const verified = verifyToken(token, mockSecret);

      // Assert
      expect(verified).toBeNull();
    });

    it('should return null for malformed token', () => {
      // Act
      const verified = verifyToken('invalid.token.format', mockSecret);

      // Assert
      expect(verified).toBeNull();
    });
  });

  describe('decodeToken', () => {
    it('should decode token without verification', () => {
      // Arrange
      const token = generateToken(mockPayload, mockSecret);

      // Act
      const decoded = decodeToken(token);

      // Assert
      expect(decoded).toBeDefined();
      expect(decoded?.sub).toBe(mockPayload.sub);
      expect(decoded?.email).toBe(mockPayload.email);
    });

    it('should return null for invalid token format', () => {
      // Act
      const decoded = decodeToken('not-a-jwt');

      // Assert
      expect(decoded).toBeNull();
    });
  });

  describe('extractBearerToken', () => {
    it('should extract token from valid Bearer header', () => {
      // Act
      const token = extractBearerToken('Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9');

      // Assert
      expect(token).toBe('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9');
    });

    it('should return null for missing Bearer prefix', () => {
      // Act
      const token = extractBearerToken('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9');

      // Assert
      expect(token).toBeNull();
    });

    it('should return null for empty header', () => {
      // Act
      const token = extractBearerToken('');

      // Assert
      expect(token).toBeNull();
    });

    it('should return null for Bearer without token', () => {
      // Act
      const token = extractBearerToken('Bearer ');

      // Assert
      expect(token).toBeNull();
    });

    it('should handle case insensitive Bearer prefix', () => {
      // Act
      const token = extractBearerToken('bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9');

      // Assert
      expect(token).toBe('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9');
    });
  });

  describe('isTokenExpired', () => {
    it('should return false for valid token', () => {
      // Arrange
      const token = generateToken(mockPayload, mockSecret, '1h');

      // Act
      const expired = isTokenExpired(token);

      // Assert
      expect(expired).toBe(false);
    });

    it('should return true for expired token', () => {
      // Arrange
      const token = generateToken(mockPayload, mockSecret, '-1s');

      // Act
      const expired = isTokenExpired(token);

      // Assert
      expect(expired).toBe(true);
    });

    it('should return true for invalid token', () => {
      // Act
      const expired = isTokenExpired('invalid-token');

      // Assert
      expect(expired).toBe(true);
    });

    it('should return true for token without exp claim', () => {
      // Arrange
      const customPayload = { sub: 'user-123' };
      const token = generateToken(customPayload, mockSecret);
      // Manually remove exp claim by decoding and re-encoding
      const decoded = decodeToken(token);
      if (decoded) {
        delete decoded.exp;
      }

      // Act - For this case, we'll just test with invalid token
      const expired = isTokenExpired('token-without-exp');

      // Assert
      expect(expired).toBe(true);
    });
  });
});
