"""
온톨로지 도메인 예외 정의
도메인 특화 예외들을 정의하여 명확한 에러 처리
"""

from typing import Optional, List, Dict, Any


class OntologyException(Exception):
    """온톨로지 관련 기본 예외"""
    
    def __init__(self, message: str, code: Optional[str] = None, 
                 details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code or self.__class__.__name__
        self.details = details or {}


class OntologyNotFoundError(OntologyException):
    """온톨로지를 찾을 수 없을 때 발생하는 예외"""
    
    def __init__(self, ontology_id: str, db_name: Optional[str] = None):
        message = f"Ontology not found: {ontology_id}"
        if db_name:
            message += f" in database '{db_name}'"
        
        super().__init__(
            message=message,
            code="ONTOLOGY_NOT_FOUND",
            details={"ontology_id": ontology_id, "db_name": db_name}
        )


class DuplicateOntologyError(OntologyException):
    """중복된 온톨로지 ID일 때 발생하는 예외"""
    
    def __init__(self, ontology_id: str, db_name: Optional[str] = None):
        message = f"Duplicate ontology ID: {ontology_id}"
        if db_name:
            message += f" in database '{db_name}'"
        
        super().__init__(
            message=message,
            code="DUPLICATE_ONTOLOGY",
            details={"ontology_id": ontology_id, "db_name": db_name}
        )


class OntologyValidationError(OntologyException):
    """온톨로지 유효성 검증 실패시 발생하는 예외"""
    
    def __init__(self, errors: List[str], ontology_id: Optional[str] = None):
        message = "Ontology validation failed"
        if ontology_id:
            message += f" for '{ontology_id}'"
        message += f": {'; '.join(errors)}"
        
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            details={"errors": errors, "ontology_id": ontology_id}
        )


class PropertyValidationError(OntologyException):
    """속성 유효성 검증 실패시 발생하는 예외"""
    
    def __init__(self, property_name: str, errors: List[str]):
        message = f"Property '{property_name}' validation failed: {'; '.join(errors)}"
        
        super().__init__(
            message=message,
            code="PROPERTY_VALIDATION_ERROR",
            details={"property_name": property_name, "errors": errors}
        )


class RelationshipValidationError(OntologyException):
    """관계 유효성 검증 실패시 발생하는 예외"""
    
    def __init__(self, predicate: str, error: str):
        message = f"Relationship '{predicate}' validation failed: {error}"
        
        super().__init__(
            message=message,
            code="RELATIONSHIP_VALIDATION_ERROR",
            details={"predicate": predicate, "error": error}
        )


class OntologyOperationError(OntologyException):
    """온톨로지 작업 중 발생하는 일반적인 오류"""
    
    def __init__(self, operation: str, message: str, 
                 ontology_id: Optional[str] = None):
        full_message = f"Operation '{operation}' failed"
        if ontology_id:
            full_message += f" for ontology '{ontology_id}'"
        full_message += f": {message}"
        
        super().__init__(
            message=full_message,
            code="OPERATION_ERROR",
            details={"operation": operation, "ontology_id": ontology_id}
        )