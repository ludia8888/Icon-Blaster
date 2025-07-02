"""
Unified Circuit Breaker Implementation
Consolidates all circuit breaker implementations with configurable behavior
"""

import asyncio
import time
import logging
from enum import Enum
from typing import Optional, Callable, Any, Dict, List, Union, Set
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime, timedelta
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"         # Failing, rejecting calls  
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreakerMode(Enum):
    """Operation modes for different use cases"""
    SIMPLE = "simple"           # Basic local circuit breaker
    DISTRIBUTED = "distributed"  # Redis-backed for distributed systems
    LIFE_CRITICAL = "life_critical"  # Enhanced safety for critical systems
    RETRY_INTEGRATED = "retry_integrated"  # Integrated with retry logic


@dataclass
class CircuitBreakerConfig:
    """Unified configuration for circuit breaker"""
    
    # Basic thresholds
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_seconds: float = 60.0
    
    # Advanced thresholds
    error_rate_threshold: float = 0.5  # 50% error rate
    response_time_threshold: Optional[float] = None  # seconds
    half_open_max_calls: int = 3
    
    # Operation mode
    mode: CircuitBreakerMode = CircuitBreakerMode.SIMPLE
    
    # Distributed mode settings
    redis_client: Optional[redis.Redis] = None
    redis_key_prefix: str = "circuit_breaker"
    redis_ttl: int = 3600
    
    # Life-critical mode settings
    require_health_check: bool = False
    health_check_func: Optional[Callable] = None
    gradual_recovery: bool = False
    recovery_factor: float = 0.1  # Start with 10% traffic
    alert_on_open: bool = False
    alert_func: Optional[Callable] = None
    
    # Retry integration settings
    retry_budget: Optional[int] = None
    bulkhead_size: Optional[int] = None
    
    # Monitoring and callbacks
    excluded_exceptions: Set[type] = field(default_factory=set)
    fallback_func: Optional[Callable] = None
    on_state_change: Optional[Callable] = None
    collect_metrics: bool = True
    
    # Backpressure settings
    enable_backpressure: bool = False
    backpressure_threshold: int = 100
    queue_timeout: float = 5.0
    
    @classmethod
    def simple(cls) -> "CircuitBreakerConfig":
        """Simple local circuit breaker"""
        return cls(mode=CircuitBreakerMode.SIMPLE)
    
    @classmethod
    def distributed(cls, redis_client: redis.Redis) -> "CircuitBreakerConfig":
        """Distributed circuit breaker with Redis"""
        return cls(
            mode=CircuitBreakerMode.DISTRIBUTED,
            redis_client=redis_client,
            collect_metrics=True
        )
    
    @classmethod
    def life_critical(cls, health_check_func: Callable) -> "CircuitBreakerConfig":
        """Life-critical circuit breaker with enhanced safety"""
        return cls(
            mode=CircuitBreakerMode.LIFE_CRITICAL,
            failure_threshold=3,  # More sensitive
            success_threshold=10,  # More conservative
            error_rate_threshold=0.2,  # 20% error rate
            response_time_threshold=1.0,  # 1 second max
            half_open_max_calls=1,  # Very cautious
            require_health_check=True,
            health_check_func=health_check_func,
            gradual_recovery=True,
            alert_on_open=True,
            collect_metrics=True
        )
    
    @classmethod
    def retry_integrated(cls, retry_budget: int = 100) -> "CircuitBreakerConfig":
        """Circuit breaker integrated with retry logic"""
        return cls(
            mode=CircuitBreakerMode.RETRY_INTEGRATED,
            retry_budget=retry_budget,
            collect_metrics=True
        )


