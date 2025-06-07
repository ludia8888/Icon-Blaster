import * as authExports from '../index';

describe('Auth module exports', () => {
  it('should export JWT functions', () => {
    // Assert
    expect(authExports).toHaveProperty('generateToken');
    expect(authExports).toHaveProperty('verifyToken');
    expect(authExports).toHaveProperty('decodeToken');
    expect(authExports).toHaveProperty('extractBearerToken');
    expect(authExports).toHaveProperty('isTokenExpired');
  });

  it('should export config functions', () => {
    // Assert
    expect(authExports).toHaveProperty('getJwtConfig');
    expect(authExports).toHaveProperty('validateJwtConfig');
  });

  it('should export types', () => {
    // Note: TypeScript interfaces are not available at runtime
    // This test just ensures the module loads correctly
    expect(authExports).toBeDefined();
  });
});
