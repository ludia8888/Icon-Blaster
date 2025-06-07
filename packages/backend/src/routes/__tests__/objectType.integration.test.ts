import { NodeStatus, NodeVisibility } from '@arrakis/shared';
import { Application } from 'express';
import request from 'supertest';

import { createApp } from '../../app';
import { generateToken } from '../../auth/jwt';
import { initializeDatabase, closeDatabase, getDataSource } from '../../database';

describe('ObjectType API Integration Tests', () => {
  let app: Application;
  let adminToken: string;
  let editorToken: string;
  let viewerToken: string;

  beforeAll(async () => {
    await initializeDatabase();
    app = createApp();

    // Generate test tokens
    const secret = process.env['JWT_SECRET'] ?? 'test-secret';
    adminToken = generateToken(
      { sub: 'admin-user', email: 'admin@test.com', name: 'Admin', roles: ['admin'] },
      secret
    );
    editorToken = generateToken(
      { sub: 'editor-user', email: 'editor@test.com', name: 'Editor', roles: ['editor'] },
      secret
    );
    viewerToken = generateToken(
      { sub: 'viewer-user', email: 'viewer@test.com', name: 'Viewer', roles: ['viewer'] },
      secret
    );

    // Set JWT secret for tests
    process.env['JWT_SECRET'] = secret;
  });

  afterAll(async () => {
    await closeDatabase();
  });

  beforeEach(async () => {
    // Clear the ObjectType table before each test
    const dataSource = getDataSource();
    await dataSource.getRepository('ObjectType').clear();
  });

  describe('POST /api/object-types', () => {
    const validObjectType = {
      apiName: 'TestObject',
      displayName: 'Test Object',
      description: 'A test object type',
      icon: 'test-icon',
      color: '#FF5733',
      groups: ['group1', 'group2'],
    };

    it('should create a new object type with valid data', async () => {
      const response = await request(app)
        .post('/api/object-types')
        .set('Authorization', `Bearer ${adminToken}`)
        .send(validObjectType)
        .expect(201);

      expect(response.body).toMatchObject({
        apiName: 'TestObject',
        displayName: 'Test Object',
        description: 'A test object type',
        status: NodeStatus.ACTIVE,
        visibility: NodeVisibility.NORMAL,
      });
      expect(response.body.rid).toBeDefined();
      expect(response.body.createdAt).toBeDefined();
    });

    it('should reject invalid data with 400 error', async () => {
      const response = await request(app)
        .post('/api/object-types')
        .set('Authorization', `Bearer ${adminToken}`)
        .send({
          apiName: 'Invalid Name!', // Invalid format
          displayName: 'Test',
          color: 'not-a-color', // Invalid hex color
        })
        .expect(400);

      expect(response.body.error).toBeDefined();
      expect(response.body.error.code).toBe('VALIDATION_ERROR');
      expect(response.body.error.details).toContain(
        expect.stringContaining('API name must be alphanumeric')
      );
    });

    it('should reject duplicate apiName with 409 error', async () => {
      // Create first object type
      await request(app)
        .post('/api/object-types')
        .set('Authorization', `Bearer ${adminToken}`)
        .send(validObjectType)
        .expect(201);

      // Try to create duplicate
      const response = await request(app)
        .post('/api/object-types')
        .set('Authorization', `Bearer ${adminToken}`)
        .send(validObjectType)
        .expect(409);

      expect(response.body.error.code).toBe('CONFLICT');
    });

    it('should require authentication', async () => {
      await request(app).post('/api/object-types').send(validObjectType).expect(401);
    });

    it('should require proper authorization', async () => {
      await request(app)
        .post('/api/object-types')
        .set('Authorization', `Bearer ${viewerToken}`)
        .send(validObjectType)
        .expect(403);
    });
  });

  describe('GET /api/object-types', () => {
    beforeEach(async () => {
      // Create test data
      const objectTypes = [
        { apiName: 'Object1', displayName: 'First Object', status: NodeStatus.ACTIVE },
        { apiName: 'Object2', displayName: 'Second Object', status: NodeStatus.ACTIVE },
        { apiName: 'Object3', displayName: 'Third Object', status: NodeStatus.DEPRECATED },
      ];

      for (const ot of objectTypes) {
        await request(app)
          .post('/api/object-types')
          .set('Authorization', `Bearer ${adminToken}`)
          .send(ot);
      }
    });

    it('should list all object types with pagination', async () => {
      const response = await request(app)
        .get('/api/object-types')
        .set('Authorization', `Bearer ${viewerToken}`)
        .query({ page: 1, limit: 2 })
        .expect(200);

      expect(response.body.data).toHaveLength(2);
      expect(response.body.pagination).toEqual({
        total: 3,
        page: 1,
        limit: 2,
        totalPages: 2,
      });
    });

    it('should filter by status', async () => {
      const response = await request(app)
        .get('/api/object-types')
        .set('Authorization', `Bearer ${viewerToken}`)
        .query({ status: NodeStatus.DEPRECATED })
        .expect(200);

      expect(response.body.data).toHaveLength(1);
      expect(response.body.data[0].apiName).toBe('Object3');
    });

    it('should search by display name', async () => {
      const response = await request(app)
        .get('/api/object-types')
        .set('Authorization', `Bearer ${viewerToken}`)
        .query({ search: 'Second' })
        .expect(200);

      expect(response.body.data).toHaveLength(1);
      expect(response.body.data[0].apiName).toBe('Object2');
    });

    it('should sort by different fields', async () => {
      const response = await request(app)
        .get('/api/object-types')
        .set('Authorization', `Bearer ${viewerToken}`)
        .query({ sortBy: 'displayName', sortOrder: 'desc' })
        .expect(200);

      expect(response.body.data[0].displayName).toBe('Third Object');
      expect(response.body.data[1].displayName).toBe('Second Object');
      expect(response.body.data[2].displayName).toBe('First Object');
    });
  });

  describe('GET /api/object-types/:id', () => {
    let objectTypeId: string;

    beforeEach(async () => {
      const response = await request(app)
        .post('/api/object-types')
        .set('Authorization', `Bearer ${adminToken}`)
        .send({
          apiName: 'TestObject',
          displayName: 'Test Object',
        });

      objectTypeId = response.body.rid;
    });

    it('should get a single object type by ID', async () => {
      const response = await request(app)
        .get(`/api/object-types/${objectTypeId}`)
        .set('Authorization', `Bearer ${viewerToken}`)
        .expect(200);

      expect(response.body.rid).toBe(objectTypeId);
      expect(response.body.apiName).toBe('TestObject');
    });

    it('should return 404 for non-existent ID', async () => {
      const fakeId = '550e8400-e29b-41d4-a716-446655440000';

      const response = await request(app)
        .get(`/api/object-types/${fakeId}`)
        .set('Authorization', `Bearer ${viewerToken}`)
        .expect(404);

      expect(response.body.error.code).toBe('NOT_FOUND');
    });

    it('should validate UUID format', async () => {
      const response = await request(app)
        .get('/api/object-types/not-a-uuid')
        .set('Authorization', `Bearer ${viewerToken}`)
        .expect(400);

      expect(response.body.error.code).toBe('VALIDATION_ERROR');
    });
  });

  describe('PUT /api/object-types/:id', () => {
    let objectTypeId: string;

    beforeEach(async () => {
      const response = await request(app)
        .post('/api/object-types')
        .set('Authorization', `Bearer ${adminToken}`)
        .send({
          apiName: 'TestObject',
          displayName: 'Test Object',
        });

      objectTypeId = response.body.rid;
    });

    it('should update object type with valid data', async () => {
      const response = await request(app)
        .put(`/api/object-types/${objectTypeId}`)
        .set('Authorization', `Bearer ${editorToken}`)
        .send({
          displayName: 'Updated Object',
          description: 'Updated description',
        })
        .expect(200);

      expect(response.body.displayName).toBe('Updated Object');
      expect(response.body.description).toBe('Updated description');
      expect(response.body.apiName).toBe('TestObject'); // Should not change
    });

    it('should require proper authorization', async () => {
      await request(app)
        .put(`/api/object-types/${objectTypeId}`)
        .set('Authorization', `Bearer ${viewerToken}`)
        .send({ displayName: 'Updated' })
        .expect(403);
    });
  });

  describe('DELETE /api/object-types/:id', () => {
    let objectTypeId: string;

    beforeEach(async () => {
      const response = await request(app)
        .post('/api/object-types')
        .set('Authorization', `Bearer ${adminToken}`)
        .send({
          apiName: 'TestObject',
          displayName: 'Test Object',
        });

      objectTypeId = response.body.rid;
    });

    it('should soft delete object type', async () => {
      await request(app)
        .delete(`/api/object-types/${objectTypeId}`)
        .set('Authorization', `Bearer ${adminToken}`)
        .expect(200);

      // Verify it's soft deleted
      const response = await request(app)
        .get(`/api/object-types/${objectTypeId}`)
        .set('Authorization', `Bearer ${adminToken}`)
        .expect(200);

      // Status should be DEPRECATED as soft delete
      expect(response.body.status).toBe(NodeStatus.DEPRECATED);
    });

    it('should require admin role', async () => {
      await request(app)
        .delete(`/api/object-types/${objectTypeId}`)
        .set('Authorization', `Bearer ${editorToken}`)
        .expect(403);
    });
  });

  describe('Type Safety Verification', () => {
    it('should provide type-safe request bodies', async () => {
      // This test verifies that TypeScript compilation succeeds
      // with proper type inference in the controller

      const response = await request(app)
        .post('/api/object-types')
        .set('Authorization', `Bearer ${adminToken}`)
        .send({
          apiName: 'TypeSafeObject',
          displayName: 'Type Safe Object',
          // If TypeScript types are working correctly,
          // the controller will have access to typed req.body
        })
        .expect(201);

      expect(response.body.apiName).toBe('TypeSafeObject');
    });
  });
});
