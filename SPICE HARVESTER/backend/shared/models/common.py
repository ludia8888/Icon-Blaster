"""
Common base models and utilities
"""

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum


class BaseResponse(BaseModel):
    """기본 응답 모델"""
    status: str
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TimestampMixin(BaseModel):
    """타임스탬프 믹스인"""
    created_at: Optional[datetime] = Field(default_factory=datetime.utcnow)
    updated_at: Optional[datetime] = Field(default_factory=datetime.utcnow)


class PaginationRequest(BaseModel):
    """페이지네이션 요청"""
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class PaginationResponse(BaseModel):
    """페이지네이션 응답"""
    count: int
    total: Optional[int] = None
    limit: int
    offset: int


class DataType(str, Enum):
    """지원되는 데이터 타입"""
    STRING = "xsd:string"
    INTEGER = "xsd:integer"
    DECIMAL = "xsd:decimal"
    BOOLEAN = "xsd:boolean"
    DATE = "xsd:date"
    DATETIME = "xsd:dateTime"
    URI = "xsd:anyURI"
    
    @classmethod
    def validate(cls, value: str) -> bool:
        """데이터 타입 유효성 검증"""
        return value in [item.value for item in cls]


class Cardinality(str, Enum):
    """관계의 카디널리티"""
    ONE = "one"
    MANY = "many"
    ONE_TO_ONE = "1:1"
    ONE_TO_MANY = "1:n"
    MANY_TO_MANY = "n:n"


class QueryOperator(str, Enum):
    """쿼리 연산자"""
    EQUALS = "eq"
    NOT_EQUALS = "neq"
    GREATER_THAN = "gt"
    GREATER_THAN_OR_EQUAL = "gte"
    LESS_THAN = "lt"
    LESS_THAN_OR_EQUAL = "lte"
    IN = "in"
    NOT_IN = "nin"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"


class ValidationError(BaseModel):
    """유효성 검증 오류"""
    field: str
    message: str
    code: str


class BulkOperationResult(BaseModel):
    """대량 작업 결과"""
    successful: int = 0
    failed: int = 0
    errors: List[ValidationError] = Field(default_factory=list)
    results: List[Dict[str, Any]] = Field(default_factory=list)