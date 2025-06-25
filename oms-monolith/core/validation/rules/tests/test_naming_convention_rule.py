"""
NamingConventionRule 테스트
중복 감지, case_sensitive, 이름 변경 추적 기능 검증
"""
import pytest
from unittest.mock import Mock, patch

from core.validation.rules.naming_convention_rule import NamingConventionRule
from core.validation.models import (
    ValidationContext, Severity, BreakingChange, ValidationWarning
)
from core.validation.naming_convention import (
    NamingConvention, NamingRule, EntityType, NamingPattern
)


class TestNamingConventionRule:
    """NamingConventionRule 테스트"""
    
    @pytest.fixture
    def default_convention(self):
        """기본 명명 규칙"""
        return NamingConvention(
            id="test",
            name="Test Convention",
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
                ),
                EntityType.LINK_TYPE: NamingRule(
                    entity_type=EntityType.LINK_TYPE,
                    pattern=NamingPattern.CAMEL_CASE,
                    min_length=3,
                    max_length=60
                )
            },
            reserved_words=["class", "type", "function"],
            case_sensitive=True,
            auto_fix_enabled=True,
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            created_by="test"
        )
    
    @pytest.fixture
    def case_insensitive_convention(self, default_convention):
        """대소문자 무시 명명 규칙"""
        convention = default_convention.model_copy()
        convention.case_sensitive = False
        return convention
    
    @pytest.fixture
    def rule_with_convention(self, default_convention):
        """명명 규칙이 설정된 Rule"""
        with patch('core.validation.rules.naming_convention_rule.get_naming_engine') as mock_engine:
            engine = Mock()
            engine.convention = default_convention
            engine.normalize = lambda name: name if default_convention.case_sensitive else name.lower()
            mock_engine.return_value = engine
            
            rule = NamingConventionRule()
            rule.engine = engine
            return rule
    
    @pytest.fixture
    def rule_case_insensitive(self, case_insensitive_convention):
        """대소문자 무시 Rule"""
        with patch('core.validation.rules.naming_convention_rule.get_naming_engine') as mock_engine:
            engine = Mock()
            engine.convention = case_insensitive_convention
            engine.normalize = lambda name: name.lower()
            mock_engine.return_value = engine
            
            rule = NamingConventionRule()
            rule.engine = engine
            return rule

    @pytest.mark.asyncio
    async def test_duplicate_detection_fixed(self, rule_with_convention):
        """중복 감지 로직이 올바르게 작동하는지 테스트"""
        # Mock ValidationContext 사용
        class MockValidationContext:
            def __init__(self, source_schemas, target_schemas):
                self.source_schemas = source_schemas
                self.target_schemas = target_schemas
        
        context = MockValidationContext(
            source_schemas={},
            target_schemas={
                "object_types": {
                    "obj1": {"name": "User"},
                    "obj2": {"name": "User"},  # 중복!
                    "obj3": {"name": "Product"}
                }
            }
        )
        
        result = await rule_with_convention.execute(context)
        
        # 중복 경고 확인
        duplicate_warnings = [w for w in result.warnings if w.code == "duplicate-names"]
        assert len(duplicate_warnings) == 1
        
        warning = duplicate_warnings[0]
        assert "User" in warning.message
        assert warning.details["entities"]["User"] == ["ObjectType:obj1", "ObjectType:obj2"]
    
    @pytest.mark.asyncio
    async def test_case_sensitive_duplicate_detection(self, rule_with_convention):
        """대소문자 구분 모드에서 중복 감지"""
        context = ValidationContext(
            source_schemas={},
            target_schemas={
                "object_types": {
                    "obj1": {"name": "User"},
                    "obj2": {"name": "user"},  # 대소문자만 다름
                    "obj3": {"name": "USER"}   # 대소문자만 다름
                }
            }
        )
        
        result = await rule_with_convention.execute(context)
        
        # case_sensitive=True이므로 중복 없음
        duplicate_warnings = [w for w in result.warnings if w.code == "duplicate-names"]
        assert len(duplicate_warnings) == 0
    
    @pytest.mark.asyncio
    async def test_case_insensitive_duplicate_detection(self, rule_case_insensitive):
        """대소문자 무시 모드에서 중복 감지"""
        context = ValidationContext(
            source_schemas={},
            target_schemas={
                "object_types": {
                    "obj1": {"name": "User"},
                    "obj2": {"name": "user"},  # 중복!
                    "obj3": {"name": "USER"}   # 중복!
                }
            }
        )
        
        result = await rule_case_insensitive.execute(context)
        
        # case_sensitive=False이므로 모두 중복
        duplicate_warnings = [w for w in result.warnings if w.code == "duplicate-names"]
        assert len(duplicate_warnings) == 1
        
        warning = duplicate_warnings[0]
        assert "case-insensitive" in warning.message
        assert len(warning.details["entities"]["user"]) == 3
        assert warning.details["case_sensitive"] is False
    
    @pytest.mark.asyncio
    async def test_cross_entity_duplicate_detection(self, rule_with_convention):
        """서로 다른 엔티티 타입 간 중복 감지"""
        context = ValidationContext(
            source_schemas={},
            target_schemas={
                "object_types": {
                    "obj1": {"name": "Order", "properties": {
                        "prop1": {"name": "status"}
                    }}
                },
                "link_types": {
                    "link1": {"name": "Order"}  # ObjectType과 중복!
                }
            }
        )
        
        result = await rule_with_convention.execute(context)
        
        # 크로스 엔티티 중복 확인
        duplicate_warnings = [w for w in result.warnings if w.code == "duplicate-names"]
        assert len(duplicate_warnings) == 1
        
        warning = duplicate_warnings[0]
        assert "Order" in warning.details["entities"]
        assert "ObjectType:obj1" in warning.details["entities"]["Order"]
        assert "LinkType:link1" in warning.details["entities"]["Order"]
    
    @pytest.mark.asyncio
    async def test_name_change_detection(self, rule_with_convention):
        """이름 변경 감지 테스트"""
        # Mock validation result
        validation_result = Mock()
        validation_result.is_valid = False
        validation_result.issues = [Mock(
            rule_violated="pattern",
            message="Name must follow PascalCase",
            suggestion="UserType"
        )]
        validation_result.suggestions = {"userType": "UserType"}
        
        rule_with_convention.engine.validate = Mock(return_value=validation_result)
        
        context = ValidationContext(
            source_schemas={
                "object_types": {
                    "obj1": {"name": "UserType"}  # 이전 이름
                }
            },
            target_schemas={
                "object_types": {
                    "obj1": {"name": "userType"}  # 새 이름 (규칙 위반)
                }
            }
        )
        
        result = await rule_with_convention.execute(context)
        
        # Breaking change 확인
        assert len(result.breaking_changes) == 1
        change = result.breaking_changes[0]
        assert change.resource_type == "ObjectType"
        assert change.change_type == "naming-violation"
        assert "userType" in change.description
    
    @pytest.mark.asyncio
    async def test_reserved_word_detection_case_sensitive(self, rule_with_convention):
        """예약어 충돌 감지 (대소문자 구분)"""
        context = ValidationContext(
            source_schemas={},
            target_schemas={
                "object_types": {
                    "obj1": {"name": "class"},  # 예약어!
                    "obj2": {"name": "Class"},  # 대소문자 다름
                    "obj3": {"name": "TYPE"}    # 대소문자 다름
                }
            }
        )
        
        result = await rule_with_convention.execute(context)
        
        # 예약어 충돌 확인
        reserved_warnings = [w for w in result.warnings if w.code == "reserved-word-conflict"]
        assert len(reserved_warnings) == 1
        assert "class" in reserved_warnings[0].details["conflicts"]
        assert "Class" not in reserved_warnings[0].details["conflicts"]
    
    @pytest.mark.asyncio
    async def test_reserved_word_detection_case_insensitive(self, rule_case_insensitive):
        """예약어 충돌 감지 (대소문자 무시)"""
        context = ValidationContext(
            source_schemas={},
            target_schemas={
                "object_types": {
                    "obj1": {"name": "Class"},  # 예약어!
                    "obj2": {"name": "TYPE"},   # 예약어!
                    "obj3": {"name": "Function"} # 예약어!
                }
            }
        )
        
        result = await rule_case_insensitive.execute(context)
        
        # 예약어 충돌 확인
        reserved_warnings = [w for w in result.warnings if w.code == "reserved-word-conflict"]
        assert len(reserved_warnings) == 1
        
        conflicts = reserved_warnings[0].details["conflicts"]
        assert len(conflicts) == 3
    
    @pytest.mark.asyncio
    async def test_property_duplicate_within_object(self, rule_with_convention):
        """같은 ObjectType 내 Property 중복은 감지하지 않음"""
        context = ValidationContext(
            source_schemas={},
            target_schemas={
                "object_types": {
                    "obj1": {
                        "name": "User",
                        "properties": {
                            "prop1": {"name": "name"},
                            "prop2": {"name": "name"}  # 같은 객체 내 중복
                        }
                    }
                }
            }
        )
        
        result = await rule_with_convention.execute(context)
        
        # Property 중복은 크로스 엔티티 체크에서 제외
        duplicate_warnings = [w for w in result.warnings if w.code == "duplicate-names"]
        assert len(duplicate_warnings) == 0
    
    @pytest.mark.asyncio
    async def test_only_changed_entities_validated(self, rule_with_convention):
        """변경되지 않은 엔티티는 검증하지 않음"""
        # Mock - 변경되지 않은 엔티티는 validate 호출 안 됨
        rule_with_convention.engine.validate = Mock()
        
        context = ValidationContext(
            source_schemas={
                "object_types": {
                    "obj1": {"name": "User"},
                    "obj2": {"name": "Product"}
                }
            },
            target_schemas={
                "object_types": {
                    "obj1": {"name": "User"},      # 변경 없음
                    "obj2": {"name": "ProductNew"}  # 변경됨
                }
            }
        )
        
        await rule_with_convention.execute(context)
        
        # validate는 변경된 엔티티에 대해서만 호출
        assert rule_with_convention.engine.validate.call_count == 1
        call_args = rule_with_convention.engine.validate.call_args[0]
        assert call_args[1] == "ProductNew"