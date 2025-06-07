/**
 * Express Request 타입 확장
 * 
 * 장점: Express 생태계와 완전 호환
 * 단점: 글로벌 타입 오염 가능성
 */

import { JwtPayload } from '../auth/types';

declare global {
  namespace Express {
    interface Request {
      // 검증된 상태를 나타내는 플래그들
      _bodyValidated?: boolean;
      _queryValidated?: boolean; 
      _paramsValidated?: boolean;
      
      // 사용자 정보 (JWT에서 추출)
      user?: JwtPayload;
      
      // 요청 추적용 ID
      id?: string;
    }
  }
}

/**
 * 검증된 Request 타입
 * 
 * @template TBody - 검증된 body 타입 (기본값: unknown)
 * @template TQuery - 검증된 query 타입 (기본값: Record<string, string | string[]>)
 * @template TParams - 검증된 params 타입 (기본값: Record<string, string>)
 */
export interface ValidatedRequest<
  TBody = unknown,
  TQuery = Record<string, string | string[]>,
  TParams = Record<string, string>
> extends Express.Request {
  body: TBody;
  query: TQuery;
  params: TParams;
  _bodyValidated: true;
  _queryValidated: true;
  _paramsValidated: true;
}

/**
 * 부분적으로 검증된 Request 타입들
 */
export interface BodyValidatedRequest<T> extends Express.Request {
  body: T;
  _bodyValidated: true;
}

export interface QueryValidatedRequest<T> extends Express.Request {
  query: T;
  _queryValidated: true;
}

export interface ParamsValidatedRequest<T> extends Express.Request {
  params: T;
  _paramsValidated: true;
}