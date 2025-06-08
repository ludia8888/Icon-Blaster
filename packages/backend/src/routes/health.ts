import { Router, Request, Response } from 'express';

import { getConfig } from '../config';
import { getDataSource } from '../database/connection';

const router = Router();
const startTime = Date.now();

/**
 * Basic health check
 */
router.get('/', (_req: Request, res: Response): void => {
  const config = getConfig();
  const uptime = Date.now() - startTime;

  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    uptime,
    environment: config.env,
    version: process.env['npm_package_version'] ?? '1.0.0',
  });
});

/**
 * Readiness check (for Kubernetes)
 */
router.get('/ready', async (_req: Request, res: Response): Promise<void> => {
  const checks = {
    database: false,
    cache: true, // Note: Redis connection check not implemented yet
  };

  // Check database connection
  try {
    const dataSource = getDataSource();
    if (dataSource && dataSource.isInitialized) {
      // Run a simple query to verify the connection is working
      await dataSource.query('SELECT 1');
      checks.database = true;
    }
  } catch (error) {
    // Database check failed, keep it as false
    console.error('Database health check failed:', error);
  }

  // TODO: When Redis is implemented, add connection check here
  // For now, we'll assume cache is always ready since it's not implemented

  const ready = Object.values(checks).every(Boolean);

  res.status(ready ? 200 : 503).json({
    ready,
    checks,
  });
});

export { router as healthRouter };
