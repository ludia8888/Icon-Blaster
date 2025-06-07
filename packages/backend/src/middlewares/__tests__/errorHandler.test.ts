import { ErrorCode } from '@arrakis/contracts';
import { Request, Response, NextFunction } from 'express';

import { errorHandler, AppError } from '../errorHandler';

describe('Error Handler Middleware', () => {
  let mockRequest: Partial<Request>;
  let mockResponse: Partial<Response>;
  let mockNext: NextFunction;

  beforeEach(() => {
    mockRequest = {
      path: '/test',
      id: 'test-request-id',
    };
    mockResponse = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn(),
    };
    mockNext = jest.fn();
  });

  it('should handle AppError correctly', () => {
    // Arrange
    const error = new AppError('Test error', 400, ErrorCode.BAD_REQUEST, ['Detail 1', 'Detail 2']);

    // Act
    errorHandler(error, mockRequest as Request, mockResponse as Response, mockNext);

    // Assert
    expect(mockResponse.status).toHaveBeenCalledWith(400);
    expect(mockResponse.json).toHaveBeenCalledWith(
      expect.objectContaining({
        error: {
          code: ErrorCode.BAD_REQUEST,
          message: 'Test error',
          details: ['Detail 1', 'Detail 2'],
        },
      })
    );
  });

  it('should handle JSON syntax error', () => {
    // Arrange
    const error = new SyntaxError('Unexpected token');
    const syntaxError = error as SyntaxError & { body: boolean };
    syntaxError.body = true;

    // Act
    errorHandler(error, mockRequest as Request, mockResponse as Response, mockNext);

    // Assert
    expect(mockResponse.status).toHaveBeenCalledWith(400);
    expect(mockResponse.json).toHaveBeenCalledWith(
      expect.objectContaining({
        error: {
          code: ErrorCode.BAD_REQUEST,
          message: 'Invalid JSON payload',
        },
      })
    );
  });

  it('should handle generic errors', () => {
    // Arrange
    const error = new Error('Something went wrong');

    // Act
    errorHandler(error, mockRequest as Request, mockResponse as Response, mockNext);

    // Assert
    expect(mockResponse.status).toHaveBeenCalledWith(500);
    expect(mockResponse.json).toHaveBeenCalledWith(
      expect.objectContaining({
        error: {
          code: ErrorCode.INTERNAL_ERROR,
          message: 'Internal server error',
        },
      })
    );
  });

  it('should log errors in non-test environment', () => {
    // Arrange
    const originalEnv = process.env['NODE_ENV'];
    process.env['NODE_ENV'] = 'development';
    const consoleSpy = jest.spyOn(console, 'error').mockImplementation();
    const error = new Error('Test error');

    // Act
    errorHandler(error, mockRequest as Request, mockResponse as Response, mockNext);

    // Assert
    expect(consoleSpy).toHaveBeenCalledWith('Error:', error);

    // Cleanup
    consoleSpy.mockRestore();
    process.env['NODE_ENV'] = originalEnv;
  });
});
