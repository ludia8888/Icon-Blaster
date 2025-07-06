"""
JSON Schema Validation for Naming Conventions
JSON 스키마 검증 및 외부 입력 검증 모듈
"""
import json
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
from enum import Enum
from datetime import datetime, timezone

try:
    import jsonschema
    from jsonschema import validate, ValidationError as JsonSchemaValidationError
    HAS_JSONSCHEMA = True
except ImportError:
    HAS_JSONSCHEMA = False
    JsonSchemaValidationError = Exception

from pydantic import BaseModel, Field, ValidationError, field_validator, ConfigDict
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaValue

from core.validation.naming_convention import (
    EntityType, NamingPattern, NamingRule, NamingConvention,
    enum_encoder, utc_datetime_encoder
)
from common_logging.setup import get_logger

logger = get_logger(__name__)


class SchemaValidationError(Exception):
    """스키마 검증 실패 예외"""
    def __init__(self, message: str, errors: List[Dict] = None):
        super().__init__(message)
        self.errors = errors or []


class NamingConventionSchema(BaseModel):
    """
    NamingConvention용 강화된 Pydantic 스키마
    외부 입력 검증 및 JSON 스키마 생성용
    """
    schema_version: str = Field("1.0.0", description="Schema version for compatibility", alias="__version__")
    
    id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r'^[a-zA-Z0-9_-]+$',
        description="Unique convention identifier"
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Human-readable convention name"
    )
    description: Optional[str] = Field(
        None,
        max_length=1000,
        description="Optional description of the convention"
    )
    rules: Dict[EntityType, NamingRule] = Field(
        ...,
        description="Entity type to naming rule mapping"
    )
    reserved_words: List[str] = Field(
        default_factory=list,
        description="Words that cannot be used in entity names"
    )
    case_sensitive: bool = Field(
        True,
        description="Whether naming validation is case sensitive"
    )
    auto_fix_enabled: bool = Field(
        True,
        description="Whether automatic name fixing is enabled"
    )
    created_at: str = Field(
        ...,
        description="UTC timestamp when convention was created"
    )
    updated_at: str = Field(
        ...,
        description="UTC timestamp when convention was last updated"
    )
    created_by: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="User who created the convention"
    )
    
    @field_validator('created_at', 'updated_at')
    def validate_timestamp(cls, v):
        """UTC 타임스탬프 형식 검증"""
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except ValueError:
            raise ValueError(f"Invalid timestamp format: {v}. Expected ISO format with timezone.")
    
    @field_validator('rules')
    def validate_rules_not_empty(cls, v):
        """최소 하나의 규칙이 있어야 함"""
        if not v:
            raise ValueError("At least one naming rule must be defined")
        return v
    
    @field_validator('reserved_words')
    def validate_reserved_words(cls, v):
        """예약어 검증"""
        # 중복 제거
        unique_words = list(set(v))
        # 빈 문자열 제거
        return [word for word in unique_words if word and word.strip()]
    
    model_config = ConfigDict(
        json_encoders={
            Enum: enum_encoder,
            datetime: utc_datetime_encoder
        },
        json_schema_extra={
            "title": "Naming Convention Schema",
            "description": "Schema for validating naming convention configurations",
            "examples": [{
                "__version__": "1.0.0",
                "id": "enterprise-standard",
                "name": "Enterprise Standard Naming Convention",
                "description": "Corporate naming standards for all projects",
                "rules": {
                    "objectType": {
                        "entity_type": "objectType",
                        "pattern": "PascalCase",
                        "min_length": 3,
                        "max_length": 50,
                        "forbidden_prefix": ["_", "temp"],
                        "description": "Object types should be descriptive nouns"
                    }
                },
                "reserved_words": ["test", "temp", "admin"],
                "case_sensitive": True,
                "auto_fix_enabled": True,
                "created_at": "2024-01-01T12:00:00Z",
                "updated_at": "2024-01-01T12:00:00Z",
                "created_by": "system-admin"
            }]
        }
    )


