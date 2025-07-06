"""
Distributed Lock Adapter

기존 BranchLockManager 인터페이스를 유지하면서
Redis 기반 잠금으로 전환하는 어댑터
"""

import asyncio
from typing import Optional, Dict, List, Any
from datetime import datetime, timezone, timedelta
from contextlib import AsyncExitStack

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from models.branch_state import (
    BranchState, BranchLock, BranchStateInfo,
    LockType, LockScope
)
from core.branch.lock_manager import BranchLockManager, LockConflictError
from core.branch.redis_lock_manager import RedisLockManager, LockInfo
from common_logging.setup import get_logger

logger = get_logger(__name__)


class DistributedLockAdapter(BranchLockManager):
    """
    기존 BranchLockManager 인터페이스를 구현하면서
    내부적으로 Redis 기반 분산 잠금을 사용하는 어댑터
    """
    
    def __init__(
        self,
        redis_client: redis.Redis,
        db_session: AsyncSession,
        cache_service=None,
        namespace: str = "oms:branch"
    ):
        # 부모 클래스 초기화 (캐시 서비스 활용)
        super().__init__(cache_service=cache_service, db_service=None)
        
        # Redis 기반 잠금 관리자
        self.redis_lock_manager = RedisLockManager(
            redis_client=redis_client,
            namespace=f"{namespace}:locks"
        )
        
        # DB 세션 (상태 저장용)
        self.db_session = db_session
        
        # 활성 잠금 추적 (비동기 컨텍스트 매니저 저장)
        self._active_locks: Dict[str, AsyncExitStack] = {}
        
    def _build_resource_id(
        self,
        branch_name: str,
        lock_scope: LockScope,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None
    ) -> str:
        """잠금 리소스 ID 생성"""
        if lock_scope == LockScope.BRANCH:
            return f"branch:{branch_name}"
        elif lock_scope == LockScope.RESOURCE_TYPE:
            return f"branch:{branch_name}:type:{resource_type}"
        else:  # RESOURCE
            return f"branch:{branch_name}:type:{resource_type}:id:{resource_id}"
    
    async def acquire_lock(
        self,
        branch_name: str,
        lock_type: LockType,
        locked_by: str,
        lock_scope: LockScope = LockScope.BRANCH,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        reason: str = "Lock acquired",
        timeout: Optional[timedelta] = None,
        enable_heartbeat: bool = True,
        heartbeat_interval: int = 60
    ) -> str:
        """
        브랜치 잠금 획득 - Redis 분산 잠금 사용
        
        Returns:
            lock_id: 획득한 잠금의 ID
        """
        # 리소스 ID 생성
        dist_resource_id = self._build_resource_id(
            branch_name, lock_scope, resource_type, resource_id
        )
        
        # TTL 계산
        ttl_seconds = int(timeout.total_seconds()) if timeout else 300
        
        # 비동기 컨텍스트 스택 생성
        exit_stack = AsyncExitStack()
        
        try:
            # Redis 분산 잠금 획득
            lock_info = await exit_stack.enter_async_context(
                self.redis_lock_manager.acquire_lock(
                    resource_id=dist_resource_id,
                    lock_type=lock_type,
                    lock_scope=lock_scope,
                    ttl_seconds=ttl_seconds,
                    wait_timeout=5.0  # 5초 대기
                )
            )
            
            # BranchLock 객체 생성 (호환성 유지)
            branch_lock = BranchLock(
                id=lock_info.lock_id,
                branch_name=branch_name,
                lock_type=lock_type,
                lock_scope=lock_scope,
                locked_by=locked_by,
                resource_type=resource_type,
                resource_id=resource_id,
                reason=reason,
                acquired_at=lock_info.acquired_at,
                expires_at=lock_info.acquired_at + timedelta(seconds=ttl_seconds),
                heartbeat_interval=heartbeat_interval,
                last_heartbeat=lock_info.acquired_at if enable_heartbeat else None,
                is_active=True
            )
            
            # 브랜치 상태 업데이트
            state_info = await self.get_branch_state(branch_name)
            state_info.active_locks.append(branch_lock)
            await self._store_branch_state(state_info)
            
            # 활성 잠금 추적
            self._active_locks[lock_info.lock_id] = exit_stack
            
            # Heartbeat 시작 (필요시)
            if enable_heartbeat:
                asyncio.create_task(
                    self._heartbeat_loop(
                        lock_info.lock_id,
                        branch_name,
                        heartbeat_interval
                    )
                )
            
            logger.info(
                f"Acquired {lock_type.value} lock on {branch_name} "
                f"(scope: {lock_scope.value}, id: {lock_info.lock_id})"
            )
            
            return lock_info.lock_id
            
        except Exception as e:
            # 실패 시 컨텍스트 정리
            await exit_stack.aclose()
            
            if "LockConflictError" in str(type(e)):
                raise LockConflictError(
                    f"Failed to acquire lock on {branch_name}: {str(e)}"
                )
            raise
    
    async def release_lock(
        self,
        lock_id: str,
        released_by: Optional[str] = None
    ) -> bool:
        """잠금 해제"""
        try:
            # 활성 잠금 확인
            if lock_id not in self._active_locks:
                logger.warning(f"Lock {lock_id} not found in active locks")
                return False
            
            # 컨텍스트 종료 (Redis 잠금 자동 해제)
            exit_stack = self._active_locks.pop(lock_id)
            await exit_stack.aclose()
            
            # 브랜치 상태에서 제거
            await self._remove_lock_from_state(lock_id)
            
            logger.info(f"Released lock {lock_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error releasing lock {lock_id}: {e}")
            return False
    
    async def extend_lock(
        self,
        lock_id: str,
        extension_time: timedelta,
        extended_by: Optional[str] = None
    ) -> bool:
        """잠금 TTL 연장"""
        try:
            # Redis TTL 연장
            success = await self.redis_lock_manager.extend_lock_ttl(
                lock_id,
                int(extension_time.total_seconds())
            )
            
            if success:
                # 브랜치 상태 업데이트
                await self._update_lock_expiry(lock_id, extension_time)
                logger.info(f"Extended lock {lock_id} by {extension_time}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error extending lock {lock_id}: {e}")
            return False
    
    async def _heartbeat_loop(
        self,
        lock_id: str,
        branch_name: str,
        interval: int
    ):
        """Heartbeat 루프"""
        while lock_id in self._active_locks:
            try:
                await asyncio.sleep(interval)
                
                # 잠금이 여전히 활성인지 확인
                if lock_id not in self._active_locks:
                    break
                
                # Heartbeat 업데이트
                state_info = await self.get_branch_state(branch_name)
                for lock in state_info.active_locks:
                    if lock.id == lock_id:
                        lock.last_heartbeat = datetime.now(timezone.utc)
                        break
                
                await self._store_branch_state(state_info)
                
                # TTL 갱신 (heartbeat 주기의 2배로 설정)
                await self.redis_lock_manager.extend_lock_ttl(
                    lock_id,
                    interval * 2
                )
                
            except Exception as e:
                logger.error(f"Heartbeat error for lock {lock_id}: {e}")
                break
    
    async def _remove_lock_from_state(self, lock_id: str):
        """브랜치 상태에서 잠금 제거"""
        # 모든 브랜치 검색 (최적화 필요)
        result = await self.db_session.execute(
            text("SELECT branch_name, state_data FROM branch_states")
        )
        
        for row in result:
            branch_name = row[0]
            state_info = BranchStateInfo.model_validate_json(row[1])
            
            # 해당 잠금 찾기
            original_count = len(state_info.active_locks)
            state_info.active_locks = [
                l for l in state_info.active_locks if l.id != lock_id
            ]
            
            # 변경되었으면 저장
            if len(state_info.active_locks) < original_count:
                await self._store_branch_state(state_info)
                break
    
    async def _update_lock_expiry(self, lock_id: str, extension: timedelta):
        """잠금 만료 시간 업데이트"""
        # 모든 브랜치 검색 (최적화 필요)
        result = await self.db_session.execute(
            text("SELECT branch_name, state_data FROM branch_states")
        )
        
        for row in result:
            branch_name = row[0]
            state_info = BranchStateInfo.model_validate_json(row[1])
            
            # 해당 잠금 찾아서 업데이트
            for lock in state_info.active_locks:
                if lock.id == lock_id:
                    lock.expires_at = lock.expires_at + extension
                    await self._store_branch_state(state_info)
                    return
    
    async def get_active_locks(self, branch_name: str) -> List[BranchLock]:
        """특정 브랜치의 활성 잠금 목록"""
        state_info = await self.get_branch_state(branch_name)
        
        # Redis 실제 상태와 동기화
        active_locks = []
        for lock in state_info.active_locks:
            resource_id = self._build_resource_id(
                branch_name,
                lock.lock_scope,
                lock.resource_type,
                lock.resource_id
            )
            
            # Redis에서 실제 잠금 확인
            lock_info = await self.redis_lock_manager.get_lock_info(resource_id)
            if lock_info:
                active_locks.append(lock)
        
        return active_locks
    
    async def has_active_locks(self, branch_name: str) -> bool:
        """브랜치에 활성 잠금이 있는지 확인"""
        locks = await self.get_active_locks(branch_name)
        return len(locks) > 0
    
    async def check_lock_conflict(
        self,
        branch_name: str,
        requested_lock_type: LockType,
        requested_scope: LockScope,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None
    ) -> Optional[BranchLock]:
        """잠금 충돌 확인"""
        # Redis에서 직접 확인
        dist_resource_id = self._build_resource_id(
            branch_name, requested_scope, resource_type, resource_id
        )
        
        lock_info = await self.redis_lock_manager.get_lock_info(dist_resource_id)
        
        if lock_info:
            # 충돌하는 잠금 정보 반환
            state_info = await self.get_branch_state(branch_name)
            for lock in state_info.active_locks:
                if (lock.lock_scope == requested_scope and
                    lock.resource_type == resource_type and
                    lock.resource_id == resource_id):
                    return lock
        
        return None
    
    async def force_release_expired_locks(self):
        """만료된 잠금 강제 해제"""
        # Redis TTL이 자동으로 처리하므로 DB 상태만 정리
        result = await self.db_session.execute(
            text("SELECT branch_name, state_data FROM branch_states")
        )
        
        for row in result:
            branch_name = row[0]
            state_info = BranchStateInfo.model_validate_json(row[1])
            
            # 만료된 잠금 제거
            now = datetime.now(timezone.utc)
            original_count = len(state_info.active_locks)
            
            state_info.active_locks = [
                lock for lock in state_info.active_locks
                if lock.expires_at > now
            ]
            
            if len(state_info.active_locks) < original_count:
                await self._store_branch_state(state_info)
                logger.info(
                    f"Cleaned {original_count - len(state_info.active_locks)} "
                    f"expired locks from branch {branch_name}"
                )