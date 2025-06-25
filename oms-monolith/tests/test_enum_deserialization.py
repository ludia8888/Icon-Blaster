"""
Tests for Enum Deserialization (Load) routines
Enum 역직렬화(Load) 루틴 테스트
"""
import pytest
import json
import tempfile
from datetime import datetime
from pathlib import Path
from enum import Enum

from core.validation.naming_convention import EntityType, NamingPattern, NamingRule, NamingConvention
from core.validation.naming_config import safe_enum_parse, NamingConfigService
from core.validation.naming_history import (
    safe_enum_parse as history_safe_enum_parse, 
    NamingConventionHistory, ChangeType, ChangeDiff
)


class TestSafeEnumParse:
    """안전한 Enum 파싱 함수 테스트"""
    
    def test_valid_enum_by_value(self):
        """유효한 Enum value로 파싱 테스트"""
        # EntityType 파싱
        result = safe_enum_parse(EntityType, "objectType")
        assert result == EntityType.OBJECT_TYPE
        assert isinstance(result, EntityType)
        
        # NamingPattern 파싱
        result = safe_enum_parse(NamingPattern, "camelCase")
        assert result == NamingPattern.CAMEL_CASE
        assert isinstance(result, NamingPattern)
        
        # ChangeType 파싱
        result = safe_enum_parse(ChangeType, "create")
        assert result == ChangeType.CREATE
        assert isinstance(result, ChangeType)
    
    def test_valid_enum_by_name(self):
        """유효한 Enum name으로 파싱 테스트 (호환성)"""
        # name으로 파싱
        result = safe_enum_parse(EntityType, "OBJECT_TYPE")
        assert result == EntityType.OBJECT_TYPE
        
        result = safe_enum_parse(NamingPattern, "CAMEL_CASE")
        assert result == NamingPattern.CAMEL_CASE
    
    def test_case_insensitive_parsing(self):
        """대소문자 무시 파싱 테스트"""
        # value 대소문자 무시
        result = safe_enum_parse(EntityType, "OBJECTTYPE")
        assert result == EntityType.OBJECT_TYPE
        
        result = safe_enum_parse(NamingPattern, "CAMELCASE")
        assert result == NamingPattern.CAMEL_CASE
        
        # name 대소문자 무시
        result = safe_enum_parse(EntityType, "object_type")
        assert result == EntityType.OBJECT_TYPE
    
    def test_already_enum_instance(self):
        """이미 Enum 인스턴스인 경우 테스트"""
        enum_value = EntityType.PROPERTY
        result = safe_enum_parse(EntityType, enum_value)
        assert result is enum_value  # 동일한 인스턴스
    
    def test_invalid_value_with_default(self):
        """잘못된 값에 대한 기본값 반환 테스트"""
        default_value = EntityType.OBJECT_TYPE
        result = safe_enum_parse(EntityType, "invalid_value", default=default_value)
        assert result == default_value
    
    def test_invalid_value_without_default(self):
        """잘못된 값에 대한 예외 발생 테스트"""
        with pytest.raises(ValueError) as exc_info:
            safe_enum_parse(EntityType, "totally_invalid")
        
        assert "Cannot convert 'totally_invalid' to EntityType" in str(exc_info.value)
        assert "Valid values:" in str(exc_info.value)
    
    def test_none_and_empty_values(self):
        """None 및 빈 값 처리 테스트"""
        default_value = EntityType.PROPERTY
        
        # None with default
        result = safe_enum_parse(EntityType, None, default=default_value)
        assert result == default_value
        
        # Empty string with default
        result = safe_enum_parse(EntityType, "", default=default_value)
        assert result == default_value
        
        # None without default - should raise
        with pytest.raises(ValueError):
            safe_enum_parse(EntityType, None)
        
        # Empty string without default - should raise
        with pytest.raises(ValueError):
            safe_enum_parse(EntityType, "")
    
    def test_history_and_config_consistency(self):
        """history와 config 모듈의 safe_enum_parse 일관성 테스트"""
        test_values = [
            (EntityType, "objectType"),
            (NamingPattern, "PascalCase"),
            (ChangeType, "update")
        ]
        
        for enum_class, value in test_values:
            if enum_class == ChangeType:
                # ChangeType은 history 모듈에만 있음
                result = history_safe_enum_parse(enum_class, value)
                assert isinstance(result, enum_class)
            else:
                # EntityType과 NamingPattern은 두 모듈 모두에서 동일해야 함
                config_result = safe_enum_parse(enum_class, value)
                history_result = history_safe_enum_parse(enum_class, value)
                assert config_result == history_result


