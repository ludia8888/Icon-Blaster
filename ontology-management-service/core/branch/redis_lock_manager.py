"""
Redis-based Context-Aware Distributed Lock Manager

교착상태(Deadlock)를 방지하고 예측 가능한 잠금 메커니즘을 제공합니다.
"""

import asyncio
import contextvars
import hashlib
import json
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import IntEnum
from typing import Optional, Dict, List, Set, Any, AsyncContextManager, AsyncIterator

import redis.asyncio as redis
from redis.exceptions import RedisError, LockError as RedisLockError

from models.branch_state import LockType, LockScope
from core.branch.lock_manager import LockConflictError
from common_logging.setup import get_logger

logger = get_logger(__name__)


# 현재 스레드/코루틴의 잠금 컨텍스트
current_locks_context: contextvars.ContextVar[List['LockInfo']] = contextvars.ContextVar(
    'current_locks', default=[]
)


class LockHierarchy(IntEnum):
    """잠금 계층 정의 - 숫자가 작을수록 상위 계층"""
    BRANCH = 1
    RESOURCE_TYPE = 2
    RESOURCE = 3


@dataclass
class LockInfo:
    """획득한 잠금 정보"""
    lock_id: str
    resource_id: str
    lock_type: LockType
    lock_scope: LockScope
    hierarchy_level: int
    acquired_at: datetime
    ttl_seconds: int
    owner_id: str


class LockHierarchyViolationError(Exception):
    """잠금 계층 위반 오류"""
    pass


