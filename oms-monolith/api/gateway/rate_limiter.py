"""
Rate Limiter 구현
API 요청 제한 기능
"""
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

from services.api_gateway.core.models import RateLimitPolicy, RequestContext

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate Limiter"""

    def __init__(self, redis_client, policy: RateLimitPolicy):
        self.redis = redis_client
        self.policy = policy
        self.key_prefix = "rate_limit:"

    async def check_rate_limit(self, context: RequestContext) -> Tuple[bool, Optional[Dict]]:
        """Rate limit 확인"""

        # Rate limit 키 생성
        key = self._generate_key(context)

        # 현재 시간 (분 단위)
        current_minute = int(time.time() / 60)

        # 분당 요청 수 확인
        if self.policy.requests_per_minute:
            minute_key = f"{key}:minute:{current_minute}"
            minute_count = await self._increment_counter(minute_key, 60)

            if minute_count > self.policy.requests_per_minute:
                return False, {
                    "limit": self.policy.requests_per_minute,
                    "window": "minute",
                    "retry_after": 60 - (int(time.time()) % 60)
                }

        # 시간당 요청 수 확인
        if self.policy.requests_per_hour:
            hour_key = f"{key}:hour:{int(time.time() / 3600)}"
            hour_count = await self._increment_counter(hour_key, 3600)

            if hour_count > self.policy.requests_per_hour:
                return False, {
                    "limit": self.policy.requests_per_hour,
                    "window": "hour",
                    "retry_after": 3600 - (int(time.time()) % 3600)
                }

        # 일일 요청 수 확인
        if self.policy.requests_per_day:
            day_key = f"{key}:day:{datetime.utcnow().strftime('%Y%m%d')}"
            day_count = await self._increment_counter(day_key, 86400)

            if day_count > self.policy.requests_per_day:
                return False, {
                    "limit": self.policy.requests_per_day,
                    "window": "day",
                    "retry_after": int((datetime.utcnow().replace(hour=0, minute=0, second=0) + timedelta(days=1) - datetime.utcnow()).total_seconds())
                }

        # Burst 확인
        burst_key = f"{key}:burst"
        burst_count = await self._check_burst(burst_key)

        if burst_count > self.policy.burst_size:
            return False, {
                "limit": self.policy.burst_size,
                "window": "burst",
                "retry_after": 1
            }

        return True, None

    def _generate_key(self, context: RequestContext) -> str:
        """Rate limit 키 생성"""

        parts = [self.key_prefix]

        if self.policy.by_user and context.user_id:
            parts.append(f"user:{context.user_id}")
        elif self.policy.by_ip:
            parts.append(f"ip:{context.client_ip}")
        else:
            parts.append("global")

        return ":".join(parts)

    async def _increment_counter(self, key: str, ttl: int) -> int:
        """카운터 증가"""

        # INCR 명령으로 원자적 증가
        count = await self.redis.incr(key)

        # 첫 요청인 경우 TTL 설정
        if count == 1:
            await self.redis.expire(key, ttl)

        return count

    async def _check_burst(self, key: str) -> int:
        """Burst 확인"""

        # 현재 시간 (마이크로초)
        now = int(time.time() * 1000000)

        # 1초 전 시간
        window_start = now - 1000000

        # 오래된 항목 제거
        await self.redis.zremrangebyscore(key, 0, window_start)

        # 현재 요청 추가
        await self.redis.zadd(key, {str(now): now})

        # 윈도우 내 요청 수
        count = await self.redis.zcard(key)

        # TTL 설정
        await self.redis.expire(key, 2)

        return count

    async def get_rate_limit_headers(self, context: RequestContext) -> Dict[str, str]:
        """Rate limit 헤더 생성"""

        key = self._generate_key(context)
        headers = {}

        # 분당 제한이 있는 경우
        if self.policy.requests_per_minute:
            current_minute = int(time.time() / 60)
            minute_key = f"{key}:minute:{current_minute}"

            count = await self.redis.get(minute_key)
            remaining = max(0, self.policy.requests_per_minute - (int(count) if count else 0))

            headers.update({
                "X-RateLimit-Limit": str(self.policy.requests_per_minute),
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": str(int((current_minute + 1) * 60))
            })

        return headers


class DistributedRateLimiter(RateLimiter):
    """분산 Rate Limiter (Redis Cluster 사용)"""

    def __init__(self, redis_cluster, policy: RateLimitPolicy):
        super().__init__(redis_cluster, policy)
        self.sliding_window = True  # Sliding window 알고리즘 사용

    async def check_rate_limit(self, context: RequestContext) -> Tuple[bool, Optional[Dict]]:
        """향상된 rate limit 확인 (sliding window)"""

        if self.sliding_window:
            return await self._check_sliding_window(context)
        else:
            return await super().check_rate_limit(context)

    async def _check_sliding_window(self, context: RequestContext) -> Tuple[bool, Optional[Dict]]:
        """Sliding window 알고리즘"""

        key = self._generate_key(context)
        now = time.time()

        # 분당 제한 확인
        if self.policy.requests_per_minute:
            window_start = now - 60
            window_key = f"{key}:sliding:minute"

            # 트랜잭션으로 원자적 처리
            pipe = self.redis.pipeline()

            # 오래된 항목 제거
            pipe.zremrangebyscore(window_key, 0, window_start)

            # 현재 요청 추가
            pipe.zadd(window_key, {str(now): now})

            # 윈도우 내 요청 수 확인
            pipe.zcard(window_key)

            # TTL 설정
            pipe.expire(window_key, 120)

            results = await pipe.execute()
            count = results[2]

            if count > self.policy.requests_per_minute:
                # 가장 오래된 요청 시간 조회
                oldest = await self.redis.zrange(window_key, 0, 0, withscores=True)
                if oldest:
                    retry_after = int(60 - (now - oldest[0][1]))
                else:
                    retry_after = 60

                return False, {
                    "limit": self.policy.requests_per_minute,
                    "window": "sliding_minute",
                    "current": count,
                    "retry_after": retry_after
                }

        return True, None
