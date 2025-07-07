"""
Enterprise-grade circuit breaker with half-open state and backpressure.

Features:
- States: Closed, Open, Half-Open
- Configurable failure thresholds and timeouts
- Error rate and response time based triggers
- Distributed state management with Redis
- Fallback mechanisms
- Backpressure handling
- Circuit breaker groups
- Health monitoring and metrics
"""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Callable, Any, TypeVar, Generic, Set
import redis.asyncio as redis
from collections import deque
from functools import wraps
import logging
import random
from contextvars import ContextVar

logger = logging.getLogger(__name__)

T = TypeVar('T')

# Context for circuit breaker state
circuit_context: ContextVar[Dict[str, Any]] = ContextVar('circuit_context', default={})


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class TripReason(Enum):
    """Reasons for circuit breaker trips."""
    ERROR_RATE = "error_rate"
    RESPONSE_TIME = "response_time"
    CONSECUTIVE_FAILURES = "consecutive_failures"
    MANUAL = "manual"
    BACKPRESSURE = "backpressure"


@dataclass
class CircuitConfig:
    """Circuit breaker configuration."""
    name: str
    failure_threshold: int = 5
    success_threshold: int = 3
    timeout_seconds: float = 60
    half_open_max_calls: int = 3
    error_rate_threshold: float = 0.5
    response_time_threshold: Optional[float] = None
    backpressure_threshold: Optional[int] = None
    excluded_exceptions: Set[type] = field(default_factory=set)
    fallback: Optional[Callable] = None
    on_state_change: Optional[Callable] = None
    redis_ttl: int = 3600


@dataclass
class CircuitMetrics:
    """Circuit breaker metrics."""
    total_calls: int = 0
    failed_calls: int = 0
    successful_calls: int = 0
    total_response_time: float = 0
    last_failure_time: Optional[datetime] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    
    @property
    def error_rate(self) -> float:
        """Calculate error rate."""
        if self.total_calls == 0:
            return 0
        return self.failed_calls / self.total_calls
    
    @property
    def average_response_time(self) -> float:
        """Calculate average response time."""
        if self.successful_calls == 0:
            return 0
        return self.total_response_time / self.successful_calls


@dataclass
class CircuitStats:
    """Circuit breaker statistics."""
    state: CircuitState
    metrics: CircuitMetrics
    last_state_change: datetime
    trip_reason: Optional[TripReason] = None
    next_attempt_time: Optional[datetime] = None


class CircuitBreakerError(Exception):
    """Circuit breaker error."""
    def __init__(self, message: str, circuit_name: str, fallback_result: Any = None):
        super().__init__(message)
        self.circuit_name = circuit_name
        self.fallback_result = fallback_result


class BackpressureHandler:
    """Handles backpressure for circuit breakers."""
    
    def __init__(self, max_queue_size: int = 1000):
        self.max_queue_size = max_queue_size
        self.queues: Dict[str, deque] = {}
        self.processing_counts: Dict[str, int] = {}
    
    def can_accept_request(self, circuit_name: str, threshold: Optional[int] = None) -> bool:
        """Check if we can accept more requests."""
        queue_size = len(self.queues.get(circuit_name, []))
        processing = self.processing_counts.get(circuit_name, 0)
        total_load = queue_size + processing
        
        max_allowed = threshold or self.max_queue_size
        return total_load < max_allowed
    
    def enqueue_request(self, circuit_name: str, request_id: str):
        """Enqueue a request."""
        if circuit_name not in self.queues:
            self.queues[circuit_name] = deque(maxlen=self.max_queue_size)
        self.queues[circuit_name].append(request_id)
    
    def start_processing(self, circuit_name: str, request_id: str):
        """Mark request as processing."""
        if circuit_name in self.queues and request_id in self.queues[circuit_name]:
            self.queues[circuit_name].remove(request_id)
        
        if circuit_name not in self.processing_counts:
            self.processing_counts[circuit_name] = 0
        self.processing_counts[circuit_name] += 1
    
    def finish_processing(self, circuit_name: str):
        """Mark request as finished."""
        if circuit_name in self.processing_counts:
            self.processing_counts[circuit_name] = max(0, self.processing_counts[circuit_name] - 1)
    
    def get_load(self, circuit_name: str) -> Dict[str, int]:
        """Get current load metrics."""
        return {
            'queued': len(self.queues.get(circuit_name, [])),
            'processing': self.processing_counts.get(circuit_name, 0),
            'total': len(self.queues.get(circuit_name, [])) + self.processing_counts.get(circuit_name, 0)
        }


