"""
Tests for JSON Serialization with Enum handling
JSON 직렬화 및 Enum 처리 테스트
"""
import pytest
import json
import tempfile
from datetime import datetime
from pathlib import Path
from enum import Enum

from core.validation.naming_convention import EntityType, NamingPattern
from core.validation.naming_config import json_serializer, NamingConfigService
from core.validation.naming_history import json_serializer as history_json_serializer


class SampleEnum(str, Enum):
    """테스트용 Enum"""
    TEST_VALUE = "testValue"
    ANOTHER_VALUE = "anotherValue"


class TestJsonSerializer:
    """JSON 직렬화 함수 테스트"""
    
    def test_enum_serialization(self):
        """Enum 직렬화 테스트"""
        # EntityType Enum
        result = json_serializer(EntityType.OBJECT_TYPE)
        assert result == "objectType"
        assert isinstance(result, str)
        
        # NamingPattern Enum  
        result = json_serializer(NamingPattern.CAMEL_CASE)
        assert result == "camelCase"
        assert isinstance(result, str)
        
        # 커스텀 Enum
        result = json_serializer(SampleEnum.TEST_VALUE)
        assert result == "testValue"
        assert isinstance(result, str)
    
    def test_datetime_serialization(self):
        """datetime 직렬화 테스트"""
        dt = datetime(2023, 12, 25, 14, 30, 45)
        result = json_serializer(dt)
        # UTC 시간대가 자동으로 추가됨
        assert result == "2023-12-25T14:30:45+00:00"
        assert isinstance(result, str)
    
    def test_pydantic_model_serialization(self):
        """Pydantic 모델 직렬화 테스트"""
        from core.validation.naming_convention import NamingRule
        
        rule = NamingRule(
            entity_type=EntityType.OBJECT_TYPE,
            pattern=NamingPattern.PASCAL_CASE,
            min_length=3,
            max_length=50
        )
        
        result = json_serializer(rule)
        assert isinstance(result, dict)
        assert result["entity_type"] == "objectType"
        assert result["pattern"] == "PascalCase"
    
    def test_fallback_str_serialization(self):
        """str() fallback 직렬화 테스트"""
        # 숫자
        assert json_serializer(42) == "42"
        
        # __dict__가 없는 객체만 str() fallback 사용
        class CustomObjectWithoutDict:
            __slots__ = ['value']
            
            def __init__(self, value):
                self.value = value
            
            def __str__(self):
                return "custom_string"
        
        obj = CustomObjectWithoutDict("test")
        result = json_serializer(obj)
        assert result == "custom_string"
    
    def test_complex_data_structure(self):
        """복잡한 데이터 구조 직렬화 테스트"""
        data = {
            "entity_type": EntityType.PROPERTY,
            "pattern": NamingPattern.SNAKE_CASE,
            "timestamp": datetime(2023, 1, 1, 12, 0, 0),
            "count": 42,
            "flag": True,
            "nested": {
                "another_enum": SampleEnum.ANOTHER_VALUE
            }
        }
        
        # JSON 직렬화가 성공하는지 확인
        json_str = json.dumps(data, default=json_serializer, indent=2)
        
        # 역직렬화해서 값 확인
        parsed = json.loads(json_str)
        assert parsed["entity_type"] == "property"
        assert parsed["pattern"] == "snake_case"
        assert parsed["timestamp"] == "2023-01-01T12:00:00+00:00"
        assert parsed["nested"]["another_enum"] == "anotherValue"
    
    def test_history_json_serializer_consistency(self):
        """history와 config의 json_serializer 일관성 테스트"""
        # 같은 Enum에 대해 동일한 결과 반환하는지 확인
        enum_value = EntityType.LINK_TYPE
        
        config_result = json_serializer(enum_value)
        history_result = history_json_serializer(enum_value)
        
        assert config_result == history_result == "linkType"


