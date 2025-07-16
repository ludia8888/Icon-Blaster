"""
도메인 예외 정의
도메인별로 구체적인 예외를 정의하여 명확한 에러 처리
"""

from .ontology import (
    OntologyException,
    OntologyNotFoundError,
    DuplicateOntologyError,
    OntologyValidationError,
    PropertyValidationError,
    RelationshipValidationError,
    OntologyOperationError
)

from .branch import (
    BranchException,
    BranchNotFoundError,
    BranchAlreadyExistsError,
    ProtectedBranchError,
    BranchMergeConflictError,
    InvalidBranchNameError
)

from .version import (
    VersionException,
    VersionControlError,
    CommitNotFoundError,
    InvalidCommitError,
    RollbackError
)

from .query import (
    QueryException,
    QueryExecutionError,
    InvalidQueryError,
    QueryTimeoutError
)

from .label import (
    LabelNotFoundError,
    LabelMappingError,
    InvalidLabelError
)

from .base import DomainException, ConnectionError, ConnectionPoolError


class DatabaseNotFoundError(DomainException):
    """데이터베이스를 찾을 수 없을 때 발생하는 예외"""
    
    def __init__(self, db_name: str):
        super().__init__(
            message=f"Database not found: {db_name}",
            code="DATABASE_NOT_FOUND",
            details={"db_name": db_name}
        )


class DatabaseAlreadyExistsError(DomainException):
    """데이터베이스가 이미 존재할 때 발생하는 예외"""
    
    def __init__(self, db_name: str):
        super().__init__(
            message=f"Database already exists: {db_name}",
            code="DATABASE_ALREADY_EXISTS",
            details={"db_name": db_name}
        )




__all__ = [
    # Base
    "DomainException",
    "ConnectionError",
    "ConnectionPoolError",
    
    # Database
    "DatabaseNotFoundError",
    "DatabaseAlreadyExistsError",
    
    # Ontology
    "OntologyException",
    "OntologyNotFoundError",
    "DuplicateOntologyError",
    "OntologyValidationError",
    "PropertyValidationError",
    "RelationshipValidationError",
    "OntologyOperationError",
    
    # Branch
    "BranchException",
    "BranchNotFoundError",
    "BranchAlreadyExistsError",
    "ProtectedBranchError",
    "BranchMergeConflictError",
    "InvalidBranchNameError",
    
    # Version
    "VersionException",
    "VersionControlError",
    "CommitNotFoundError",
    "InvalidCommitError",
    "RollbackError",
    
    # Query
    "QueryException",
    "QueryExecutionError",
    "InvalidQueryError",
    "QueryTimeoutError",
    
    # Label
    "LabelNotFoundError",
    "LabelMappingError",
    "InvalidLabelError",
]