class CircuitBreaker:
    """Circuit breaker implementation."""
    
    def __init__(
        self,
        config: CircuitConfig,
        redis_client: Optional[redis.Redis] = None,
        backpressure_handler: Optional[BackpressureHandler] = None
    ):
        self.config = config
        self.redis_client = redis_client
        self.backpressure_handler = backpressure_handler or BackpressureHandler()
        
        # Local state
        self.state = CircuitState.CLOSED
        self.metrics = CircuitMetrics()
        self.last_state_change = datetime.now()
        self.trip_reason: Optional[TripReason] = None
        self.half_open_calls = 0
        
        # Request tracking
        self.response_times: deque = deque(maxlen=100)
        self.error_window: deque = deque(maxlen=100)
        
        # State lock for thread safety
        self._state_lock = asyncio.Lock()
    
    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function with circuit breaker protection."""
        request_id = f"{self.config.name}:{time.time()}"
        
        # Check backpressure
        if self.config.backpressure_threshold:
            if not self.backpressure_handler.can_accept_request(
                self.config.name,
                self.config.backpressure_threshold
            ):
                await self._trip_circuit(TripReason.BACKPRESSURE)
                raise CircuitBreakerError(
                    f"Circuit {self.config.name} tripped due to backpressure",
                    self.config.name
                )
        
        # Enqueue request
        self.backpressure_handler.enqueue_request(self.config.name, request_id)
        
        try:
            # Check circuit state
            current_state = await self._get_state()
            
            if current_state == CircuitState.OPEN:
                # Check if we should transition to half-open
                if await self._should_attempt_reset():
                    await self._transition_to_half_open()
                else:
                    # Circuit is open, use fallback or raise error
                    if self.config.fallback:
                        result = await self._execute_fallback(func, args, kwargs)
                        raise CircuitBreakerError(
                            f"Circuit {self.config.name} is open",
                            self.config.name,
                            result
                        )
                    else:
                        raise CircuitBreakerError(
                            f"Circuit {self.config.name} is open",
                            self.config.name
                        )
            
            elif current_state == CircuitState.HALF_OPEN:
                # Check if we've exceeded half-open calls
                async with self._state_lock:
                    if self.half_open_calls >= self.config.half_open_max_calls:
                        # Wait for other half-open calls to complete
                        await asyncio.sleep(0.1)
                        return await self.call(func, *args, **kwargs)
                    self.half_open_calls += 1
            
            # Start processing
            self.backpressure_handler.start_processing(self.config.name, request_id)
            
            # Execute function
            start_time = time.time()
            try:
                result = await self._execute_function(func, args, kwargs)
                response_time = time.time() - start_time
                
                # Record success
                await self._record_success(response_time)
                
                # Check if we should close circuit from half-open
                if current_state == CircuitState.HALF_OPEN:
                    await self._check_half_open_success()
                
                return result
                
            except Exception as e:
                response_time = time.time() - start_time
                
                # Check if exception should be ignored
                if type(e) in self.config.excluded_exceptions:
                    await self._record_success(response_time)
                    raise
                
                # Record failure
                await self._record_failure(e, response_time)
                
                # Check if we should open circuit
                if current_state == CircuitState.CLOSED:
                    await self._check_failure_threshold()
                elif current_state == CircuitState.HALF_OPEN:
                    await self._trip_circuit(TripReason.CONSECUTIVE_FAILURES)
                
                # Use fallback if available
                if self.config.fallback:
                    return await self._execute_fallback(func, args, kwargs)
                raise
            
        finally:
            # Finish processing
            self.backpressure_handler.finish_processing(self.config.name)
            
            # Decrement half-open calls
            if await self._get_state() == CircuitState.HALF_OPEN:
                async with self._state_lock:
                    self.half_open_calls = max(0, self.half_open_calls - 1)
    
    async def _execute_function(self, func: Callable, args: tuple, kwargs: dict) -> Any:
        """Execute the protected function."""
        if asyncio.iscoroutinefunction(func):
            return await func(*args, **kwargs)
        else:
            # Run sync function in executor
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, func, *args, **kwargs)
    
    async def _execute_fallback(self, func: Callable, args: tuple, kwargs: dict) -> Any:
        """Execute fallback function."""
        if not self.config.fallback:
            return None
        
        try:
            if asyncio.iscoroutinefunction(self.config.fallback):
                return await self.config.fallback(func, args, kwargs)
            else:
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None,
                    self.config.fallback,
                    func, args, kwargs
                )
        except Exception as e:
            logger.error(f"Fallback failed for circuit {self.config.name}: {e}")
            return None
    
    async def _get_state(self) -> CircuitState:
        """Get current circuit state."""
        if self.redis_client:
            # Get distributed state
            state_key = f"circuit:{self.config.name}:state"
            state_value = await self.redis_client.get(state_key)
            if state_value:
                self.state = CircuitState(state_value.decode())
        return self.state
    
    async def _set_state(self, state: CircuitState, reason: Optional[TripReason] = None):
        """Set circuit state."""
        old_state = self.state
        self.state = state
        self.last_state_change = datetime.now()
        self.trip_reason = reason
        
        if self.redis_client:
            # Set distributed state
            state_key = f"circuit:{self.config.name}:state"
            await self.redis_client.setex(
                state_key,
                self.config.redis_ttl,
                state.value
            )
            
            # Store state change time
            time_key = f"circuit:{self.config.name}:last_change"
            await self.redis_client.setex(
                time_key,
                self.config.redis_ttl,
                self.last_state_change.timestamp()
            )
        
        # Reset half-open calls
        if state != CircuitState.HALF_OPEN:
            self.half_open_calls = 0
        
        # Notify state change
        if self.config.on_state_change and old_state != state:
            try:
                await self._notify_state_change(old_state, state, reason)
            except Exception as e:
                logger.error(f"Error notifying state change: {e}")
        
        # Log state change
        logger.info(
            f"Circuit {self.config.name} state changed from {old_state.value} to {state.value}",
            extra={
                'circuit_name': self.config.name,
                'old_state': old_state.value,
                'new_state': state.value,
                'reason': reason.value if reason else None
            }
        )
    
    async def _notify_state_change(
        self,
        old_state: CircuitState,
        new_state: CircuitState,
        reason: Optional[TripReason]
    ):
        """Notify state change."""
        if asyncio.iscoroutinefunction(self.config.on_state_change):
            await self.config.on_state_change(
                self.config.name,
                old_state,
                new_state,
                reason
            )
        else:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                self.config.on_state_change,
                self.config.name,
                old_state,
                new_state,
                reason
            )
    
    async def _record_success(self, response_time: float):
        """Record successful call."""
        async with self._state_lock:
            self.metrics.total_calls += 1
            self.metrics.successful_calls += 1
            self.metrics.total_response_time += response_time
            self.metrics.consecutive_failures = 0
            self.metrics.consecutive_successes += 1
            
            # Track response time
            self.response_times.append(response_time)
            self.error_window.append(0)
        
        # Store in Redis if available
        if self.redis_client:
            await self._update_redis_metrics('success', response_time)
    
    async def _record_failure(self, error: Exception, response_time: float):
        """Record failed call."""
        async with self._state_lock:
            self.metrics.total_calls += 1
            self.metrics.failed_calls += 1
            self.metrics.last_failure_time = datetime.now()
            self.metrics.consecutive_failures += 1
            self.metrics.consecutive_successes = 0
            
            # Track error
            self.error_window.append(1)
        
        # Store in Redis if available
        if self.redis_client:
            await self._update_redis_metrics('failure', response_time)
        
        # Log failure
        logger.warning(
            f"Circuit {self.config.name} recorded failure: {error}",
            extra={
                'circuit_name': self.config.name,
                'error': str(error),
                'consecutive_failures': self.metrics.consecutive_failures
            }
        )
    
    async def _update_redis_metrics(self, result: str, response_time: float):
        """Update metrics in Redis."""
        metrics_key = f"circuit:{self.config.name}:metrics"
        
        # Lua script for atomic metric update
        lua_script = """
        local key = KEYS[1]
        local result = ARGV[1]
        local response_time = tonumber(ARGV[2])
        local ttl = tonumber(ARGV[3])
        
        -- Get current metrics
        local metrics = redis.call('HMGET', key, 
            'total_calls', 'failed_calls', 'successful_calls', 
            'total_response_time', 'consecutive_failures', 'consecutive_successes'
        )
        
        local total_calls = tonumber(metrics[1]) or 0
        local failed_calls = tonumber(metrics[2]) or 0
        local successful_calls = tonumber(metrics[3]) or 0
        local total_response_time = tonumber(metrics[4]) or 0
        local consecutive_failures = tonumber(metrics[5]) or 0
        local consecutive_successes = tonumber(metrics[6]) or 0
        
        -- Update metrics
        total_calls = total_calls + 1
        
        if result == 'success' then
            successful_calls = successful_calls + 1
            total_response_time = total_response_time + response_time
            consecutive_failures = 0
            consecutive_successes = consecutive_successes + 1
        else
            failed_calls = failed_calls + 1
            consecutive_failures = consecutive_failures + 1
            consecutive_successes = 0
        end
        
        -- Store updated metrics
        redis.call('HMSET', key,
            'total_calls', total_calls,
            'failed_calls', failed_calls,
            'successful_calls', successful_calls,
            'total_response_time', total_response_time,
            'consecutive_failures', consecutive_failures,
            'consecutive_successes', consecutive_successes,
            'last_update', tostring(redis.call('TIME')[1])
        )
        
        redis.call('EXPIRE', key, ttl)
        
        return {total_calls, failed_calls, successful_calls, consecutive_failures}
        """
        
        await self.redis_client.eval(
            lua_script,
            1,
            metrics_key,
            result,
            str(response_time),
            str(self.config.redis_ttl)
        )
    
    async def _should_attempt_reset(self) -> bool:
        """Check if we should attempt to reset circuit."""
        if self.redis_client:
            # Check distributed last change time
            time_key = f"circuit:{self.config.name}:last_change"
            last_change = await self.redis_client.get(time_key)
            if last_change:
                last_change_time = datetime.fromtimestamp(float(last_change))
            else:
                last_change_time = self.last_state_change
        else:
            last_change_time = self.last_state_change
        
        time_since_change = (datetime.now() - last_change_time).total_seconds()
        return time_since_change >= self.config.timeout_seconds
    
    async def _transition_to_half_open(self):
        """Transition to half-open state."""
        await self._set_state(CircuitState.HALF_OPEN)
    
    async def _check_failure_threshold(self):
        """Check if failure threshold is exceeded."""
        # Check consecutive failures
        if self.metrics.consecutive_failures >= self.config.failure_threshold:
            await self._trip_circuit(TripReason.CONSECUTIVE_FAILURES)
            return
        
        # Check error rate
        if len(self.error_window) >= 10:  # Minimum window size
            error_rate = sum(self.error_window) / len(self.error_window)
            if error_rate >= self.config.error_rate_threshold:
                await self._trip_circuit(TripReason.ERROR_RATE)
                return
        
        # Check response time
        if self.config.response_time_threshold and len(self.response_times) >= 10:
            avg_response_time = sum(self.response_times) / len(self.response_times)
            if avg_response_time >= self.config.response_time_threshold:
                await self._trip_circuit(TripReason.RESPONSE_TIME)
    
    async def _check_half_open_success(self):
        """Check if we should close circuit from half-open."""
        if self.metrics.consecutive_successes >= self.config.success_threshold:
            await self._set_state(CircuitState.CLOSED)
    
    async def _trip_circuit(self, reason: TripReason):
        """Trip the circuit breaker."""
        await self._set_state(CircuitState.OPEN, reason)
    
    async def open(self):
        """Manually open the circuit."""
        await self._trip_circuit(TripReason.MANUAL)
    
    async def close(self):
        """Manually close the circuit."""
        await self._set_state(CircuitState.CLOSED)
    
    async def reset(self):
        """Reset circuit breaker metrics."""
        async with self._state_lock:
            self.metrics = CircuitMetrics()
            self.response_times.clear()
            self.error_window.clear()
        
        if self.redis_client:
            metrics_key = f"circuit:{self.config.name}:metrics"
            await self.redis_client.delete(metrics_key)
        
        await self._set_state(CircuitState.CLOSED)
    
    async def get_stats(self) -> CircuitStats:
        """Get circuit breaker statistics."""
        return CircuitStats(
            state=await self._get_state(),
            metrics=self.metrics,
            last_state_change=self.last_state_change,
            trip_reason=self.trip_reason,
            next_attempt_time=(
                self.last_state_change + timedelta(seconds=self.config.timeout_seconds)
                if self.state == CircuitState.OPEN
                else None
            )
        )


class CircuitBreakerGroup:
    """Manages a group of circuit breakers."""
    
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis_client = redis_client
        self.breakers: Dict[str, CircuitBreaker] = {}
        self.backpressure_handler = BackpressureHandler()
    
    def add_breaker(self, config: CircuitConfig) -> CircuitBreaker:
        """Add a circuit breaker to the group."""
        breaker = CircuitBreaker(config, self.redis_client, self.backpressure_handler)
        self.breakers[config.name] = breaker
        return breaker
    
    def get_breaker(self, name: str) -> Optional[CircuitBreaker]:
        """Get a circuit breaker by name."""
        return self.breakers.get(name)
    
    async def get_all_stats(self) -> Dict[str, CircuitStats]:
        """Get statistics for all circuit breakers."""
        stats = {}
        for name, breaker in self.breakers.items():
            stats[name] = await breaker.get_stats()
        return stats
    
    async def open_all(self):
        """Open all circuit breakers."""
        tasks = [breaker.open() for breaker in self.breakers.values()]
        await asyncio.gather(*tasks)
    
    async def close_all(self):
        """Close all circuit breakers."""
        tasks = [breaker.close() for breaker in self.breakers.values()]
        await asyncio.gather(*tasks)
    
    async def reset_all(self):
        """Reset all circuit breakers."""
        tasks = [breaker.reset() for breaker in self.breakers.values()]
        await asyncio.gather(*tasks)
    
    def get_backpressure_stats(self) -> Dict[str, Dict[str, int]]:
        """Get backpressure statistics."""
        stats = {}
        for name in self.breakers:
            stats[name] = self.backpressure_handler.get_load(name)
        return stats


def circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    timeout_seconds: float = 60,
    **kwargs
) -> Callable:
    """Decorator for circuit breaker protection."""
    def decorator(func: Callable) -> Callable:
        # Create config
        config = CircuitConfig(
            name=name,
            failure_threshold=failure_threshold,
            timeout_seconds=timeout_seconds,
            **kwargs
        )
        
        # Create breaker
        breaker = CircuitBreaker(config)
        
        @wraps(func)
        async def wrapper(*args, **func_kwargs):
            try:
                return await breaker.call(func, *args, **func_kwargs)
            except CircuitBreakerError as e:
                if e.fallback_result is not None:
                    return e.fallback_result
                raise
        
        # Add breaker reference
        wrapper._circuit_breaker = breaker
        
        return wrapper
    return decorator