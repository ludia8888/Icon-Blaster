"""
Dependency Injection Container for Validation Service
의존성 주입 컨테이너 - 실제 구현체와 Port를 연결
"""
from typing import Optional
import logging

from core.validation.service_refactored import ValidationServiceRefactored
from core.validation.adapters import (
    create_cache_adapter,
    create_terminus_adapter,
    create_event_adapter,
    MockCacheAdapter,
    MockTerminusAdapter,
    MockEventAdapter
)
from core.validation.rule_registry import RuleRegistry

logger = logging.getLogger(__name__)


class ValidationContainer:
    """
    Validation 모듈의 의존성 주입 컨테이너
    모든 의존성을 중앙에서 관리하고 주입
    """
    
    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        self._cache_adapter = None
        self._terminus_adapter = None
        self._event_adapter = None
        self._rule_registry = None
        self._validation_service = None
    
    def get_cache_adapter(self):
        """캐시 어댑터 가져오기 (lazy loading)"""
        if self._cache_adapter is None:
            if self.test_mode:
                self._cache_adapter = MockCacheAdapter()
            else:
                self._cache_adapter = create_cache_adapter()
        return self._cache_adapter
    
    def get_terminus_adapter(self):
        """TerminusDB 어댑터 가져오기"""
        if self._terminus_adapter is None:
            if self.test_mode:
                self._terminus_adapter = MockTerminusAdapter()
            else:
                self._terminus_adapter = create_terminus_adapter()
        return self._terminus_adapter
    
    def get_event_adapter(self):
        """이벤트 어댑터 가져오기"""
        if self._event_adapter is None:
            if self.test_mode:
                self._event_adapter = MockEventAdapter()
            else:
                self._event_adapter = create_event_adapter()
        return self._event_adapter
    
    def get_rule_registry(self):
        """규칙 레지스트리 가져오기"""
        if self._rule_registry is None:
            self._rule_registry = RuleRegistry(
                cache=self.get_cache_adapter(),
                tdb=self.get_terminus_adapter(),
                event=self.get_event_adapter()
            )
        return self._rule_registry
    
    def get_validation_service(self) -> ValidationServiceRefactored:
        """검증 서비스 가져오기 (모든 의존성 주입)"""
        if self._validation_service is None:
            self._validation_service = ValidationServiceRefactored(
                cache=self.get_cache_adapter(),
                tdb=self.get_terminus_adapter(),
                events=self.get_event_adapter(),
                rule_registry=self.get_rule_registry()
            )
        return self._validation_service
    
    def set_cache_adapter(self, adapter):
        """캐시 어댑터 교체"""
        self._cache_adapter = adapter
        self._validation_service = None  # 서비스 재생성 필요
    
    def set_terminus_adapter(self, adapter):
        """TerminusDB 어댑터 교체"""
        self._terminus_adapter = adapter
        self._validation_service = None
    
    def set_event_adapter(self, adapter):
        """이벤트 어댑터 교체"""
        self._event_adapter = adapter
        self._validation_service = None


# 전역 컨테이너 인스턴스
_default_container: Optional[ValidationContainer] = None


def get_container(test_mode: bool = False) -> ValidationContainer:
    """전역 컨테이너 가져오기"""
    global _default_container
    if _default_container is None:
        _default_container = ValidationContainer(test_mode=test_mode)
    return _default_container


def get_validation_service(test_mode: bool = False) -> ValidationServiceRefactored:
    """검증 서비스 가져오기 (간편 함수)"""
    container = get_container(test_mode=test_mode)
    return container.get_validation_service()


# FastAPI Dependency Injection을 위한 함수들
async def get_cache_port():
    """FastAPI Depends를 위한 캐시 포트 제공자"""
    container = get_container()
    return container.get_cache_adapter()


async def get_terminus_port():
    """FastAPI Depends를 위한 TerminusDB 포트 제공자"""
    container = get_container()
    return container.get_terminus_adapter()


async def get_event_port():
    """FastAPI Depends를 위한 이벤트 포트 제공자"""
    container = get_container()
    return container.get_event_adapter()


async def get_validation_service_dependency():
    """FastAPI Depends를 위한 검증 서비스 제공자"""
    container = get_container()
    return container.get_validation_service()


# 기존 코드와의 호환성을 위한 래퍼
def create_validation_service_with_legacy_interface(
    tdb_client=None,
    cache=None,
    event_publisher=None
) -> ValidationServiceRefactored:
    """
    기존 인터페이스로 ValidationService 생성
    레거시 코드 지원을 위한 래퍼 함수
    """
    from core.validation.adapters import (
        SmartCacheAdapter,
        TerminusDBAdapter,
        EventPublisherAdapter
    )
    
    # 어댑터 생성
    cache_adapter = SmartCacheAdapter(cache) if cache else create_cache_adapter()
    tdb_adapter = TerminusDBAdapter(tdb_client) if tdb_client else create_terminus_adapter()
    event_adapter = EventPublisherAdapter(event_publisher) if event_publisher else create_event_adapter()
    
    # 서비스 생성
    return ValidationServiceRefactored(
        cache=cache_adapter,
        tdb=tdb_adapter,
        events=event_adapter
    )