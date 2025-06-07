import { createApp } from './app';
import { getConfig, validateConfig } from './config';

/**
 * Start the server
 */
function startServer(): void {
  try {
    const config = getConfig();
    validateConfig(config);

    const app = createApp();

    const server = app.listen(config.port, () => {
      // Server running on port ${config.port} in ${config.env} mode
      // Health check: http://localhost:${config.port}/health
    });

    // Graceful shutdown
    process.on('SIGTERM', () => {
      // SIGTERM signal received: closing HTTP server
      server.close(() => {
        // HTTP server closed
        process.exit(0);
      });
    });
  } catch (error) {
    // Failed to start server
    process.exit(1);
  }
}

// Start server if not in test environment
if (process.env['NODE_ENV'] !== 'test') {
  void startServer();
}
