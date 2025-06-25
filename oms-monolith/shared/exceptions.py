"""
공통 예외 정의
"""

class OmsException(Exception):
    """OMS 기본 예외"""
    pass

class ValidationError(OmsException):
    """검증 오류"""
    pass

class ConflictError(OmsException):
    """충돌 오류"""
    pass

class NotFoundError(OmsException):
    """리소스를 찾을 수 없음"""
    pass

class PermissionError(OmsException):
    """권한 없음"""
    pass