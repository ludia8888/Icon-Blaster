"""
브랜치 관련 도메인 예외 정의
"""

from typing import Optional, List, Dict, Any


class BranchException(Exception):
    """브랜치 관련 기본 예외"""
    
    def __init__(self, message: str, code: Optional[str] = None, 
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code or self.__class__.__name__
        self.details = details or {}


class BranchNotFoundError(BranchException):
    """브랜치를 찾을 수 없을 때 발생하는 예외"""
    
    def __init__(self, branch_name: str, db_name: Optional[str] = None):
        message = f"Branch not found: {branch_name}"
        if db_name:
            message += f" in database '{db_name}'"
        
        super().__init__(
            message=message,
            code="BRANCH_NOT_FOUND",
            details={"branch_name": branch_name, "db_name": db_name}
        )


class BranchAlreadyExistsError(BranchException):
    """브랜치가 이미 존재할 때 발생하는 예외"""
    
    def __init__(self, branch_name: str, db_name: Optional[str] = None):
        message = f"Branch already exists: {branch_name}"
        if db_name:
            message += f" in database '{db_name}'"
        
        super().__init__(
            message=message,
            code="BRANCH_ALREADY_EXISTS",
            details={"branch_name": branch_name, "db_name": db_name}
        )


class ProtectedBranchError(BranchException):
    """보호된 브랜치에 대한 작업 시도시 발생하는 예외"""
    
    def __init__(self, branch_name: str, operation: str):
        message = f"Cannot {operation} protected branch: {branch_name}"
        
        super().__init__(
            message=message,
            code="PROTECTED_BRANCH",
            details={"branch_name": branch_name, "operation": operation}
        )


class BranchMergeConflictError(BranchException):
    """브랜치 병합 충돌시 발생하는 예외"""
    
    def __init__(self, source: str, target: str, conflicts: List[Dict[str, Any]]):
        message = f"Merge conflict between '{source}' and '{target}'"
        
        super().__init__(
            message=message,
            code="MERGE_CONFLICT",
            details={
                "source_branch": source,
                "target_branch": target,
                "conflicts": conflicts
            }
        )


class InvalidBranchNameError(BranchException):
    """잘못된 브랜치 이름일 때 발생하는 예외"""
    
    def __init__(self, branch_name: str, reason: str):
        message = f"Invalid branch name '{branch_name}': {reason}"
        
        super().__init__(
            message=message,
            code="INVALID_BRANCH_NAME",
            details={"branch_name": branch_name, "reason": reason}
        )