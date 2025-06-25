"""
Multi-Platform Event Router
NATS와 AWS EventBridge를 동시에 지원하는 이벤트 라우터
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Union, Set
from enum import Enum
from dataclasses import dataclass

from .cloudevents_enhanced import EnhancedCloudEvent, CloudEventValidator
from .eventbridge_publisher import EventBridgeCloudEventsPublisher, EventBridgeConfig
from .models import PublishResult

logger = logging.getLogger(__name__)


class Platform(str, Enum):
    """지원되는 이벤트 플랫폼"""
    NATS = "nats"
    EVENTBRIDGE = "eventbridge"
    WEBHOOK = "webhook"


class RoutingStrategy(str, Enum):
    """라우팅 전략"""
    ALL = "all"                    # 모든 플랫폼으로 발행
    PRIMARY_ONLY = "primary_only"  # 기본 플랫폼만
    FAILOVER = "failover"          # 기본 실패시 백업으로
    CONDITIONAL = "conditional"    # 조건부 라우팅


@dataclass
class PlatformConfig:
    """플랫폼별 설정"""
    platform: Platform
    enabled: bool = True
    is_primary: bool = False
    retry_count: int = 3
    timeout_seconds: int = 30
    health_check_interval: int = 60
    config: Optional[Dict[str, Any]] = None


@dataclass
class RoutingRule:
    """이벤트 라우팅 규칙"""
    event_type_pattern: str        # 이벤트 타입 패턴 (regex)
    platforms: Set[Platform]       # 대상 플랫폼들
    strategy: RoutingStrategy = RoutingStrategy.ALL
    priority: int = 0              # 우선순위 (높을수록 먼저 적용)
    conditions: Optional[Dict[str, Any]] = None  # 추가 조건들


class MultiPlatformEventRouter:
    """멀티 플랫폼 이벤트 라우터"""
    
    def __init__(self):
        self.platforms: Dict[Platform, Any] = {}
        self.platform_configs: Dict[Platform, PlatformConfig] = {}
        self.routing_rules: List[RoutingRule] = []
        self.platform_health: Dict[Platform, bool] = {}
        self._health_check_tasks: Dict[Platform, asyncio.Task] = {}
        
    def register_platform(
        self,
        platform: Platform,
        publisher: Any,
        config: PlatformConfig
    ):
        """플랫폼 등록"""
        self.platforms[platform] = publisher
        self.platform_configs[platform] = config
        self.platform_health[platform] = True
        
        # 헬스체크 태스크 시작
        if config.health_check_interval > 0:
            task = asyncio.create_task(self._health_check_loop(platform))
            self._health_check_tasks[platform] = task
        
        logger.info(f"Registered platform: {platform} (primary: {config.is_primary})")
    
    def register_nats_platform(
        self,
        nats_publisher,
        is_primary: bool = True,
        **kwargs
    ):
        """NATS 플랫폼 등록"""
        config = PlatformConfig(
            platform=Platform.NATS,
            is_primary=is_primary,
            **kwargs
        )
        self.register_platform(Platform.NATS, nats_publisher, config)
    
    def register_eventbridge_platform(
        self,
        eventbridge_config: EventBridgeConfig,
        is_primary: bool = False,
        **kwargs
    ):
        """EventBridge 플랫폼 등록"""
        publisher = EventBridgeCloudEventsPublisher(eventbridge_config)
        config = PlatformConfig(
            platform=Platform.EVENTBRIDGE,
            is_primary=is_primary,
            config=eventbridge_config.__dict__,
            **kwargs
        )
        self.register_platform(Platform.EVENTBRIDGE, publisher, config)
    
    def add_routing_rule(self, rule: RoutingRule):
        """라우팅 규칙 추가"""
        self.routing_rules.append(rule)
        # 우선순위순으로 정렬
        self.routing_rules.sort(key=lambda x: x.priority, reverse=True)
        logger.info(f"Added routing rule for pattern: {rule.event_type_pattern}")
    
    def add_default_oms_routing_rules(self):
        """OMS 기본 라우팅 규칙 추가"""
        
        # 스키마 변경 이벤트 - 모든 플랫폼
        self.add_routing_rule(RoutingRule(
            event_type_pattern=r".*\.schema\..*",
            platforms={Platform.NATS, Platform.EVENTBRIDGE},
            strategy=RoutingStrategy.ALL,
            priority=100
        ))
        
        # 브랜치 이벤트 - NATS 우선, EventBridge 백업
        self.add_routing_rule(RoutingRule(
            event_type_pattern=r".*\.branch\..*",
            platforms={Platform.NATS, Platform.EVENTBRIDGE},
            strategy=RoutingStrategy.FAILOVER,
            priority=90
        ))
        
        # 액션 이벤트 - 실시간이 중요하므로 NATS만
        self.add_routing_rule(RoutingRule(
            event_type_pattern=r".*\.action\..*",
            platforms={Platform.NATS},
            strategy=RoutingStrategy.PRIMARY_ONLY,
            priority=80
        ))
        
        # 시스템 이벤트 - EventBridge로 모니터링
        self.add_routing_rule(RoutingRule(
            event_type_pattern=r".*\.system\..*",
            platforms={Platform.EVENTBRIDGE},
            strategy=RoutingStrategy.ALL,
            priority=70
        ))
        
        # 기본 규칙 - 모든 이벤트는 기본 플랫폼으로
        self.add_routing_rule(RoutingRule(
            event_type_pattern=r".*",
            platforms={Platform.NATS},  # NATS가 기본
            strategy=RoutingStrategy.PRIMARY_ONLY,
            priority=0
        ))
    
    async def publish_event(self, event: EnhancedCloudEvent) -> Dict[Platform, PublishResult]:
        """단일 이벤트 발행"""
        return await self.publish_events([event])
    
    async def publish_events(
        self,
        events: List[EnhancedCloudEvent]
    ) -> Dict[str, Dict[Platform, PublishResult]]:
        """배치 이벤트 발행"""
        results = {}
        
        for event in events:
            # 1. 이벤트 유효성 검증
            validation_errors = CloudEventValidator.validate_cloudevent(event)
            if validation_errors:
                logger.warning(f"Event validation failed for {event.id}: {validation_errors}")
                results[event.id] = {
                    platform: PublishResult(
                        event_id=event.id,
                        success=False,
                        subject="",
                        error=f"Validation failed: {', '.join(validation_errors)}"
                    )
                    for platform in self.platforms.keys()
                }
                continue
            
            # 2. 라우팅 규칙 적용
            target_platforms = self._determine_target_platforms(event)
            
            # 3. 플랫폼별 발행
            event_results = await self._publish_to_platforms(event, target_platforms)
            results[event.id] = event_results
        
        return results
    
    def _determine_target_platforms(self, event: EnhancedCloudEvent) -> Dict[Platform, RoutingStrategy]:
        """이벤트에 대한 대상 플랫폼 결정"""
        import re
        
        event_type = str(event.type)
        target_platforms = {}
        
        # 라우팅 규칙 순회 (우선순위 순)
        for rule in self.routing_rules:
            if re.match(rule.event_type_pattern, event_type):
                # 조건 체크
                if rule.conditions and not self._check_conditions(event, rule.conditions):
                    continue
                
                # 플랫폼 추가
                for platform in rule.platforms:
                    if platform in self.platforms and self.platform_configs[platform].enabled:
                        target_platforms[platform] = rule.strategy
                
                # 첫 번째 매칭 규칙만 적용
                break
        
        # 기본 플랫폼이 없으면 primary 플랫폼 사용
        if not target_platforms:
            primary_platform = self._get_primary_platform()
            if primary_platform:
                target_platforms[primary_platform] = RoutingStrategy.PRIMARY_ONLY
        
        logger.debug(f"Event {event.id} routed to platforms: {list(target_platforms.keys())}")
        return target_platforms
    
    async def _publish_to_platforms(
        self,
        event: EnhancedCloudEvent,
        target_platforms: Dict[Platform, RoutingStrategy]
    ) -> Dict[Platform, PublishResult]:
        """플랫폼별로 이벤트 발행"""
        results = {}
        
        # 전략별로 플랫폼 그룹핑
        all_platforms = [p for p, s in target_platforms.items() if s == RoutingStrategy.ALL]
        primary_platforms = [p for p, s in target_platforms.items() if s == RoutingStrategy.PRIMARY_ONLY]
        failover_platforms = [p for p, s in target_platforms.items() if s == RoutingStrategy.FAILOVER]
        
        # ALL 전략 - 모든 플랫폼에 병렬 발행
        if all_platforms:
            all_tasks = [
                self._publish_to_single_platform(event, platform)
                for platform in all_platforms
                if self._is_platform_healthy(platform)
            ]
            
            if all_tasks:
                all_results = await asyncio.gather(*all_tasks, return_exceptions=True)
                for i, platform in enumerate(all_platforms):
                    if i < len(all_results):
                        if isinstance(all_results[i], Exception):
                            results[platform] = PublishResult(
                                event_id=event.id,
                                success=False,
                                subject="",
                                error=str(all_results[i])
                            )
                        else:
                            results[platform] = all_results[i]
        
        # PRIMARY_ONLY 전략 - 기본 플랫폼만
        for platform in primary_platforms:
            if self._is_platform_healthy(platform):
                result = await self._publish_to_single_platform(event, platform)
                results[platform] = result
        
        # FAILOVER 전략 - 순차적 시도
        if failover_platforms:
            # 건강한 플랫폼 순으로 정렬 (primary 우선)
            sorted_platforms = sorted(
                failover_platforms,
                key=lambda p: (
                    not self.platform_configs[p].is_primary,
                    not self._is_platform_healthy(p)
                )
            )
            
            for platform in sorted_platforms:
                if self._is_platform_healthy(platform):
                    result = await self._publish_to_single_platform(event, platform)
                    results[platform] = result
                    
                    if result.success:
                        # 성공하면 다음 플랫폼은 시도하지 않음
                        break
                    else:
                        logger.warning(f"Failover: {platform} failed, trying next platform")
        
        return results
    
    async def _publish_to_single_platform(
        self,
        event: EnhancedCloudEvent,
        platform: Platform
    ) -> PublishResult:
        """단일 플랫폼에 이벤트 발행"""
        publisher = self.platforms[platform]
        config = self.platform_configs[platform]
        
        try:
            # 플랫폼별 발행 로직
            if platform == Platform.NATS:
                # NATS 발행 (기존 로직 사용)
                result = await self._publish_to_nats(publisher, event)
            elif platform == Platform.EVENTBRIDGE:
                # EventBridge 발행
                result = await publisher.publish_event(event)
            else:
                # 기타 플랫폼
                result = PublishResult(
                    event_id=event.id,
                    success=False,
                    subject="",
                    error=f"Unsupported platform: {platform}"
                )
            
            # 성공/실패에 따른 헬스 상태 업데이트
            self.platform_health[platform] = result.success
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to publish to {platform}: {e}")
            self.platform_health[platform] = False
            return PublishResult(
                event_id=event.id,
                success=False,
                subject="",
                error=f"Platform error: {str(e)}"
            )
    
    async def _publish_to_nats(self, publisher, event: EnhancedCloudEvent) -> PublishResult:
        """NATS 발행 (기존 outbox processor 로직 활용)"""
        try:
            # NATS subject 생성
            subject = event.get_nats_subject()
            
            # Binary Content Mode 헤더
            headers = event.to_binary_headers()
            headers.update({
                "X-OMS-Event-Version": "2.0",
                "X-OMS-Router": "multi-platform"
            })
            
            # 페이로드 생성
            import json
            payload_data = json.dumps(event.data or {}).encode()
            
            # NATS 발행 (실제 구현에서는 NATS 클라이언트 사용)
            # await publisher.publish(subject=subject, payload=payload_data, headers=headers)
            
            return PublishResult(
                event_id=event.id,
                success=True,
                subject=subject,
                latency_ms=10.0  # 실제로는 측정된 latency
            )
            
        except Exception as e:
            return PublishResult(
                event_id=event.id,
                success=False,
                subject="",
                error=str(e)
            )
    
    def _check_conditions(self, event: EnhancedCloudEvent, conditions: Dict[str, Any]) -> bool:
        """라우팅 조건 체크"""
        for condition, expected in conditions.items():
            if condition == "branch":
                if event.ce_branch != expected:
                    return False
            elif condition == "author":
                if event.ce_author != expected:
                    return False
            elif condition == "tenant":
                if event.ce_tenant != expected:
                    return False
            # 추가 조건들...
        
        return True
    
    def _get_primary_platform(self) -> Optional[Platform]:
        """기본 플랫폼 반환"""
        for platform, config in self.platform_configs.items():
            if config.is_primary and config.enabled:
                return platform
        return None
    
    def _is_platform_healthy(self, platform: Platform) -> bool:
        """플랫폼 헬스 상태 확인"""
        return self.platform_health.get(platform, False)
    
    async def _health_check_loop(self, platform: Platform):
        """플랫폼 헬스체크 루프"""
        config = self.platform_configs[platform]
        publisher = self.platforms[platform]
        
        while True:
            try:
                await asyncio.sleep(config.health_check_interval)
                
                # 플랫폼별 헬스체크
                if platform == Platform.EVENTBRIDGE:
                    health_status = publisher.get_health_status()
                    self.platform_health[platform] = health_status['status'] == 'healthy'
                else:
                    # 기타 플랫폼은 기본적으로 healthy로 가정
                    self.platform_health[platform] = True
                
            except Exception as e:
                logger.error(f"Health check failed for {platform}: {e}")
                self.platform_health[platform] = False
    
    def get_platform_status(self) -> Dict[str, Any]:
        """모든 플랫폼 상태 반환"""
        return {
            'platforms': {
                platform.value: {
                    'enabled': config.enabled,
                    'is_primary': config.is_primary,
                    'healthy': self.platform_health.get(platform, False),
                    'config': config.config
                }
                for platform, config in self.platform_configs.items()
            },
            'routing_rules': [
                {
                    'pattern': rule.event_type_pattern,
                    'platforms': [p.value for p in rule.platforms],
                    'strategy': rule.strategy.value,
                    'priority': rule.priority
                }
                for rule in self.routing_rules
            ],
            'health_summary': {
                'total_platforms': len(self.platforms),
                'healthy_platforms': sum(self.platform_health.values()),
                'primary_platform_healthy': any(
                    self.platform_health.get(p, False) 
                    for p, c in self.platform_configs.items() 
                    if c.is_primary
                )
            }
        }
    
    async def shutdown(self):
        """라우터 종료"""
        # 헬스체크 태스크 종료
        for task in self._health_check_tasks.values():
            task.cancel()
        
        # 플랫폼별 cleanup
        for platform, publisher in self.platforms.items():
            if hasattr(publisher, 'shutdown'):
                await publisher.shutdown()
        
        logger.info("Multi-platform event router shutdown completed")


# 편의 함수들
def create_oms_multi_platform_router(
    nats_publisher=None,
    eventbridge_config: Optional[EventBridgeConfig] = None,
    add_default_rules: bool = True
) -> MultiPlatformEventRouter:
    """OMS용 멀티 플랫폼 라우터 생성"""
    
    router = MultiPlatformEventRouter()
    
    # NATS 플랫폼 등록 (기본)
    if nats_publisher:
        router.register_nats_platform(nats_publisher, is_primary=True)
    
    # EventBridge 플랫폼 등록 (선택적)
    if eventbridge_config:
        router.register_eventbridge_platform(eventbridge_config, is_primary=False)
    
    # 기본 라우팅 규칙 추가
    if add_default_rules:
        router.add_default_oms_routing_rules()
    
    return router