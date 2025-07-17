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
    # 기본 XSD 타입
    STRING = "xsd:string"
    INTEGER = "xsd:integer"
    DECIMAL = "xsd:decimal"
    BOOLEAN = "xsd:boolean"
    DATE = "xsd:date"
    DATETIME = "xsd:dateTime"
    URI = "xsd:anyURI"
    
    # 🔥 THINK ULTRA! 복합 타입들
    ARRAY = "custom:array"           # 배열 타입
    OBJECT = "custom:object"         # 중첩 객체
    ENUM = "custom:enum"             # 열거형
    MONEY = "custom:money"           # 통화 타입
    PHONE = "custom:phone"           # 전화번호
    EMAIL = "custom:email"           # 이메일
    COORDINATE = "custom:coordinate" # 좌표 (위도/경도)
    ADDRESS = "custom:address"       # 주소
    IMAGE = "custom:image"           # 이미지 URL
    FILE = "custom:file"             # 파일 첨부
    
    @classmethod
    def validate(cls, value: str) -> bool:
        """데이터 타입 유효성 검증"""
        return value in [item.value for item in cls]
    
    @classmethod
    def is_complex_type(cls, data_type: str) -> bool:
        """복합 타입 여부 확인"""
        return data_type.startswith("custom:")
    
    @classmethod
    def get_base_type(cls, data_type: str) -> str:
        """복합 타입의 기본 저장 타입 반환"""
        base_type_map = {
            cls.ARRAY.value: cls.STRING.value,  # JSON string으로 저장
            cls.OBJECT.value: cls.STRING.value,  # JSON string으로 저장
            cls.ENUM.value: cls.STRING.value,
            cls.MONEY.value: cls.DECIMAL.value,
            cls.PHONE.value: cls.STRING.value,
            cls.EMAIL.value: cls.STRING.value,
            cls.COORDINATE.value: cls.STRING.value,  # "lat,lng" 형식
            cls.ADDRESS.value: cls.STRING.value,  # JSON string으로 저장
            cls.IMAGE.value: cls.URI.value,
            cls.FILE.value: cls.URI.value
        }
        return base_type_map.get(data_type, data_type)


class Cardinality(str, Enum):
    """관계의 카디널리티"""
    ONE = "one"
    MANY = "many"
    ONE_TO_ONE = "1:1"
    ONE_TO_MANY = "1:n"
    MANY_TO_ONE = "n:1"
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