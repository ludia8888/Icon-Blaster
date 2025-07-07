"""
Production-grade retry strategy with exponential backoff, circuit breaker, and bulkhead patterns
Implements Palantir-style resilience patterns for critical operations
"""
import asyncio
import functools
import logging
import random
import time
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, TypeVar

import httpx
from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

# Type definitions
T = TypeVar('T')
AsyncFunc = TypeVar('AsyncFunc', bound=Callable[..., Any])

# Prometheus metrics
retry_attempts = Counter('retry_attempts_total', 'Total retry attempts', ['operation', 'status'])
retry_duration = Histogram('retry_duration_seconds', 'Time spent in retry logic', ['operation'])
circuit_breaker_state = Gauge('circuit_breaker_state', 'Circuit breaker state (0=closed, 1=open, 2=half-open)', ['operation'])
bulkhead_usage = Gauge('bulkhead_usage', 'Bulkhead resource usage', ['resource'])
retry_budget_remaining = Gauge('retry_budget_remaining', 'Remaining retry budget percentage', ['operation'])

class RetryStrategy(Enum):
    """Retry strategies based on operation criticality"""
    AGGRESSIVE = "aggressive"  # For critical operations (data consistency)
    STANDARD = "standard"      # For normal operations
    CONSERVATIVE = "conservative"  # For non-critical operations
    CUSTOM = "custom"         # For custom configurations

class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = 0
    OPEN = 1
    HALF_OPEN = 2

class RetryConfig:
    """Configuration for retry behavior"""
    def __init__(
        self,
        strategy: RetryStrategy = RetryStrategy.STANDARD,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        jitter_factor: float = 0.1,
        retryable_exceptions: Optional[Set[type]] = None,
        non_retryable_exceptions: Optional[Set[type]] = None,
        timeout: Optional[float] = None,
        circuit_breaker_threshold: int = 5,
        circuit_breaker_timeout: float = 60.0,
        bulkhead_size: Optional[int] = None,
        retry_budget_percent: float = 10.0,  # 10% of requests can be retries
        retry_budget_window: float = 60.0,   # Budget window in seconds
    ):
        self.strategy = strategy
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.jitter_factor = jitter_factor
        self.retryable_exceptions = retryable_exceptions or {
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.ReadTimeout,
            ConnectionError,
            TimeoutError,
            asyncio.TimeoutError,
        }
        self.non_retryable_exceptions = non_retryable_exceptions or {
            httpx.HTTPStatusError,  # Will be checked for status code
            ValueError,
            TypeError,
            PermissionError,
        }
        self.timeout = timeout
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.circuit_breaker_timeout = circuit_breaker_timeout
        self.bulkhead_size = bulkhead_size
        self.retry_budget_percent = retry_budget_percent
        self.retry_budget_window = retry_budget_window

    @classmethod
    def for_strategy(cls, strategy: RetryStrategy) -> 'RetryConfig':
        """Factory method for common strategies"""
        configs = {
            RetryStrategy.AGGRESSIVE: cls(
                strategy=strategy,
                max_attempts=10,
                initial_delay=0.5,
                max_delay=300.0,
                exponential_base=1.5,
                circuit_breaker_threshold=20,
                retry_budget_percent=20.0,
            ),
            RetryStrategy.STANDARD: cls(
                strategy=strategy,
                max_attempts=5,
                initial_delay=1.0,
                max_delay=60.0,
                exponential_base=2.0,
                circuit_breaker_threshold=10,
                retry_budget_percent=10.0,
            ),
            RetryStrategy.CONSERVATIVE: cls(
                strategy=strategy,
                max_attempts=3,
                initial_delay=2.0,
                max_delay=30.0,
                exponential_base=2.0,
                circuit_breaker_threshold=5,
                retry_budget_percent=5.0,
            ),
        }
        return configs.get(strategy, cls())

