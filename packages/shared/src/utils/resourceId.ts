import { randomUUID } from 'crypto';

/**
 * UUID v4 정규식 패턴
 */
const UUID_V4_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

/**
 * 새로운 리소스 ID (UUID v4) 생성
 */
export function generateResourceId(): string {
  return randomUUID();
}

/**
 * 리소스 ID 유효성 검증
 */
export function isValidResourceId(id: unknown): boolean {
  if (typeof id !== 'string') {
    return false;
  }
  return UUID_V4_REGEX.test(id);
}

/**
 * 리소스 ID 파싱 결과
 */
interface ParseResult {
  valid: boolean;
  id: string | null;
  error: string | null;
}

/**
 * 리소스 ID 파싱 및 검증
 */
export function parseResourceId(id: string): ParseResult {
  if (isValidResourceId(id)) {
    return {
      valid: true,
      id,
      error: null,
    };
  }

  return {
    valid: false,
    id: null,
    error: 'Invalid resource ID format',
  };
}
