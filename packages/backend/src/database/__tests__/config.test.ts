import { getDatabaseConfig, validateDatabaseConfig } from '../config';

describe('Database Configuration', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...originalEnv };
  });

  afterAll(() => {
    process.env = originalEnv;
  });

  describe('getDatabaseConfig', () => {
    it('should return default configuration for test environment', () => {
      // Arrange
      process.env['NODE_ENV'] = 'test';

      // Act
      const config = getDatabaseConfig();

      // Assert
      expect(config).toMatchObject({
        type: 'postgres',
        host: 'localhost',
        port: 5432,
        username: 'arrakis',
        password: 'arrakis',
        database: 'arrakis_test',
        synchronize: false,
        logging: false,
      });
    });

    it('should use environment variables when set', () => {
      // Arrange
      process.env['DATABASE_HOST'] = 'db.example.com';
      process.env['DATABASE_PORT'] = '5433';
      process.env['DATABASE_USER'] = 'custom_user';
      process.env['DATABASE_PASSWORD'] = 'custom_pass';
      process.env['DATABASE_NAME'] = 'custom_db';

      // Act
      const config = getDatabaseConfig();

      // Assert
      interface PostgresConfig {
        host?: string;
        port?: number;
        username?: string;
        password?: string;
        database?: string;
      }
      const pgConfig = config as PostgresConfig;
      expect(pgConfig.host).toBe('db.example.com');
      expect(pgConfig.port).toBe(5433);
      expect(pgConfig.username).toBe('custom_user');
      expect(pgConfig.password).toBe('custom_pass');
      expect(pgConfig.database).toBe('custom_db');
    });

    it('should enable synchronize in development mode', () => {
      // Arrange
      process.env['NODE_ENV'] = 'development';

      // Act
      const config = getDatabaseConfig();

      // Assert
      expect(config.synchronize).toBe(true);
    });

    it('should disable synchronize in production mode', () => {
      // Arrange
      process.env['NODE_ENV'] = 'production';

      // Act
      const config = getDatabaseConfig();

      // Assert
      expect(config.synchronize).toBe(false);
    });
  });

  describe('validateDatabaseConfig', () => {
    it('should validate valid configuration', () => {
      // Arrange
      const config = {
        type: 'postgres' as const,
        host: 'localhost',
        port: 5432,
        username: 'user',
        password: 'pass',
        database: 'db',
        synchronize: false,
        logging: false,
      };

      // Act & Assert
      expect(() => validateDatabaseConfig(config)).not.toThrow();
    });

    it('should throw on invalid port', () => {
      // Arrange
      const config = {
        type: 'postgres' as const,
        host: 'localhost',
        port: -1,
        username: 'user',
        password: 'pass',
        database: 'db',
        synchronize: false,
        logging: false,
      };

      // Act & Assert
      expect(() => validateDatabaseConfig(config)).toThrow('Invalid database port');
    });

    it('should throw on missing host', () => {
      // Arrange
      const config = {
        type: 'postgres' as const,
        host: '',
        port: 5432,
        username: 'user',
        password: 'pass',
        database: 'db',
        synchronize: false,
        logging: false,
      };

      // Act & Assert
      expect(() => validateDatabaseConfig(config)).toThrow('Database host is required');
    });

    it('should throw on missing database name', () => {
      // Arrange
      const config = {
        type: 'postgres' as const,
        host: 'localhost',
        port: 5432,
        username: 'user',
        password: 'pass',
        database: '',
        synchronize: false,
        logging: false,
      };

      // Act & Assert
      expect(() => validateDatabaseConfig(config)).toThrow('Database name is required');
    });
  });
});
