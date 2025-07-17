"""
Shared ontology models for OMS and BFF
"""

from pydantic import BaseModel, Field, validator, root_validator
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

from .common import (
    BaseResponse, 
    TimestampMixin, 
    PaginationRequest, 
    PaginationResponse,
    DataType,
    Cardinality,
    QueryOperator,
    ValidationError
)


class MultiLingualText(BaseModel):
    """다국어 텍스트 지원"""
    ko: Optional[str] = None
    en: Optional[str] = None
    ja: Optional[str] = None
    zh: Optional[str] = None
    
    @validator('*')
    def at_least_one_language(cls, v, values):
        """최소 하나의 언어는 필수"""
        if not any(values.values()) and v is None:
            raise ValueError("최소 하나의 언어로 된 텍스트가 필요합니다")
        return v
    
    def get(self, lang: str, fallback_chain: List[str] = None) -> str:
        """
        언어 코드로 텍스트 조회 (fallback 지원)
        """
        if hasattr(self, lang) and getattr(self, lang):
            return getattr(self, lang)
        
        if fallback_chain:
            for fallback_lang in fallback_chain:
                if hasattr(self, fallback_lang) and getattr(self, fallback_lang):
                    return getattr(self, fallback_lang)
        
        # 기본 fallback: 첫 번째로 발견되는 텍스트
        for value in self.dict().values():
            if value:
                return value
        
        return ""
    
    @classmethod
    def from_string(cls, text: str, lang: str = 'ko') -> 'MultiLingualText':
        """단일 언어 문자열로부터 MultiLingualText 생성"""
        return cls(**{lang: text})


class Property(BaseModel):
    """속성 정의"""
    name: str = Field(..., description="속성의 내부 ID")
    type: DataType = Field(..., description="데이터 타입")
    label: Union[str, MultiLingualText] = Field(..., description="속성 레이블")
    description: Optional[Union[str, MultiLingualText]] = None
    required: bool = Field(default=False, description="필수 여부")
    default: Optional[Any] = None
    constraints: Optional[Dict[str, Any]] = None
    
    @validator('name')
    def validate_name(cls, v):
        """속성명 검증"""
        import re
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', v):
            raise ValueError("속성명은 영문자로 시작하고 영문, 숫자, 언더스코어만 포함해야 합니다")
        return v


class Relationship(BaseModel):
    """관계 정의"""
    predicate: str = Field(..., description="관계의 내부 ID")
    target: str = Field(..., description="대상 클래스 ID")
    label: Union[str, MultiLingualText] = Field(..., description="관계 레이블")
    description: Optional[Union[str, MultiLingualText]] = None
    cardinality: Cardinality = Field(default=Cardinality.MANY)
    inverse_predicate: Optional[str] = None
    inverse_label: Optional[Union[str, MultiLingualText]] = None
    
    @validator('predicate', 'target')
    def validate_identifiers(cls, v):
        """식별자 검증"""
        import re
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', v):
            raise ValueError("식별자는 영문자로 시작하고 영문, 숫자, 언더스코어만 포함해야 합니다")
        return v


class OntologyBase(BaseModel):
    """온톨로지 기본 모델"""
    id: str = Field(..., description="클래스 ID")
    label: Union[str, MultiLingualText] = Field(..., description="클래스 레이블")
    description: Optional[Union[str, MultiLingualText]] = None
    properties: List[Property] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)
    parent_class: Optional[str] = None
    abstract: bool = Field(default=False)
    metadata: Optional[Dict[str, Any]] = None
    
    @validator('id')
    def validate_id(cls, v):
        """클래스 ID 검증"""
        import re
        if not re.match(r'^[A-Z][a-zA-Z0-9]*$', v):
            raise ValueError("클래스 ID는 대문자로 시작하는 CamelCase여야 합니다")
        return v


class OntologyCreateRequest(OntologyBase):
    """온톨로지 생성 요청"""
    pass


