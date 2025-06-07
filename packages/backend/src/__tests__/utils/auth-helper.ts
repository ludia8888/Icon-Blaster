/**
 * 테스트용 인증 헬퍼
 *
 * 명시적으로 테스트 토큰을 생성하는 유틸리티
 */

import jwt from 'jsonwebtoken';
import { JwtPayload } from '../../auth/types';

/**
 * 테스트용 JWT 토큰 생성
 * @param payload 사용자 정보
 * @returns JWT 토큰 문자열
 */
export function generateTestToken(
  payload: Partial<JwtPayload> & { sub: string; email: string; roles: string[] }
): string {
  const secret = process.env['JWT_SECRET'] || 'test-secret';

  const fullPayload: JwtPayload = {
    sub: payload.sub,
    email: payload.email,
    name: payload.name || 'Test User',
    roles: payload.roles,
  };

  return jwt.sign(fullPayload, secret, {
    expiresIn: '1h',
    issuer: 'arrakis-backend',
  });
}

/**
 * 다양한 권한의 테스트 사용자
 */
export const testUsers = {
  admin: {
    sub: 'admin-user',
    email: 'admin@test.com',
    name: 'Admin User',
    roles: ['admin'] as const,
  },
  editor: {
    sub: 'editor-user',
    email: 'editor@test.com',
    name: 'Editor User',
    roles: ['editor'] as const,
  },
  viewer: {
    sub: 'viewer-user',
    email: 'viewer@test.com',
    name: 'Viewer User',
    roles: ['viewer'] as const,
  },
  multiRole: {
    sub: 'multi-user',
    email: 'multi@test.com',
    name: 'Multi Role User',
    roles: ['editor', 'viewer'] as const,
  },
} as const;

/**
 * 특정 역할의 토큰을 빠르게 생성
 */
export function getTokenForRole(role: 'admin' | 'editor' | 'viewer'): string {
  const user = testUsers[role];
  return generateTestToken({
    sub: user.sub,
    email: user.email,
    name: user.name,
    roles: [...user.roles], // Convert readonly array to mutable
  });
}
