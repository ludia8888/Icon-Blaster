"""
Tests for JSON Schema Validation
JSON 스키마 검증 기능 테스트
"""
import pytest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

from core.validation.schema_validator import (
    JsonSchemaValidator, NamingConventionSchema, NamingRuleSchema,
    SchemaValidationError, get_schema_validator,
    validate_external_naming_convention, validate_external_naming_rule
)
from core.validation.naming_convention import EntityType, NamingPattern
from core.validation.naming_config import NamingConfigService


class TestNamingConventionSchema:
    """NamingConventionSchema 검증 테스트"""
    
    def test_valid_naming_convention_schema(self):
        """유효한 명명 규칙 스키마 테스트"""
        valid_data = {
            "__version__": "1.0.0",
            "id": "test-convention",
            "name": "Test Convention",
            "description": "Test description",
            "rules": {
                EntityType.OBJECT_TYPE: {
                    "entity_type": EntityType.OBJECT_TYPE,
                    "pattern": NamingPattern.PASCAL_CASE,
                    "min_length": 3,
                    "max_length": 50
                }
            },
            "reserved_words": ["test", "example"],
            "case_sensitive": True,
            "auto_fix_enabled": True,
            "created_at": "2024-01-01T12:00:00Z",
            "updated_at": "2024-01-01T12:00:00Z",
            "created_by": "test-user"
        }
        
        schema = NamingConventionSchema(**valid_data)
        assert schema.id == "test-convention"
        assert schema.name == "Test Convention"
        assert len(schema.rules) == 1
        assert schema.case_sensitive is True
        assert schema.schema_version == "1.0.0"
    
    def test_invalid_id_format(self):
        """잘못된 ID 형식 테스트"""
        invalid_data = {
            "id": "invalid@id!",  # 특수문자 포함
            "name": "Test Convention",
            "rules": {},
            "created_at": "2024-01-01T12:00:00Z",
            "updated_at": "2024-01-01T12:00:00Z",
            "created_by": "test-user"
        }
        
        with pytest.raises(Exception):  # ValidationError
            NamingConventionSchema(**invalid_data)
    
    def test_invalid_timestamp_format(self):
        """잘못된 타임스탬프 형식 테스트"""
        invalid_data = {
            "id": "test-convention",
            "name": "Test Convention",
            "rules": {},
            "created_at": "invalid-timestamp",
            "updated_at": "2024-01-01T12:00:00Z",
            "created_by": "test-user"
        }
        
        with pytest.raises(Exception):  # ValidationError
            NamingConventionSchema(**invalid_data)
    
    def test_empty_rules_validation(self):
        """빈 규칙 검증 테스트"""
        invalid_data = {
            "id": "test-convention",
            "name": "Test Convention",
            "rules": {},  # 빈 규칙
            "created_at": "2024-01-01T12:00:00Z",
            "updated_at": "2024-01-01T12:00:00Z",
            "created_by": "test-user"
        }
        
        with pytest.raises(Exception):  # ValidationError
            NamingConventionSchema(**invalid_data)
    
    def test_reserved_words_deduplication(self):
        """예약어 중복 제거 테스트"""
        data = {
            "id": "test-convention",
            "name": "Test Convention",
            "rules": {
                EntityType.OBJECT_TYPE: {
                    "entity_type": EntityType.OBJECT_TYPE,
                    "pattern": NamingPattern.PASCAL_CASE,
                    "min_length": 3,
                    "max_length": 50
                }
            },
            "reserved_words": ["test", "example", "test", "", "  ", "example"],  # 중복 및 빈 값
            "created_at": "2024-01-01T12:00:00Z",
            "updated_at": "2024-01-01T12:00:00Z",
            "created_by": "test-user"
        }
        
        schema = NamingConventionSchema(**data)
        # 중복 제거 및 빈 값 제거 확인
        assert set(schema.reserved_words) == {"test", "example"}


