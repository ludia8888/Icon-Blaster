import { ErrorCode } from '@arrakis/contracts';
import { Request, Response } from 'express';
import { z } from 'zod';

import { ValidationError } from '../../errors/ValidationError';
import { validateBody, validateQuery, validateParams } from '../validate';

import {
  createMockRequest,
  createMockResponse,
  createMockNext,
  getMockNextError,
} from './test-utils';

describe('Validation Middleware', () => {
  let mockRequest: Partial<Request>;
  let mockResponse: Partial<Response>;
  let mockNext: ReturnType<typeof createMockNext>;

  beforeEach(() => {
    mockRequest = createMockRequest();
    mockResponse = createMockResponse();
    mockNext = createMockNext();
  });

  describe('validateBody', () => {
    const testSchema = z.object({
      name: z.string().min(1),
      age: z.number().positive(),
      email: z.string().email().optional(),
    });

    it('should pass valid data and replace body with parsed data', () => {
      // Arrange
      mockRequest.body = {
        name: 'John Doe',
        age: 30,
        email: 'john@example.com',
      };

      // Act
      const middleware = validateBody(testSchema);
      middleware(mockRequest as Request, mockResponse as Response, mockNext);

      // Assert
      expect(mockNext).toHaveBeenCalledWith();
      expect(mockRequest.body).toEqual({
        name: 'John Doe',
        age: 30,
        email: 'john@example.com',
      });
    });

    it('should reject invalid data with 400 error', () => {
      // Arrange
      mockRequest.body = {
        name: '',
        age: -5,
        email: 'invalid-email',
      };

      // Act
      const middleware = validateBody(testSchema);
      middleware(mockRequest as Request, mockResponse as Response, mockNext);

      // Assert
      expect(mockNext).toHaveBeenCalledWith(expect.any(ValidationError));
      const error = getMockNextError(mockNext) as ValidationError;
      expect(error).toBeInstanceOf(ValidationError);
      expect(error.statusCode).toBe(400);
      expect(error.code).toBe(ErrorCode.VALIDATION_ERROR);
    });

    it('should provide detailed error messages', () => {
      // Arrange
      mockRequest.body = {
        age: 'not-a-number',
      };

      // Act
      const middleware = validateBody(testSchema);
      middleware(mockRequest as Request, mockResponse as Response, mockNext);

      // Assert
      expect(mockNext).toHaveBeenCalledWith(expect.any(ValidationError));
      const error = getMockNextError(mockNext) as ValidationError;
      expect(error).toBeInstanceOf(ValidationError);
      expect(error.validationDetails).toContainEqual(
        expect.objectContaining({
          path: 'name',
          message: expect.any(String) as string,
        })
      );
      expect(error.validationDetails).toContainEqual(
        expect.objectContaining({
          path: 'age',
          message: expect.any(String) as string,
        })
      );
    });

    it('should handle nested object validation', () => {
      // Arrange
      const nestedSchema = z.object({
        user: z.object({
          name: z.string(),
          profile: z.object({
            bio: z.string(),
            age: z.number(),
          }),
        }),
      });

      mockRequest.body = {
        user: {
          name: 'John',
          profile: {
            bio: '',
            age: 'invalid',
          },
        },
      };

      // Act
      const middleware = validateBody(nestedSchema);
      middleware(mockRequest as Request, mockResponse as Response, mockNext);

      // Assert
      expect(mockNext).toHaveBeenCalledWith(expect.any(ValidationError));
      const error = getMockNextError(mockNext) as ValidationError;
      expect(error).toBeInstanceOf(ValidationError);
      expect(error.validationDetails).toContainEqual(
        expect.objectContaining({
          path: 'user.profile.age',
          message: expect.any(String) as string,
        })
      );
    });

    it('should coerce string numbers to numbers when possible', () => {
      // Arrange
      const coerceSchema = z.object({
        age: z.coerce.number(),
        active: z.coerce.boolean(),
      });

      mockRequest.body = {
        age: '25',
        active: 'true',
      };

      // Act
      const middleware = validateBody(coerceSchema);
      middleware(mockRequest as Request, mockResponse as Response, mockNext);

      // Assert
      expect(mockNext).toHaveBeenCalledWith();
      expect(mockRequest.body).toEqual({
        age: 25,
        active: true,
      });
    });
  });

  describe('validateQuery', () => {
    const querySchema = z.object({
      page: z.coerce.number().positive().default(1),
      limit: z.coerce.number().positive().max(100).default(10),
      search: z.string().optional(),
    });

    it('should validate query parameters', () => {
      // Arrange
      mockRequest.query = {
        page: '2',
        limit: '20',
        search: 'test',
      };

      // Act
      const middleware = validateQuery(querySchema);
      middleware(mockRequest as Request, mockResponse as Response, mockNext);

      // Assert
      expect(mockNext).toHaveBeenCalledWith();
      expect(mockRequest.query).toEqual({
        page: 2,
        limit: 20,
        search: 'test',
      });
    });

    it('should apply defaults for missing query params', () => {
      // Arrange
      mockRequest.query = {};

      // Act
      const middleware = validateQuery(querySchema);
      middleware(mockRequest as Request, mockResponse as Response, mockNext);

      // Assert
      expect(mockNext).toHaveBeenCalledWith();
      expect(mockRequest.query).toEqual({
        page: 1,
        limit: 10,
      });
    });

    it('should reject invalid query parameters', () => {
      // Arrange
      mockRequest.query = {
        page: '-1',
        limit: '200',
      };

      // Act
      const middleware = validateQuery(querySchema);
      middleware(mockRequest as Request, mockResponse as Response, mockNext);

      // Assert
      expect(mockNext).toHaveBeenCalledWith(expect.any(ValidationError));
    });
  });

  describe('validateParams', () => {
    const paramsSchema = z.object({
      id: z.string().uuid(),
      slug: z.string().regex(/^[a-z0-9-]+$/),
    });

    it('should validate path parameters', () => {
      // Arrange
      mockRequest.params = {
        id: '550e8400-e29b-41d4-a716-446655440000',
        slug: 'test-slug',
      };

      // Act
      const middleware = validateParams(paramsSchema);
      middleware(mockRequest as Request, mockResponse as Response, mockNext);

      // Assert
      expect(mockNext).toHaveBeenCalledWith();
      expect(mockRequest.params).toEqual({
        id: '550e8400-e29b-41d4-a716-446655440000',
        slug: 'test-slug',
      });
    });

    it('should reject invalid path parameters', () => {
      // Arrange
      mockRequest.params = {
        id: 'not-a-uuid',
        slug: 'Invalid Slug!',
      };

      // Act
      const middleware = validateParams(paramsSchema);
      middleware(mockRequest as Request, mockResponse as Response, mockNext);

      // Assert
      expect(mockNext).toHaveBeenCalledWith(expect.any(ValidationError));
      const error = getMockNextError(mockNext) as ValidationError;
      expect(error).toBeInstanceOf(ValidationError);
      expect(error.validationDetails).toHaveLength(2);
    });
  });
});
