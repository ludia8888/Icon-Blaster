"""
Tests for Advanced JSON Features
고급 JSON 기능 테스트 (Pydantic encoders, orjson, UTC timezone, backward compatibility)
"""
import pytest
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.validation.naming_convention import (
    EntityType, NamingPattern, NamingRule, NamingConvention,
    enum_encoder, utc_datetime_encoder
)
from core.validation.naming_config import (
    NamingConfigService, create_utc_timestamp, parse_enum_with_backward_compatibility,
    save_json_optimized, load_json_optimized, HAS_ORJSON
)


class TestPydanticEncoders:
    """Pydantic json_encoders 테스트"""
    
    def test_enum_encoder_function(self):
        """enum_encoder 함수 테스트"""
        # Enum 값
        result = enum_encoder(EntityType.OBJECT_TYPE)
        assert result == "objectType"
        
        result = enum_encoder(NamingPattern.CAMEL_CASE)
        assert result == "camelCase"
        
        # 비 Enum 값은 그대로 반환
        result = enum_encoder("string_value")
        assert result == "string_value"
        
        result = enum_encoder(42)
        assert result == 42
    
    def test_utc_datetime_encoder_function(self):
        """utc_datetime_encoder 함수 테스트"""
        # UTC datetime
        utc_dt = datetime(2023, 12, 25, 14, 30, 45, tzinfo=timezone.utc)
        result = utc_datetime_encoder(utc_dt)
        assert result.endswith("+00:00") or result.endswith("Z")
        
        # Naive datetime (UTC로 가정)
        naive_dt = datetime(2023, 12, 25, 14, 30, 45)
        result = utc_datetime_encoder(naive_dt)
        assert result.endswith("+00:00") or result.endswith("Z")
        
        # 비 datetime 값은 그대로 반환
        result = utc_datetime_encoder("not_datetime")
        assert result == "not_datetime"
    
    def test_pydantic_model_json_serialization(self):
        """Pydantic 모델의 json_encoders 테스트"""
        rule = NamingRule(
            entity_type=EntityType.OBJECT_TYPE,
            pattern=NamingPattern.PASCAL_CASE,
            min_length=3,
            max_length=50
        )
        
        # model_dump()으로 직렬화 시 encoders 적용
        serialized = rule.model_dump()
        
        # Enum이 .value로 직렬화되었는지 확인
        assert serialized["entity_type"] == "objectType"
        assert serialized["pattern"] == "PascalCase"
        
        # JSON 문자열로 변환 테스트
        json_str = rule.model_dump_json()
        parsed = json.loads(json_str)
        
        assert parsed["entity_type"] == "objectType"
        assert parsed["pattern"] == "PascalCase"
    
    def test_naming_convention_json_serialization(self):
        """NamingConvention 모델의 json_encoders 테스트"""
        convention = NamingConvention(
            id="test-convention",
            name="Test Convention",
            description="Test",
            rules={
                EntityType.OBJECT_TYPE: NamingRule(
                    entity_type=EntityType.OBJECT_TYPE,
                    pattern=NamingPattern.PASCAL_CASE,
                    min_length=3,
                    max_length=50
                )
            },
            reserved_words=["test"],
            case_sensitive=True,
            auto_fix_enabled=True,
            created_at=create_utc_timestamp(),
            updated_at=create_utc_timestamp(),
            created_by="test-user"
        )
        
        # model_dump()로 직렬화
        serialized = convention.model_dump()
        
        # rules 딕셔너리의 키가 문자열로 변환되었는지 확인
        assert "objectType" in serialized["rules"]
        rule_data = serialized["rules"]["objectType"]
        assert rule_data["entity_type"] == "objectType"
        assert rule_data["pattern"] == "PascalCase"


