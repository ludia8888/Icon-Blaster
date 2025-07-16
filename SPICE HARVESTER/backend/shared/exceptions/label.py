"""
레이블 관련 도메인 예외
"""

from .base import DomainException


class LabelNotFoundError(DomainException):
    """레이블을 찾을 수 없음"""
    
    def __init__(self, label: str, label_type: str = "label"):
        super().__init__(
            message=f"{label_type} '{label}' 을(를) 찾을 수 없습니다",
            code="LABEL_NOT_FOUND",
            details={"label": label, "label_type": label_type}
        )


class LabelMappingError(DomainException):
    """레이블 매핑 오류"""
    
    def __init__(self, message: str, details: dict = None):
        super().__init__(
            message=message,
            code="LABEL_MAPPING_ERROR",
            details=details or {}
        )


class InvalidLabelError(DomainException):
    """잘못된 레이블"""
    
    def __init__(self, label: str, reason: str):
        super().__init__(
            message=f"잘못된 레이블 '{label}': {reason}",
            code="INVALID_LABEL",
            details={"label": label, "reason": reason}
        )