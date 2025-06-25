"""
Validation Service DI 테스트
순환 참조가 해결되었는지 확인하는 테스트
"""
import pytest
import asyncio
from datetime import datetime

from core.validation.ports import CachePort, TerminusPort, EventPort, ValidationContext
from core.validation.container import ValidationContainer, get_validation_service
from core.validation.service_refactored import ValidationServiceRefactored
from core.validation.models import ValidationRequest, Severity
from core.validation.adapters import MockCacheAdapter, MockTerminusAdapter, MockEventAdapter


class TestValidationDI:
    """의존성 주입 테스트"""
    
    def test_container_creation(self):
        """컨테이너 생성 테스트"""
        container = ValidationContainer(test_mode=True)
        assert container is not None
        assert container.test_mode is True
    
    def test_adapter_lazy_loading(self):
        """어댑터 지연 로딩 테스트"""
        container = ValidationContainer(test_mode=True)
        
        # 처음에는 None
        assert container._cache_adapter is None
        
        # 요청 시 생성
        cache = container.get_cache_adapter()
        assert cache is not None
        assert isinstance(cache, MockCacheAdapter)
        
        # 재요청 시 동일 인스턴스
        cache2 = container.get_cache_adapter()
        assert cache is cache2
    
    def test_service_creation_without_circular_imports(self):
        """순환 import 없이 서비스 생성 테스트"""
        container = ValidationContainer(test_mode=True)
        
        # 서비스 생성 (순환 참조 없이)
        service = container.get_validation_service()
        assert service is not None
        assert isinstance(service, ValidationServiceRefactored)
        
        # 의존성들이 제대로 주입되었는지 확인
        assert service.cache is not None
        assert service.tdb is not None
        assert service.events is not None
        assert service.rule_registry is not None
    
    @pytest.mark.asyncio
    async def test_validation_with_mock_adapters(self):
        """Mock 어댑터를 사용한 검증 테스트"""
        container = ValidationContainer(test_mode=True)
        service = container.get_validation_service()
        
        # Mock 데이터 설정
        mock_tdb = container.get_terminus_adapter()
        mock_tdb.query_results = [
            {
                "objectType": "ObjectType/User",
                "name": "User",
                "displayName": "User",
                "properties": []
            }
        ]
        
        # 검증 요청
        request = ValidationRequest(
            source_branch="main",
            target_branch="feature/test",
            include_warnings=True,
            include_impact_analysis=False
        )
        
        # 검증 실행
        result = await service.validate_breaking_changes(request)
        
        assert result is not None
        assert result.source_branch == "main"
        assert result.target_branch == "feature/test"
        assert isinstance(result.breaking_changes, list)
    
    @pytest.mark.asyncio
    async def test_cache_adapter_functionality(self):
        """캐시 어댑터 기능 테스트"""
        cache = MockCacheAdapter()
        
        # set/get 테스트
        await cache.set("test_key", "test_value")
        value = await cache.get("test_key")
        assert value == "test_value"
        
        # exists 테스트
        exists = await cache.exists("test_key")
        assert exists is True
        
        # delete 테스트
        await cache.delete("test_key")
        exists = await cache.exists("test_key")
        assert exists is False
        
        # 호출 횟수 확인
        assert cache.call_count['set'] == 1
        assert cache.call_count['get'] == 1
        assert cache.call_count['exists'] == 2
        assert cache.call_count['delete'] == 1
    
    @pytest.mark.asyncio
    async def test_event_adapter_functionality(self):
        """이벤트 어댑터 기능 테스트"""
        events = MockEventAdapter()
        
        # 단일 이벤트 발행
        await events.publish(
            event_type="test.event",
            data={"key": "value"},
            correlation_id="test-123"
        )
        
        assert len(events.published_events) == 1
        assert events.published_events[0]['event_type'] == "test.event"
        assert events.published_events[0]['data']['key'] == "value"
        
        # 배치 이벤트 발행
        batch = [
            {"event_type": "batch.event1", "data": {"id": 1}},
            {"event_type": "batch.event2", "data": {"id": 2}}
        ]
        await events.publish_batch(batch)
        
        assert len(events.published_events) == 3
        assert events.call_count['publish'] == 1
        assert events.call_count['publish_batch'] == 1
    
    def test_adapter_replacement(self):
        """어댑터 교체 테스트"""
        container = ValidationContainer(test_mode=True)
        
        # 기본 어댑터
        original_cache = container.get_cache_adapter()
        
        # 새 어댑터로 교체
        new_cache = MockCacheAdapter()
        container.set_cache_adapter(new_cache)
        
        # 교체 확인
        current_cache = container.get_cache_adapter()
        assert current_cache is new_cache
        assert current_cache is not original_cache
    
    def test_rule_registry_integration(self):
        """규칙 레지스트리 통합 테스트"""
        container = ValidationContainer(test_mode=True)
        service = container.get_validation_service()
        
        # 규칙이 로드되었는지 확인
        assert hasattr(service, 'rules')
        # 테스트 모드에서는 실제 규칙이 로드되지 않을 수 있음
        assert isinstance(service.rules, list)
    
    @pytest.mark.asyncio
    async def test_no_circular_imports_in_rules(self):
        """규칙 로딩 시 순환 import 없음 확인"""
        from core.validation.rule_registry import RuleRegistry
        from core.validation.adapters import MockCacheAdapter, MockTerminusAdapter, MockEventAdapter
        
        # Mock 어댑터로 레지스트리 생성
        registry = RuleRegistry(
            cache=MockCacheAdapter(),
            tdb=MockTerminusAdapter(),
            event=MockEventAdapter()
        )
        
        # 규칙 로드 시도 (순환 참조 없어야 함)
        try:
            rules = registry.load_rules_from_package()
            # 성공적으로 로드됨 (또는 빈 리스트)
            assert isinstance(rules, list)
        except ImportError as e:
            # 순환 참조로 인한 ImportError가 발생하면 안 됨
            pytest.fail(f"Circular import detected: {e}")


class TestValidationContextPort:
    """ValidationContext와 Port 통합 테스트"""
    
    @pytest.mark.asyncio
    async def test_context_with_ports(self):
        """Port를 포함한 컨텍스트 생성 테스트"""
        from core.validation.ports import ValidationContext
        
        cache = MockCacheAdapter()
        tdb = MockTerminusAdapter()
        events = MockEventAdapter()
        
        context = ValidationContext(
            source_branch="main",
            target_branch="feature/test",
            user_id="test-user",
            cache=cache,
            terminus_client=tdb,
            event_publisher=events,
            metadata={"test": "data"}
        )
        
        assert context.source_branch == "main"
        assert context.target_branch == "feature/test"
        assert context.cache is cache
        assert context.terminus_client is tdb
        assert context.event_publisher is events
        
        # 메타데이터 확장 테스트
        new_context = context.with_metadata(additional="info")
        assert new_context.metadata["test"] == "data"
        assert new_context.metadata["additional"] == "info"
        assert new_context is not context  # 새 인스턴스


if __name__ == "__main__":
    pytest.main([__file__, "-v"])