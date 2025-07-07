"""
Lock Monitor - 분산 잠금 모니터링 및 디버깅 도구

잠금 상태를 실시간으로 모니터링하고 교착상태를 감지합니다.
"""

import asyncio
from typing import Dict, List, Set, Optional, Any
from datetime import datetime, timezone
from dataclasses import dataclass
from collections import defaultdict

import redis.asyncio as redis
import networkx as nx

from core.branch.redis_lock_manager import RedisLockManager, LockInfo
from common_logging.setup import get_logger

logger = get_logger(__name__)


@dataclass
class LockWaitInfo:
    """잠금 대기 정보"""
    waiter_id: str
    waiting_for: str
    resource_id: str
    wait_started: datetime
    wait_duration_seconds: float


@dataclass
class DeadlockInfo:
    """교착상태 정보"""
    cycle: List[str]  # 순환 참조하는 프로세스 ID 리스트
    resources: List[str]  # 관련된 리소스 ID 리스트
    detected_at: datetime


class LockMonitor:
    """
    분산 잠금 모니터
    
    기능:
    1. 활성 잠금 실시간 모니터링
    2. 잠금 대기 상태 추적
    3. 교착상태 감지
    4. 잠금 통계 수집
    """
    
    def __init__(
        self,
        redis_client: redis.Redis,
        lock_manager: RedisLockManager,
        check_interval: int = 5
    ):
        self.redis = redis_client
        self.lock_manager = lock_manager
        self.check_interval = check_interval
        
        # 모니터링 데이터
        self.active_locks: Dict[str, LockInfo] = {}
        self.waiting_locks: Dict[str, LockWaitInfo] = {}
        self.lock_stats: Dict[str, Any] = defaultdict(int)
        
        # 교착상태 감지용 그래프
        self.wait_for_graph = nx.DiGraph()
        
        # 모니터링 태스크
        self._monitor_task: Optional[asyncio.Task] = None
        
    async def start_monitoring(self):
        """모니터링 시작"""
        if self._monitor_task:
            logger.warning("Monitor already running")
            return
        
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Lock monitor started")
    
    async def stop_monitoring(self):
        """모니터링 중지"""
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
            self._monitor_task = None
            logger.info("Lock monitor stopped")
    
    async def _monitor_loop(self):
        """모니터링 루프"""
        while True:
            try:
                # 1. 활성 잠금 수집
                await self._collect_active_locks()
                
                # 2. 대기 상태 분석
                await self._analyze_wait_states()
                
                # 3. 교착상태 감지
                deadlocks = self._detect_deadlocks()
                if deadlocks:
                    await self._handle_deadlocks(deadlocks)
                
                # 4. 통계 업데이트
                self._update_statistics()
                
                # 5. 대기
                await asyncio.sleep(self.check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitor error: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _collect_active_locks(self):
        """활성 잠금 정보 수집"""
        try:
            # Redis에서 모든 잠금 조회
            all_locks = await self.lock_manager.list_all_locks()
            
            # 활성 잠금 업데이트
            self.active_locks.clear()
            for lock_data in all_locks:
                resource_id = lock_data["resource_id"]
                
                # 간단한 LockInfo 생성 (실제로는 더 많은 정보 필요)
                lock_info = LockInfo(
                    lock_id=lock_data.get("lock_id", "unknown"),
                    resource_id=resource_id,
                    lock_type=lock_data.get("type", "exclusive"),
                    lock_scope=None,  # 실제 구현에서는 파싱 필요
                    hierarchy_level=0,
                    acquired_at=datetime.now(timezone.utc),
                    ttl_seconds=lock_data.get("ttl_ms", 0) // 1000,
                    owner_id=lock_data.get("lock_id", "").split(":")[0]
                )
                
                self.active_locks[resource_id] = lock_info
                
        except Exception as e:
            logger.error(f"Error collecting active locks: {e}")
    
    async def _analyze_wait_states(self):
        """대기 상태 분석"""
        # Redis에서 대기 중인 연결 정보 수집
        # 실제 구현에서는 Redis CLIENT LIST 명령 등을 사용
        
        # 여기서는 시뮬레이션
        # 실제로는 pg_locks나 Redis의 blocking 정보를 분석해야 함
        pass
    
    def _detect_deadlocks(self) -> List[DeadlockInfo]:
        """교착상태 감지"""
        deadlocks = []
        
        # Wait-for 그래프에서 사이클 찾기
        try:
            cycles = list(nx.simple_cycles(self.wait_for_graph))
            
            for cycle in cycles:
                # 사이클에 포함된 리소스 찾기
                resources = []
                for node in cycle:
                    if node in self.active_locks:
                        resources.append(self.active_locks[node].resource_id)
                
                deadlock = DeadlockInfo(
                    cycle=cycle,
                    resources=resources,
                    detected_at=datetime.now(timezone.utc)
                )
                deadlocks.append(deadlock)
                
                logger.error(
                    f"Deadlock detected! Cycle: {' -> '.join(cycle)} -> {cycle[0]}"
                )
                
        except Exception as e:
            logger.error(f"Error detecting deadlocks: {e}")
        
        return deadlocks
    
    async def _handle_deadlocks(self, deadlocks: List[DeadlockInfo]):
        """교착상태 처리"""
        for deadlock in deadlocks:
            logger.error(
                f"Handling deadlock: {len(deadlock.cycle)} processes involved"
            )
            
            # 가장 오래된 잠금을 희생양으로 선택
            victim = self._select_deadlock_victim(deadlock)
            
            if victim:
                logger.warning(f"Killing lock {victim} to resolve deadlock")
                # 실제로는 해당 프로세스에 시그널을 보내거나
                # 강제로 잠금을 해제해야 함
                # await self.lock_manager.force_unlock(victim)
            
            # 알림 발송 (실제 구현에서는 알림 시스템 연동)
            await self._send_deadlock_alert(deadlock)
    
    def _select_deadlock_victim(self, deadlock: DeadlockInfo) -> Optional[str]:
        """교착상태 희생양 선택"""
        # 간단한 전략: 가장 최근에 획득한 잠금
        latest_lock = None
        latest_time = datetime.min.replace(tzinfo=timezone.utc)
        
        for resource in deadlock.resources:
            if resource in self.active_locks:
                lock = self.active_locks[resource]
                if lock.acquired_at > latest_time:
                    latest_time = lock.acquired_at
                    latest_lock = resource
        
        return latest_lock
    
    async def _send_deadlock_alert(self, deadlock: DeadlockInfo):
        """교착상태 알림 발송"""
        # 실제 구현에서는 Slack, Email 등으로 알림
        logger.critical(
            f"DEADLOCK ALERT: {len(deadlock.cycle)} processes in deadlock"
        )
    
    def _update_statistics(self):
        """통계 업데이트"""
        self.lock_stats["total_active_locks"] = len(self.active_locks)
        self.lock_stats["total_waiting_locks"] = len(self.waiting_locks)
        self.lock_stats["last_check_time"] = datetime.now(timezone.utc)
    
    def get_lock_statistics(self) -> Dict[str, Any]:
        """잠금 통계 반환"""
        stats = dict(self.lock_stats)
        
        # 잠금 타입별 통계
        lock_types = defaultdict(int)
        for lock in self.active_locks.values():
            lock_types[lock.lock_type] += 1
        stats["locks_by_type"] = dict(lock_types)
        
        # 평균 대기 시간
        if self.waiting_locks:
            total_wait = sum(
                w.wait_duration_seconds for w in self.waiting_locks.values()
            )
            stats["avg_wait_seconds"] = total_wait / len(self.waiting_locks)
        else:
            stats["avg_wait_seconds"] = 0
        
        return stats
    
    def get_lock_graph(self) -> Dict[str, Any]:
        """잠금 그래프 시각화 데이터"""
        nodes = []
        edges = []
        
        # 노드 추가 (활성 잠금)
        for resource_id, lock in self.active_locks.items():
            nodes.append({
                "id": resource_id,
                "label": f"{resource_id}\n({lock.owner_id})",
                "type": "active",
                "owner": lock.owner_id
            })
        
        # 엣지 추가 (대기 관계)
        for waiter, wait_info in self.waiting_locks.items():
            edges.append({
                "from": waiter,
                "to": wait_info.waiting_for,
                "label": f"waiting {wait_info.wait_duration_seconds:.1f}s"
            })
        
        return {
            "nodes": nodes,
            "edges": edges,
            "has_cycle": len(list(nx.simple_cycles(self.wait_for_graph))) > 0
        }
    
    async def diagnose_lock_issues(self, resource_id: str) -> Dict[str, Any]:
        """특정 리소스의 잠금 문제 진단"""
        diagnosis = {
            "resource_id": resource_id,
            "status": "unknown",
            "issues": [],
            "recommendations": []
        }
        
        # 활성 잠금 확인
        if resource_id in self.active_locks:
            lock = self.active_locks[resource_id]
            diagnosis["status"] = "locked"
            diagnosis["lock_info"] = {
                "owner": lock.owner_id,
                "acquired_at": lock.acquired_at.isoformat(),
                "ttl_seconds": lock.ttl_seconds
            }
            
            # 잠금 시간이 너무 긴지 확인
            lock_duration = (
                datetime.now(timezone.utc) - lock.acquired_at
            ).total_seconds()
            
            if lock_duration > 300:  # 5분 이상
                diagnosis["issues"].append(
                    f"Lock held for {lock_duration:.0f} seconds"
                )
                diagnosis["recommendations"].append(
                    "Consider implementing finer-grained locking"
                )
        
        # 대기 상태 확인
        waiters = [
            w for w, info in self.waiting_locks.items()
            if info.waiting_for == resource_id
        ]
        
        if waiters:
            diagnosis["waiters"] = waiters
            diagnosis["issues"].append(
                f"{len(waiters)} processes waiting for this lock"
            )
            
            if len(waiters) > 5:
                diagnosis["recommendations"].append(
                    "High contention detected. Consider sharding or caching"
                )
        
        return diagnosis


# 전역 모니터 인스턴스 (싱글톤)
_monitor_instance: Optional[LockMonitor] = None


async def get_lock_monitor(
    redis_client: redis.Redis,
    lock_manager: RedisLockManager
) -> LockMonitor:
    """Lock Monitor 싱글톤 인스턴스 반환"""
    global _monitor_instance
    
    if _monitor_instance is None:
        _monitor_instance = LockMonitor(redis_client, lock_manager)
        await _monitor_instance.start_monitoring()
    
    return _monitor_instance