class TestUTCTimezone:
    """UTC 시간대 처리 테스트"""
    
    def test_create_utc_timestamp(self):
        """UTC 타임스탬프 생성 테스트"""
        timestamp = create_utc_timestamp()
        
        # ISO 형식인지 확인
        parsed_dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        assert parsed_dt.tzinfo is not None
        
        # UTC 시간대인지 확인 (Z 또는 +00:00)
        assert timestamp.endswith('Z') or timestamp.endswith('+00:00')
    
    def test_utc_timestamp_consistency(self):
        """UTC 타임스탬프 일관성 테스트"""
        # 연속으로 생성한 타임스탬프가 순서대로 증가하는지 확인
        ts1 = create_utc_timestamp()
        ts2 = create_utc_timestamp()
        
        dt1 = datetime.fromisoformat(ts1.replace('Z', '+00:00'))
        dt2 = datetime.fromisoformat(ts2.replace('Z', '+00:00'))
        
        assert dt2 >= dt1
    
    def test_convention_creation_with_utc(self):
        """UTC 시간으로 Convention 생성 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "test_utc.json"
            history_path = Path(temp_dir) / "test_utc_history.json"
            
            service = NamingConfigService(str(config_path), str(history_path))
            
            convention = NamingConvention(
                id="utc-test",
                name="UTC Test",
                description="Testing UTC timestamps",
                rules={
                    EntityType.OBJECT_TYPE: NamingRule(
                        entity_type=EntityType.OBJECT_TYPE,
                        pattern=NamingPattern.PASCAL_CASE,
                        min_length=3,
                        max_length=50
                    )
                },
                reserved_words=[],
                case_sensitive=True,
                auto_fix_enabled=True,
                created_at=create_utc_timestamp(),
                updated_at=create_utc_timestamp(),
                created_by="test-user"
            )
            
            service.create_convention(convention, "test-user", "UTC test")
            
            # 저장된 파일에서 UTC 형식 확인
            with open(config_path, 'r') as f:
                saved_data = json.load(f)
            
            saved_convention = saved_data["conventions"][0]
            
            # 타임스탬프가 UTC 형식인지 확인
            created_at = saved_convention["created_at"]
            updated_at = saved_convention["updated_at"]
            
            assert created_at.endswith('Z') or '+' in created_at
            assert updated_at.endswith('Z') or '+' in updated_at


class TestBackwardCompatibility:
    """백워드 호환성 테스트"""
    
    def test_parse_legacy_enum_format(self):
        """레거시 Enum 형식 파싱 테스트"""
        # EntityType.OBJECT_TYPE → EntityType.OBJECT_TYPE
        result = parse_enum_with_backward_compatibility("EntityType.OBJECT_TYPE", EntityType)
        assert result == EntityType.OBJECT_TYPE
        
        # NamingPattern.CAMEL_CASE → NamingPattern.CAMEL_CASE
        result = parse_enum_with_backward_compatibility("NamingPattern.CAMEL_CASE", NamingPattern)
        assert result == NamingPattern.CAMEL_CASE
        
        # 새로운 형식도 여전히 작동
        result = parse_enum_with_backward_compatibility("objectType", EntityType)
        assert result == EntityType.OBJECT_TYPE
        
        result = parse_enum_with_backward_compatibility("camelCase", NamingPattern)
        assert result == NamingPattern.CAMEL_CASE
    
    def test_parse_legacy_convention_file(self):
        """레거시 형식의 convention 파일 파싱 테스트"""
        legacy_data = {
            "id": "legacy-convention",
            "name": "Legacy Convention",
            "description": "Legacy format test",
            "rules": {
                "EntityType.OBJECT_TYPE": {  # 레거시 키 형식
                    "entity_type": "EntityType.OBJECT_TYPE",  # 레거시 값 형식
                    "pattern": "NamingPattern.PASCAL_CASE",   # 레거시 값 형식
                    "min_length": 3,
                    "max_length": 50
                },
                "property": {  # 혼재: 새로운 키 형식
                    "entity_type": "EntityType.PROPERTY",    # 레거시 값 형식
                    "pattern": "camelCase",                   # 새로운 값 형식
                    "min_length": 2,
                    "max_length": 40
                }
            },
            "reserved_words": ["test"],
            "case_sensitive": True,
            "auto_fix_enabled": True
        }
        
        service = NamingConfigService()
        convention = service._parse_convention(legacy_data)
        
        # 두 규칙 모두 올바르게 파싱되어야 함
        assert len(convention.rules) == 2
        assert EntityType.OBJECT_TYPE in convention.rules
        assert EntityType.PROPERTY in convention.rules
        
        # Enum 값들이 올바르게 변환되었는지 확인
        obj_rule = convention.rules[EntityType.OBJECT_TYPE]
        assert obj_rule.entity_type == EntityType.OBJECT_TYPE
        assert obj_rule.pattern == NamingPattern.PASCAL_CASE
        
        prop_rule = convention.rules[EntityType.PROPERTY]
        assert prop_rule.entity_type == EntityType.PROPERTY
        assert prop_rule.pattern == NamingPattern.CAMEL_CASE
    
    def test_mixed_format_round_trip(self):
        """혼재 형식 라운드트립 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "mixed_format.json"
            
            # 레거시 형식으로 파일 작성
            legacy_data = {
                "conventions": [{
                    "id": "mixed-test",
                    "name": "Mixed Format Test",
                    "rules": {
                        "EntityType.OBJECT_TYPE": {
                            "entity_type": "EntityType.OBJECT_TYPE",
                            "pattern": "NamingPattern.PASCAL_CASE",
                            "min_length": 3,
                            "max_length": 50
                        }
                    },
                    "reserved_words": [],
                    "case_sensitive": True,
                    "auto_fix_enabled": True,
                    "created_at": "2023-01-01T12:00:00+00:00",
                    "updated_at": "2023-01-01T12:00:00+00:00",
                    "created_by": "legacy-system"
                }]
            }
            
            with open(config_path, 'w') as f:
                json.dump(legacy_data, f, indent=2)
            
            # 서비스로 로드
            service = NamingConfigService(str(config_path))
            loaded_convention = service.get_convention("mixed-test")
            
            # 올바르게 로드되었는지 확인
            assert loaded_convention is not None
            assert loaded_convention.id == "mixed-test"
            assert len(loaded_convention.rules) == 1
            
            # 업데이트 후 다시 저장
            service.update_convention(
                "mixed-test",
                {"description": "Updated description"},
                "modern-user",
                "Modernization test"
            )
            
            # 새로 저장된 파일 확인
            with open(config_path, 'r') as f:
                saved_data = json.load(f)
            
            saved_convention = saved_data["conventions"][0]
            
            # 새로운 형식으로 저장되었는지 확인
            assert "objectType" in saved_convention["rules"]
            rule_data = saved_convention["rules"]["objectType"]
            assert rule_data["entity_type"] == "objectType"
            assert rule_data["pattern"] == "PascalCase"


