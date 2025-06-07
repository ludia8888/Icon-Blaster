import path from 'path';

import { DataSourceOptions } from 'typeorm';

export function getDatabaseConfig(): DataSourceOptions {
  const env = process.env['NODE_ENV'] ?? 'development';
  const isProduction = env === 'production';
  const isTest = env === 'test';

  const config: DataSourceOptions = {
    type: 'postgres',
    host: process.env['DATABASE_HOST'] ?? 'localhost',
    port: parseInt(process.env['DATABASE_PORT'] ?? '5432', 10),
    username: process.env['DATABASE_USER'] ?? 'arrakis',
    password: process.env['DATABASE_PASSWORD'] ?? 'arrakis',
    database: process.env['DATABASE_NAME'] ?? (isTest ? 'arrakis_test' : 'arrakis'),
    synchronize: !isProduction && !isTest,
    logging: process.env['DATABASE_LOGGING'] === 'true',
    entities: [path.join(__dirname, '../entities/**/*.{ts,js}')],
    migrations: [path.join(__dirname, '../migrations/**/*.{ts,js}')],
    migrationsRun: isProduction,
  };

  validateDatabaseConfig(config);
  return config;
}

interface PostgresConfig {
  host?: string;
  port?: number;
  username?: string;
  password?: string;
  database?: string;
}

function validateRequired(value: string | undefined, fieldName: string): void {
  if (value === undefined || value === '') {
    throw new Error(`${fieldName} is required`);
  }
}

function validatePort(port: number | undefined): void {
  if (port === undefined || port <= 0 || port > 65535) {
    throw new Error('Invalid database port');
  }
}

function validatePostgresConfig(pgConfig: PostgresConfig): void {
  validateRequired(pgConfig.host, 'Database host');
  validateRequired(pgConfig.database, 'Database name');
  validateRequired(pgConfig.username, 'Database username');
  validateRequired(pgConfig.password, 'Database password');
  validatePort(pgConfig.port);
}

export function validateDatabaseConfig(config: DataSourceOptions): void {
  if (config.type !== 'postgres') {
    throw new Error('Only PostgreSQL is supported');
  }

  const pgConfig = config as PostgresConfig;
  validatePostgresConfig(pgConfig);
}