class CircuitBreaker:
    """Circuit breaker implementation"""
    def __init__(self, operation: str, config: RetryConfig):
        self.operation = operation
        self.config = config
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = CircuitState.CLOSED
        self.half_open_attempts = 0

    def record_success(self):
        """Record a successful operation"""
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.half_open_attempts = 0
            circuit_breaker_state.labels(operation=self.operation).set(CircuitState.CLOSED.value)
            logger.info(f"Circuit breaker for {self.operation} closed after successful operation")

    def record_failure(self):
        """Record a failed operation"""
        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()

        if self.failure_count >= self.config.circuit_breaker_threshold:
            self.state = CircuitState.OPEN
            circuit_breaker_state.labels(operation=self.operation).set(CircuitState.OPEN.value)
            logger.warning(f"Circuit breaker for {self.operation} opened after {self.failure_count} failures")

    def is_open(self) -> bool:
        """Check if circuit breaker should block requests"""
        if self.state == CircuitState.CLOSED:
            return False

        if self.state == CircuitState.OPEN:
            # Check if timeout has passed
            if self.last_failure_time and \
               (datetime.utcnow() - self.last_failure_time).total_seconds() > self.config.circuit_breaker_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_attempts = 0
                circuit_breaker_state.labels(operation=self.operation).set(CircuitState.HALF_OPEN.value)
                logger.info(f"Circuit breaker for {self.operation} half-open for testing")
                return False
            return True

        if self.state == CircuitState.HALF_OPEN:
            # Allow limited attempts in half-open state
            if self.half_open_attempts < 3:
                self.half_open_attempts += 1
                return False
            return True

        return False

class RetryBudget:
    """Retry budget to prevent retry storms"""
    def __init__(self, operation: str, config: RetryConfig):
        self.operation = operation
        self.config = config
        self.window_start = time.time()
        self.total_requests = 0
        self.retry_requests = 0

    def can_retry(self) -> bool:
        """Check if retry budget allows another retry"""
        current_time = time.time()

        # Reset window if needed
        if current_time - self.window_start > self.config.retry_budget_window:
            self.window_start = current_time
            self.total_requests = 0
            self.retry_requests = 0

        if self.total_requests == 0:
            return True

        retry_percentage = (self.retry_requests / self.total_requests) * 100
        budget_remaining = self.config.retry_budget_percent - retry_percentage
        retry_budget_remaining.labels(operation=self.operation).set(max(0, budget_remaining))

        return retry_percentage < self.config.retry_budget_percent

    def record_request(self, is_retry: bool = False):
        """Record a request"""
        self.total_requests += 1
        if is_retry:
            self.retry_requests += 1

class Bulkhead:
    """Bulkhead pattern for resource isolation"""
    def __init__(self, resource: str, size: int):
        self.resource = resource
        self.size = size
        self.active = 0
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Acquire bulkhead resource"""
        async with self._lock:
            if self.active >= self.size:
                raise BulkheadFullError(f"Bulkhead for {self.resource} is full ({self.active}/{self.size})")
            self.active += 1
            bulkhead_usage.labels(resource=self.resource).set(self.active)

    async def release(self):
        """Release bulkhead resource"""
        async with self._lock:
            self.active = max(0, self.active - 1)
            bulkhead_usage.labels(resource=self.resource).set(self.active)

class BulkheadFullError(Exception):
    """Raised when bulkhead is at capacity"""
    pass

# Global registries
_circuit_breakers: Dict[str, CircuitBreaker] = {}
_retry_budgets: Dict[str, RetryBudget] = {}
_bulkheads: Dict[str, Bulkhead] = {}

def get_circuit_breaker(operation: str, config: RetryConfig) -> CircuitBreaker:
    """Get or create circuit breaker for operation"""
    if operation not in _circuit_breakers:
        _circuit_breakers[operation] = CircuitBreaker(operation, config)
    return _circuit_breakers[operation]

def get_retry_budget(operation: str, config: RetryConfig) -> RetryBudget:
    """Get or create retry budget for operation"""
    if operation not in _retry_budgets:
        _retry_budgets[operation] = RetryBudget(operation, config)
    return _retry_budgets[operation]

def get_bulkhead(resource: str, size: int) -> Bulkhead:
    """Get or create bulkhead for resource"""
    if resource not in _bulkheads:
        _bulkheads[resource] = Bulkhead(resource, size)
    return _bulkheads[resource]

def calculate_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate delay with exponential backoff and jitter"""
    delay = min(
        config.initial_delay * (config.exponential_base ** (attempt - 1)),
        config.max_delay
    )

    if config.jitter:
        jitter_range = delay * config.jitter_factor
        jitter = random.uniform(-jitter_range, jitter_range)
        delay = max(0, delay + jitter)

    return delay

