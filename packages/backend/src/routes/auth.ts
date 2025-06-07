import { Router, Request, Response } from 'express';

import { getJwtConfig } from '../auth/config';
import { generateToken } from '../auth/jwt';
import { JwtPayload } from '../auth/types';

const router = Router();

/**
 * Generate mock token response
 */
function generateMockTokenResponse(
  userData: Partial<{
    userId: string;
    email: string;
    name: string;
    roles: string[];
  }>
): {
  token: string;
  expiresIn: string;
  user: { id: string; email: string; name: string; roles: string[] };
} {
  const jwtConfig = getJwtConfig();
  const {
    userId = 'mock-user-123',
    email = 'mock@example.com',
    name = 'Mock User',
    roles = ['user'],
  } = userData;

  const payload: JwtPayload = { sub: userId, email, name, roles };
  const token = generateToken(payload, jwtConfig.secret, jwtConfig.expiresIn);

  return {
    token,
    expiresIn: jwtConfig.expiresIn,
    user: { id: userId, email, name, roles },
  };
}

/**
 * Mock token generation endpoint (development only)
 * POST /auth/mock-token
 */
router.post('/mock-token', (req: Request, res: Response): void => {
  try {
    if (process.env['NODE_ENV'] === 'production') {
      res.status(404).json({ error: { message: 'Not found' } });
      return;
    }

    const response = generateMockTokenResponse(
      req.body as Partial<{
        userId: string;
        email: string;
        name: string;
        roles: string[];
      }>
    );
    res.json(response);
  } catch (error) {
    res.status(500).json({
      error: {
        message: error instanceof Error ? error.message : 'Failed to generate token',
      },
    });
  }
});

export { router as authRouter };
