/**
 * 명시적 에러 처리 유틸리티
 * 
 * 원칙:
 * 1. 모든 에러는 구체적인 타입과 메시지를 가짐
 * 2. 에러 발생 지점을 추적 가능하게 함
 * 3. 복구 가능한 에러와 치명적 에러를 구분
 */

import { AppError, ErrorCode } from '../errors/AppError';

import { logger } from './logger';

/**
 * 에러 발생 맥락 정보
 */
export interface ErrorContext {
  operation: string;      // 어떤 작업 중이었는지
  entity?: string;       // 어떤 엔티티와 관련있는지
  userId?: string;       // 누가 작업했는지
  data?: Record<string, unknown>; // 관련 데이터
}

/**
 * AppError 로깅
 */
function logAppError(error: AppError, context: ErrorContext): void {
  logger.error('Known error occurred', {
    ...context,
    error: {
      message: error.message,
      code: error.code,
      statusCode: error.statusCode
    }
  });
}

/**
 * 일반 에러 로깅
 */
function logGenericError(error: Error, context: ErrorContext): void {
  logger.error('Unexpected error occurred', {
    ...context,
    error: {
      message: error.message,
      stack: error.stack
    }
  });
}

/**
 * 명시적 에러 처리기
 * 에러를 적절한 AppError로 변환하고 로깅
 */
export function handleError(
  error: unknown,
  context: ErrorContext
): AppError {
  // 이미 AppError인 경우
  if (error instanceof AppError) {
    logAppError(error, context);
    return error;
  }

  // TypeORM 에러 처리
  if (isTypeORMError(error)) {
    return handleDatabaseError(error, context);
  }

  // 일반 Error
  if (error instanceof Error) {
    logGenericError(error, context);
    return new AppError(
      `${context.operation} failed: ${error.message}`,
      500,
      ErrorCode.INTERNAL_ERROR
    );
  }

  // 알 수 없는 에러
  logger.error('Unknown error type', { ...context, error });
  return new AppError(
    `${context.operation} failed with unknown error`,
    500,
    ErrorCode.INTERNAL_ERROR
  );
}

/**
 * TypeORM 에러인지 확인
 */
function isTypeORMError(error: unknown): error is Error {
  return error instanceof Error && 
    (error.constructor.name.includes('QueryFailedError') ||
     error.constructor.name.includes('EntityNotFoundError'));
}

/**
 * Unique constraint 에러 처리
 */
function handleUniqueConstraintError(message: string, context: ErrorContext): AppError {
  const field = extractFieldFromError(message);
  return new AppError(
    `${context.entity ?? 'Resource'} with this ${field} already exists`,
    409,
    ErrorCode.CONFLICT
  );
}

/**
 * Foreign key constraint 에러 처리
 */
function handleForeignKeyError(): AppError {
  return new AppError(
    'Related resource not found or cannot be deleted due to existing references',
    400,
    ErrorCode.VALIDATION_ERROR
  );
}

/**
 * Not null constraint 에러 처리
 */
function handleNotNullError(message: string): AppError {
  const field = extractFieldFromError(message);
  return new AppError(
    `Required field '${field}' is missing`,
    400,
    ErrorCode.VALIDATION_ERROR
  );
}

/**
 * 데이터베이스 에러를 구체적인 AppError로 변환
 */
function handleDatabaseError(error: Error, context: ErrorContext): AppError {
  const message = error.message.toLowerCase();

  // Unique constraint 위반
  if (message.includes('duplicate key') || message.includes('unique constraint')) {
    return handleUniqueConstraintError(message, context);
  }

  // Foreign key 위반
  if (message.includes('foreign key constraint')) {
    return handleForeignKeyError();
  }

  // Not null 위반
  if (message.includes('not-null constraint')) {
    return handleNotNullError(message);
  }

  // 기타 DB 에러
  return new AppError(
    'Database operation failed',
    500,
    ErrorCode.DATABASE_ERROR as ErrorCode
  );
}

/**
 * 에러 메시지에서 필드명 추출
 */
function extractFieldFromError(message: string): string {
  // PostgreSQL 에러 메시지 패턴에서 필드명 추출
  const match = message.match(/column "(\w+)"|key \((\w+)\)/);
  const field1 = match?.[1];
  const field2 = match?.[2];
  
  if (field1 !== undefined && field1.length > 0) return field1;
  if (field2 !== undefined && field2.length > 0) return field2;
  return 'field';
}

/**
 * 비동기 작업을 명시적으로 처리하는 래퍼
 * 
 * @example
 * const result = await withErrorHandling(
 *   async () => await repository.save(data),
 *   { operation: 'Create ObjectType', entity: 'ObjectType' }
 * );
 */
export async function withErrorHandling<T>(
  operation: () => Promise<T>,
  context: ErrorContext
): Promise<T> {
  try {
    return await operation();
  } catch (error) {
    throw handleError(error, context);
  }
}

/**
 * 결과를 명시적으로 표현하는 Result 타입
 * 에러를 예외가 아닌 값으로 처리
 */
export type Result<T, E = AppError> = 
  | { success: true; data: T }
  | { success: false; error: E };

/**
 * Result를 반환하는 비동기 작업 래퍼
 */
export async function tryAsync<T>(
  operation: () => Promise<T>,
  context: ErrorContext
): Promise<Result<T>> {
  try {
    const data = await operation();
    return { success: true, data };
  } catch (error) {
    const appError = handleError(error, context);
    return { success: false, error: appError };
  }
}

/**
 * Result 타입을 위한 유틸리티 함수들
 */
export const Result = {
  isSuccess<T>(result: Result<T>): result is { success: true; data: T } {
    return result.success === true;
  },

  isError<T>(result: Result<T>): result is { success: false; error: AppError } {
    return result.success === false;
  },

  unwrap<T>(result: Result<T>): T {
    if (Result.isSuccess(result)) {
      return result.data;
    }
    throw result.error;
  }
};