def is_retryable_exception(exception: Exception, config: RetryConfig) -> bool:
    """Determine if exception is retryable"""
    # Check non-retryable first
    if type(exception) in config.non_retryable_exceptions:
        # Special handling for HTTP errors
        if isinstance(exception, httpx.HTTPStatusError):
            # Don't retry 4xx errors (client errors)
            if 400 <= exception.response.status_code < 500:
                return False
            # Retry 5xx errors (server errors)
            return True
        return False

    # Check retryable
    return type(exception) in config.retryable_exceptions

def with_retry(
    operation: str,
    config: Optional[RetryConfig] = None,
    bulkhead_resource: Optional[str] = None,
):
    """Decorator for adding retry logic to async functions"""
    if config is None:
        config = RetryConfig()

    def decorator(func: AsyncFunc) -> AsyncFunc:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            retry_context = RetryContext(
                operation=operation,
                config=config,
                bulkhead_resource=bulkhead_resource
            )
            return await _execute_with_retry(func, args, kwargs, retry_context)

        return wrapper
    return decorator


class RetryContext:
    """Context for retry execution"""
    def __init__(self, operation: str, config: RetryConfig, bulkhead_resource: Optional[str]):
        self.operation = operation
        self.config = config
        self.circuit_breaker = get_circuit_breaker(operation, config)
        self.retry_budget = get_retry_budget(operation, config)
        self.bulkhead = get_bulkhead(bulkhead_resource, config.bulkhead_size) if bulkhead_resource and config.bulkhead_size else None
        self.start_time = time.time()
        self.last_exception = None


async def _execute_with_retry(func: AsyncFunc, args, kwargs, context: RetryContext):
    """Execute function with retry logic"""
    for attempt in range(1, context.config.max_attempts + 1):
        try:
            # Pre-execution checks
            await _pre_execution_checks(context, attempt)

            # Acquire resources
            await _acquire_resources(context)

            try:
                # Execute function
                result = await _execute_function(func, args, kwargs, context.config)

                # Handle success
                _handle_success(context, attempt)
                return result

            finally:
                # Release resources
                await _release_resources(context)

        except Exception as e:
            # Handle failure
            should_retry = await _handle_failure(e, context, attempt)
            if not should_retry:
                raise

    # All retries exhausted
    _record_exhausted_retries(context)
    raise context.last_exception


async def _pre_execution_checks(context: RetryContext, attempt: int):
    """Perform pre-execution checks"""
    # Check circuit breaker
    if context.circuit_breaker.is_open():
        logger.warning(f"Circuit breaker open for {context.operation}, failing fast")
        raise CircuitBreakerOpenError(f"Circuit breaker open for {context.operation}")

    # Check retry budget (only for retries)
    if attempt > 1:
        if not context.retry_budget.can_retry():
            logger.warning(f"Retry budget exhausted for {context.operation}")
            raise RetryBudgetExhaustedError(f"Retry budget exhausted for {context.operation}")
        context.retry_budget.record_request(is_retry=True)
    else:
        context.retry_budget.record_request(is_retry=False)


async def _acquire_resources(context: RetryContext):
    """Acquire necessary resources"""
    if context.bulkhead:
        try:
            await context.bulkhead.acquire()
        except BulkheadFullError:
            logger.warning(f"Bulkhead full for {context.operation}, failing")
            raise


async def _release_resources(context: RetryContext):
    """Release acquired resources"""
    if context.bulkhead:
        await context.bulkhead.release()


async def _execute_function(func: AsyncFunc, args, kwargs, config: RetryConfig):
    """Execute the function with optional timeout"""
    if config.timeout:
        return await asyncio.wait_for(func(*args, **kwargs), timeout=config.timeout)
    else:
        return await func(*args, **kwargs)


