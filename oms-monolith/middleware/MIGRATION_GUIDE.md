# Middleware 리팩토링 마이그레이션 가이드

## 개요

기존의 대용량 미들웨어 파일들(700-800줄)을 도메인별 패키지로 모듈화했습니다.

## 변경 사항

### 1. Health Monitoring

**기존:**
```python
from middleware.component_health import ComponentHealthMonitor, HealthCheck

monitor = ComponentHealthMonitor()
```

**새로운 구조:**
```python
from middleware.health import HealthCoordinator
from middleware.health.checks import DatabaseHealthCheck, RedisHealthCheck

coordinator = HealthCoordinator("my_service")
coordinator.register_check(DatabaseHealthCheck(connection_string))
coordinator.register_check(RedisHealthCheck())
```

### 2. Rate Limiting

**기존:**
```python
from middleware.rate_limiter import RateLimiter, RateLimitAlgorithm

limiter = RateLimiter(algorithm=RateLimitAlgorithm.SLIDING_WINDOW)
```

**새로운 구조:**
```python
from middleware.rate_limiting import RateLimitCoordinator, RateLimitConfig
from middleware.rate_limiting.models import RateLimitAlgorithm, RateLimitScope

config = RateLimitConfig(
    requests_per_window=100,
    window_seconds=60,
    algorithm=RateLimitAlgorithm.SLIDING_WINDOW,
    scope=RateLimitScope.USER
)
coordinator = RateLimitCoordinator(config)
```

### 3. 데코레이터 사용법

**Rate Limiting 데코레이터:**
```python
from middleware.rate_limiting import RateLimiter

limiter = RateLimiter()

@limiter.limit(requests=10, window=60)
async def my_api_endpoint(request):
    # 처리 로직
    pass
```

## 주요 개선사항

### 1. 명확한 책임 분리
- 각 모듈이 단일 책임 원칙을 따름
- 파일당 200-300줄로 축소

### 2. 재사용 가능한 컴포넌트
```python
# 공통 Redis 유틸리티
from middleware.common import RedisClient, RedisKeyPatterns

# 공통 메트릭 수집
from middleware.common import MetricsCollector

# 공통 재시도 로직
from middleware.common import exponential_backoff
```

### 3. 확장 가능한 구조
```python
# 커스텀 헬스체크 추가
from middleware.health.checks.base import HealthCheck

class CustomHealthCheck(HealthCheck):
    async def check(self):
        # 커스텀 로직
        pass

# 커스텀 rate limiting 전략
from middleware.rate_limiting.strategies.base import RateLimitStrategy

class CustomStrategy(RateLimitStrategy):
    async def check_limit(self, key, state):
        # 커스텀 로직
        pass
```

## 통합 사용 예제

```python
# middleware_setup.py
from middleware.coordinator import MiddlewareCoordinator
from middleware.health import HealthCoordinator
from middleware.health.checks import DatabaseHealthCheck, RedisHealthCheck
from middleware.rate_limiting import RateLimitConfig

# 미들웨어 코디네이터 설정
coordinator = MiddlewareCoordinator()

# 헬스 체크 설정
health = HealthCoordinator("api_service")
health.register_check(DatabaseHealthCheck("postgresql://..."))
health.register_check(RedisHealthCheck())
await health.start()

# Rate limiting 설정
coordinator.rate_limiter.configure_endpoint("/api/users", RateLimitConfig(
    requests_per_window=100,
    window_seconds=60
))

# 요청 처리
result = await coordinator.process_request(
    request_id="req-123",
    user_id="user-456",
    ip_address="192.168.1.1",
    endpoint="/api/users",
    method="GET",
    request_data={}
)
```

## 테스트 방법

```python
# 단위 테스트 예제
import pytest
from middleware.health.checks import RedisHealthCheck
from middleware.health.models import HealthStatus

@pytest.mark.asyncio
async def test_redis_health_check():
    check = RedisHealthCheck()
    result = await check.execute()
    
    assert result.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.UNHEALTHY]
    assert result.duration_ms > 0
```

## 점진적 마이그레이션 전략

1. **Phase 1**: 새 모듈과 기존 모듈 병행 사용
2. **Phase 2**: 점진적으로 기존 코드를 새 모듈로 교체
3. **Phase 3**: 모든 참조가 교체되면 기존 파일 제거

## 주의사항

- 기존 파일들은 `middleware/legacy_backup/`에 백업됨
- 새 모듈은 Python 3.8+ 필요
- Redis 연결 설정이 환경변수로 이동됨