class RedisLockManager:
    """
    Redis 기반 분산 잠금 관리자
    
    특징:
    1. Context-aware: 현재 보유한 잠금 추적
    2. 계층적 잠금 순서 강제로 교착상태 방지
    3. TTL 기반 자동 만료로 orphan lock 방지
    4. 세밀한 오류 처리
    """
    
    def __init__(
        self, 
        redis_client: redis.Redis,
        namespace: str = "oms:locks",
        default_ttl: int = 300,  # 5분
        retry_delay: float = 0.1,
        max_retries: int = 50
    ):
        self.redis = redis_client
        self.namespace = namespace
        self.default_ttl = default_ttl
        self.retry_delay = retry_delay
        self.max_retries = max_retries
        
        # 잠금 획득 시 사용할 고유 ID (프로세스/인스턴스 식별용)
        self.owner_id = f"{uuid.uuid4().hex[:8]}"
        
    def _make_lock_key(self, resource_id: str) -> str:
        """Redis 키 생성"""
        return f"{self.namespace}:{resource_id}"
    
    def _get_hierarchy_level(self, lock_scope: LockScope) -> int:
        """잠금 스코프의 계층 레벨 반환"""
        mapping = {
            LockScope.BRANCH: LockHierarchy.BRANCH,
            LockScope.RESOURCE_TYPE: LockHierarchy.RESOURCE_TYPE,
            LockScope.RESOURCE: LockHierarchy.RESOURCE
        }
        return mapping.get(lock_scope, LockHierarchy.RESOURCE)
    
    def _validate_lock_hierarchy(self, new_lock_scope: LockScope) -> None:
        """
        잠금 계층 순서 검증
        
        현재 보유한 잠금보다 상위 계층의 잠금을 획득하려 하면 오류 발생
        """
        current_locks = current_locks_context.get()
        new_hierarchy = self._get_hierarchy_level(new_lock_scope)
        
        for held_lock in current_locks:
            if held_lock.hierarchy_level > new_hierarchy:
                raise LockHierarchyViolationError(
                    f"Cannot acquire {new_lock_scope.value} lock while holding "
                    f"{LockScope(held_lock.lock_scope).value} lock. "
                    f"This would violate lock hierarchy and risk deadlock."
                )
    
    @asynccontextmanager
    async def acquire_lock(
        self,
        resource_id: str,
        lock_type: LockType = LockType.EXCLUSIVE,
        lock_scope: LockScope = LockScope.RESOURCE,
        ttl_seconds: Optional[int] = None,
        wait_timeout: Optional[float] = None
    ) -> AsyncIterator[LockInfo]:
        """
        분산 잠금 획득 (컨텍스트 매니저)
        
        Args:
            resource_id: 잠금 대상 리소스 ID
            lock_type: 잠금 타입 (EXCLUSIVE/SHARED)
            lock_scope: 잠금 범위
            ttl_seconds: 잠금 TTL (기본값: self.default_ttl)
            wait_timeout: 잠금 대기 시간 제한
            
        Yields:
            LockInfo: 획득한 잠금 정보
            
        Raises:
            LockHierarchyViolationError: 잠금 계층 위반
            LockConflictError: 잠금 획득 실패
            RedisError: Redis 연결 오류
        """
        # 1. 잠금 계층 검증
        self._validate_lock_hierarchy(lock_scope)
        
        # 2. 잠금 정보 생성
        lock_id = f"{self.owner_id}:{uuid.uuid4().hex[:8]}"
        lock_key = self._make_lock_key(resource_id)
        ttl = ttl_seconds or self.default_ttl
        
        lock_info = LockInfo(
            lock_id=lock_id,
            resource_id=resource_id,
            lock_type=lock_type,
            lock_scope=lock_scope,
            hierarchy_level=self._get_hierarchy_level(lock_scope),
            acquired_at=datetime.now(timezone.utc),
            ttl_seconds=ttl,
            owner_id=self.owner_id
        )
        
        acquired = False
        start_time = asyncio.get_event_loop().time()
        
        try:
            # 3. 잠금 획득 시도
            if lock_type == LockType.EXCLUSIVE:
                acquired = await self._acquire_exclusive_lock(
                    lock_key, lock_id, ttl, wait_timeout, start_time
                )
            else:  # SHARED
                acquired = await self._acquire_shared_lock(
                    lock_key, lock_id, ttl, wait_timeout, start_time
                )
            
            if not acquired:
                raise LockConflictError(
                    f"Failed to acquire {lock_type.value} lock on {resource_id} "
                    f"within timeout"
                )
            
            # 4. 컨텍스트에 잠금 추가
            current_locks = current_locks_context.get()
            current_locks.append(lock_info)
            current_locks_context.set(current_locks)
            
            logger.debug(
                f"Acquired {lock_type.value} lock on {resource_id} "
                f"(lock_id: {lock_id}, ttl: {ttl}s)"
            )
            
            yield lock_info
            
        except RedisError as e:
            # Redis 연결 오류는 그대로 전파
            logger.error(f"Redis error while acquiring lock: {e}")
            raise
            
        finally:
            if acquired:
                # 5. 잠금 해제
                try:
                    await self._release_lock(lock_key, lock_id, lock_type)
                    logger.debug(f"Released lock {lock_id} on {resource_id}")
                except Exception as e:
                    logger.error(f"Error releasing lock {lock_id}: {e}")
                
                # 6. 컨텍스트에서 제거
                current_locks = current_locks_context.get()
                current_locks = [l for l in current_locks if l.lock_id != lock_id]
                current_locks_context.set(current_locks)
    
    async def _acquire_exclusive_lock(
        self,
        lock_key: str,
        lock_id: str,
        ttl: int,
        wait_timeout: Optional[float],
        start_time: float
    ) -> bool:
        """독점 잠금 획득"""
        # SET key value NX PX ttl
        # NX: 키가 없을 때만 설정
        # PX: 밀리초 단위 TTL
        
        retry_count = 0
        while retry_count < self.max_retries:
            # 원자적 잠금 시도
            result = await self.redis.set(
                lock_key,
                lock_id,
                nx=True,  # Not eXists
                px=ttl * 1000  # TTL in milliseconds
            )
            
            if result:
                return True
            
            # 타임아웃 확인
            if wait_timeout:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= wait_timeout:
                    return False
            
            # 재시도 대기
            await asyncio.sleep(self.retry_delay)
            retry_count += 1
        
        return False
    
    async def _acquire_shared_lock(
        self,
        lock_key: str,
        lock_id: str,
        ttl: int,
        wait_timeout: Optional[float],
        start_time: float
    ) -> bool:
        """공유 잠금 획득 (Redis Hash 사용)"""
        shared_key = f"{lock_key}:shared"
        
        retry_count = 0
        while retry_count < self.max_retries:
            # 독점 잠금이 있는지 확인
            if await self.redis.exists(lock_key):
                # 독점 잠금이 있으면 대기
                if wait_timeout:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    if elapsed >= wait_timeout:
                        return False
                
                await asyncio.sleep(self.retry_delay)
                retry_count += 1
                continue
            
            # 공유 잠금 추가
            pipe = self.redis.pipeline()
            pipe.hset(shared_key, lock_id, json.dumps({
                "owner": self.owner_id,
                "acquired_at": datetime.now(timezone.utc).isoformat()
            }))
            pipe.expire(shared_key, ttl)
            await pipe.execute()
            
            return True
        
        return False
    
    async def _release_lock(self, lock_key: str, lock_id: str, lock_type: LockType):
        """잠금 해제"""
        if lock_type == LockType.EXCLUSIVE:
            # 독점 잠금: 값이 일치할 때만 삭제 (원자적 연산)
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            await self.redis.eval(lua_script, 1, lock_key, lock_id)
        else:
            # 공유 잠금: Hash에서 제거
            shared_key = f"{lock_key}:shared"
            await self.redis.hdel(shared_key, lock_id)
            
            # 마지막 공유 잠금이었다면 키 삭제
            if await self.redis.hlen(shared_key) == 0:
                await self.redis.delete(shared_key)
    
    async def get_lock_info(self, resource_id: str) -> Optional[Dict[str, Any]]:
        """특정 리소스의 잠금 정보 조회"""
        lock_key = self._make_lock_key(resource_id)
        
        # 독점 잠금 확인
        exclusive_lock = await self.redis.get(lock_key)
        if exclusive_lock:
            ttl = await self.redis.pttl(lock_key)
            return {
                "type": "exclusive",
                "lock_id": exclusive_lock,
                "ttl_ms": ttl
            }
        
        # 공유 잠금 확인
        shared_key = f"{lock_key}:shared"
        shared_locks = await self.redis.hgetall(shared_key)
        if shared_locks:
            return {
                "type": "shared",
                "count": len(shared_locks),
                "locks": {
                    lock_id.decode(): json.loads(data.decode())
                    for lock_id, data in shared_locks.items()
                }
            }
        
        return None
    
    async def force_unlock(self, resource_id: str) -> bool:
        """강제 잠금 해제 (관리자용)"""
        lock_key = self._make_lock_key(resource_id)
        shared_key = f"{lock_key}:shared"
        
        pipe = self.redis.pipeline()
        pipe.delete(lock_key)
        pipe.delete(shared_key)
        results = await pipe.execute()
        
        return any(results)
    
    async def list_all_locks(self) -> List[Dict[str, Any]]:
        """모든 활성 잠금 목록 조회"""
        pattern = f"{self.namespace}:*"
        locks = []
        
        async for key in self.redis.scan_iter(match=pattern):
            key_str = key.decode()
            
            # 공유 잠금 키는 제외
            if key_str.endswith(":shared"):
                continue
            
            resource_id = key_str.replace(f"{self.namespace}:", "")
            lock_info = await self.get_lock_info(resource_id)
            
            if lock_info:
                locks.append({
                    "resource_id": resource_id,
                    **lock_info
                })
        
        return locks
    
    def get_current_locks(self) -> List[LockInfo]:
        """현재 컨텍스트의 잠금 목록 반환"""
        return current_locks_context.get()
    
    async def extend_lock_ttl(self, lock_id: str, additional_seconds: int) -> bool:
        """잠금 TTL 연장"""
        current_locks = self.get_current_locks()
        
        for lock_info in current_locks:
            if lock_info.lock_id == lock_id:
                lock_key = self._make_lock_key(lock_info.resource_id)
                
                if lock_info.lock_type == LockType.EXCLUSIVE:
                    # 독점 잠금 TTL 연장
                    return await self.redis.expire(
                        lock_key, 
                        lock_info.ttl_seconds + additional_seconds
                    )
                else:
                    # 공유 잠금은 전체 Hash의 TTL 연장
                    shared_key = f"{lock_key}:shared"
                    return await self.redis.expire(
                        shared_key,
                        lock_info.ttl_seconds + additional_seconds
                    )
        
        return False


