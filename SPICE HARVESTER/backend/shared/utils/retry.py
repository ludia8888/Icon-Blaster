"""
재시도 및 오류 처리 유틸리티
네트워크 오류 및 일시적 장애에 대한 자동 재시도를 제공합니다.
"""

import time
import logging
from typing import TypeVar, Callable, Any, Optional, Tuple, Union, Type
from functools import wraps
import random
from datetime import datetime, timedelta

# 예외 클래스 import
from exceptions.base import DatabaseError, OperationalError

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RetryError(Exception):
    """재시도 실패 시 발생하는 예외"""
    def __init__(self, message: str, last_error: Optional[Exception] = None, attempts: int = 0):
        super().__init__(message)
        self.last_error = last_error
        self.attempts = attempts


def exponential_backoff(attempt: int, 
                       base_delay: float = 1.0,
                       max_delay: float = 60.0,
                       jitter: bool = True) -> float:
    """
    지수 백오프 계산
    
    Args:
        attempt: 시도 횟수 (0부터 시작)
        base_delay: 기본 지연 시간 (초)
        max_delay: 최대 지연 시간 (초)
        jitter: 랜덤 지터 추가 여부
        
    Returns:
        대기 시간 (초)
    """
    delay = min(base_delay * (2 ** attempt), max_delay)
    
    if jitter:
        # 0.5 ~ 1.0 사이의 랜덤 계수 적용
        delay *= (0.5 + random.random() * 0.5)
    
    return delay


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: str = "exponential",
    max_delay: float = 60.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None,
    timeout: Optional[float] = None
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    재시도 데코레이터
    
    Args:
        max_attempts: 최대 시도 횟수
        delay: 초기 지연 시간 (초)
        backoff: 백오프 전략 ("fixed", "linear", "exponential")
        max_delay: 최대 지연 시간 (초)
        exceptions: 재시도할 예외 타입들
        on_retry: 재시도 시 호출할 콜백 함수
        timeout: 전체 타임아웃 (초)
        
    Returns:
        데코레이터 함수
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            start_time = time.time()
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    # 타임아웃 체크
                    if timeout and (time.time() - start_time) > timeout:
                        raise RetryError(
                            f"Timeout exceeded after {attempt} attempts",
                            last_exception,
                            attempt
                        )
                    
                    # 함수 실행
                    result = func(*args, **kwargs)
                    
                    # 성공 시 로깅
                    if attempt > 0:
                        logger.info(
                            f"Successfully executed {func.__name__} "
                            f"after {attempt + 1} attempts"
                        )
                    
                    return result
                    
                except exceptions as e:
                    last_exception = e
                    
                    # 마지막 시도인 경우
                    if attempt == max_attempts - 1:
                        logger.error(
                            f"Failed to execute {func.__name__} "
                            f"after {max_attempts} attempts: {e}"
                        )
                        raise RetryError(
                            f"Max attempts ({max_attempts}) exceeded",
                            e,
                            max_attempts
                        )
                    
                    # 재시도 로깅
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_attempts} failed "
                        f"for {func.__name__}: {e}"
                    )
                    
                    # 재시도 콜백
                    if on_retry:
                        on_retry(e, attempt + 1)
                    
                    # 대기 시간 계산
                    if backoff == "fixed":
                        wait_time = delay
                    elif backoff == "linear":
                        wait_time = min(delay * (attempt + 1), max_delay)
                    elif backoff == "exponential":
                        wait_time = exponential_backoff(attempt, delay, max_delay)
                    else:
                        wait_time = delay
                    
                    logger.debug(f"Waiting {wait_time:.2f}s before retry...")
                    time.sleep(wait_time)
            
            # 이론적으로 도달하지 않는 코드
            raise RetryError(
                "Unexpected retry error",
                last_exception,
                max_attempts
            )
        
        return wrapper
    return decorator


