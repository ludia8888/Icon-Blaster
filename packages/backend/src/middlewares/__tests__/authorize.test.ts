import { ErrorCode } from '@arrakis/contracts';
import { Request, Response, NextFunction } from 'express';

import { authorize } from '../authorize';

describe('Authorization Middleware', () => {
  let mockRequest: Partial<Request>;
  let mockResponse: Partial<Response>;
  let mockNext: NextFunction;

  beforeEach(() => {
    mockRequest = {};
    mockResponse = {};
    mockNext = jest.fn();
  });

  describe('Single role authorization', () => {
    it('should allow access when user has required role', () => {
      // Arrange
      mockRequest.user = {
        id: 'user-123',
        email: 'test@example.com',
        name: 'Test User',
        roles: ['admin', 'editor'],
      };

      const middleware = authorize('admin');

      // Act
      middleware(mockRequest as Request, mockResponse as Response, mockNext);

      // Assert
      expect(mockNext).toHaveBeenCalledWith();
    });

    it('should deny access when user lacks required role', () => {
      // Arrange
      mockRequest.user = {
        id: 'user-123',
        email: 'test@example.com',
        name: 'Test User',
        roles: ['user'],
      };

      const middleware = authorize('admin');

      // Act
      middleware(mockRequest as Request, mockResponse as Response, mockNext);

      // Assert
      expect(mockNext).toHaveBeenCalledWith(
        expect.objectContaining({
          statusCode: 403,
          code: ErrorCode.FORBIDDEN,
          message: 'Insufficient permissions',
        })
      );
    });
  });

  describe('Multiple roles authorization', () => {
    it('should allow access when user has at least one required role', () => {
      // Arrange
      mockRequest.user = {
        id: 'user-123',
        email: 'test@example.com',
        name: 'Test User',
        roles: ['editor'],
      };

      const middleware = authorize(['admin', 'editor']);

      // Act
      middleware(mockRequest as Request, mockResponse as Response, mockNext);

      // Assert
      expect(mockNext).toHaveBeenCalledWith();
    });

    it('should allow access when user has all required roles', () => {
      // Arrange
      mockRequest.user = {
        id: 'user-123',
        email: 'test@example.com',
        name: 'Test User',
        roles: ['admin', 'editor', 'viewer'],
      };

      const middleware = authorize(['admin', 'editor']);

      // Act
      middleware(mockRequest as Request, mockResponse as Response, mockNext);

      // Assert
      expect(mockNext).toHaveBeenCalledWith();
    });

    it('should deny access when user has none of required roles', () => {
      // Arrange
      mockRequest.user = {
        id: 'user-123',
        email: 'test@example.com',
        name: 'Test User',
        roles: ['viewer'],
      };

      const middleware = authorize(['admin', 'editor']);

      // Act
      middleware(mockRequest as Request, mockResponse as Response, mockNext);

      // Assert
      expect(mockNext).toHaveBeenCalledWith(
        expect.objectContaining({
          statusCode: 403,
          code: ErrorCode.FORBIDDEN,
          message: 'Insufficient permissions',
        })
      );
    });
  });

  describe('Edge cases', () => {
    it('should fail when user is not authenticated', () => {
      // Arrange
      const middleware = authorize('admin');

      // Act
      middleware(mockRequest as Request, mockResponse as Response, mockNext);

      // Assert
      expect(mockNext).toHaveBeenCalledWith(
        expect.objectContaining({
          statusCode: 401,
          code: ErrorCode.UNAUTHORIZED,
          message: 'Authentication required',
        })
      );
    });

    it('should handle empty roles array', () => {
      // Arrange
      mockRequest.user = {
        id: 'user-123',
        email: 'test@example.com',
        name: 'Test User',
        roles: [],
      };

      const middleware = authorize('admin');

      // Act
      middleware(mockRequest as Request, mockResponse as Response, mockNext);

      // Assert
      expect(mockNext).toHaveBeenCalledWith(
        expect.objectContaining({
          statusCode: 403,
          code: ErrorCode.FORBIDDEN,
        })
      );
    });

    it('should handle empty required roles array', () => {
      // Arrange
      mockRequest.user = {
        id: 'user-123',
        email: 'test@example.com',
        name: 'Test User',
        roles: ['admin'],
      };

      const middleware = authorize([]);

      // Act
      middleware(mockRequest as Request, mockResponse as Response, mockNext);

      // Assert
      expect(mockNext).toHaveBeenCalledWith();
    });

    it('should be case-sensitive for role matching', () => {
      // Arrange
      mockRequest.user = {
        id: 'user-123',
        email: 'test@example.com',
        name: 'Test User',
        roles: ['Admin'], // Capital A
      };

      const middleware = authorize('admin'); // lowercase

      // Act
      middleware(mockRequest as Request, mockResponse as Response, mockNext);

      // Assert
      expect(mockNext).toHaveBeenCalledWith(
        expect.objectContaining({
          statusCode: 403,
          code: ErrorCode.FORBIDDEN,
        })
      );
    });
  });
});
