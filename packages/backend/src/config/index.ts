import dotenv from 'dotenv';

// Load environment variables
dotenv.config();

/**
 * Application configuration
 */
export interface AppConfig {
  env: string;
  port: number;
  cors: {
    origin: string[];
    credentials: boolean;
  };
  rateLimit: {
    windowMs: number;
    max: number;
  };
}

/**
 * Get configuration from environment
 */
export function getConfig(): AppConfig {
  return {
    env: process.env['NODE_ENV'] ?? 'development',
    port: parseInt(process.env['PORT'] ?? '4000', 10),
    cors: {
      origin:
        process.env['CORS_ORIGIN'] !== undefined && process.env['CORS_ORIGIN'] !== ''
          ? process.env['CORS_ORIGIN'].split(',')
          : ['http://localhost:3000', 'http://localhost:3001'],
      credentials: true,
    },
    rateLimit: {
      windowMs: parseInt(process.env['RATE_LIMIT_WINDOW'] ?? '60000', 10), // 1 minute
      max: parseInt(process.env['RATE_LIMIT_MAX'] ?? '100', 10),
    },
  };
}

/**
 * Validate configuration
 */
export function validateConfig(config: AppConfig): void {
  if (config.port < 0 || config.port > 65535) {
    throw new Error('Invalid port number');
  }

  if (config.rateLimit.windowMs <= 0) {
    throw new Error('Rate limit window must be positive');
  }

  if (config.rateLimit.max <= 0) {
    throw new Error('Rate limit max must be positive');
  }

  if (!['development', 'test', 'production'].includes(config.env)) {
    throw new Error('Invalid environment');
  }
}