def retry_async(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: str = "exponential",
    max_delay: float = 60.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None,
    timeout: Optional[float] = None
) -> Callable:
    """
    비동기 함수를 위한 재시도 데코레이터
    
    Args: retry()와 동일
    
    Returns:
        비동기 데코레이터 함수
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            import asyncio
            
            start_time = time.time()
            last_exception = None
            
            for attempt in range(max_attempts):
                try:
                    # 타임아웃 체크
                    if timeout and (time.time() - start_time) > timeout:
                        raise RetryError(
                            f"Timeout exceeded after {attempt} attempts",
                            last_exception,
                            attempt
                        )
                    
                    # 비동기 함수 실행
                    result = await func(*args, **kwargs)
                    
                    # 성공 시 로깅
                    if attempt > 0:
                        logger.info(
                            f"Successfully executed {func.__name__} "
                            f"after {attempt + 1} attempts"
                        )
                    
                    return result
                    
                except exceptions as e:
                    last_exception = e
                    
                    # 마지막 시도인 경우
                    if attempt == max_attempts - 1:
                        logger.error(
                            f"Failed to execute {func.__name__} "
                            f"after {max_attempts} attempts: {e}"
                        )
                        raise RetryError(
                            f"Max attempts ({max_attempts}) exceeded",
                            e,
                            max_attempts
                        )
                    
                    # 재시도 로깅
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_attempts} failed "
                        f"for {func.__name__}: {e}"
                    )
                    
                    # 재시도 콜백
                    if on_retry:
                        on_retry(e, attempt + 1)
                    
                    # 대기 시간 계산
                    if backoff == "fixed":
                        wait_time = delay
                    elif backoff == "linear":
                        wait_time = min(delay * (attempt + 1), max_delay)
                    elif backoff == "exponential":
                        wait_time = exponential_backoff(attempt, delay, max_delay)
                    else:
                        wait_time = delay
                    
                    logger.debug(f"Waiting {wait_time:.2f}s before retry...")
                    await asyncio.sleep(wait_time)
            
            # 이론적으로 도달하지 않는 코드
            raise RetryError(
                "Unexpected retry error",
                last_exception,
                max_attempts
            )
        
        return wrapper
    return decorator


class CircuitBreaker:
    """
    Circuit Breaker 패턴 구현
    연속적인 실패를 감지하여 서비스 호출을 차단합니다.
    """
    
    def __init__(self,
                 failure_threshold: int = 5,
                 recovery_timeout: float = 60.0,
                 expected_exception: Type[Exception] = Exception):
        """
        초기화
        
        Args:
            failure_threshold: 차단 전 허용되는 실패 횟수
            recovery_timeout: 차단 후 복구 대기 시간 (초)
            expected_exception: 예상되는 예외 타입
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self._failure_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._state = "closed"  # closed, open, half-open
    
    @property
    def state(self) -> str:
        """현재 상태 반환"""
        return self._state
    
    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Circuit Breaker를 통한 함수 호출
        
        Args:
            func: 호출할 함수
            *args, **kwargs: 함수 인자
            
        Returns:
            함수 실행 결과
            
        Raises:
            Exception: Circuit이 open 상태일 때
        """
        if self._state == "open":
            # 복구 시간 확인
            if self._last_failure_time:
                time_since_failure = (
                    datetime.utcnow() - self._last_failure_time
                ).total_seconds()
                
                if time_since_failure > self.recovery_timeout:
                    logger.info("Circuit breaker entering half-open state")
                    self._state = "half-open"
                else:
                    raise Exception(
                        f"Circuit breaker is open. "
                        f"Retry after {self.recovery_timeout - time_since_failure:.1f}s"
                    )
        
        try:
            # 함수 실행
            result = func(*args, **kwargs)
            
            # 성공 시 상태 업데이트
            if self._state == "half-open":
                logger.info("Circuit breaker recovered, closing")
                self._state = "closed"
                self._failure_count = 0
            
            return result
            
        except self.expected_exception as e:
            self._record_failure()
            raise e
    
    def _record_failure(self):
        """실패 기록"""
        self._failure_count += 1
        self._last_failure_time = datetime.utcnow()
        
        if self._failure_count >= self.failure_threshold:
            logger.warning(
                f"Circuit breaker opening after {self._failure_count} failures"
            )
            self._state = "open"
        
        elif self._state == "half-open":
            logger.warning("Circuit breaker reopening after half-open failure")
            self._state = "open"
            self._failure_count = 0
    
    def reset(self):
        """상태 초기화"""
        self._failure_count = 0
        self._last_failure_time = None
        self._state = "closed"
        logger.info("Circuit breaker reset")


# TerminusDB 특화 재시도 설정
terminus_retry = retry(
    max_attempts=3,
    delay=1.0,
    backoff="exponential",
    max_delay=10.0,
    exceptions=(ConnectionError, TimeoutError, OSError),
    on_retry=lambda e, attempt: logger.info(f"Retrying TerminusDB operation: {e}")
)

# 데이터베이스 쿼리용 재시도 설정
query_retry = retry(
    max_attempts=2,
    delay=0.5,
    backoff="fixed",
    exceptions=(DatabaseError, OperationalError),
    timeout=30.0
)