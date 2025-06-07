import { Request, Response, NextFunction } from 'express';

/**
 * Create a mock request object for testing
 */
export function createMockRequest(overrides: Partial<Request> = {}): Partial<Request> {
  return {
    body: {},
    query: {},
    params: {},
    headers: {},
    ...overrides,
  };
}

/**
 * Create a mock response object for testing
 */
export function createMockResponse(): Partial<Response> {
  return {};
}

/**
 * Create a mock NextFunction
 */
export function createMockNext(): jest.Mock<NextFunction> {
  return jest.fn() as unknown as jest.Mock<NextFunction>;
}

/**
 * Type assertion helper for mock NextFunction
 */
export function getMockNextError(mockNext: NextFunction): Error | undefined {
  const fn = mockNext as unknown as jest.Mock<void, [Error?]>;
  const calls = fn.mock.calls;
  if (calls.length > 0) {
    const firstCall = calls[0];
    if (firstCall && firstCall.length > 0) {
      return firstCall[0];
    }
  }
  return undefined;
}