class TestORJsonOptimization:
    """orjson 최적화 테스트"""
    
    def test_save_load_json_optimized_fallback(self):
        """orjson 없을 때 표준 JSON fallback 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test_fallback.json"
            
            test_data = {
                "test_enum": EntityType.OBJECT_TYPE.value,
                "test_datetime": create_utc_timestamp(),
                "test_number": 42,
                "test_string": "hello"
            }
            
            # orjson 비활성화하고 저장
            save_json_optimized(test_data, file_path, use_orjson=False)
            
            # 파일이 생성되었는지 확인
            assert file_path.exists()
            
            # 로드 테스트
            loaded_data = load_json_optimized(file_path, use_orjson=False)
            
            assert loaded_data["test_enum"] == "objectType"
            assert loaded_data["test_number"] == 42
            assert loaded_data["test_string"] == "hello"
    
    @pytest.mark.skipif(not HAS_ORJSON, reason="orjson not available")
    def test_save_load_json_optimized_orjson(self):
        """orjson 사용 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test_orjson.json"
            
            test_data = {
                "test_enum": EntityType.PROPERTY.value,
                "test_datetime": create_utc_timestamp(),
                "test_list": [1, 2, 3],
                "nested": {
                    "enum": NamingPattern.SNAKE_CASE.value,
                    "value": "test"
                }
            }
            
            # orjson으로 저장
            save_json_optimized(test_data, file_path, use_orjson=True)
            
            # 파일이 생성되었는지 확인
            assert file_path.exists()
            
            # orjson으로 로드
            loaded_data = load_json_optimized(file_path, use_orjson=True)
            
            assert loaded_data["test_enum"] == "property"
            assert loaded_data["test_list"] == [1, 2, 3]
            assert loaded_data["nested"]["enum"] == "snake_case"
            assert loaded_data["nested"]["value"] == "test"
    
    def test_orjson_error_fallback(self):
        """orjson 에러 시 표준 JSON으로 fallback 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test_error_fallback.json"
            
            test_data = {
                "normal_data": "test",
                "enum": EntityType.FUNCTION_TYPE.value
            }
            
            if HAS_ORJSON:
                # orjson이 있는 경우 에러 발생 시뮬레이션
                with patch('core.validation.naming_config.orjson.dumps', side_effect=Exception("Mock orjson error")):
                    # 에러가 발생해도 표준 JSON으로 저장되어야 함
                    save_json_optimized(test_data, file_path, use_orjson=True)
                    
                    # 파일이 생성되었는지 확인
                    assert file_path.exists()
                    
                    # 표준 JSON으로 로드 가능한지 확인
                    with open(file_path, 'r') as f:
                        loaded_data = json.load(f)
                    
                    assert loaded_data["normal_data"] == "test"
                    assert loaded_data["enum"] == "functionType"
            else:
                # orjson이 없는 경우 표준 JSON 동작 확인
                save_json_optimized(test_data, file_path, use_orjson=True)
                
                # 파일이 생성되었는지 확인
                assert file_path.exists()
                
                # 표준 JSON으로 로드 가능한지 확인
                with open(file_path, 'r') as f:
                    loaded_data = json.load(f)
                
                assert loaded_data["normal_data"] == "test"
                assert loaded_data["enum"] == "functionType"


class TestIntegrationAllFeatures:
    """모든 기능 통합 테스트"""
    
    def test_full_feature_integration(self):
        """모든 고급 기능 통합 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "integration_test.json"
            history_path = Path(temp_dir) / "integration_history.json"
            
            # 레거시 형식 파일 생성
            legacy_data = {
                "conventions": [{
                    "id": "integration-test",
                    "name": "Integration Test",
                    "rules": {
                        "EntityType.OBJECT_TYPE": {
                            "entity_type": "EntityType.OBJECT_TYPE",
                            "pattern": "NamingPattern.PASCAL_CASE",
                            "min_length": 3,
                            "max_length": 50
                        }
                    },
                    "reserved_words": ["legacy"],
                    "case_sensitive": True,
                    "auto_fix_enabled": True,
                    "created_at": "2023-01-01T12:00:00",  # naive datetime
                    "updated_at": "2023-01-01T12:00:00",
                    "created_by": "legacy-system"
                }]
            }
            
            # 표준 JSON으로 레거시 파일 저장
            with open(config_path, 'w') as f:
                json.dump(legacy_data, f, indent=2)
            
            # 서비스로 로드 (백워드 호환성)
            service = NamingConfigService(str(config_path), str(history_path))
            
            # 로드된 데이터 확인
            convention = service.get_convention("integration-test")
            assert convention is not None
            assert len(convention.rules) == 1
            assert EntityType.OBJECT_TYPE in convention.rules
            
            # 새로운 규칙 추가 (현대적 방식)
            updates = {
                "description": "Updated with modern features",
                "reserved_words": ["legacy", "modern"]
            }
            
            # UTC 시간으로 업데이트
            service.update_convention(
                "integration-test",
                updates,
                "modern-user",
                "Added modern features"
            )
            
            # 새로 저장된 파일 확인
            saved_data = load_json_optimized(config_path)
            saved_convention = saved_data["conventions"][0]
            
            # 1. Pydantic encoders: Enum이 .value로 직렬화
            assert "objectType" in saved_convention["rules"]
            rule_data = saved_convention["rules"]["objectType"]
            assert rule_data["entity_type"] == "objectType"
            assert rule_data["pattern"] == "PascalCase"
            
            # 2. UTC 시간대: updated_at이 UTC 형식
            updated_at = saved_convention["updated_at"]
            assert updated_at.endswith('Z') or '+' in updated_at
            
            # 3. 백워드 호환성: 레거시 데이터가 현대적 형식으로 변환
            assert saved_convention["description"] == "Updated with modern features"
            assert saved_convention["reserved_words"] == ["legacy", "modern"]
            
            # 4. 이력도 UTC 시간으로 기록되었는지 확인
            history_data = load_json_optimized(history_path)
            history_entry = history_data["integration-test"][-1]  # 마지막 업데이트 이력
            
            changed_at = history_entry["changed_at"]
            assert changed_at.endswith('Z') or '+' in changed_at
            assert history_entry["change_type"] == "update"
    
    def test_performance_comparison(self):
        """성능 비교 테스트 (orjson vs 표준 JSON)"""
        import time
        
        # 큰 데이터 세트 생성
        large_data = {
            "conventions": []
        }
        
        for i in range(100):  # 100개의 convention
            convention_data = {
                "id": f"perf-test-{i}",
                "name": f"Performance Test Convention {i}",
                "description": "Large dataset for performance testing",
                "rules": {}
            }
            
            # 각 convention에 모든 EntityType 규칙 추가
            for entity_type in EntityType:
                for pattern in NamingPattern:
                    rule_key = f"{entity_type.value}_{pattern.value}_{i}"
                    convention_data["rules"][rule_key] = {
                        "entity_type": entity_type.value,
                        "pattern": pattern.value,
                        "min_length": i % 10 + 1,
                        "max_length": i % 100 + 50,
                        "allow_numbers": i % 2 == 0,
                        "allow_underscores": i % 3 == 0
                    }
            
            large_data["conventions"].append(convention_data)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "performance_test.json"
            
            # 표준 JSON 저장 시간 측정
            start_time = time.time()
            save_json_optimized(large_data, file_path, use_orjson=False)
            standard_save_time = time.time() - start_time
            
            # 표준 JSON 로드 시간 측정
            start_time = time.time()
            loaded_standard = load_json_optimized(file_path, use_orjson=False)
            standard_load_time = time.time() - start_time
            
            if HAS_ORJSON:
                # orjson 저장 시간 측정
                start_time = time.time()
                save_json_optimized(large_data, file_path, use_orjson=True)
                orjson_save_time = time.time() - start_time
                
                # orjson 로드 시간 측정
                start_time = time.time()
                loaded_orjson = load_json_optimized(file_path, use_orjson=True)
                orjson_load_time = time.time() - start_time
                
                # 결과가 동일한지 확인
                assert len(loaded_standard["conventions"]) == len(loaded_orjson["conventions"])
                
                # 성능 정보 출력 (테스트 통과 여부와 무관)
                print(f"\nPerformance comparison (100 conventions):")
                print(f"Standard JSON - Save: {standard_save_time:.4f}s, Load: {standard_load_time:.4f}s")
                print(f"orjson - Save: {orjson_save_time:.4f}s, Load: {orjson_load_time:.4f}s")
                print(f"orjson speedup - Save: {standard_save_time/orjson_save_time:.2f}x, Load: {standard_load_time/orjson_load_time:.2f}x")
            else:
                print(f"\nStandard JSON only - Save: {standard_save_time:.4f}s, Load: {standard_load_time:.4f}s")
                print("orjson not available for comparison")
            
            # 데이터 무결성 확인
            assert len(loaded_standard["conventions"]) == 100
            first_convention = loaded_standard["conventions"][0]
            assert first_convention["id"] == "perf-test-0"
            assert len(first_convention["rules"]) > 0