class NamingRuleSchema(BaseModel):
    """NamingRule용 강화된 스키마"""
    entity_type: EntityType = Field(..., description="Type of entity this rule applies to")
    pattern: NamingPattern = Field(..., description="Required naming pattern")
    required_prefix: Optional[List[str]] = Field(
        default_factory=list,
        description="Required prefixes (at least one must match)"
    )
    required_suffix: Optional[List[str]] = Field(
        default_factory=list,
        description="Required suffixes (at least one must match)"
    )
    forbidden_prefix: Optional[List[str]] = Field(
        default_factory=list,
        description="Forbidden prefixes"
    )
    forbidden_suffix: Optional[List[str]] = Field(
        default_factory=list,
        description="Forbidden suffixes"
    )
    forbidden_words: Optional[List[str]] = Field(
        default_factory=list,
        description="Words that cannot appear in the name"
    )
    min_length: int = Field(1, ge=1, le=1000, description="Minimum name length")
    max_length: int = Field(255, ge=1, le=1000, description="Maximum name length")
    allow_numbers: bool = Field(True, description="Whether numbers are allowed")
    allow_underscores: bool = Field(True, description="Whether underscores are allowed")
    custom_regex: Optional[str] = Field(
        None,
        max_length=500,
        description="Custom regex pattern for validation"
    )
    description: Optional[str] = Field(
        None,
        max_length=500,
        description="Human-readable description of this rule"
    )
    
    @field_validator('min_length', 'max_length')
    def validate_length_range(cls, v, info):
        """길이 범위 검증"""
        if info.field_name == 'max_length' and hasattr(info, 'data'):
            min_length = info.data.get('min_length', 1)
            if v < min_length:
                raise ValueError(f"max_length ({v}) must be >= min_length ({min_length})")
        return v
    
    @field_validator('custom_regex')
    def validate_regex_pattern(cls, v):
        """정규식 패턴 검증"""
        if v:
            try:
                import re
                re.compile(v)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern: {e}")
        return v
    
    model_config = ConfigDict(
        json_encoders={
            Enum: enum_encoder,
            datetime: utc_datetime_encoder
        }
    )


