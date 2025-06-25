"""
대소문자 구분 테스트
"""
import pytest
from core.validation.naming_convention import (
    NamingConventionEngine, NamingConvention, NamingRule,
    EntityType, NamingPattern, get_naming_engine
)


class TestCaseSensitivity:
    """대소문자 구분 기능 테스트"""
    
    def test_case_sensitive_true(self):
        """case_sensitive=True일 때 대소문자 구분"""
        convention = NamingConvention(
            id="test_case_sensitive",
            name="Case Sensitive Test",
            rules={
                EntityType.PROPERTY: NamingRule(
                    entity_type=EntityType.PROPERTY,
                    pattern=NamingPattern.CAMEL_CASE,
                    min_length=1,
                    max_length=50
                )
            },
            reserved_words=["name", "type", "class", "id"],
            case_sensitive=True,  # 대소문자 구분
            auto_fix_enabled=True,
            created_at="2025-01-15",
            updated_at="2025-01-15",
            created_by="test"
        )
        
        engine = NamingConventionEngine(convention)
        
        # 소문자는 예약어
        assert not engine.validate(EntityType.PROPERTY, "name").is_valid
        assert not engine.validate(EntityType.PROPERTY, "type").is_valid
        assert not engine.validate(EntityType.PROPERTY, "class").is_valid
        assert not engine.validate(EntityType.PROPERTY, "id").is_valid
        
        # camelCase 패턴에 맞는 대문자 시작 이름들은 허용되지 않음 (패턴 위반)
        # 하지만 예약어가 아니므로 패턴만 위반됨
        result = engine.validate(EntityType.PROPERTY, "Name")
        assert not result.is_valid  # camelCase 패턴 위반
        assert any(issue.rule_violated == "pattern" for issue in result.issues)
        
        # 유효한 camelCase 이름들 (예약어가 아님)
        assert engine.validate(EntityType.PROPERTY, "userName").is_valid  # 예약어 아님
        assert engine.validate(EntityType.PROPERTY, "userType").is_valid  # 예약어 아님
        assert engine.validate(EntityType.PROPERTY, "myClass").is_valid   # 예약어 아님
    
    def test_case_sensitive_false(self):
        """case_sensitive=False일 때 대소문자 무시"""
        convention = NamingConvention(
            id="test_case_insensitive",
            name="Case Insensitive Test",
            rules={
                EntityType.PROPERTY: NamingRule(
                    entity_type=EntityType.PROPERTY,
                    pattern=NamingPattern.CAMEL_CASE,
                    min_length=1,
                    max_length=50
                )
            },
            reserved_words=["name", "type", "class", "id"],
            case_sensitive=False,  # 대소문자 무시
            auto_fix_enabled=True,
            created_at="2025-01-15",
            updated_at="2025-01-15",
            created_by="test"
        )
        
        engine = NamingConventionEngine(convention)
        
        # 모든 변형이 예약어로 처리됨
        test_cases = [
            "name", "Name", "NAME", "nAmE",
            "type", "Type", "TYPE", "tYpE",
            "class", "Class", "CLASS", "cLaSs",
            "id", "Id", "ID", "iD"
        ]
        
        for word in test_cases:
            result = engine.validate(EntityType.PROPERTY, word)
            assert not result.is_valid, f"'{word}' should be reserved when case_sensitive=False"
            assert any(issue.rule_violated == "reserved_word" for issue in result.issues)
    
    def test_mixed_case_reserved_words(self):
        """예약어 목록에 대소문자 혼합된 경우"""
        convention = NamingConvention(
            id="test_mixed",
            name="Mixed Case Test",
            rules={
                EntityType.PROPERTY: NamingRule(
                    entity_type=EntityType.PROPERTY,
                    pattern=NamingPattern.CAMEL_CASE,
                    min_length=1,
                    max_length=50
                )
            },
            reserved_words=["ID", "UUID", "URL", "API", "JSON", "XML"],  # 대문자 약어
            case_sensitive=True,
            auto_fix_enabled=True,
            created_at="2025-01-15",
            updated_at="2025-01-15",
            created_by="test"
        )
        
        engine = NamingConventionEngine(convention)
        
        # 정확히 일치하는 것만 예약어
        assert not engine.validate(EntityType.PROPERTY, "ID").is_valid
        assert not engine.validate(EntityType.PROPERTY, "UUID").is_valid
        assert not engine.validate(EntityType.PROPERTY, "API").is_valid
        
        # 소문자는 허용 (예약어 목록에 없고 camelCase 패턴)
        assert engine.validate(EntityType.PROPERTY, "id").is_valid
        assert engine.validate(EntityType.PROPERTY, "uuid").is_valid
        assert engine.validate(EntityType.PROPERTY, "api").is_valid
        
        # 대문자로 시작하는 이름들은 camelCase 패턴 위반
        result = engine.validate(EntityType.PROPERTY, "Id")
        assert not result.is_valid  # camelCase 패턴 위반
        assert any(issue.rule_violated == "pattern" for issue in result.issues)
    
    def test_auto_fix_with_case_sensitivity(self):
        """대소문자 구분과 자동 수정"""
        convention = NamingConvention(
            id="test_autofix",
            name="Auto Fix Test",
            rules={
                EntityType.PROPERTY: NamingRule(
                    entity_type=EntityType.PROPERTY,
                    pattern=NamingPattern.CAMEL_CASE,
                    min_length=1,
                    max_length=50
                )
            },
            reserved_words=["name", "type", "id"],
            case_sensitive=True,
            auto_fix_enabled=True,
            created_at="2025-01-15",
            updated_at="2025-01-15",
            created_by="test"
        )
        
        engine = NamingConventionEngine(convention)
        
        # 소문자 예약어는 _ 추가
        assert engine.auto_fix(EntityType.PROPERTY, "name") == "name_"
        assert engine.auto_fix(EntityType.PROPERTY, "type") == "type_"
        assert engine.auto_fix(EntityType.PROPERTY, "id") == "id_"
        
        # 대문자로 시작하는 이름들은 camelCase로 변환되지만 예약어 체크도 수행됨
        assert engine.auto_fix(EntityType.PROPERTY, "Name") == "name_"  # camelCase 변환 후 예약어 체크
        assert engine.auto_fix(EntityType.PROPERTY, "Type") == "type_"  # camelCase 변환 후 예약어 체크
        
        # 예약어가 아닌 이름은 단순 변환
        assert engine.auto_fix(EntityType.PROPERTY, "User") == "user"
    
    def test_performance_with_many_reserved_words(self):
        """많은 예약어가 있을 때 성능"""
        import time
        
        # 1000개의 예약어
        large_reserved_list = [f"reserved{i}" for i in range(1000)]
        
        convention = NamingConvention(
            id="test_perf",
            name="Performance Test",
            rules={
                EntityType.PROPERTY: NamingRule(
                    entity_type=EntityType.PROPERTY,
                    pattern=NamingPattern.CAMEL_CASE,
                    min_length=1,
                    max_length=50
                )
            },
            reserved_words=large_reserved_list,
            case_sensitive=False,  # 더 느린 케이스
            auto_fix_enabled=True,
            created_at="2025-01-15",
            updated_at="2025-01-15",
            created_by="test"
        )
        
        engine = NamingConventionEngine(convention)
        
        # 100번 검증
        start = time.time()
        for i in range(100):
            engine.validate(EntityType.PROPERTY, f"testProperty{i}")
        elapsed = time.time() - start
        
        # 0.1초 이내여야 함
        assert elapsed < 0.1, f"Performance issue: {elapsed:.3f}s for 100 validations"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])