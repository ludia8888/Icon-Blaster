import request from 'supertest';

import { createApp } from '../app';

describe('App Configuration', () => {
  const app = createApp();

  it('should have security headers', async () => {
    // Act
    const response = await request(app).get('/health');

    // Assert
    expect(response.headers).toHaveProperty('content-security-policy');
    expect(response.headers['x-frame-options']).toBe('SAMEORIGIN');
    expect(response.headers['x-content-type-options']).toBe('nosniff');
  });

  it('should handle 404 for unknown routes', async () => {
    // Act
    const response = await request(app).get('/unknown-route');

    // Assert
    expect(response.status).toBe(404);
    const responseBody = response.body as {
      error: { code: string; message: string };
      timestamp: string;
      path: string;
    };
    expect(responseBody).toMatchObject({
      error: {
        code: 'NOT_FOUND',
        message: expect.any(String) as unknown,
      },
      timestamp: expect.any(String) as unknown,
      path: '/unknown-route',
    });
  });

  it('should handle invalid JSON', async () => {
    // Act
    const response = await request(app)
      .post('/api/test')
      .set('Content-Type', 'application/json')
      .send('invalid json');

    // Assert
    expect(response.status).toBe(400);
    const responseBody = response.body as { error: { code: string } };
    expect(responseBody.error.code).toBe('BAD_REQUEST');
  });

  it('should support CORS for allowed origins', async () => {
    // Act
    const response = await request(app).get('/health').set('Origin', 'http://localhost:3000');

    // Assert
    expect(response.headers['access-control-allow-origin']).toBe('http://localhost:3000');
  });
});
