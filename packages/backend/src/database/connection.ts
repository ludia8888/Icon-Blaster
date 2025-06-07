import 'reflect-metadata';

import { DataSource } from 'typeorm';

import { getDatabaseConfig } from './config';

let dataSource: DataSource | null = null;

export async function initializeDatabase(): Promise<DataSource> {
  if (dataSource && dataSource.isInitialized) {
    return dataSource;
  }

  const config = getDatabaseConfig();

  dataSource = new DataSource(config);

  try {
    await dataSource.initialize();

    if (process.env['NODE_ENV'] !== 'test') {
      // Database connection established successfully
    }

    return dataSource;
  } catch (error) {
    dataSource = null;
    throw new Error(
      `Failed to connect to database: ${error instanceof Error ? error.message : 'Unknown error'}`
    );
  }
}

export async function closeDatabase(): Promise<void> {
  if (dataSource && dataSource.isInitialized) {
    await dataSource.destroy();
    dataSource = null;
  }
}

export function getDataSource(): DataSource {
  if (!dataSource || !dataSource.isInitialized) {
    throw new Error('Database connection not initialized');
  }

  return dataSource;
}

/**
 * Set the DataSource (for testing purposes)
 */
export function setDataSource(ds: DataSource): void {
  dataSource = ds;
}
