"""
기본 도메인 예외 정의
"""


class DomainException(Exception):
    """도메인 기본 예외"""
    
    def __init__(self, message: str, code: str = "DOMAIN_ERROR", 
                 details: dict = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class ConnectionError(DomainException):
    """연결 오류"""
    
    def __init__(self, message: str, server_url: str = None):
        super().__init__(
            message=f"Connection error: {message}",
            code="CONNECTION_ERROR",
            details={"server_url": server_url} if server_url else {}
        )


class ConnectionPoolError(DomainException):
    """연결 풀 오류"""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(
            message=f"Connection pool error: {message}",
            code="CONNECTION_POOL_ERROR",
            details=details or {}
        )


class DatabaseError(DomainException):
    """데이터베이스 오류"""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(
            message=f"Database error: {message}",
            code="DATABASE_ERROR",
            details=details or {}
        )


class OperationalError(DomainException):
    """운영 오류"""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(
            message=f"Operational error: {message}",
            code="OPERATIONAL_ERROR",
            details=details or {}
        )