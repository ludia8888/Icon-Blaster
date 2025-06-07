import { getConfig, validateConfig } from '../index';

describe('Configuration', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...originalEnv };
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  describe('getConfig', () => {
    it('should return default configuration', () => {
      // Arrange
      process.env['NODE_ENV'] = 'test';

      // Act
      const config = getConfig();

      // Assert
      expect(config).toMatchObject({
        env: 'test',
        port: 4000,
        cors: {
          origin: expect.any(Array) as unknown,
          credentials: true,
        },
        rateLimit: {
          windowMs: expect.any(Number) as unknown,
          max: expect.any(Number) as unknown,
        },
      });
    });

    it('should use environment variables when set', () => {
      // Arrange
      process.env['PORT'] = '5000';
      process.env['NODE_ENV'] = 'production';

      // Act
      const config = getConfig();

      // Assert
      expect(config.port).toBe(5000);
      expect(config.env).toBe('production');
    });
  });

  describe('validateConfig', () => {
    it('should validate valid configuration', () => {
      // Arrange
      const config = {
        env: 'development',
        port: 3000,
        cors: { origin: ['http://localhost:3000'], credentials: true },
        rateLimit: { windowMs: 60000, max: 100 },
      };

      // Act & Assert
      expect(() => validateConfig(config)).not.toThrow();
    });

    it('should throw on invalid port', () => {
      // Arrange
      const config = {
        env: 'development',
        port: -1,
        cors: { origin: [], credentials: true },
        rateLimit: { windowMs: 60000, max: 100 },
      };

      // Act & Assert
      expect(() => validateConfig(config)).toThrow('Invalid port number');
    });

    it('should throw on invalid environment', () => {
      // Arrange
      const config = {
        env: 'invalid',
        port: 3000,
        cors: { origin: [], credentials: true },
        rateLimit: { windowMs: 60000, max: 100 },
      };

      // Act & Assert
      expect(() => validateConfig(config)).toThrow('Invalid environment');
    });

    it('should throw on invalid rate limit window', () => {
      // Arrange
      const config = {
        env: 'development',
        port: 3000,
        cors: { origin: [], credentials: true },
        rateLimit: { windowMs: 0, max: 100 },
      };

      // Act & Assert
      expect(() => validateConfig(config)).toThrow('Rate limit window must be positive');
    });

    it('should throw on invalid rate limit max', () => {
      // Arrange
      const config = {
        env: 'development',
        port: 3000,
        cors: { origin: [], credentials: true },
        rateLimit: { windowMs: 60000, max: 0 },
      };

      // Act & Assert
      expect(() => validateConfig(config)).toThrow('Rate limit max must be positive');
    });
  });
});
