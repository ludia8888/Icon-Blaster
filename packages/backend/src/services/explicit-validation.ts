/**
 * 명시적 검증 유틸리티
 *
 * 비즈니스 규칙을 명확하게 표현하고 검증
 */

import { z } from 'zod';

/**
 * 검증 규칙을 명시적으로 정의하는 빌더
 */
export class ValidationBuilder<T> {
  private rules: Array<{
    name: string;
    check: (value: T) => boolean;
    message: string;
  }> = [];

  /**
   * 검증 규칙 추가
   */
  addRule(name: string, check: (value: T) => boolean, message: string): this {
    this.rules.push({ name, check, message });
    return this;
  }

  /**
   * 모든 규칙 검증
   */
  validate(value: T): ValidationResult {
    const errors: ValidationError[] = [];

    for (const rule of this.rules) {
      if (!rule.check(value)) {
        errors.push({
          rule: rule.name,
          message: rule.message,
        });
      }
    }

    return {
      isValid: errors.length === 0,
      errors,
    };
  }
}

export interface ValidationResult {
  isValid: boolean;
  errors: ValidationError[];
}

export interface ValidationError {
  rule: string;
  message: string;
}

/**
 * ObjectType 비즈니스 규칙 검증
 */
export const ObjectTypeValidation = {
  /**
   * API 이름 규칙
   * - 소문자와 언더스코어만 허용
   * - 3자 이상 50자 이하
   * - 예약어 사용 불가
   */
  apiName: new ValidationBuilder<string>()
    .addRule(
      'format',
      (name) => /^[a-z][a-z0-9_]*$/.test(name),
      'API name must start with lowercase letter and contain only lowercase letters, numbers, and underscores'
    )
    .addRule(
      'length',
      (name) => name.length >= 3 && name.length <= 50,
      'API name must be between 3 and 50 characters'
    )
    .addRule(
      'reserved',
      (name) => !RESERVED_WORDS.includes(name),
      'API name cannot be a reserved word'
    ),

  /**
   * 표시 이름 규칙
   * - 비어있지 않음
   * - 100자 이하
   * - 특수문자 제한
   */
  displayName: new ValidationBuilder<string>()
    .addRule('notEmpty', (name) => name.trim().length > 0, 'Display name cannot be empty')
    .addRule('length', (name) => name.length <= 100, 'Display name must be 100 characters or less')
    .addRule(
      'validChars',
      (name) => /^[a-zA-Z0-9\s\-_()]+$/.test(name),
      'Display name can only contain letters, numbers, spaces, hyphens, underscores, and parentheses'
    ),

  /**
   * 그룹 검증
   * - 배열의 각 항목이 유효한 그룹 이름
   */
  groups: new ValidationBuilder<string[]>()
    .addRule(
      'validGroups',
      (groups) => groups.every((g) => /^[a-z][a-z0-9_]*$/.test(g)),
      'Each group must be a valid identifier'
    )
    .addRule(
      'uniqueGroups',
      (groups) => new Set(groups).size === groups.length,
      'Groups must be unique'
    ),
};

/**
 * 예약어 목록
 */
const RESERVED_WORDS = [
  'id',
  'type',
  'class',
  'function',
  'const',
  'let',
  'var',
  'return',
  'if',
  'else',
  'for',
  'while',
  'do',
  'switch',
  'case',
  'break',
  'continue',
  'throw',
  'try',
  'catch',
  'finally',
  'new',
  'this',
  'super',
  'extends',
  'static',
  'public',
  'private',
  'protected',
  'abstract',
  'interface',
  'enum',
  'namespace',
  'module',
  'declare',
  'as',
  'from',
  'import',
  'export',
  'default',
  'null',
  'undefined',
  'true',
  'false',
  'object',
  'string',
  'number',
  'boolean',
  'symbol',
  'any',
  'unknown',
  'never',
  'void',
];

/**
 * 상태 전이 규칙
 * 명시적으로 허용된 전이만 가능
 */
export const StateTransitions = {
  ObjectType: {
    draft: ['active', 'archived'],
    active: ['archived'],
    archived: ['active'],
  },

  canTransition(currentState: string, newState: string, entityType: 'ObjectType'): boolean {
    const transitions = this[entityType][currentState as keyof typeof this.ObjectType];
    return transitions?.includes(newState) ?? false;
  },

  getValidTransitions(currentState: string, entityType: 'ObjectType'): string[] {
    return this[entityType][currentState as keyof typeof this.ObjectType] ?? [];
  },
};

/**
 * 권한 검증 규칙
 * 명시적으로 각 작업에 필요한 권한 정의
 */
export const PermissionRules = {
  ObjectType: {
    create: ['admin', 'editor'],
    update: ['admin', 'editor'],
    delete: ['admin'],
    activate: ['admin', 'editor'],
    deactivate: ['admin', 'editor'],
    view: ['admin', 'editor', 'viewer'],
  },

  canPerform(action: keyof typeof this.ObjectType, userRoles: string[]): boolean {
    const requiredRoles = this.ObjectType[action];
    return userRoles.some((role) => requiredRoles.includes(role));
  },
};

/**
 * 데이터 무결성 검증
 */
export function validateDataIntegrity<T extends Record<string, unknown>>(
  data: T,
  schema: z.ZodSchema<T>
): { isValid: boolean; errors?: z.ZodError } {
  const result = schema.safeParse(data);

  if (result.success) {
    return { isValid: true };
  }

  return {
    isValid: false,
    errors: result.error,
  };
}

/**
 * 명시적 전제조건 검증
 *
 * @example
 * assertPrecondition(
 *   user.roles.includes('admin'),
 *   'User must have admin role'
 * );
 */
export function assertPrecondition(condition: boolean, message: string): asserts condition {
  if (!condition) {
    throw new Error(`Precondition failed: ${message}`);
  }
}

/**
 * 명시적 사후조건 검증
 *
 * @example
 * const result = await operation();
 * assertPostcondition(
 *   result.id !== undefined,
 *   'Operation must return an object with id'
 * );
 */
export function assertPostcondition(condition: boolean, message: string): asserts condition {
  if (!condition) {
    throw new Error(`Postcondition failed: ${message}`);
  }
}
