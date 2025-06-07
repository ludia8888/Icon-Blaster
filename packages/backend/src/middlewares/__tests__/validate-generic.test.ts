import { Request, Response, NextFunction } from 'express';
import { z } from 'zod';
import { 
  validateBody, 
  validateParams, 
  createValidation 
} from '../validate-generic';

describe('Generic Validation Middleware', () => {
  let mockReq: Request;
  let mockRes: Response;
  let mockNext: NextFunction;

  beforeEach(() => {
    mockReq = {
      body: {},
      query: {},
      params: {}
    } as Request;
    
    mockRes = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn()
    } as unknown as Response;
    
    mockNext = jest.fn();
  });

  describe('validateBody with generics', () => {
    it('should transform request type after validation', () => {
      const schema = z.object({
        name: z.string(),
        age: z.number()
      });
      
      // Test type transformation - this compiles without errors
      // which proves the generic types are working correctly
      const middleware = validateBody(schema);
      
      // Setup valid data
      mockReq.body = { name: 'John', age: 30 };
      
      // Execute middleware
      middleware(mockReq, mockRes, mockNext);
      
      // Verify transformation
      expect(mockNext).toHaveBeenCalledWith();
      expect(mockReq.body).toEqual({ name: 'John', age: 30 });
    });
  });

  describe('createValidation builder', () => {
    it('should create combined validation with proper types', () => {
      const validation = createValidation({
        body: z.object({
          title: z.string(),
          content: z.string()
        }),
        params: z.object({
          id: z.string().uuid()
        }),
        query: z.object({
          includeDeleted: z.boolean().optional()
        })
      });
      
      // Verify middleware array is created
      expect(validation.middleware).toHaveLength(3);
      
      // Test handler type inference
      const handler = validation.handler(async (req, res) => {
        // These should have proper types
        const title: string = req.body.title;
        const content: string = req.body.content;
        const id: string = req.params.id;
        const includeDeleted: boolean | undefined = req.query.includeDeleted;
        
        res.json({ 
          id, 
          title, 
          content, 
          includeDeleted 
        });
      });
      
      expect(handler).toBeDefined();
      expect(typeof handler).toBe('function');
    });

    it('should work with partial validation config', () => {
      // Only body validation
      const bodyOnly = createValidation({
        body: z.object({ name: z.string() })
      });
      
      expect(bodyOnly.middleware).toHaveLength(1);
      
      // Only params validation
      const paramsOnly = createValidation({
        params: z.object({ id: z.string() })
      });
      
      expect(paramsOnly.middleware).toHaveLength(1);
    });
  });

  describe('Type preservation through middleware chain', () => {
    it('should maintain types when chaining middlewares', () => {
      const bodySchema = z.object({ name: z.string() });
      const paramsSchema = z.object({ id: z.string() });
      
      // Create middlewares
      const validateBodyMw = validateBody(bodySchema);
      const validateParamsMw = validateParams(paramsSchema);
      
      // Simulate middleware chain
      mockReq.body = { name: 'Test' };
      mockReq.params = { id: '123' };
      
      // Execute first middleware
      validateBodyMw(mockReq, mockRes, mockNext);
      expect(mockNext).toHaveBeenCalled();
      
      // Reset mock
      (mockNext as jest.Mock).mockClear();
      
      // Execute second middleware
      validateParamsMw(mockReq, mockRes, mockNext);
      expect(mockNext).toHaveBeenCalled();
      
      // Verify both transformations applied
      expect(mockReq.body).toEqual({ name: 'Test' });
      expect(mockReq.params).toEqual({ id: '123' });
    });
  });

  describe('Error handling with proper types', () => {
    it('should call next with ValidationError on invalid data', () => {
      const schema = z.object({
        email: z.string().email()
      });
      
      const middleware = validateBody(schema);
      
      mockReq.body = { email: 'invalid-email' };
      
      middleware(mockReq, mockRes, mockNext);
      
      expect(mockNext).toHaveBeenCalledWith(
        expect.any(Error)
      );
      
      const error = (mockNext as jest.Mock).mock.calls[0][0];
      expect(error.message).toContain('Validation failed');
      expect(error.statusCode).toBe(400);
    });
  });
});