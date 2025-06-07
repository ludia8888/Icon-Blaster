/**
 * Type Safety Improvements Test Suite
 * 
 * Verifies that our type-transforming middleware provides
 * compile-time and runtime type safety.
 */

import { Request, Response } from 'express';
import { z } from 'zod';

import {
  defineRoute,
  middlewareChain,
  validateBody,
  validateParams,
  validateQuery,
} from '../middlewares/type-transforming-middleware';

describe('Type Safety Improvements', () => {
  describe('defineRoute', () => {
    it('should provide full type inference for request handlers', () => {
      const UserSchema = z.object({
        name: z.string(),
        email: z.string().email(),
        age: z.number().min(0),
      });

      const ParamsSchema = z.object({
        id: z.string().uuid(),
      });

      const QuerySchema = z.object({
        includeDeleted: z.boolean().optional(),
      });

      const route = defineRoute({
        body: UserSchema,
        params: ParamsSchema,
        query: QuerySchema,
        handler: async (req, res) => {
          // Type assertions to verify inference
          const name: string = req.body.name;
          const email: string = req.body.email;
          const age: number = req.body.age;
          const id: string = req.params.id;
          const includeDeleted: boolean | undefined = req.query.includeDeleted;

          // This would cause a compile error:
          // const invalid: number = req.body.name; // Error: string is not assignable to number

          res.json({ name, email, age, id, includeDeleted });
        },
      });

      expect(route).toHaveLength(4); // 3 validation middlewares + handler
    });

    it('should handle optional validation schemas', () => {
      const route = defineRoute({
        body: z.object({ data: z.string() }),
        handler: async (req, res) => {
          const data: string = req.body.data;
          // req.params and req.query retain default Express types
          const anyParam: string = req.params.anyParam ?? '';
          const anyQuery: string = String(req.query.anyQuery ?? '');
          
          res.json({ data, anyParam, anyQuery });
        },
      });

      expect(route).toHaveLength(2); // 1 validation middleware + handler
    });
  });

  describe('middlewareChain', () => {
    it('should accumulate types through the chain', () => {
      const chain = middlewareChain()
        .use(validateBody(z.object({ name: z.string() })))
        .use(validateParams(z.object({ id: z.string().uuid() })))
        .use(validateQuery(z.object({ page: z.number().default(1) })))
        .build();

      const handlers = chain.handler(async (req, res) => {
        // All types are properly inferred
        const name: string = req.body.name;
        const id: string = req.params.id;
        const page: number = req.query.page;

        res.json({ name, id, page });
      });

      expect(handlers).toHaveLength(4); // 3 middlewares + handler
    });

    it('should maintain type safety with custom middleware', () => {
      interface CustomContext {
        userId: string;
        timestamp: Date;
      }

      const addContext = (req: Request, _res: Response, next: Function) => {
        (req as Request & { context: CustomContext }).context = {
          userId: 'user-123',
          timestamp: new Date(),
        };
        next();
      };

      const chain = middlewareChain()
        .use(validateBody(z.object({ data: z.string() })))
        .use(addContext as any) // Custom middleware
        .build();

      // While the chain doesn't track custom middleware types,
      // we can still use type assertions in the handler
      const handlers = chain.handler(async (req, res) => {
        const data: string = req.body.data;
        const context = (req as Request & { context: CustomContext }).context;
        
        res.json({ data, userId: context.userId });
      });

      expect(handlers).toHaveLength(3);
    });
  });

  describe('Individual validators', () => {
    it('validateBody should transform request body type', () => {
      const Schema = z.object({
        username: z.string().min(3),
        password: z.string().min(8),
      });

      const middleware = validateBody(Schema);
      
      // The middleware signature indicates type transformation
      const req = { body: { username: 'john', password: 'secret123' } } as Request;
      const res = {} as Response;
      const next = jest.fn();

      middleware(req, res, next);

      expect(next).toHaveBeenCalled();
      expect(req.body).toEqual({
        username: 'john',
        password: 'secret123',
      });
    });

    it('validateQuery should handle coercion', () => {
      const Schema = z.object({
        page: z.coerce.number().default(1),
        limit: z.coerce.number().default(10),
        active: z.coerce.boolean().optional(),
      });

      const middleware = validateQuery(Schema);
      
      const req = {
        query: { page: '2', limit: '20', active: 'true' },
      } as Request;
      const res = {} as Response;
      const next = jest.fn();

      middleware(req, res, next);

      expect(next).toHaveBeenCalled();
      expect(req.query).toEqual({
        page: 2,
        limit: 20,
        active: true,
      });
    });

    it('validateParams should validate route parameters', () => {
      const Schema = z.object({
        id: z.string().uuid(),
        version: z.coerce.number().optional(),
      });

      const middleware = validateParams(Schema);
      
      const req = {
        params: { id: '550e8400-e29b-41d4-a716-446655440000', version: '1' },
      } as Request;
      const res = {} as Response;
      const next = jest.fn();

      middleware(req, res, next);

      expect(next).toHaveBeenCalled();
      expect(req.params).toEqual({
        id: '550e8400-e29b-41d4-a716-446655440000',
        version: 1,
      });
    });
  });

  describe('Error handling', () => {
    it('should call next with ValidationError on invalid input', () => {
      const Schema = z.object({
        email: z.string().email(),
      });

      const middleware = validateBody(Schema);
      
      const req = { body: { email: 'not-an-email' } } as Request;
      const res = {} as Response;
      const next = jest.fn();

      middleware(req, res, next);

      expect(next).toHaveBeenCalledWith(expect.objectContaining({
        name: 'ValidationError',
      }));
    });
  });

  describe('Type safety comparison', () => {
    it('demonstrates improved type safety over basic Express', () => {
      // Basic Express - no compile-time safety
      const basicHandler = (req: Request, res: Response) => {
        const name = req.body.name; // any
        const id = req.params.id; // string
        const page = req.query.page; // string | ParsedQs | string[] | ParsedQs[]
        
        // No compile-time errors, but runtime errors possible
        const age: number = req.body.age; // Could be undefined or wrong type
        
        res.json({ name, id, page, age });
      };

      // Our type-safe approach
      const typeSafeRoute = defineRoute({
        body: z.object({
          name: z.string(),
          age: z.number(),
        }),
        params: z.object({
          id: z.string().uuid(),
        }),
        query: z.object({
          page: z.coerce.number().default(1),
        }),
        handler: async (req, res) => {
          const name: string = req.body.name; // Guaranteed string
          const age: number = req.body.age; // Guaranteed number
          const id: string = req.params.id; // Guaranteed UUID string
          const page: number = req.query.page; // Guaranteed number

          // This would cause compile error:
          // const invalid: string = req.body.age; // Error!
          
          res.json({ name, age, id, page });
        },
      });

      expect(basicHandler).toBeDefined();
      expect(typeSafeRoute).toBeDefined();
    });
  });
});

/**
 * Benefits demonstrated:
 * 
 * 1. Compile-time type safety
 *    - Request properties have correct types
 *    - Type errors caught during development
 * 
 * 2. Runtime validation
 *    - Zod schemas validate at runtime
 *    - Invalid requests rejected with proper errors
 * 
 * 3. Type transformation
 *    - String query params converted to numbers
 *    - Optional fields handled correctly
 * 
 * 4. Developer experience
 *    - IntelliSense shows available properties
 *    - Refactoring is safer
 */