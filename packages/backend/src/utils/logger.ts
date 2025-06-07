/**
 * Winston 기반 프로덕션 로거
 * 
 * 특징:
 * - 구조화된 로깅 (JSON 형식)
 * - 로그 레벨별 필터링
 * - 일별 로그 파일 로테이션
 * - 컨텍스트 정보 포함
 * - 에러 스택 트레이스 지원
 */

import winston from 'winston';
import DailyRotateFile from 'winston-daily-rotate-file';
import path from 'path';
import { Request, Response, NextFunction } from 'express';

const { combine, timestamp, errors, json, printf, colorize } = winston.format;

/**
 * 로그 컨텍스트 타입
 */
export interface LogContext {
  [key: string]: unknown;
  correlationId?: string;
  userId?: string;
  operation?: string;
  duration?: number;
}

/**
 * 개발 환경용 포맷터
 */
const devFormat = printf(({ level, message, timestamp, ...metadata }) => {
  const meta = Object.keys(metadata).length > 0 ? JSON.stringify(metadata, null, 2) : '';
  return `${String(timestamp)} [${String(level)}] ${String(message)} ${meta}`;
});

/**
 * 로그 파일 전송 설정
 */
const fileRotateTransport = new DailyRotateFile({
  filename: path.join('logs', '%DATE%-app.log'),
  datePattern: 'YYYY-MM-DD',
  maxSize: '20m',
  maxFiles: '14d',
  format: combine(
    timestamp(),
    errors({ stack: true }),
    json()
  )
});

/**
 * 에러 로그 전용 파일
 */
const errorFileTransport = new DailyRotateFile({
  level: 'error',
  filename: path.join('logs', '%DATE%-error.log'),
  datePattern: 'YYYY-MM-DD',
  maxSize: '20m',
  maxFiles: '30d',
  format: combine(
    timestamp(),
    errors({ stack: true }),
    json()
  )
});

/**
 * Winston 로거 인스턴스 생성
 */
const winstonLogger = winston.createLogger({
  level: process.env['LOG_LEVEL'] ?? 'info',
  format: combine(
    timestamp({
      format: 'YYYY-MM-DD HH:mm:ss'
    }),
    errors({ stack: true }),
    json()
  ),
  defaultMeta: { 
    service: 'arrakis-backend',
    environment: process.env['NODE_ENV'] ?? 'development'
  },
  transports: [
    // 파일 로테이션
    fileRotateTransport,
    errorFileTransport
  ]
});

/**
 * 개발 환경에서는 콘솔 출력 추가
 */
if (process.env['NODE_ENV'] !== 'production') {
  winstonLogger.add(new winston.transports.Console({
    format: combine(
      colorize(),
      timestamp({
        format: 'YYYY-MM-DD HH:mm:ss'
      }),
      devFormat
    )
  }));
}

/**
 * 로거 인터페이스
 */
export interface Logger {
  info(message: string, context?: LogContext): void;
  error(message: string, context?: LogContext): void;
  warn(message: string, context?: LogContext): void;
  debug(message: string, context?: LogContext): void;
  http(message: string, context?: LogContext): void;
}

/**
 * Winston 로거 래퍼
 * 타입 안전성과 일관된 인터페이스 제공
 */
class WinstonLogger implements Logger {
  private sanitizeContext(context?: LogContext): LogContext {
    if (!context) return {};
    
    // 민감한 정보 필터링
    const sanitized = { ...context };
    const sensitiveKeys = ['password', 'token', 'secret', 'apiKey'];
    
    Object.keys(sanitized).forEach(key => {
      if (sensitiveKeys.some(sensitive => key.toLowerCase().includes(sensitive))) {
        sanitized[key] = '[REDACTED]';
      }
    });
    
    return sanitized;
  }

  info(message: string, context?: LogContext): void {
    winstonLogger.info(message, this.sanitizeContext(context));
  }

  error(message: string, context?: LogContext): void {
    // 에러 객체 특별 처리
    if (context?.error instanceof Error) {
      winstonLogger.error(message, {
        ...this.sanitizeContext(context),
        error: {
          message: context.error.message,
          stack: context.error.stack,
          name: context.error.name
        }
      });
    } else {
      winstonLogger.error(message, this.sanitizeContext(context));
    }
  }

  warn(message: string, context?: LogContext): void {
    winstonLogger.warn(message, this.sanitizeContext(context));
  }

  debug(message: string, context?: LogContext): void {
    winstonLogger.debug(message, this.sanitizeContext(context));
  }

  http(message: string, context?: LogContext): void {
    winstonLogger.http(message, this.sanitizeContext(context));
  }
}

/**
 * 싱글톤 로거 인스턴스
 */
export const logger = new WinstonLogger();

/**
 * 확장된 Request 타입 정의
 */
interface ExtendedRequest extends Request {
  correlationId?: string;
  user?: {
    id: string;
    [key: string]: unknown;
  };
}

/**
 * Express 미들웨어용 HTTP 로거
 */
export const httpLogger = (req: ExtendedRequest, res: Response, next: NextFunction): void => {
  const start = Date.now();
  
  res.on('finish', () => {
    const duration = Date.now() - start;
    
    logger.http(`${req.method} ${req.originalUrl}`, {
      method: req.method,
      url: req.originalUrl,
      status: res.statusCode,
      duration,
      ip: req.ip,
      userAgent: req.get('user-agent'),
      correlationId: req.correlationId,
      userId: req.user?.id
    });
  });
  
  next();
};

/**
 * 프로세스 종료 시 로거 정리
 */
process.on('SIGTERM', () => {
  winstonLogger.end();
});