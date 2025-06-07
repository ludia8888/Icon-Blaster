import request from 'supertest';

import { createApp } from '../app';

describe('Health Check', () => {
  const app = createApp();

  describe('GET /health', () => {
    it('should return 200 with health status', async () => {
      // Act
      const response = await request(app).get('/health');

      // Assert
      expect(response.status).toBe(200);
      const responseBody = response.body as {
        status: string;
        timestamp: string;
        uptime: number;
        environment: string;
      };
      expect(responseBody).toMatchObject({
        status: 'healthy',
        timestamp: expect.any(String) as unknown,
        uptime: expect.any(Number) as unknown,
        environment: 'test',
      });
    });

    it('should include version information', async () => {
      // Act
      const response = await request(app).get('/health');

      // Assert
      const responseBody = response.body as { version?: string };
      expect(responseBody).toHaveProperty('version');
      expect(responseBody.version).toBeTruthy();
    });

    it('should have correct content type', async () => {
      // Act
      const response = await request(app).get('/health');

      // Assert
      expect(response.headers['content-type']).toMatch(/application\/json/);
    });
  });

  describe('GET /health/ready', () => {
    it('should return readiness status', async () => {
      // Act
      const response = await request(app).get('/health/ready');

      // Assert
      expect(response.status).toBe(200);
      const responseBody = response.body as {
        ready: boolean;
        checks: { database: boolean; cache: boolean };
      };
      expect(responseBody).toMatchObject({
        ready: true,
        checks: {
          database: expect.any(Boolean) as unknown,
          cache: expect.any(Boolean) as unknown,
        },
      });
    });
  });
});
