"""
버전 관리 관련 도메인 예외 정의
"""

from typing import Optional, Dict, Any


class VersionException(Exception):
    """버전 관리 관련 기본 예외"""
    
    def __init__(self, message: str, code: Optional[str] = None, 
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code or self.__class__.__name__
        self.details = details or {}


class VersionControlError(VersionException):
    """버전 제어 작업 실패시 발생하는 예외"""
    
    def __init__(self, message: str, operation: str):
        super().__init__(
            message=message,
            code="VERSION_CONTROL_ERROR",
            details={"operation": operation}
        )


class CommitNotFoundError(VersionException):
    """커밋을 찾을 수 없을 때 발생하는 예외"""
    
    def __init__(self, commit_id: str, db_name: Optional[str] = None):
        message = f"Commit not found: {commit_id}"
        if db_name:
            message += f" in database '{db_name}'"
        
        super().__init__(
            message=message,
            code="COMMIT_NOT_FOUND",
            details={"commit_id": commit_id, "db_name": db_name}
        )


class InvalidCommitError(VersionException):
    """잘못된 커밋 정보일 때 발생하는 예외"""
    
    def __init__(self, reason: str, commit_data: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=f"Invalid commit: {reason}",
            code="INVALID_COMMIT",
            details={"reason": reason, "commit_data": commit_data}
        )


class RollbackError(VersionException):
    """롤백 실패시 발생하는 예외"""
    
    def __init__(self, target_commit: str, reason: str):
        super().__init__(
            message=f"Failed to rollback to commit '{target_commit}': {reason}",
            code="ROLLBACK_ERROR",
            details={"target_commit": target_commit, "reason": reason}
        )