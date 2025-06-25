"""
FastAPI 의존성 주입 설정
Validation 서비스를 위한 DI 구성
"""
from typing import Annotated, Optional
from fastapi import Depends
import os

from core.validation.ports import CachePort, TerminusPort, EventPort
from core.validation.container import ValidationContainer, get_container
from core.validation.service_refactored import ValidationServiceRefactored
from core.validation.adapters import (
    MockCacheAdapter, 
    MockTerminusAdapter, 
    MockEventAdapter,
    SmartCacheAdapter,
    TerminusDBAdapter,
    EventPublisherAdapter
)


# 환경별 설정
def get_test_mode() -> bool:
    """테스트 모드 여부 확인"""
    return os.getenv("TEST_MODE", "false").lower() == "true"


# 기본 Port 제공자들
async def get_cache_port(test_mode: bool = Depends(get_test_mode)) -> CachePort:
    """캐시 포트 의존성"""
    if test_mode:
        return MockCacheAdapter()
    return SmartCacheAdapter()


async def get_terminus_port(test_mode: bool = Depends(get_test_mode)) -> TerminusPort:
    """TerminusDB 포트 의존성"""
    if test_mode:
        return MockTerminusAdapter()
    return TerminusDBAdapter()


async def get_event_port(test_mode: bool = Depends(get_test_mode)) -> EventPort:
    """이벤트 포트 의존성"""
    if test_mode:
        return MockEventAdapter()
    return EventPublisherAdapter()


# ValidationService 의존성
async def get_validation_service(
    cache: Annotated[CachePort, Depends(get_cache_port)],
    tdb: Annotated[TerminusPort, Depends(get_terminus_port)],
    events: Annotated[EventPort, Depends(get_event_port)]
) -> ValidationServiceRefactored:
    """
    ValidationService 의존성 주입
    
    FastAPI 엔드포인트에서 사용:
    
    @router.post("/validate")
    async def validate(
        request: ValidationRequest,
        service: ValidationServiceRefactored = Depends(get_validation_service)
    ):
        return await service.validate_breaking_changes(request)
    """
    from core.validation.rule_registry import RuleRegistry
    
    # 규칙 레지스트리 생성
    rule_registry = RuleRegistry(cache=cache, tdb=tdb, event=events)
    
    # 서비스 생성 및 반환
    return ValidationServiceRefactored(
        cache=cache,
        tdb=tdb,
        events=events,
        rule_registry=rule_registry
    )


# 단일 컨테이너 기반 의존성 (선택적)
_container: Optional[ValidationContainer] = None


async def get_validation_container(
    test_mode: bool = Depends(get_test_mode)
) -> ValidationContainer:
    """ValidationContainer 의존성"""
    global _container
    if _container is None or _container.test_mode != test_mode:
        _container = ValidationContainer(test_mode=test_mode)
    return _container


async def get_validation_service_from_container(
    container: ValidationContainer = Depends(get_validation_container)
) -> ValidationServiceRefactored:
    """컨테이너 기반 ValidationService 의존성"""
    return container.get_validation_service()


# 타입 힌트를 위한 Annotated 타입들
CachePortDep = Annotated[CachePort, Depends(get_cache_port)]
TerminusPortDep = Annotated[TerminusPort, Depends(get_terminus_port)]
EventPortDep = Annotated[EventPort, Depends(get_event_port)]
ValidationServiceDep = Annotated[ValidationServiceRefactored, Depends(get_validation_service)]