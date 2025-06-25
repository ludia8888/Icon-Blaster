"""
개선된 Validation 시스템 테스트
데코레이터, FastAPI DI, 캐싱 기능 테스트
"""
import pytest
import asyncio
from datetime import datetime

from core.validation.decorators import (
    validation_rule, 
    get_registered_rules,
    clear_rule_registry,
    get_rules_by_category
)
from core.validation.interfaces import BreakingChangeRule
from core.validation.models import BreakingChange, Severity
from core.validation.ports import ValidationContext
from core.validation.rule_registry import RuleRegistry
from core.validation.adapters import MockCacheAdapter, MockTerminusAdapter, MockEventAdapter


class TestDecorators:
    """데코레이터 기능 테스트"""
    
    def setup_method(self):
        """각 테스트 전 레지스트리 초기화"""
        clear_rule_registry()
    
    def test_rule_registration(self):
        """규칙 등록 테스트"""
        
        @validation_rule(category="test", severity_default="high")
        class TestRule(BreakingChangeRule):
            rule_id = "test_rule"
            
            async def check(self, old_schema, new_schema, context):
                return None
        
        # 규칙이 등록되었는지 확인
        rules = get_registered_rules()
        assert len(rules) == 1
        assert rules[0] == TestRule
        
        # 메타데이터 확인
        assert hasattr(TestRule, '_rule_metadata')
        assert TestRule._rule_metadata['category'] == "test"
        assert TestRule._rule_metadata['severity_default'] == "high"
    
    def test_auto_rule_id_generation(self):
        """자동 rule_id 생성 테스트"""
        
        @validation_rule()
        class MyAwesomeValidationRule(BreakingChangeRule):
            async def check(self, old_schema, new_schema, context):
                return None
        
        # 자동 생성된 rule_id 확인
        assert MyAwesomeValidationRule.rule_id == "my_awesome_validation"
    
    def test_category_filtering(self):
        """카테고리별 필터링 테스트"""
        
        @validation_rule(category="schema")
        class SchemaRule(BreakingChangeRule):
            rule_id = "schema_rule"
            async def check(self, old_schema, new_schema, context):
                return None
        
        @validation_rule(category="data")
        class DataRule(BreakingChangeRule):
            rule_id = "data_rule"
            async def check(self, old_schema, new_schema, context):
                return None
        
        # 카테고리별 필터링
        schema_rules = get_rules_by_category("schema")
        data_rules = get_rules_by_category("data")
        
        assert len(schema_rules) == 1
        assert len(data_rules) == 1
        assert schema_rules[0].rule_id == "schema_rule"
        assert data_rules[0].rule_id == "data_rule"


class TestRuleRegistryCache:
    """규칙 레지스트리 캐싱 테스트"""
    
    @pytest.mark.asyncio
    async def test_rule_loading_cache(self):
        """규칙 로딩 캐싱 테스트"""
        registry = RuleRegistry(
            cache=MockCacheAdapter(),
            tdb=MockTerminusAdapter(),
            event=MockEventAdapter()
        )
        
        # 첫 번째 로드 (캐시 미스)
        start_time = datetime.now()
        rules1 = registry.load_rules_from_package()
        first_load_time = (datetime.now() - start_time).total_seconds()
        
        # 두 번째 로드 (캐시 히트)
        start_time = datetime.now()
        rules2 = registry.load_rules_from_package()
        second_load_time = (datetime.now() - start_time).total_seconds()
        
        # 캐시된 로드가 더 빨라야 함
        assert second_load_time < first_load_time
        assert len(rules1) == len(rules2)
    
    def test_cache_invalidation(self):
        """캐시 무효화 테스트"""
        registry = RuleRegistry()
        
        # 규칙 로드
        rules1 = registry.load_rules_from_package()
        
        # 캐시 무효화
        registry.reload_rules()
        
        # 새로 로드된 규칙
        rules2 = registry.get_all_rules()
        
        # 인스턴스는 다르지만 개수는 같아야 함
        assert len(rules1) == len(rules2)


class TestFastAPIDependencies:
    """FastAPI 의존성 주입 테스트"""
    
    @pytest.mark.asyncio
    async def test_dependency_injection(self):
        """의존성 주입 테스트"""
        from core.validation.dependencies import (
            get_cache_port,
            get_terminus_port,
            get_event_port,
            get_validation_service
        )
        
        # 테스트 모드 의존성 주입
        async def get_test_mode():
            return True
        
        # 각 포트 가져오기
        cache = await get_cache_port(test_mode=True)
        tdb = await get_terminus_port(test_mode=True)
        events = await get_event_port(test_mode=True)
        
        # Mock 어댑터인지 확인
        assert cache.__class__.__name__ == "MockCacheAdapter"
        assert tdb.__class__.__name__ == "MockTerminusAdapter"
        assert events.__class__.__name__ == "MockEventAdapter"
        
        # ValidationService 생성
        service = await get_validation_service(cache, tdb, events)
        assert service is not None
        assert service.cache is cache
        assert service.tdb is tdb
        assert service.events is events


@pytest.mark.asyncio
async def test_end_to_end_with_improvements():
    """개선사항을 포함한 전체 시스템 테스트"""
    from core.validation.container import ValidationContainer
    from core.validation.models import ValidationRequest
    
    # 테스트용 규칙 등록
    @validation_rule(
        rule_id="test_e2e_rule",
        category="test",
        severity_default="medium"
    )
    class TestE2ERule(BreakingChangeRule):
        def __init__(self, cache=None, tdb=None):
            self.cache = cache
            self.tdb = tdb
            
        async def check(self, old_schema, new_schema, context):
            # 간단한 테스트 로직
            if old_schema.get("version") != new_schema.get("version"):
                return [BreakingChange(
                    id="test_change_1",
                    rule_id=self.rule_id,
                    object_type="Test",
                    property_name="version",
                    change_type="version_change",
                    severity=Severity.MEDIUM,
                    description="Version changed"
                )]
            return None
    
    # 컨테이너 생성
    container = ValidationContainer(test_mode=True)
    service = container.get_validation_service()
    
    # Mock 데이터 설정
    mock_tdb = container.get_terminus_adapter()
    mock_tdb.query_results = [
        {
            "objectType": "ObjectType/Test",
            "name": "Test",
            "version": "1.0"
        }
    ]
    
    # 검증 실행
    request = ValidationRequest(
        source_branch="main",
        target_branch="feature/test"
    )
    
    result = await service.validate_breaking_changes(request)
    
    # 결과 확인
    assert result.is_valid is not None
    assert result.validation_id is not None
    assert isinstance(result.performance_metrics, dict)
    
    # 이벤트 발행 확인
    mock_events = container.get_event_adapter()
    assert len(mock_events.published_events) > 0
    assert mock_events.published_events[0]['event_type'] == "validation.completed"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])