class TestNamingConventionDeserialization:
    """NamingConvention 역직렬화 테스트"""
    
    def test_parse_convention_with_valid_enums(self):
        """유효한 Enum이 포함된 convention 파싱 테스트"""
        data = {
            "id": "test-convention",
            "name": "Test Convention",
            "description": "Test description",
            "rules": {
                "objectType": {
                    "entity_type": "objectType",
                    "pattern": "PascalCase",
                    "min_length": 3,
                    "max_length": 50
                },
                "property": {
                    "entity_type": "property", 
                    "pattern": "camelCase",
                    "min_length": 2,
                    "max_length": 40
                }
            },
            "reserved_words": ["test", "example"],
            "case_sensitive": True,
            "auto_fix_enabled": True,
            "created_at": "2023-01-01T12:00:00",
            "updated_at": "2023-01-01T12:00:00",
            "created_by": "test-user"
        }
        
        service = NamingConfigService()
        convention = service._parse_convention(data)
        
        assert convention.id == "test-convention"
        assert convention.name == "Test Convention"
        assert len(convention.rules) == 2
        
        # ObjectType 규칙 확인
        obj_rule = convention.rules[EntityType.OBJECT_TYPE]
        assert obj_rule.entity_type == EntityType.OBJECT_TYPE
        assert obj_rule.pattern == NamingPattern.PASCAL_CASE
        
        # Property 규칙 확인
        prop_rule = convention.rules[EntityType.PROPERTY]
        assert prop_rule.entity_type == EntityType.PROPERTY
        assert prop_rule.pattern == NamingPattern.CAMEL_CASE
    
    def test_parse_convention_with_legacy_enum_names(self):
        """레거시 Enum name 포맷으로 파싱 테스트"""
        data = {
            "id": "legacy-convention",
            "name": "Legacy Convention",
            "rules": {
                "OBJECT_TYPE": {  # name 포맷
                    "entity_type": "OBJECT_TYPE",
                    "pattern": "PASCAL_CASE",
                    "min_length": 3,
                    "max_length": 50
                }
            },
            "reserved_words": [],
            "case_sensitive": True,
            "auto_fix_enabled": True
        }
        
        service = NamingConfigService()
        convention = service._parse_convention(data)
        
        # 올바르게 파싱되어야 함
        assert len(convention.rules) == 1
        obj_rule = convention.rules[EntityType.OBJECT_TYPE]
        assert obj_rule.entity_type == EntityType.OBJECT_TYPE
        assert obj_rule.pattern == NamingPattern.PASCAL_CASE
    
    def test_parse_convention_with_invalid_enum(self):
        """잘못된 Enum 값에 대한 처리 테스트"""
        data = {
            "id": "invalid-convention",
            "name": "Invalid Convention",
            "rules": {
                "objectType": {
                    "entity_type": "objectType",
                    "pattern": "PascalCase",
                    "min_length": 3,
                    "max_length": 50
                },
                "invalidEntityType": {  # 잘못된 entity type
                    "entity_type": "invalidEntityType",
                    "pattern": "invalidPattern",  # 잘못된 pattern
                    "min_length": 1,
                    "max_length": 10
                }
            },
            "reserved_words": []
        }
        
        service = NamingConfigService()
        convention = service._parse_convention(data)
        
        # 유효한 규칙만 파싱되고, 잘못된 규칙은 건너뛰어야 함
        assert len(convention.rules) == 1
        assert EntityType.OBJECT_TYPE in convention.rules
    
    def test_parse_convention_missing_required_fields(self):
        """필수 필드 누락 시 예외 발생 테스트"""
        # ID 누락
        data_no_id = {
            "name": "Test Convention",
            "rules": {}
        }
        
        service = NamingConfigService()
        with pytest.raises(ValueError) as exc_info:
            service._parse_convention(data_no_id)
        assert "Convention ID is required" in str(exc_info.value)
        
        # Name 누락
        data_no_name = {
            "id": "test-convention", 
            "rules": {}
        }
        
        with pytest.raises(ValueError) as exc_info:
            service._parse_convention(data_no_name)
        assert "Convention name is required" in str(exc_info.value)


