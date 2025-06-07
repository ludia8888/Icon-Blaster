import { ErrorCode } from '@arrakis/contracts';
import { Request, Response, NextFunction } from 'express';

import { generateToken } from '../../auth/jwt';
import { JwtPayload } from '../../auth/types';
import { authenticate } from '../auth';

describe('Authentication Middleware', () => {
  let mockRequest: Partial<Request>;
  let mockResponse: Partial<Response>;
  let mockNext: NextFunction;

  const mockSecret = process.env['JWT_SECRET'] ?? 'test-secret';
  const mockPayload: JwtPayload = {
    sub: 'user-123',
    email: 'test@example.com',
    name: 'Test User',
    roles: ['user'],
  };

  beforeEach(() => {
    mockRequest = {
      headers: {},
    };
    mockResponse = {};
    mockNext = jest.fn();
    // Set test JWT secret
    process.env['JWT_SECRET'] = mockSecret;
  });

  afterEach(() => {
    delete process.env['JWT_SECRET'];
  });

  it('should authenticate with valid Bearer token', () => {
    // Arrange
    const token = generateToken(mockPayload, mockSecret);
    mockRequest.headers = {
      authorization: `Bearer ${token}`,
    };

    // Act
    authenticate(mockRequest as Request, mockResponse as Response, mockNext);

    // Assert
    expect(mockNext).toHaveBeenCalledWith();
    expect(mockRequest.user).toBeDefined();
    expect(mockRequest.user?.id).toBe(mockPayload.sub);
    expect(mockRequest.user?.email).toBe(mockPayload.email);
    expect(mockRequest.user?.name).toBe(mockPayload.name);
    expect(mockRequest.user?.roles).toEqual(mockPayload.roles);
  });

  it('should fail when Authorization header is missing', () => {
    // Act
    authenticate(mockRequest as Request, mockResponse as Response, mockNext);

    // Assert
    expect(mockNext).toHaveBeenCalledWith(
      expect.objectContaining({
        statusCode: 401,
        code: ErrorCode.UNAUTHORIZED,
        message: 'No authorization header provided',
      })
    );
    expect(mockRequest.user).toBeUndefined();
  });

  it('should fail when Bearer token is missing', () => {
    // Arrange
    mockRequest.headers = {
      authorization: 'NotBearer token',
    };

    // Act
    authenticate(mockRequest as Request, mockResponse as Response, mockNext);

    // Assert
    expect(mockNext).toHaveBeenCalledWith(
      expect.objectContaining({
        statusCode: 401,
        code: ErrorCode.UNAUTHORIZED,
        message: 'Invalid authorization header format',
      })
    );
  });

  it('should fail with invalid token', () => {
    // Arrange
    mockRequest.headers = {
      authorization: 'Bearer invalid.token.here',
    };

    // Act
    authenticate(mockRequest as Request, mockResponse as Response, mockNext);

    // Assert
    expect(mockNext).toHaveBeenCalledWith(
      expect.objectContaining({
        statusCode: 401,
        code: ErrorCode.UNAUTHORIZED,
        message: 'Invalid token',
      })
    );
  });

  it('should fail with expired token', () => {
    // Arrange
    const expiredToken = generateToken(mockPayload, mockSecret, '-1s');
    mockRequest.headers = {
      authorization: `Bearer ${expiredToken}`,
    };

    // Act
    authenticate(mockRequest as Request, mockResponse as Response, mockNext);

    // Assert
    expect(mockNext).toHaveBeenCalledWith(
      expect.objectContaining({
        statusCode: 401,
        code: ErrorCode.UNAUTHORIZED,
        message: 'Invalid token',
      })
    );
  });

  it('should fail with wrong secret', () => {
    // Arrange
    const token = generateToken(mockPayload, 'wrong-secret');
    mockRequest.headers = {
      authorization: `Bearer ${token}`,
    };

    // Act
    authenticate(mockRequest as Request, mockResponse as Response, mockNext);

    // Assert
    expect(mockNext).toHaveBeenCalledWith(
      expect.objectContaining({
        statusCode: 401,
        code: ErrorCode.UNAUTHORIZED,
        message: 'Invalid token',
      })
    );
  });

  it('should fail when JWT_SECRET is not configured', () => {
    // Arrange
    delete process.env['JWT_SECRET'];
    const token = generateToken(mockPayload, mockSecret);
    mockRequest.headers = {
      authorization: `Bearer ${token}`,
    };

    // Act
    authenticate(mockRequest as Request, mockResponse as Response, mockNext);

    // Assert
    expect(mockNext).toHaveBeenCalledWith(
      expect.objectContaining({
        message: 'JWT secret not configured',
      })
    );
  });

  it('should handle malformed JWT payload', () => {
    // Arrange
    // Create a token with incomplete payload
    const incompletePayload = { sub: 'user-123' };
    const token = generateToken(incompletePayload, mockSecret);
    mockRequest.headers = {
      authorization: `Bearer ${token}`,
    };

    // Act
    authenticate(mockRequest as Request, mockResponse as Response, mockNext);

    // Assert
    expect(mockNext).toHaveBeenCalledWith(
      expect.objectContaining({
        statusCode: 401,
        code: ErrorCode.UNAUTHORIZED,
        message: 'Invalid token payload',
      })
    );
  });
});
