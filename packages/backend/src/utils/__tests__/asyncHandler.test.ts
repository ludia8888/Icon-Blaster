import { Request, Response, NextFunction } from 'express';
import { asyncHandler } from '../asyncHandler';

describe('asyncHandler with generic type support', () => {
  let mockNext: jest.MockedFunction<NextFunction>;
  
  beforeEach(() => {
    mockNext = jest.fn();
  });

  it('should preserve request and response types', () => {
    // Define typed request and response
    type TypedRequest = Request & { body: { name: string; age: number } };
    type TypedResponse = Response<{ success: boolean; message: string }>;
    
    // Create handler with specific types
    const handler = asyncHandler<TypedRequest, TypedResponse>(
      async (req, res) => {
        // TypeScript should know these types
        const name: string = req.body.name;
        const age: number = req.body.age;
        
        res.json({ 
          success: true, 
          message: `Hello ${name}, you are ${age} years old` 
        });
      }
    );
    
    // Verify handler is created
    expect(handler).toBeDefined();
    expect(typeof handler).toBe('function');
  });

  it('should catch and forward async errors', async () => {
    const error = new Error('Test error');
    
    const handler = asyncHandler(async () => {
      throw error;
    });
    
    const mockReq = {} as Request;
    const mockRes = {} as Response;
    
    // Call handler - should not throw
    handler(mockReq, mockRes, mockNext);
    
    // Wait for async operation
    await new Promise(resolve => setImmediate(resolve));
    
    // Verify error was passed to next
    expect(mockNext).toHaveBeenCalledWith(error);
  });

  it('should handle synchronous handlers', () => {
    const mockRes = {
      json: jest.fn()
    } as unknown as Response;
    
    const handler = asyncHandler((_req, res) => {
      res.json({ sync: true });
    });
    
    handler({} as Request, mockRes, mockNext);
    
    expect(mockRes.json).toHaveBeenCalledWith({ sync: true });
    expect(mockNext).not.toHaveBeenCalled();
  });

  it('should work with ValidatedRequest from safe-handler', () => {
    // Import types from safe-handler
    type ValidatedRequest = Request & {
      body: { email: string };
      params: { id: string };
      query: { limit: number };
    };
    
    const handler = asyncHandler<ValidatedRequest>(
      async (req, res) => {
        // All these should be type-safe
        const email: string = req.body.email;
        const id: string = req.params.id;
        const limit: number = req.query.limit;
        
        res.json({ email, id, limit });
      }
    );
    
    expect(handler).toBeDefined();
  });

  it('should maintain compatibility with existing non-generic usage', () => {
    // Old style should still work
    const handler = asyncHandler(async (_req: Request, res: Response) => {
      res.json({ legacy: true });
    });
    
    expect(handler).toBeDefined();
  });
});