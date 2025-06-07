import { getJwtConfig, validateJwtConfig } from '../config';

describe('JWT Configuration', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...originalEnv };
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  describe('getJwtConfig', () => {
    it('should return configuration when JWT_SECRET is set', () => {
      // Arrange
      process.env['JWT_SECRET'] = 'test-secret-key-at-least-32-characters-long';

      // Act
      const config = getJwtConfig();

      // Assert
      expect(config).toEqual({
        secret: 'test-secret-key-at-least-32-characters-long',
        expiresIn: '1h',
      });
    });

    it('should use custom expiration when JWT_EXPIRES_IN is set', () => {
      // Arrange
      process.env['JWT_SECRET'] = 'test-secret-key-at-least-32-characters-long';
      process.env['JWT_EXPIRES_IN'] = '2d';

      // Act
      const config = getJwtConfig();

      // Assert
      expect(config.expiresIn).toBe('2d');
    });

    it('should throw error when JWT_SECRET is not set', () => {
      // Arrange
      delete process.env['JWT_SECRET'];

      // Act & Assert
      expect(() => getJwtConfig()).toThrow('JWT_SECRET environment variable is required');
    });
  });

  describe('validateJwtConfig', () => {
    it('should validate valid configuration', () => {
      // Arrange
      const config = {
        secret: 'test-secret-key-at-least-32-characters-long',
        expiresIn: '1h',
      };

      // Act & Assert
      expect(() => validateJwtConfig(config)).not.toThrow();
    });

    it('should throw error for short secret', () => {
      // Arrange
      const config = {
        secret: 'short-secret',
        expiresIn: '1h',
      };

      // Act & Assert
      expect(() => validateJwtConfig(config)).toThrow(
        'JWT secret must be at least 32 characters long'
      );
    });

    it('should throw error for empty secret', () => {
      // Arrange
      const config = {
        secret: '',
        expiresIn: '1h',
      };

      // Act & Assert
      expect(() => validateJwtConfig(config)).toThrow(
        'JWT secret must be at least 32 characters long'
      );
    });

    it('should validate various expiration formats', () => {
      // Arrange
      const validFormats = ['1s', '30m', '1h', '7d', '4w', '1y'];

      // Act & Assert
      validFormats.forEach((expiresIn) => {
        const config = {
          secret: 'test-secret-key-at-least-32-characters-long',
          expiresIn,
        };
        expect(() => validateJwtConfig(config)).not.toThrow();
      });
    });

    it('should throw error for invalid expiration format', () => {
      // Arrange
      const invalidFormats = ['1', 'abc', '1x', '1 hour', ''];

      // Act & Assert
      invalidFormats.forEach((expiresIn) => {
        const config = {
          secret: 'test-secret-key-at-least-32-characters-long',
          expiresIn,
        };
        expect(() => validateJwtConfig(config)).toThrow('Invalid JWT expiration format');
      });
    });
  });
});