# 헬퍼 함수: 데코레이터로 사용
def with_lock(
    resource_id_param: str = "resource_id",
    lock_type: LockType = LockType.EXCLUSIVE,
    lock_scope: LockScope = LockScope.RESOURCE,
    ttl_seconds: int = 300
):
    """
    메소드에 자동 잠금을 적용하는 데코레이터
    
    Usage:
        @with_lock(resource_id_param="branch_name", lock_scope=LockScope.BRANCH)
        async def update_branch(self, branch_name: str):
            ...
    """
    def decorator(func):
        async def wrapper(self, *args, **kwargs):
            # resource_id 추출
            resource_id = kwargs.get(resource_id_param)
            if not resource_id:
                # 위치 인자에서 찾기
                import inspect
                sig = inspect.signature(func)
                params = list(sig.parameters.keys())
                if resource_id_param in params:
                    idx = params.index(resource_id_param)
                    if idx < len(args):
                        resource_id = args[idx]
            
            if not resource_id:
                raise ValueError(f"Cannot find {resource_id_param} in function arguments")
            
            # 잠금 획득 후 함수 실행
            async with self.lock_manager.acquire_lock(
                resource_id=resource_id,
                lock_type=lock_type,
                lock_scope=lock_scope,
                ttl_seconds=ttl_seconds
            ):
                return await func(self, *args, **kwargs)
        
        return wrapper
    return decorator