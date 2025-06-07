import { Router, Request, Response } from 'express';

import { getConfig } from '../config';

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
router.get('/ready', (_req: Request, res: Response): void => {
  // In the future, check actual database and cache connections
  const checks = {
    database: true, // TODO: Check actual DB connection
    cache: true, // TODO: Check Redis connection
  };

  const ready = Object.values(checks).every(Boolean);

  res.status(ready ? 200 : 503).json({
    ready,
    checks,
  });
});

export { router as healthRouter };