class TestNamingRuleSchema:
    """NamingRuleSchema 검증 테스트"""
    
    def test_valid_naming_rule_schema(self):
        """유효한 명명 규칙 스키마 테스트"""
        valid_data = {
            "entity_type": EntityType.OBJECT_TYPE,
            "pattern": NamingPattern.PASCAL_CASE,
            "min_length": 3,
            "max_length": 50,
            "allow_numbers": True,
            "allow_underscores": False,
            "description": "Test rule"
        }
        
        schema = NamingRuleSchema(**valid_data)
        assert schema.entity_type == EntityType.OBJECT_TYPE
        assert schema.pattern == NamingPattern.PASCAL_CASE
        assert schema.min_length == 3
        assert schema.max_length == 50
    
    def test_invalid_length_range(self):
        """잘못된 길이 범위 테스트"""
        invalid_data = {
            "entity_type": EntityType.OBJECT_TYPE,
            "pattern": NamingPattern.PASCAL_CASE,
            "min_length": 50,
            "max_length": 10,  # min_length보다 작음
            "allow_numbers": True,
            "allow_underscores": False
        }
        
        with pytest.raises(Exception):  # ValidationError
            NamingRuleSchema(**invalid_data)
    
    def test_invalid_regex_pattern(self):
        """잘못된 정규식 패턴 테스트"""
        invalid_data = {
            "entity_type": EntityType.OBJECT_TYPE,
            "pattern": NamingPattern.PASCAL_CASE,
            "min_length": 3,
            "max_length": 50,
            "custom_regex": "[invalid(regex",  # 잘못된 정규식
            "allow_numbers": True,
            "allow_underscores": False
        }
        
        with pytest.raises(Exception):  # ValidationError
            NamingRuleSchema(**invalid_data)
    
    def test_valid_regex_pattern(self):
        """유효한 정규식 패턴 테스트"""
        valid_data = {
            "entity_type": EntityType.OBJECT_TYPE,
            "pattern": NamingPattern.PASCAL_CASE,
            "min_length": 3,
            "max_length": 50,
            "custom_regex": r"^[A-Z][a-zA-Z0-9]*$",  # 유효한 정규식
            "allow_numbers": True,
            "allow_underscores": False
        }
        
        schema = NamingRuleSchema(**valid_data)
        assert schema.custom_regex == r"^[A-Z][a-zA-Z0-9]*$"