class TestHistoryDeserialization:
    """History 역직렬화 테스트"""
    
    def test_history_from_dict_with_valid_enums(self):
        """유효한 Enum이 포함된 history 역직렬화 테스트"""
        data = {
            "id": "test_v1_123456",
            "convention_id": "test-convention",
            "version": 1,
            "change_type": "create",
            "change_summary": "Created convention",
            "diffs": [
                {
                    "field": "name",
                    "old_value": None,
                    "new_value": "New Convention",
                    "path": "name"
                }
            ],
            "full_snapshot": {"id": "test", "name": "Test"},
            "changed_by": "test-user",
            "changed_at": "2023-01-01T12:00:00",
            "change_reason": "Initial creation"
        }
        
        history = NamingConventionHistory.from_dict(data)
        
        assert history.id == "test_v1_123456"
        assert history.convention_id == "test-convention"
        assert history.version == 1
        assert history.change_type == ChangeType.CREATE
        assert history.change_summary == "Created convention"
        assert len(history.diffs) == 1
        assert history.changed_by == "test-user"
        assert history.change_reason == "Initial creation"
    
    def test_history_from_dict_with_invalid_change_type(self):
        """잘못된 ChangeType에 대한 처리 테스트"""
        data = {
            "id": "test_v1_123456",
            "convention_id": "test-convention",
            "version": 1,
            "change_type": "invalid_change_type",  # 잘못된 값
            "change_summary": "Test",
            "diffs": [],
            "changed_by": "test-user",
            "changed_at": "2023-01-01T12:00:00"
        }
        
        with pytest.raises(ValueError) as exc_info:
            NamingConventionHistory.from_dict(data)
        assert "Cannot convert 'invalid_change_type' to ChangeType" in str(exc_info.value)
    
    def test_history_from_dict_with_invalid_datetime(self):
        """잘못된 datetime 형식 처리 테스트"""
        data = {
            "id": "test_v1_123456",
            "convention_id": "test-convention",
            "version": 1,
            "change_type": "create",
            "change_summary": "Test",
            "diffs": [],
            "changed_by": "test-user",
            "changed_at": "invalid-datetime-format"  # 잘못된 형식
        }
        
        # 예외는 발생하지 않고, 현재 시간으로 대체되어야 함
        history = NamingConventionHistory.from_dict(data)
        assert history.change_type == ChangeType.CREATE
        assert isinstance(history.changed_at, datetime)


