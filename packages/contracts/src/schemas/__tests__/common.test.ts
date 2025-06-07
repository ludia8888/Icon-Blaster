import {
  ErrorResponseSchema,
  PaginationSchema,
  QueryParamsSchema,
  createErrorResponse,
  createSuccessResponse,
  ErrorCode,
} from '../common';

describe('Common Schemas', () => {
  describe('ErrorResponseSchema', () => {
    it('should validate error response', () => {
      // Arrange
      const errorData = {
        error: {
          code: 'VALIDATION_ERROR',
          message: 'Invalid input data',
          details: ['Field apiName is required'],
        },
        timestamp: '2024-01-01T00:00:00Z',
        path: '/api/object-type',
        requestId: '123e4567-e89b-12d3-a456-426614174000',
      };

      // Act
      const result = ErrorResponseSchema.safeParse(errorData);

      // Assert
      expect(result.success).toBe(true);
    });

    it('should allow error without details', () => {
      // Arrange
      const errorData = {
        error: {
          code: 'NOT_FOUND',
          message: 'Resource not found',
        },
        timestamp: '2024-01-01T00:00:00Z',
        path: '/api/object-type/123',
        requestId: '123e4567-e89b-12d3-a456-426614174000',
      };

      // Act
      const result = ErrorResponseSchema.safeParse(errorData);

      // Assert
      expect(result.success).toBe(true);
    });
  });

  describe('PaginationSchema', () => {
    it('should validate pagination params', () => {
      // Arrange
      const paginationData = {
        page: 1,
        limit: 20,
        sortBy: 'createdAt',
        sortOrder: 'desc' as const,
      };

      // Act
      const result = PaginationSchema.safeParse(paginationData);

      // Assert
      expect(result.success).toBe(true);
    });

    it('should apply default values', () => {
      // Arrange
      const emptyData = {};

      // Act
      const result = PaginationSchema.safeParse(emptyData);

      // Assert
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.page).toBe(1);
        expect(result.data.limit).toBe(20);
        expect(result.data.sortOrder).toBe('asc');
      }
    });

    it('should enforce max limit', () => {
      // Arrange
      const data = {
        limit: 200,
      };

      // Act
      const result = PaginationSchema.safeParse(data);

      // Assert
      expect(result.success).toBe(false);
    });
  });

  describe('QueryParamsSchema', () => {
    it('should validate search query params', () => {
      // Arrange
      const queryData = {
        q: 'employee',
        page: 2,
        limit: 10,
        sortBy: 'displayName',
        sortOrder: 'asc' as const,
        status: 'active',
        visibility: 'normal',
      };

      // Act
      const result = QueryParamsSchema.safeParse(queryData);

      // Assert
      expect(result.success).toBe(true);
    });
  });

  describe('ErrorCode enum', () => {
    it('should have correct error codes', () => {
      expect(ErrorCode.VALIDATION_ERROR).toBe('VALIDATION_ERROR');
      expect(ErrorCode.NOT_FOUND).toBe('NOT_FOUND');
      expect(ErrorCode.CONFLICT).toBe('CONFLICT');
      expect(ErrorCode.UNAUTHORIZED).toBe('UNAUTHORIZED');
      expect(ErrorCode.FORBIDDEN).toBe('FORBIDDEN');
      expect(ErrorCode.INTERNAL_ERROR).toBe('INTERNAL_ERROR');
      expect(ErrorCode.BAD_REQUEST).toBe('BAD_REQUEST');
    });
  });

  describe('Helper functions', () => {
    it('should create error response', () => {
      // Act
      const response = createErrorResponse({
        code: ErrorCode.VALIDATION_ERROR,
        message: 'Invalid input',
        details: ['Field is required'],
        path: '/api/test',
        requestId: '123',
      });

      // Assert
      expect(response.error.code).toBe(ErrorCode.VALIDATION_ERROR);
      expect(response.timestamp).toBeDefined();
    });

    it('should create success response', () => {
      // Arrange
      const data = { id: 1, name: 'Test' };

      // Act
      const response = createSuccessResponse(data);

      // Assert
      expect(response.success).toBe(true);
      expect(response.data).toEqual(data);
    });
  });
});