class TestJsonSchemaValidator:
    """JsonSchemaValidator 클래스 테스트"""
    
    def test_validator_initialization(self):
        """검증기 초기화 테스트"""
        validator = JsonSchemaValidator()
        assert 'naming_convention' in validator.schemas
        assert 'naming_rule' in validator.schemas
        assert isinstance(validator.schemas['naming_convention'], dict)
        assert isinstance(validator.schemas['naming_rule'], dict)
    
    def test_validate_naming_convention_success(self):
        """명명 규칙 검증 성공 테스트"""
        validator = JsonSchemaValidator()
        
        valid_data = {
            "__version__": "1.0.0",
            "id": "test-convention",
            "name": "Test Convention",
            "rules": {
                "objectType": {
                    "entity_type": "objectType",
                    "pattern": "PascalCase",
                    "min_length": 3,
                    "max_length": 50
                }
            },
            "reserved_words": ["test"],
            "case_sensitive": True,
            "auto_fix_enabled": True,
            "created_at": "2024-01-01T12:00:00Z",
            "updated_at": "2024-01-01T12:00:00Z",
            "created_by": "test-user"
        }
        
        result = validator.validate_naming_convention(valid_data)
        assert result.id == "test-convention"
        assert result.name == "Test Convention"
    
    def test_validate_naming_convention_failure(self):
        """명명 규칙 검증 실패 테스트"""
        validator = JsonSchemaValidator()
        
        invalid_data = {
            "id": "",  # 빈 ID
            "name": "Test Convention",
            "rules": {},  # 빈 규칙
            "created_at": "invalid-date",
            "updated_at": "2024-01-01T12:00:00Z",
            "created_by": "test-user"
        }
        
        with pytest.raises(SchemaValidationError) as exc_info:
            validator.validate_naming_convention(invalid_data)
        
        assert "validation failed" in str(exc_info.value)
        assert len(exc_info.value.errors) > 0
    
    def test_validate_external_json_string(self):
        """외부 JSON 문자열 검증 테스트"""
        validator = JsonSchemaValidator()
        
        json_string = json.dumps({
            "__version__": "1.0.0",
            "id": "external-test",
            "name": "External Test",
            "rules": {
                "objectType": {
                    "entity_type": "objectType",
                    "pattern": "PascalCase",
                    "min_length": 3,
                    "max_length": 50
                }
            },
            "reserved_words": [],
            "case_sensitive": True,
            "auto_fix_enabled": True,
            "created_at": "2024-01-01T12:00:00Z",
            "updated_at": "2024-01-01T12:00:00Z",
            "created_by": "external-user"
        })
        
        result = validator.validate_external_json(json_string, "naming_convention")
        assert result["id"] == "external-test"
        assert result["name"] == "External Test"
    
    def test_validate_invalid_json_string(self):
        """잘못된 JSON 문자열 검증 테스트"""
        validator = JsonSchemaValidator()
        
        invalid_json = "{ invalid json format"
        
        with pytest.raises(SchemaValidationError) as exc_info:
            validator.validate_external_json(invalid_json, "naming_convention")
        
        assert "Invalid JSON format" in str(exc_info.value)
    
    def test_get_schema(self):
        """스키마 반환 테스트"""
        validator = JsonSchemaValidator()
        
        schema = validator.get_schema("naming_convention")
        assert isinstance(schema, dict)
        assert "properties" in schema
        assert "required" in schema
        
        # 필수 필드 확인
        required_fields = schema["required"]
        assert "id" in required_fields
        assert "name" in required_fields
        assert "rules" in required_fields
    
    def test_export_schema(self):
        """스키마 내보내기 테스트"""
        validator = JsonSchemaValidator()
        
        # 문자열로 내보내기
        schema_json = validator.export_schema("naming_convention")
        assert isinstance(schema_json, str)
        
        # JSON 파싱 가능한지 확인
        schema_dict = json.loads(schema_json)
        assert "properties" in schema_dict
        
        # 파일로 내보내기
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "schema.json"
            schema_json = validator.export_schema("naming_convention", str(file_path))
            
            assert file_path.exists()
            with open(file_path) as f:
                saved_schema = json.load(f)
            assert "properties" in saved_schema


