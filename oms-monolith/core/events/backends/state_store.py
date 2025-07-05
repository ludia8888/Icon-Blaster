"""
상태 저장소 - TerminusDB 내부 캐싱 활용
브랜치별 HEAD 상태 관리
"""
import logging
from typing import Dict, Optional

from shared.cache.smart_cache import SmartCacheManager

logger = logging.getLogger(__name__)


class StateStore:
    """상태 저장소 - TerminusDB 내부 캐싱 활용"""

    def __init__(self, redis_client, terminus_client=None):
        self.redis = redis_client  # 후방 호환성을 위해 유지
        self.cache = SmartCacheManager(terminus_client) if terminus_client else None
        self.key_prefix = "event_publisher:state:"

    async def get(self, key: str) -> Optional[str]:
        """상태 조회 - TerminusDB 내부 캐싱 우선 사용"""
        if self.cache:
            cache_key = f"{self.key_prefix}{key}"
            value = await self.cache.get_with_optimization(
                key=cache_key,
                db="oms",
                branch="_system",
                query_factory=lambda: self._get_from_redis(key),
                doc_type="EventState"
            )
            return value
        else:
            return await self._get_from_redis(key)

    async def _get_from_redis(self, key: str) -> Optional[str]:
        """Redis에서 상태 조회 (fallback)"""
        full_key = f"{self.key_prefix}{key}"
        value = await self.redis.get(full_key)
        return value

    async def set(self, key: str, value: str):
        """상태 저장 - TerminusDB 내부 캐싱 및 Redis 동시 저장"""
        # Redis에 저장 (기존 동작 유지)
        full_key = f"{self.key_prefix}{key}"
        await self.redis.set(full_key, value)

        # TerminusDB 내부 캐시에도 저장
        if self.cache:
            cache_key = f"{self.key_prefix}{key}"
            await self.cache.set_with_optimization(
                key=cache_key,
                value=value,
                db="oms",
                branch="_system",
                doc_type="EventState",
                access_pattern="frequent"
            )

    async def delete(self, key: str):
        """상태 삭제"""
        full_key = f"{self.key_prefix}{key}"
        await self.redis.delete(full_key)

    async def get_all_branch_states(self) -> Dict[str, str]:
        """모든 브랜치 상태 조회"""
        pattern = f"{self.key_prefix}branch:*:head"
        keys = await self.redis.keys(pattern)

        states = {}
        for key in keys:
            # 브랜치 이름 추출
            parts = key.split(":")
            if len(parts) >= 4:
                branch_name = parts[2]
                value = await self.redis.get(key)
                if value:
                    states[branch_name] = value

        return states