class JsonSchemaValidator:
    """JSON 스키마 기반 검증 클래스"""
    
    def __init__(self):
        self.schemas = {}
        self._load_schemas()
    
    def _load_schemas(self):
        """Pydantic 모델에서 JSON 스키마 생성"""
        try:
            # NamingConvention 스키마 생성
            self.schemas['naming_convention'] = NamingConventionSchema.model_json_schema()
            
            # NamingRule 스키마 생성
            self.schemas['naming_rule'] = NamingRuleSchema.model_json_schema()
            
            logger.info("JSON schemas loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load JSON schemas: {e}")
            self.schemas = {}
    
    def validate_naming_convention(self, data: Dict) -> NamingConventionSchema:
        """
        명명 규칙 데이터 검증
        
        Args:
            data: 검증할 딕셔너리 데이터
            
        Returns:
            검증된 NamingConventionSchema 인스턴스
            
        Raises:
            SchemaValidationError: 검증 실패 시
        """
        try:
            # Pydantic 검증
            validated = NamingConventionSchema(**data)
            
            # 추가 jsonschema 검증 (사용 가능한 경우)
            if HAS_JSONSCHEMA and 'naming_convention' in self.schemas:
                try:
                    validate(data, self.schemas['naming_convention'])
                except JsonSchemaValidationError as e:
                    logger.warning(f"jsonschema validation warning: {e}")
            
            return validated
            
        except ValidationError as e:
            errors = []
            for error in e.errors():
                errors.append({
                    "field": " -> ".join(str(x) for x in error['loc']),
                    "message": error['msg'],
                    "value": error.get('input', 'N/A')
                })
            
            raise SchemaValidationError(
                f"Naming convention validation failed: {len(errors)} errors found",
                errors
            )
        except Exception as e:
            raise SchemaValidationError(f"Unexpected validation error: {e}")
    
    def validate_naming_rule(self, data: Dict) -> NamingRuleSchema:
        """
        명명 규칙 데이터 검증
        
        Args:
            data: 검증할 딕셔너리 데이터
            
        Returns:
            검증된 NamingRuleSchema 인스턴스
            
        Raises:
            SchemaValidationError: 검증 실패 시
        """
        try:
            # Pydantic 검증
            validated = NamingRuleSchema(**data)
            
            # 추가 jsonschema 검증 (사용 가능한 경우)
            if HAS_JSONSCHEMA and 'naming_rule' in self.schemas:
                try:
                    validate(data, self.schemas['naming_rule'])
                except JsonSchemaValidationError as e:
                    logger.warning(f"jsonschema validation warning: {e}")
            
            return validated
            
        except ValidationError as e:
            errors = []
            for error in e.errors():
                errors.append({
                    "field": " -> ".join(str(x) for x in error['loc']),
                    "message": error['msg'],
                    "value": error.get('input', 'N/A')
                })
            
            raise SchemaValidationError(
                f"Naming rule validation failed: {len(errors)} errors found",
                errors
            )
        except Exception as e:
            raise SchemaValidationError(f"Unexpected validation error: {e}")
    
    def validate_external_json(self, json_data: Union[str, Dict], schema_type: str = "naming_convention") -> Dict:
        """
        외부 JSON 입력 검증
        
        Args:
            json_data: JSON 문자열 또는 딕셔너리
            schema_type: 스키마 타입 ("naming_convention" 또는 "naming_rule")
            
        Returns:
            검증된 딕셔너리 데이터
            
        Raises:
            SchemaValidationError: 검증 실패 시
        """
        try:
            # JSON 파싱 (문자열인 경우)
            if isinstance(json_data, str):
                try:
                    data = json.loads(json_data)
                except json.JSONDecodeError as e:
                    raise SchemaValidationError(f"Invalid JSON format: {e}")
            else:
                data = json_data
            
            # 스키마별 검증
            if schema_type == "naming_convention":
                validated = self.validate_naming_convention(data)
                return validated.model_dump()
            elif schema_type == "naming_rule":
                validated = self.validate_naming_rule(data)
                return validated.model_dump()
            else:
                raise SchemaValidationError(f"Unknown schema type: {schema_type}")
                
        except SchemaValidationError:
            raise
        except Exception as e:
            raise SchemaValidationError(f"External JSON validation failed: {e}")
    
    def get_schema(self, schema_type: str = "naming_convention") -> Dict:
        """
        JSON 스키마 반환
        
        Args:
            schema_type: 스키마 타입
            
        Returns:
            JSON 스키마 딕셔너리
        """
        return self.schemas.get(schema_type, {})
    
    def export_schema(self, schema_type: str = "naming_convention", file_path: Optional[str] = None) -> str:
        """
        JSON 스키마를 파일로 내보내기
        
        Args:
            schema_type: 스키마 타입
            file_path: 저장할 파일 경로 (None이면 JSON 문자열만 반환)
            
        Returns:
            JSON 스키마 문자열
        """
        schema = self.get_schema(schema_type)
        schema_json = json.dumps(schema, indent=2)
        
        if file_path:
            Path(file_path).parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w') as f:
                f.write(schema_json)
            logger.info(f"Schema exported to {file_path}")
        
        return schema_json


# 싱글톤 인스턴스
_schema_validator = None

def get_schema_validator() -> JsonSchemaValidator:
    """스키마 검증기 인스턴스 반환"""
    global _schema_validator
    if not _schema_validator:
        _schema_validator = JsonSchemaValidator()
    return _schema_validator


def validate_external_naming_convention(data: Union[str, Dict]) -> Dict:
    """
    외부 명명 규칙 데이터 검증 (편의 함수)
    
    Args:
        data: JSON 문자열 또는 딕셔너리
        
    Returns:
        검증된 딕셔너리 데이터
        
    Raises:
        SchemaValidationError: 검증 실패 시
    """
    validator = get_schema_validator()
    return validator.validate_external_json(data, "naming_convention")


def validate_external_naming_rule(data: Union[str, Dict]) -> Dict:
    """
    외부 명명 규칙 데이터 검증 (편의 함수)
    
    Args:
        data: JSON 문자열 또는 딕셔너리
        
    Returns:
        검증된 딕셔너리 데이터
        
    Raises:
        SchemaValidationError: 검증 실패 시
    """
    validator = get_schema_validator()
    return validator.validate_external_json(data, "naming_rule")