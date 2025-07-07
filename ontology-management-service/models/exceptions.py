"""
OMS 공통 예외 클래스들
비즈니스 로직과 시스템 레벨 예외를 구분하여 정의
"""

from typing import Optional, Dict, Any

class OMSException(Exception):
    """OMS 시스템의 최상위 예외 클래스"""
    pass


class ConcurrencyError(OMSException):
    """동시성 충돌 예외
    
    낙관적 잠금(Optimistic Locking) 실패 시 발생
    - 동일 리소스에 대한 동시 수정 시도
    - 버전 불일치로 인한 업데이트 실패
    """
    pass


class ConflictError(OMSException):
    """비즈니스 로직 충돌 예외
    
    비즈니스 규칙 위반 시 발생
    - 중복된 리소스 생성 시도
    - 유효하지 않은 상태 전환
    - 권한 없는 작업 시도
    """
    def __init__(
        self,
        message: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        expected_commit: Optional[str] = None,
        actual_commit: Optional[str] = None,
        merge_hints: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.expected_commit = expected_commit
        self.actual_commit = actual_commit
        self.merge_hints = merge_hints


class ValidationError(OMSException):
    """데이터 검증 실패 예외
    
    입력 데이터가 유효성 검증에 실패했을 때 발생
    """
    pass


class ResourceNotFoundError(OMSException):
    """리소스를 찾을 수 없음 예외
    
    요청한 리소스가 존재하지 않을 때 발생
    """
    pass


class ServiceUnavailableError(OMSException):
    """서비스 사용 불가 예외
    
    외부 서비스나 의존성이 일시적으로 사용 불가능할 때 발생
    """
    pass