class TestSchemaIntegration:
    """스키마 검증 통합 테스트"""
    
    def test_naming_config_service_schema_integration(self):
        """NamingConfigService와 스키마 검증 통합 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "test_config.json"
            
            service = NamingConfigService(str(config_path))
            
            # 유효한 데이터 검증
            valid_data = {
                "__version__": "1.0.0",
                "id": "schema-test",
                "name": "Schema Test Convention",
                "rules": {
                    "objectType": {
                        "entity_type": "objectType",
                        "pattern": "PascalCase",
                        "min_length": 3,
                        "max_length": 50
                    }
                },
                "reserved_words": ["test"],
                "case_sensitive": True,
                "auto_fix_enabled": True,
                "created_at": "2024-01-01T12:00:00Z",
                "updated_at": "2024-01-01T12:00:00Z",
                "created_by": "schema-user"
            }
            
            # 스키마 검증을 통한 가져오기
            convention = service.import_convention(valid_data, "test-user", "Schema validation test")
            assert convention.id == "schema-test"
            assert convention.name == "Schema Test Convention"
    
    def test_naming_config_service_schema_validation_failure(self):
        """NamingConfigService 스키마 검증 실패 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "test_config.json"
            
            service = NamingConfigService(str(config_path))
            
            # 잘못된 데이터
            invalid_data = {
                "id": "",  # 빈 ID
                "name": "Invalid Convention",
                "rules": {},  # 빈 규칙
                "created_at": "invalid-date",
                "updated_at": "2024-01-01T12:00:00Z",
                "created_by": "test-user"
            }
            
            # 스키마 검증을 통한 가져오기 실패
            with pytest.raises(ValueError) as exc_info:
                service.import_convention(invalid_data, "test-user", "Should fail")
            
            assert "schema validation errors" in str(exc_info.value)
    
    def test_schema_validation_disabled(self):
        """스키마 검증 비활성화 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "test_config.json"
            
            service = NamingConfigService(str(config_path))
            
            # 잘못된 데이터지만 스키마 검증 비활성화
            invalid_data = {
                "id": "bypass-test",
                "name": "Bypass Test Convention",
                "rules": {},  # 빈 규칙이지만 _parse_convention에서 처리됨
                "created_at": "2024-01-01T12:00:00Z",
                "updated_at": "2024-01-01T12:00:00Z",
                "created_by": "test-user"
            }
            
            # 스키마 검증 비활성화하여 가져오기
            convention = service.import_convention(
                invalid_data, 
                "test-user", 
                "Bypass schema validation", 
                validate_schema=False
            )
            assert convention.id == "bypass-test"
    
    def test_export_schema_through_service(self):
        """서비스를 통한 스키마 내보내기 테스트"""
        service = NamingConfigService()
        
        # 스키마 내보내기
        schema_json = service.export_schema("naming_convention")
        assert isinstance(schema_json, str)
        
        # JSON 파싱 가능한지 확인
        schema_dict = json.loads(schema_json)
        assert "properties" in schema_dict
        assert "title" in schema_dict
        assert schema_dict["title"] == "Naming Convention Schema"


class TestConvenienceFunctions:
    """편의 함수 테스트"""
    
    def test_validate_external_naming_convention_function(self):
        """외부 명명 규칙 검증 편의 함수 테스트"""
        valid_data = {
            "__version__": "1.0.0",
            "id": "convenience-test",
            "name": "Convenience Test",
            "rules": {
                "objectType": {
                    "entity_type": "objectType",
                    "pattern": "PascalCase",
                    "min_length": 3,
                    "max_length": 50
                }
            },
            "reserved_words": [],
            "case_sensitive": True,
            "auto_fix_enabled": True,
            "created_at": "2024-01-01T12:00:00Z",
            "updated_at": "2024-01-01T12:00:00Z",
            "created_by": "convenience-user"
        }
        
        result = validate_external_naming_convention(valid_data)
        assert result["id"] == "convenience-test"
        assert result["name"] == "Convenience Test"
    
    def test_validate_external_naming_rule_function(self):
        """외부 명명 규칙 검증 편의 함수 테스트"""
        valid_data = {
            "entity_type": "objectType",
            "pattern": "PascalCase",
            "min_length": 3,
            "max_length": 50,
            "allow_numbers": True,
            "allow_underscores": False
        }
        
        result = validate_external_naming_rule(valid_data)
        assert result["entity_type"] == "objectType"
        assert result["pattern"] == "PascalCase"
    
    def test_get_schema_validator_singleton(self):
        """스키마 검증기 싱글톤 테스트"""
        validator1 = get_schema_validator()
        validator2 = get_schema_validator()
        
        # 동일한 인스턴스인지 확인
        assert validator1 is validator2


class TestSchemaErrorHandling:
    """스키마 에러 처리 테스트"""
    
    def test_schema_validation_error_with_details(self):
        """상세한 스키마 검증 에러 테스트"""
        validator = JsonSchemaValidator()
        
        invalid_data = {
            "id": "a",  # 너무 짧음
            "name": "",  # 빈 이름
            "rules": {},  # 빈 규칙
            "created_at": "not-a-date",
            "updated_at": "2024-01-01T12:00:00Z",
            "created_by": ""  # 빈 생성자
        }
        
        with pytest.raises(SchemaValidationError) as exc_info:
            validator.validate_naming_convention(invalid_data)
        
        error = exc_info.value
        assert len(error.errors) > 0
        
        # 에러 필드 확인
        error_fields = [err["field"] for err in error.errors]
        assert any("name" in field for field in error_fields)
        assert any("rules" in field for field in error_fields)
        assert any("created_at" in field for field in error_fields)
    
    def test_unknown_schema_type_error(self):
        """알 수 없는 스키마 타입 에러 테스트"""
        validator = JsonSchemaValidator()
        
        with pytest.raises(SchemaValidationError) as exc_info:
            validator.validate_external_json({}, "unknown_schema")
        
        assert "Unknown schema type" in str(exc_info.value)