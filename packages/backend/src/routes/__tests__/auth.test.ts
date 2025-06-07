import request from 'supertest';

import { createApp } from '../../app';

describe('Auth Routes', () => {
  const app = createApp();

  describe('POST /auth/mock-token', () => {
    it('should generate mock token in development mode', async () => {
      // Arrange
      process.env['NODE_ENV'] = 'development';
      process.env['JWT_SECRET'] = 'test-secret-key-for-development-only-32chars';

      // Act
      const response = await request(app)
        .post('/auth/mock-token')
        .send({
          userId: 'user-123',
          email: 'test@example.com',
          name: 'Test User',
          roles: ['user', 'editor'],
        });

      // Assert
      expect(response.status).toBe(200);
      const responseBody = response.body as { token: string; expiresIn: string };
      expect(responseBody).toHaveProperty('token');
      expect(responseBody).toHaveProperty('expiresIn');
      expect(typeof responseBody.token).toBe('string');
      expect(responseBody.token.split('.')).toHaveLength(3);
    });

    it('should use default values when not provided', async () => {
      // Arrange
      process.env['NODE_ENV'] = 'development';
      process.env['JWT_SECRET'] = 'test-secret-key-for-development-only-32chars';

      // Act
      const response = await request(app).post('/auth/mock-token').send({});

      // Assert
      expect(response.status).toBe(200);
      const responseBody = response.body as { token: string };
      expect(responseBody).toHaveProperty('token');
    });

    it('should return 404 in production mode', async () => {
      // Arrange
      process.env['NODE_ENV'] = 'production';

      // Act
      const response = await request(app).post('/auth/mock-token').send({});

      // Assert
      expect(response.status).toBe(404);
    });

    it('should return 500 when JWT_SECRET is not set', async () => {
      // Arrange
      process.env['NODE_ENV'] = 'development';
      delete process.env['JWT_SECRET'];

      // Act
      const response = await request(app).post('/auth/mock-token').send({});

      // Assert
      expect(response.status).toBe(500);
      const responseBody = response.body as { error: { message: string } };
      expect(responseBody.error.message).toContain('JWT_SECRET');
    });
  });

  afterEach(() => {
    delete process.env['JWT_SECRET'];
    process.env['NODE_ENV'] = 'test';
  });
});
