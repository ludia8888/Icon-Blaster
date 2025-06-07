import { CreateObjectTypeSchema, ObjectTypeQuerySchema, IdParamSchema , ErrorCode } from '@arrakis/contracts';
import { NodeStatus, NodeVisibility } from '@arrakis/shared';
import express, { Application } from 'express';
import request from 'supertest';
import { z } from 'zod';

import { validateBody, validateQuery, validateParams } from '../../middlewares/validate';


describe('ObjectType API Type Safety and Validation Tests', () => {
  let app: Application;

  beforeEach(() => {
    app = express();
    app.use(express.json());

    // Mock endpoint to test request body validation and type inference
    app.post('/test/object-types',
      validateBody(CreateObjectTypeSchema),
      (req, res) => {
        // If we reach here, validation passed
        // TypeScript should know req.body is CreateObjectTypeDto
        const { apiName, displayName, status, visibility } = req.body;
        
        res.json({
          validated: true,
          data: {
            apiName,
            displayName,
            status: status ?? NodeStatus.ACTIVE,
            visibility: visibility ?? NodeVisibility.NORMAL,
          }
        });
      }
    );

    // Mock endpoint to test query validation
    app.get('/test/object-types',
      validateQuery(ObjectTypeQuerySchema),
      (req, res) => {
        // TypeScript should know req.query matches ObjectTypeQuery
        const { page, limit, sortBy, sortOrder } = req.query;
        
        res.json({
          validated: true,
          query: {
            page,
            limit,
            sortBy,
            sortOrder,
          }
        });
      }
    );

    // Mock endpoint to test params validation
    app.get('/test/object-types/:id',
      validateParams(IdParamSchema),
      (req, res) => {
        // TypeScript should know req.params.id is a valid UUID
        const { id } = req.params;
        
        res.json({
          validated: true,
          id,
        });
      }
    );

    // Error handler to catch validation errors
    app.use((err: any, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
      if (err.code === ErrorCode.VALIDATION_ERROR) {
        res.status(400).json({
          error: {
            code: err.code,
            message: err.message,
            details: err.details,
          }
        });
      } else {
        res.status(500).json({ error: 'Internal error' });
      }
    });
  });

  describe('Body Validation', () => {
    it('should accept valid ObjectType creation data', async () => {
      const response = await request(app)
        .post('/test/object-types')
        .send({
          apiName: 'TestObject',
          displayName: 'Test Object',
          description: 'A test object',
          color: '#FF5733',
          groups: ['group1', 'group2'],
        })
        .expect(200);

      expect(response.body.validated).toBe(true);
      expect(response.body.data.apiName).toBe('TestObject');
      expect(response.body.data.displayName).toBe('Test Object');
    });

    it('should reject invalid API name format', async () => {
      const response = await request(app)
        .post('/test/object-types')
        .send({
          apiName: 'Invalid Name!', // Contains space and special char
          displayName: 'Test Object',
        })
        .expect(400);

      expect(response.body.error.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(response.body.error.details[0]).toContain('API name must be alphanumeric');
    });

    it('should reject invalid hex color', async () => {
      const response = await request(app)
        .post('/test/object-types')
        .send({
          apiName: 'TestObject',
          displayName: 'Test Object',
          color: 'not-a-color',
        })
        .expect(400);

      expect(response.body.error.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(response.body.error.details[0]).toContain('Color must be a valid hex color');
    });

    it('should apply default values for optional fields', async () => {
      const response = await request(app)
        .post('/test/object-types')
        .send({
          apiName: 'MinimalObject',
          displayName: 'Minimal Object',
        })
        .expect(200);

      expect(response.body.data.status).toBe(NodeStatus.ACTIVE);
      expect(response.body.data.visibility).toBe(NodeVisibility.NORMAL);
    });
  });

  describe('Query Validation', () => {
    it('should parse and validate query parameters', async () => {
      const response = await request(app)
        .get('/test/object-types')
        .query({
          page: '2',
          limit: '50',
          sortBy: 'displayName',
          sortOrder: 'desc',
        })
        .expect(200);

      expect(response.body.query.page).toBe(2); // Coerced to number
      expect(response.body.query.limit).toBe(50); // Coerced to number
      expect(response.body.query.sortBy).toBe('displayName');
      expect(response.body.query.sortOrder).toBe('desc');
    });

    it('should apply defaults for missing query params', async () => {
      const response = await request(app)
        .get('/test/object-types')
        .expect(200);

      expect(response.body.query.page).toBe(1);
      expect(response.body.query.limit).toBe(20);
      expect(response.body.query.sortBy).toBe('apiName');
      expect(response.body.query.sortOrder).toBe('asc');
    });

    it('should reject invalid query values', async () => {
      const response = await request(app)
        .get('/test/object-types')
        .query({
          page: '-1',
          limit: '200', // Exceeds max
        })
        .expect(400);

      expect(response.body.error.code).toBe(ErrorCode.VALIDATION_ERROR);
    });
  });

  describe('Params Validation', () => {
    it('should validate UUID params', async () => {
      const validUuid = '550e8400-e29b-41d4-a716-446655440000';
      
      const response = await request(app)
        .get(`/test/object-types/${validUuid}`)
        .expect(200);

      expect(response.body.validated).toBe(true);
      expect(response.body.id).toBe(validUuid);
    });

    it('should reject invalid UUID format', async () => {
      const response = await request(app)
        .get('/test/object-types/not-a-uuid')
        .expect(400);

      expect(response.body.error.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(response.body.error.details[0]).toContain('ID must be a valid UUID');
    });
  });

  describe('Type Inference Verification', () => {
    it('should demonstrate type-safe middleware chain', async () => {
      // Create a test endpoint that uses all three validations
      const testApp = express();
      testApp.use(express.json());

      testApp.put('/test/:id',
        validateParams(z.object({ id: z.string().uuid() })),
        validateQuery(z.object({ version: z.coerce.number().optional() })),
        validateBody(z.object({ name: z.string() })),
        (req, res) => {
          // At this point, TypeScript knows:
          // - req.params.id is a string (UUID)
          // - req.query.version is number | undefined
          // - req.body.name is a string
          
          res.json({
            id: req.params.id,
            version: req.query['version'],
            name: req.body.name,
          });
        }
      );

      const response = await request(testApp)
        .put('/test/550e8400-e29b-41d4-a716-446655440000')
        .query({ version: '2' })
        .send({ name: 'Updated' })
        .expect(200);

      expect(response.body).toEqual({
        id: '550e8400-e29b-41d4-a716-446655440000',
        version: 2,
        name: 'Updated',
      });
    });
  });

  describe('Complex Schema Validation', () => {
    it('should validate nested objects and arrays', async () => {
      const complexSchema = z.object({
        metadata: z.object({
          tags: z.array(z.string()).max(5),
          settings: z.object({
            enabled: z.boolean(),
            threshold: z.number().min(0).max(100),
          }),
        }),
      });

      const testApp = express();
      testApp.use(express.json());
      
      testApp.post('/test/complex',
        validateBody(complexSchema),
        (req, res) => res.json({ valid: true, data: req.body })
      );

      testApp.use((err: any, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
        res.status(400).json({ error: err.message });
      });

      const response = await request(testApp)
        .post('/test/complex')
        .send({
          metadata: {
            tags: ['tag1', 'tag2'],
            settings: {
              enabled: true,
              threshold: 75,
            },
          },
        })
        .expect(200);

      expect(response.body.valid).toBe(true);
      expect(response.body.data.metadata.settings.threshold).toBe(75);
    });
  });
});