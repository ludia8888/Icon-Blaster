"""
쿼리 관련 도메인 예외 정의
"""

from typing import Optional, Dict, Any


class QueryException(Exception):
    """쿼리 관련 기본 예외"""
    
    def __init__(self, message: str, code: Optional[str] = None, 
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code or self.__class__.__name__
        self.details = details or {}


class QueryExecutionError(QueryException):
    """쿼리 실행 실패시 발생하는 예외"""
    
    def __init__(self, message: str, query: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="QUERY_EXECUTION_ERROR",
            details={"query": query} if query else {}
        )


class InvalidQueryError(QueryException):
    """잘못된 쿼리일 때 발생하는 예외"""
    
    def __init__(self, reason: str, query: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=f"Invalid query: {reason}",
            code="INVALID_QUERY",
            details={"reason": reason, "query": query}
        )


class QueryTimeoutError(QueryException):
    """쿼리 타임아웃시 발생하는 예외"""
    
    def __init__(self, timeout_seconds: int, query: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=f"Query timed out after {timeout_seconds} seconds",
            code="QUERY_TIMEOUT",
            details={"timeout_seconds": timeout_seconds, "query": query}
        )