class TestRealWorldJsonSerialization:
    """실제 사용 시나리오에서의 JSON 직렬화 테스트"""
    
    def test_naming_config_save_load(self):
        """NamingConfigService JSON 저장/로드 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "test_config.json"
            history_path = Path(temp_dir) / "test_history.json"
            
            # 서비스 생성
            service = NamingConfigService(str(config_path), str(history_path))
            
            # 테스트 규칙 생성
            from core.validation.naming_convention import NamingConvention, NamingRule
            
            convention = NamingConvention(
                id="test-enum-serialize",
                name="Test Enum Serialization",
                description="Testing enum serialization",
                rules={
                    EntityType.OBJECT_TYPE: NamingRule(
                        entity_type=EntityType.OBJECT_TYPE,
                        pattern=NamingPattern.PASCAL_CASE,
                        min_length=3,
                        max_length=50
                    ),
                    EntityType.PROPERTY: NamingRule(
                        entity_type=EntityType.PROPERTY,
                        pattern=NamingPattern.CAMEL_CASE,
                        min_length=2,
                        max_length=40
                    )
                },
                reserved_words=["test", "example"],
                case_sensitive=True,
                auto_fix_enabled=True,
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
                created_by="test-user"
            )
            
            # 규칙 생성 (JSON 저장 발생)
            service.create_convention(convention, "test-user", "Test enum serialization")
            
            # 파일이 생성되었는지 확인
            assert config_path.exists()
            assert history_path.exists()
            
            # JSON 파일 내용 확인
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            
            # Enum이 올바르게 직렬화되었는지 확인
            saved_convention = config_data["conventions"][0]
            
            # EntityType enum 확인
            object_type_rule = saved_convention["rules"]["objectType"]
            assert object_type_rule["entity_type"] == "objectType"  # .value 사용됨
            assert object_type_rule["pattern"] == "PascalCase"      # .value 사용됨
            
            property_rule = saved_convention["rules"]["property"]
            assert property_rule["entity_type"] == "property"       # .value 사용됨  
            assert property_rule["pattern"] == "camelCase"          # .value 사용됨
            
            # 이력 파일도 확인
            with open(history_path, 'r') as f:
                history_data = json.load(f)
            
            history_entry = history_data["test-enum-serialize"][0]
            assert history_entry["change_type"] == "create"  # Enum.value 사용됨
    
    def test_enum_serialization_edge_cases(self):
        """Enum 직렬화 엣지 케이스 테스트"""
        # 중첩된 구조에서의 Enum
        nested_data = {
            "level1": {
                "level2": {
                    "enum_field": EntityType.FUNCTION_TYPE,
                    "pattern_field": NamingPattern.KEBAB_CASE
                }
            },
            "enum_list": [EntityType.INTERFACE, EntityType.BRANCH],
            "mixed_list": [
                EntityType.DATA_TYPE,
                "string_value", 
                42,
                NamingPattern.UPPER_CASE
            ]
        }
        
        # 직렬화
        json_str = json.dumps(nested_data, default=json_serializer, indent=2)
        
        # 역직렬화
        parsed = json.loads(json_str)
        
        # 중첩된 Enum 확인
        assert parsed["level1"]["level2"]["enum_field"] == "functionType"
        assert parsed["level1"]["level2"]["pattern_field"] == "kebab-case"
        
        # 리스트 내 Enum 확인
        assert parsed["enum_list"] == ["interface", "branch"]
        assert parsed["mixed_list"] == ["dataType", "string_value", 42, "UPPERCASE"]  # 숫자는 그대로 유지됨
    
    def test_enum_vs_string_serialization_comparison(self):
        """Enum vs str() 직렬화 결과 비교"""
        enum_value = EntityType.SHARED_PROPERTY
        
        # 우리의 명시적 방법
        explicit_result = json_serializer(enum_value)
        
        # str() 방법 (기존)
        str_result = str(enum_value)
        
        # 결과 비교
        assert explicit_result == "sharedProperty"  # .value 사용
        assert str_result == "EntityType.SHARED_PROPERTY"  # 실제 str() 결과 (name 사용)
        
        # 우리 방법이 더 깔끔한 JSON을 생성함을 확인
        assert explicit_result != str_result
        assert "EntityType." not in explicit_result
        assert "." not in explicit_result
    
    def test_serialization_consistency_across_modules(self):
        """모듈 간 직렬화 일관성 테스트"""
        test_enums = [
            EntityType.OBJECT_TYPE,
            EntityType.PROPERTY,
            NamingPattern.CAMEL_CASE,
            NamingPattern.PASCAL_CASE
        ]
        
        for enum_val in test_enums:
            config_result = json_serializer(enum_val)
            history_result = history_json_serializer(enum_val)
            
            # 두 모듈의 결과가 동일해야 함
            assert config_result == history_result
            # .value와 동일해야 함
            assert config_result == enum_val.value