class UnifiedCircuitBreaker:
    """Unified circuit breaker implementation"""
    
    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        
        # State management
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        
        # Metrics
        self._error_window = deque(maxlen=100)
        self._response_times = deque(maxlen=100)
        self._state_changes: List[tuple] = []
        
        # Concurrency control
        self._lock = asyncio.Lock()
        self._half_open_lock = asyncio.Lock()
        
        # Backpressure
        self._active_calls = 0
        self._call_queue: asyncio.Queue = asyncio.Queue() if config.enable_backpressure else None
        
        # Recovery state (for gradual recovery)
        self._recovery_percentage = 0.0
        self._recovery_start_time: Optional[float] = None
    
    @property
    def state(self) -> CircuitState:
        """Get current circuit state"""
        return self._state
    
    @property
    def is_closed(self) -> bool:
        return self._state == CircuitState.CLOSED
    
    @property
    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN
    
    @property
    def is_half_open(self) -> bool:
        return self._state == CircuitState.HALF_OPEN
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function through circuit breaker
        
        Args:
            func: Function to execute
            *args, **kwargs: Function arguments
            
        Returns:
            Function result or fallback result
            
        Raises:
            Exception: If circuit is open and no fallback provided
        """
        # Check backpressure
        if self.config.enable_backpressure:
            if self._active_calls >= self.config.backpressure_threshold:
                if self.config.fallback_func:
                    return await self._execute_fallback()
                raise Exception(f"Circuit breaker {self.name}: Backpressure limit reached")
        
        # Check circuit state
        if not await self._can_execute():
            if self.config.fallback_func:
                return await self._execute_fallback()
            raise Exception(f"Circuit breaker {self.name} is OPEN")
        
        # Execute with monitoring
        start_time = time.time()
        self._active_calls += 1
        
        try:
            # For half-open state, limit concurrent calls
            if self.is_half_open:
                async with self._half_open_lock:
                    if self._half_open_calls >= self.config.half_open_max_calls:
                        raise Exception("Half-open call limit reached")
                    self._half_open_calls += 1
            
            # Execute the function
            result = await func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func(*args, **kwargs)
            
            # Record success
            response_time = time.time() - start_time
            await self._on_success(response_time)
            
            return result
            
        except Exception as e:
            # Check if exception should be ignored
            if type(e) in self.config.excluded_exceptions:
                return
                
            # Record failure
            await self._on_failure(e)
            raise
            
        finally:
            self._active_calls -= 1
            if self.is_half_open:
                self._half_open_calls -= 1
    
    async def _can_execute(self) -> bool:
        """Check if execution is allowed based on current state"""
        async with self._lock:
            # Update state if needed
            await self._update_state()
            
            if self.is_closed:
                return True
                
            elif self.is_half_open:
                # Apply gradual recovery if enabled
                if self.config.gradual_recovery:
                    import random
                    return random.random() < self._recovery_percentage
                return True
                
            else:  # OPEN
                return False
    
    async def _update_state(self):
        """Update circuit state based on current conditions"""
        if self.is_open:
            # Check if timeout has passed
            if self._last_failure_time and \
               time.time() - self._last_failure_time >= self.config.timeout_seconds:
                # Transition to half-open
                await self._transition_to_half_open()
    
    async def _on_success(self, response_time: float):
        """Handle successful execution"""
        async with self._lock:
            # Track metrics
            self._error_window.append(0)
            self._response_times.append(response_time)
            
            # Check response time threshold
            if self.config.response_time_threshold and \
               response_time > self.config.response_time_threshold:
                # Treat slow response as partial failure in life-critical mode
                if self.config.mode == CircuitBreakerMode.LIFE_CRITICAL:
                    self._error_window[-1] = 0.5  # Partial failure
            
            if self.is_half_open:
                self._success_count += 1
                
                # Check if we should close the circuit
                if self._success_count >= self.config.success_threshold:
                    # Additional health check for life-critical mode
                    if self.config.require_health_check and self.config.health_check_func:
                        try:
                            if asyncio.iscoroutinefunction(self.config.health_check_func):
                                health_ok = await self.config.health_check_func()
                            else:
                                health_ok = self.config.health_check_func()
                            
                            if not health_ok:
                                return  # Stay in half-open
                        except:
                            return  # Stay in half-open on health check failure
                    
                    await self._transition_to_closed()
    
    async def _on_failure(self, exception: Exception):
        """Handle failed execution"""
        async with self._lock:
            # Track metrics
            self._error_window.append(1)
            self._last_failure_time = time.time()
            
            if self.is_closed or self.is_half_open:
                self._failure_count += 1
                
                # Check failure conditions
                should_open = False
                
                # Check failure count threshold
                if self._failure_count >= self.config.failure_threshold:
                    should_open = True
                
                # Check error rate threshold
                if len(self._error_window) >= 10:  # Minimum sample size
                    error_rate = sum(self._error_window) / len(self._error_window)
                    if error_rate > self.config.error_rate_threshold:
                        should_open = True
                
                if should_open:
                    await self._transition_to_open()
    
    async def _transition_to_open(self):
        """Transition to OPEN state"""
        self._state = CircuitState.OPEN
        self._failure_count = 0
        self._success_count = 0
        
        # Notify
        await self._notify_state_change(CircuitState.OPEN)
        
        # Alert for life-critical mode
        if self.config.alert_on_open and self.config.alert_func:
            try:
                if asyncio.iscoroutinefunction(self.config.alert_func):
                    await self.config.alert_func(self.name, "Circuit breaker opened")
                else:
                    self.config.alert_func(self.name, "Circuit breaker opened")
            except:
                pass
        
        logger.warning(f"Circuit breaker {self.name} transitioned to OPEN")
    
    async def _transition_to_half_open(self):
        """Transition to HALF_OPEN state"""
        self._state = CircuitState.HALF_OPEN
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        
        # Initialize gradual recovery
        if self.config.gradual_recovery:
            self._recovery_percentage = self.config.recovery_factor
            self._recovery_start_time = time.time()
        
        await self._notify_state_change(CircuitState.HALF_OPEN)
        logger.info(f"Circuit breaker {self.name} transitioned to HALF_OPEN")
    
    async def _transition_to_closed(self):
        """Transition to CLOSED state"""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._recovery_percentage = 1.0
        
        await self._notify_state_change(CircuitState.CLOSED)
        logger.info(f"Circuit breaker {self.name} transitioned to CLOSED")
    
    async def _notify_state_change(self, new_state: CircuitState):
        """Notify state change"""
        self._state_changes.append((time.time(), new_state))
        
        if self.config.on_state_change:
            try:
                if asyncio.iscoroutinefunction(self.config.on_state_change):
                    await self.config.on_state_change(self.name, new_state)
                else:
                    self.config.on_state_change(self.name, new_state)
            except:
                pass
    
    async def _execute_fallback(self) -> Any:
        """Execute fallback function"""
        if self.config.fallback_func:
            if asyncio.iscoroutinefunction(self.config.fallback_func):
                return await self.config.fallback_func()
            return self.config.fallback_func()
        return None
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get circuit breaker metrics"""
        error_rate = sum(self._error_window) / len(self._error_window) if self._error_window else 0
        avg_response_time = sum(self._response_times) / len(self._response_times) if self._response_times else 0
        
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "error_rate": error_rate,
            "avg_response_time": avg_response_time,
            "active_calls": self._active_calls,
            "half_open_calls": self._half_open_calls,
            "state_changes": len(self._state_changes)
        }


# Decorator for easy use
def circuit_breaker(name: str = None, config: CircuitBreakerConfig = None):
    """Decorator to apply circuit breaker to a function"""
    def decorator(func):
        cb_name = name or f"{func.__module__}.{func.__name__}"
        breaker = UnifiedCircuitBreaker(cb_name, config)
        
        async def async_wrapper(*args, **kwargs):
            return await breaker.call(func, *args, **kwargs)
        
        def sync_wrapper(*args, **kwargs):
            return asyncio.run(breaker.call(func, *args, **kwargs))
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


# Global registry for circuit breakers
_circuit_breaker_registry: Dict[str, UnifiedCircuitBreaker] = {}


def get_circuit_breaker(name: str, config: CircuitBreakerConfig = None) -> UnifiedCircuitBreaker:
    """Get or create a circuit breaker from registry"""
    if name not in _circuit_breaker_registry:
        _circuit_breaker_registry[name] = UnifiedCircuitBreaker(name, config)
    return _circuit_breaker_registry[name]


def get_all_circuit_breakers() -> Dict[str, UnifiedCircuitBreaker]:
    """Get all registered circuit breakers"""
    return _circuit_breaker_registry.copy()