class OntologyCreateRequestBFF(BaseModel):
    """BFF용 온톨로지 생성 요청 - ID 자동 생성"""
    label: Union[str, MultiLingualText] = Field(..., description="클래스 레이블")
    description: Optional[Union[str, MultiLingualText]] = None
    properties: List[Property] = Field(default_factory=list)
    relationships: List[Relationship] = Field(default_factory=list)
    parent_class: Optional[str] = None
    abstract: bool = Field(default=False)
    metadata: Optional[Dict[str, Any]] = None


class OntologyUpdateRequest(BaseModel):
    """온톨로지 업데이트 요청"""
    label: Optional[Union[str, MultiLingualText]] = None
    description: Optional[Union[str, MultiLingualText]] = None
    properties: Optional[List[Property]] = None
    relationships: Optional[List[Relationship]] = None
    parent_class: Optional[str] = None
    abstract: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None
    
    @root_validator(skip_on_failure=True)
    def at_least_one_field(cls, values):
        """최소 하나의 필드는 업데이트되어야 함"""
        if not any(v is not None for v in values.values()):
            raise ValueError("업데이트할 필드가 최소 하나는 필요합니다")
        return values


class OntologyResponse(BaseResponse, TimestampMixin):
    """온톨로지 응답"""
    data: Optional[OntologyBase] = None


class QueryFilter(BaseModel):
    """쿼리 필터 조건"""
    field: str = Field(..., description="필터할 필드")
    operator: QueryOperator = Field(default=QueryOperator.EQUALS)
    value: Any = Field(..., description="비교할 값")
    
    @validator('operator', pre=True)
    def validate_operator(cls, v):
        """문자열로 입력된 연산자도 허용"""
        if isinstance(v, str):
            operator_map = {
                'eq': QueryOperator.EQUALS,
                'neq': QueryOperator.NOT_EQUALS,
                'gt': QueryOperator.GREATER_THAN,
                'gte': QueryOperator.GREATER_THAN_OR_EQUAL,
                'lt': QueryOperator.LESS_THAN,
                'lte': QueryOperator.LESS_THAN_OR_EQUAL,
                'in': QueryOperator.IN,
                'nin': QueryOperator.NOT_IN,
                'contains': QueryOperator.CONTAINS,
                'starts_with': QueryOperator.STARTS_WITH,
                'ends_with': QueryOperator.ENDS_WITH
            }
            return operator_map.get(v, v)
        return v


class QueryRequest(BaseModel):
    """쿼리 요청 - BFF용 (레이블 기반)"""
    class_label: str = Field(..., description="조회할 클래스 레이블")
    filters: Optional[List[QueryFilter]] = Field(default_factory=list)
    select: Optional[List[str]] = None
    limit: Optional[int] = Field(default=100, ge=1, le=1000)
    offset: Optional[int] = Field(default=0, ge=0)
    order_by: Optional[str] = None
    order_direction: Optional[str] = Field(default="asc", pattern="^(asc|desc)$")


class QueryRequestInternal(BaseModel):
    """쿼리 요청 - OMS용 (내부 ID 기반)"""
    class_id: str = Field(..., description="조회할 클래스 ID")
    filters: Optional[List[QueryFilter]] = Field(default_factory=list)
    select: Optional[List[str]] = None
    limit: Optional[int] = Field(default=100, ge=1, le=1000)
    offset: Optional[int] = Field(default=0, ge=0)
    order_by: Optional[str] = None
    order_direction: Optional[str] = Field(default="asc", pattern="^(asc|desc)$")


class QueryResponse(BaseResponse, PaginationResponse):
    """쿼리 응답"""
    data: List[Dict[str, Any]] = Field(default_factory=list)


# 하위 호환성을 위한 별칭
OntologyCreateInput = OntologyCreateRequest
OntologyUpdateInput = OntologyUpdateRequest
QueryInput = QueryRequest
PropertyDefinition = Property
RelationshipDefinition = Relationship