class TestRoundTripSerialization:
    """직렬화 → 역직렬화 라운드트립 테스트"""
    
    def test_convention_round_trip(self):
        """Convention 저장 → 로드 라운드트립 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "test_config.json"
            history_path = Path(temp_dir) / "test_history.json"
            
            # 원본 convention 생성
            original_convention = NamingConvention(
                id="round-trip-test",
                name="Round Trip Test",
                description="Testing round trip serialization",
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
            
            # 서비스로 저장
            service = NamingConfigService(str(config_path), str(history_path))
            service.create_convention(original_convention, "test-user", "Round trip test")
            
            # 새 서비스 인스턴스로 로드
            service2 = NamingConfigService(str(config_path), str(history_path))
            loaded_convention = service2.get_convention("round-trip-test")
            
            # 원본과 로드된 것이 동일한지 확인
            assert loaded_convention is not None
            assert loaded_convention.id == original_convention.id
            assert loaded_convention.name == original_convention.name
            assert loaded_convention.description == original_convention.description
            assert len(loaded_convention.rules) == len(original_convention.rules)
            
            # 규칙 상세 비교
            for entity_type, original_rule in original_convention.rules.items():
                loaded_rule = loaded_convention.rules[entity_type]
                assert loaded_rule.entity_type == original_rule.entity_type
                assert loaded_rule.pattern == original_rule.pattern
                assert loaded_rule.min_length == original_rule.min_length
                assert loaded_rule.max_length == original_rule.max_length
            
            assert loaded_convention.reserved_words == original_convention.reserved_words
            assert loaded_convention.case_sensitive == original_convention.case_sensitive
            assert loaded_convention.auto_fix_enabled == original_convention.auto_fix_enabled
    
    def test_history_round_trip(self):
        """History 저장 → 로드 라운드트립 테스트"""
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "test_history.json"
            
            from core.validation.naming_history import NamingConventionHistoryService
            
            # 원본 history 생성
            service = NamingConventionHistoryService(str(history_path))
            
            original_convention = NamingConvention(
                id="history-round-trip",
                name="History Round Trip",
                description="Testing history round trip",
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
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
                created_by="test-user"
            )
            
            # 히스토리 기록
            service.record_creation(original_convention, "test-user", "Round trip test")
            
            # 새 서비스 인스턴스로 로드
            service2 = NamingConventionHistoryService(str(history_path))
            loaded_history = service2.get_history("history-round-trip")
            
            # 로드된 히스토리 확인
            assert len(loaded_history) == 1
            entry = loaded_history[0]
            assert entry.convention_id == "history-round-trip"
            assert entry.change_type == ChangeType.CREATE
            assert entry.version == 1
            assert entry.changed_by == "test-user"
            assert entry.change_reason == "Round trip test"
            
            # 스냅샷 확인
            assert entry.full_snapshot is not None
            assert entry.full_snapshot["id"] == "history-round-trip"
            assert entry.full_snapshot["name"] == "History Round Trip"


class TestEdgeCasesAndCompatibility:
    """엣지 케이스 및 호환성 테스트"""
    
    def test_mixed_enum_formats_in_same_file(self):
        """같은 파일에서 다양한 Enum 포맷 혼재 테스트"""
        data = {
            "id": "mixed-format",
            "name": "Mixed Format Test",
            "rules": {
                "objectType": {  # value 포맷
                    "entity_type": "objectType",
                    "pattern": "PascalCase",
                    "min_length": 3,
                    "max_length": 50
                },
                "PROPERTY": {  # name 포맷 (대문자)
                    "entity_type": "property",  # value 포맷
                    "pattern": "CAMEL_CASE",   # name 포맷
                    "min_length": 2,
                    "max_length": 40
                }
            },
            "reserved_words": []
        }
        
        service = NamingConfigService()
        convention = service._parse_convention(data)
        
        # 두 규칙 모두 올바르게 파싱되어야 함
        assert len(convention.rules) == 2
        assert EntityType.OBJECT_TYPE in convention.rules
        assert EntityType.PROPERTY in convention.rules
        
        # Enum 값들이 올바르게 변환되었는지 확인
        obj_rule = convention.rules[EntityType.OBJECT_TYPE]
        assert obj_rule.pattern == NamingPattern.PASCAL_CASE
        
        prop_rule = convention.rules[EntityType.PROPERTY]
        assert prop_rule.pattern == NamingPattern.CAMEL_CASE
    
    def test_partial_enum_parsing_failure_recovery(self):
        """일부 Enum 파싱 실패 시 복구 테스트"""
        data = {
            "id": "partial-fail",
            "name": "Partial Failure Test",
            "rules": {
                "objectType": {
                    "entity_type": "objectType",
                    "pattern": "PascalCase",
                    "min_length": 3,
                    "max_length": 50
                },
                "property": {
                    "entity_type": "property",
                    "pattern": "invalidPattern",  # 잘못된 패턴
                    "min_length": 2,
                    "max_length": 40
                },
                "invalidType": {  # 잘못된 엔티티 타입
                    "entity_type": "invalidType",
                    "pattern": "camelCase",
                    "min_length": 1,
                    "max_length": 30
                }
            },
            "reserved_words": []
        }
        
        service = NamingConfigService()
        convention = service._parse_convention(data)
        
        # 유효한 규칙(objectType)만 파싱되고 나머지는 무시되어야 함
        assert len(convention.rules) == 1
        assert EntityType.OBJECT_TYPE in convention.rules
        assert EntityType.PROPERTY not in convention.rules