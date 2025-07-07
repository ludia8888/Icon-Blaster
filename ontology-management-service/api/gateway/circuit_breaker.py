"""
Circuit Breaker 패턴 구현
장애 전파 방지
"""
import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit 상태"""
    CLOSED = "closed"      # 정상 (요청 허용)
    OPEN = "open"          # 차단 (요청 거부)
    HALF_OPEN = "half_open"  # 반개방 (테스트 요청 허용)


@dataclass
class CircuitConfig:
    """Circuit Breaker 설정"""
    failure_threshold: int = 5          # 실패 임계값
    success_threshold: int = 2          # 성공 임계값 (HALF_OPEN -> CLOSED)
    timeout: float = 60.0              # OPEN 상태 유지 시간 (초)
    half_open_max_requests: int = 3    # HALF_OPEN 상태에서 허용할 최대 요청 수


class CircuitBreaker:
    """Circuit Breaker"""

    def __init__(self, config: CircuitConfig = None):
        self.config = config or CircuitConfig()
        self.circuits: Dict[str, Circuit] = {}
        self._lock = asyncio.Lock()

    async def is_closed(self, service_name: str) -> bool:
        """Circuit이 닫혀있는지 확인 (요청 허용 여부)"""

        circuit = self._get_or_create_circuit(service_name)
        return await circuit.can_request()

    async def record_success(self, service_name: str):
        """성공 기록"""

        circuit = self._get_or_create_circuit(service_name)
        await circuit.record_success()

    async def record_failure(self, service_name: str):
        """실패 기록"""

        circuit = self._get_or_create_circuit(service_name)
        await circuit.record_failure()

    def get_state(self, service_name: str) -> CircuitState:
        """Circuit 상태 조회"""

        circuit = self._get_or_create_circuit(service_name)
        return circuit.state

    def get_metrics(self, service_name: str) -> Dict:
        """Circuit 메트릭 조회"""

        circuit = self._get_or_create_circuit(service_name)
        return circuit.get_metrics()

    def _get_or_create_circuit(self, service_name: str) -> 'Circuit':
        """Circuit 조회 또는 생성"""

        if service_name not in self.circuits:
            self.circuits[service_name] = Circuit(service_name, self.config)
        return self.circuits[service_name]


class Circuit:
    """개별 Circuit"""

    def __init__(self, name: str, config: CircuitConfig):
        self.name = name
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.last_state_change: float = time.time()
        self.half_open_requests = 0
        self._lock = asyncio.Lock()

        # 메트릭
        self.total_requests = 0
        self.total_failures = 0
        self.total_successes = 0
        self.consecutive_failures = 0
        self.consecutive_successes = 0

    async def can_request(self) -> bool:
        """요청 가능 여부 확인"""

        async with self._lock:
            current_time = time.time()

            if self.state == CircuitState.CLOSED:
                return True

            elif self.state == CircuitState.OPEN:
                # 타임아웃 확인
                if self.last_failure_time and (current_time - self.last_failure_time) >= self.config.timeout:
                    # HALF_OPEN으로 전환
                    logger.info(f"Circuit {self.name}: OPEN -> HALF_OPEN")
                    self._transition_to(CircuitState.HALF_OPEN)
                    return True
                return False

            else:  # HALF_OPEN
                # 최대 요청 수 확인
                if self.half_open_requests < self.config.half_open_max_requests:
                    self.half_open_requests += 1
                    return True
                return False

    async def record_success(self):
        """성공 기록"""

        async with self._lock:
            self.total_requests += 1
            self.total_successes += 1
            self.consecutive_successes += 1
            self.consecutive_failures = 0

            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1

                # 성공 임계값 도달 시 CLOSED로 전환
                if self.success_count >= self.config.success_threshold:
                    logger.info(f"Circuit {self.name}: HALF_OPEN -> CLOSED")
                    self._transition_to(CircuitState.CLOSED)

            elif self.state == CircuitState.OPEN:
                # OPEN 상태에서 성공은 무시 (발생하면 안 됨)
                logger.warning(f"Success recorded in OPEN state for {self.name}")

    async def record_failure(self):
        """실패 기록"""

        async with self._lock:
            self.total_requests += 1
            self.total_failures += 1
            self.consecutive_failures += 1
            self.consecutive_successes = 0
            self.last_failure_time = time.time()

            if self.state == CircuitState.CLOSED:
                self.failure_count += 1

                # 실패 임계값 도달 시 OPEN으로 전환
                if self.failure_count >= self.config.failure_threshold:
                    logger.warning(f"Circuit {self.name}: CLOSED -> OPEN (failures: {self.failure_count})")
                    self._transition_to(CircuitState.OPEN)

            elif self.state == CircuitState.HALF_OPEN:
                # HALF_OPEN에서 실패 시 즉시 OPEN으로
                logger.warning(f"Circuit {self.name}: HALF_OPEN -> OPEN (failure in half-open)")
                self._transition_to(CircuitState.OPEN)

    def _transition_to(self, new_state: CircuitState):
        """상태 전환"""

        self.state = new_state
        self.last_state_change = time.time()

        if new_state == CircuitState.CLOSED:
            self.failure_count = 0
            self.success_count = 0
            self.half_open_requests = 0

        elif new_state == CircuitState.OPEN:
            self.failure_count = 0
            self.success_count = 0
            self.half_open_requests = 0

        elif new_state == CircuitState.HALF_OPEN:
            self.failure_count = 0
            self.success_count = 0
            self.half_open_requests = 0

    def get_metrics(self) -> Dict:
        """메트릭 조회"""

        uptime = time.time() - self.last_state_change

        return {
            "name": self.name,
            "state": self.state.value,
            "uptime_seconds": uptime,
            "total_requests": self.total_requests,
            "total_failures": self.total_failures,
            "total_successes": self.total_successes,
            "failure_rate": self.total_failures / self.total_requests if self.total_requests > 0 else 0,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "success_threshold": self.config.success_threshold,
                "timeout": self.config.timeout
            }
        }


class DistributedCircuitBreaker(CircuitBreaker):
    """분산 Circuit Breaker (Redis 기반)"""

    def __init__(self, redis_client, config: CircuitConfig = None):
        super().__init__(config)
        self.redis = redis_client
        self.key_prefix = "circuit_breaker:"

    async def is_closed(self, service_name: str) -> bool:
        """분산 환경에서 Circuit 상태 확인"""

        state_key = f"{self.key_prefix}{service_name}:state"
        state = await self.redis.get(state_key)

        if not state:
            # 초기 상태는 CLOSED
            await self.redis.set(state_key, CircuitState.CLOSED.value)
            return True

        if state == CircuitState.CLOSED.value:
            return True

        elif state == CircuitState.OPEN.value:
            # 타임아웃 확인
            timeout_key = f"{self.key_prefix}{service_name}:timeout"
            timeout_time = await self.redis.get(timeout_key)

            if timeout_time and time.time() >= float(timeout_time):
                # HALF_OPEN으로 전환
                await self.redis.set(state_key, CircuitState.HALF_OPEN.value)
                await self.redis.delete(timeout_key)
                return True
            return False

        else:  # HALF_OPEN
            # 동시 요청 수 제한
            counter_key = f"{self.key_prefix}{service_name}:half_open_count"
            count = await self.redis.incr(counter_key)
            await self.redis.expire(counter_key, 60)  # 1분 후 자동 삭제

            return count <= self.config.half_open_max_requests

    async def record_success(self, service_name: str):
        """분산 환경에서 성공 기록"""

        state_key = f"{self.key_prefix}{service_name}:state"
        state = await self.redis.get(state_key)

        if state == CircuitState.HALF_OPEN.value:
            success_key = f"{self.key_prefix}{service_name}:success_count"
            count = await self.redis.incr(success_key)

            if count >= self.config.success_threshold:
                # CLOSED로 전환
                await self.redis.set(state_key, CircuitState.CLOSED.value)
                await self.redis.delete(success_key)
                await self.redis.delete(f"{self.key_prefix}{service_name}:failure_count")
                logger.info(f"Circuit {service_name}: HALF_OPEN -> CLOSED")

    async def record_failure(self, service_name: str):
        """분산 환경에서 실패 기록"""

        state_key = f"{self.key_prefix}{service_name}:state"
        state = await self.redis.get(state_key)

        if not state or state == CircuitState.CLOSED.value:
            failure_key = f"{self.key_prefix}{service_name}:failure_count"
            count = await self.redis.incr(failure_key)
            await self.redis.expire(failure_key, 300)  # 5분 후 자동 삭제

            if count >= self.config.failure_threshold:
                # OPEN으로 전환
                await self.redis.set(state_key, CircuitState.OPEN.value)
                timeout_key = f"{self.key_prefix}{service_name}:timeout"
                await self.redis.set(timeout_key, time.time() + self.config.timeout)
                logger.warning(f"Circuit {service_name}: CLOSED -> OPEN")

        elif state == CircuitState.HALF_OPEN.value:
            # HALF_OPEN에서 실패 시 즉시 OPEN으로
            await self.redis.set(state_key, CircuitState.OPEN.value)
            timeout_key = f"{self.key_prefix}{service_name}:timeout"
            await self.redis.set(timeout_key, time.time() + self.config.timeout)
            logger.warning(f"Circuit {service_name}: HALF_OPEN -> OPEN")
