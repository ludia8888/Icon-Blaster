/**
 * Test-specific app initialization
 *
 * Creates an Express app instance that uses the test DataSource
 */

import { Application } from 'express';
import { DataSource } from 'typeorm';

import { createApp } from '../../app';
import { setDataSource } from '../../database';

/**
 * Create test app with injected DataSource
 */
export function createTestApp(dataSource: DataSource): Application {
  // Set the test DataSource globally
  setDataSource(dataSource);

  // Create and return the app
  return createApp();
}