def _handle_success(context: RetryContext, attempt: int):
    """Handle successful execution"""
    context.circuit_breaker.record_success()
    retry_attempts.labels(operation=context.operation, status='success').inc()
    retry_duration.labels(operation=context.operation).observe(time.time() - context.start_time)

    if attempt > 1:
        logger.info(f"Operation {context.operation} succeeded after {attempt} attempts")


async def _handle_failure(exception: Exception, context: RetryContext, attempt: int) -> bool:
    """Handle execution failure. Returns True if should retry."""
    context.last_exception = exception

    # Check if retryable
    if not is_retryable_exception(exception, context.config):
        logger.error(f"Non-retryable exception in {context.operation}: {exception}")
        retry_attempts.labels(operation=context.operation, status='non_retryable').inc()
        return False

    # Record failure
    context.circuit_breaker.record_failure()

    # Check if can retry
    if attempt < context.config.max_attempts:
        delay = calculate_delay(attempt, context.config)
        logger.warning(
            f"Attempt {attempt}/{context.config.max_attempts} failed for {context.operation}: {exception}. "
            f"Retrying in {delay:.2f}s..."
        )
        await asyncio.sleep(delay)
        return True
    else:
        logger.error(f"All {context.config.max_attempts} attempts failed for {context.operation}")
        retry_attempts.labels(operation=context.operation, status='exhausted').inc()
        return False


def _record_exhausted_retries(context: RetryContext):
    """Record metrics for exhausted retries"""
    retry_duration.labels(operation=context.operation).observe(time.time() - context.start_time)

class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open"""
    pass

class RetryBudgetExhaustedError(Exception):
    """Raised when retry budget is exhausted"""
    pass

# Database-specific retry configurations
DB_READ_CONFIG = RetryConfig.for_strategy(RetryStrategy.STANDARD)
DB_WRITE_CONFIG = RetryConfig.for_strategy(RetryStrategy.AGGRESSIVE)
DB_CRITICAL_CONFIG = RetryConfig(
    strategy=RetryStrategy.CUSTOM,
    max_attempts=15,
    initial_delay=0.1,
    max_delay=120.0,
    exponential_base=1.3,
    circuit_breaker_threshold=30,
    retry_budget_percent=25.0,
)

# Example usage for TerminusDB operations
@with_retry("terminusdb_read", config=DB_READ_CONFIG, bulkhead_resource="terminusdb")
async def read_from_terminusdb(client, query: str):
    """Example read operation with retry"""
    return await client.query(query)

@with_retry("terminusdb_write", config=DB_WRITE_CONFIG, bulkhead_resource="terminusdb")
async def write_to_terminusdb(client, data: dict):
    """Example write operation with retry"""
    return await client.insert(data)

# Batch retry for multiple operations
class BatchRetryExecutor:
    """Execute multiple operations with coordinated retry logic"""

    def __init__(self, config: RetryConfig = None):
        self.config = config or RetryConfig.for_strategy(RetryStrategy.STANDARD)
        self.results: Dict[str, Any] = {}
        self.failures: Dict[str, Exception] = {}

    async def add_operation(self, name: str, operation: Callable, *args, **kwargs):
        """Add operation to batch"""
        @with_retry(f"batch_{name}", config=self.config)
        async def wrapped():
            return await operation(*args, **kwargs)

        try:
            self.results[name] = await wrapped()
        except Exception as e:
            self.failures[name] = e

    async def execute_all(self, operations: List[tuple]) -> Dict[str, Any]:
        """Execute all operations concurrently"""
        tasks = []
        for name, operation, args, kwargs in operations:
            task = self.add_operation(name, operation, *args, **kwargs)
            tasks.append(task)

        await asyncio.gather(*tasks, return_exceptions=True)

        if self.failures:
            logger.error(f"Batch execution had {len(self.failures)} failures: {list(self.failures.keys())}")

        return {
            'results': self.results,
            'failures': self.failures,
            'success_rate': len(self.results) / (len(self.results) + len(self.failures)) if self.results or self.failures else 0
        }
