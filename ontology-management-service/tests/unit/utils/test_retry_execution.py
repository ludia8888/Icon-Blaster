"""Unit tests for retry execution logic and utility functions."""

import pytest
import asyncio
import sys
import os
import random
import httpx
from unittest.mock import Mock, patch, MagicMock, AsyncMock

# Add the project root to the path to import modules directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

# Mock prometheus client before any imports
sys.modules['prometheus_client'] = MagicMock()

# Now we can safely import the retry strategy module
import importlib.util
spec = importlib.util.spec_from_file_location(
    "retry_strategy", 
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "utils", "retry_strategy.py")
)
retry_strategy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retry_strategy)

# Import what we need to test
calculate_delay = retry_strategy.calculate_delay
is_retryable_exception = retry_strategy.is_retryable_exception
with_retry = retry_strategy.with_retry
RetryConfig = retry_strategy.RetryConfig
RetryStrategy = retry_strategy.RetryStrategy
get_circuit_breaker = retry_strategy.get_circuit_breaker
get_retry_budget = retry_strategy.get_retry_budget
get_bulkhead = retry_strategy.get_bulkhead


class TestCalculateDelay:
    """Test suite for calculate_delay function."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = RetryConfig(
            initial_delay=1.0,
            max_delay=60.0,
            exponential_base=2.0,
            jitter=True,
            jitter_factor=0.1
        )
    
    def test_calculate_delay_first_attempt(self):
        """Test delay calculation for first attempt."""
        delay = calculate_delay(1, self.config)
        
        # First attempt should be close to initial delay
        if self.config.jitter:
            # With jitter, should be within jitter range of initial delay
            jitter_range = self.config.initial_delay * self.config.jitter_factor
            expected_min = self.config.initial_delay - jitter_range
            expected_max = self.config.initial_delay + jitter_range
            assert expected_min <= delay <= expected_max
        else:
            assert delay == self.config.initial_delay
    
    def test_calculate_delay_exponential_growth(self):
        """Test exponential growth of delays."""
        config_no_jitter = RetryConfig(
            initial_delay=1.0,
            max_delay=60.0,
            exponential_base=2.0,
            jitter=False
        )
        
        delays = [calculate_delay(i, config_no_jitter) for i in range(1, 6)]
        
        # Should follow exponential pattern: 1, 2, 4, 8, 16
        expected = [1.0, 2.0, 4.0, 8.0, 16.0]
        assert delays == expected
    
    def test_calculate_delay_max_cap(self):
        """Test that delays are capped at max_delay."""
        config = RetryConfig(
            initial_delay=1.0,
            max_delay=10.0,
            exponential_base=2.0,
            jitter=False
        )
        
        # High attempt number should hit max delay
        delay = calculate_delay(10, config)
        assert delay == config.max_delay
    
    def test_calculate_delay_with_jitter(self):
        """Test delay calculation with jitter."""
        config = RetryConfig(
            initial_delay=5.0,
            max_delay=60.0,
            exponential_base=2.0,
            jitter=True,
            jitter_factor=0.2
        )
        
        # Run multiple times to test jitter variation
        delays = [calculate_delay(2, config) for _ in range(10)]
        
        # All delays should be different due to jitter
        assert len(set(delays)) > 1
        
        # All delays should be non-negative
        assert all(delay >= 0 for delay in delays)
        
        # Base delay for attempt 2 is 10.0
        base_delay = 10.0
        jitter_range = base_delay * config.jitter_factor
        expected_min = base_delay - jitter_range
        expected_max = base_delay + jitter_range
        
        for delay in delays:
            assert expected_min <= delay <= expected_max
    
    def test_calculate_delay_without_jitter(self):
        """Test delay calculation without jitter."""
        config = RetryConfig(
            initial_delay=2.0,
            max_delay=60.0,
            exponential_base=3.0,
            jitter=False
        )
        
        delay1 = calculate_delay(3, config)
        delay2 = calculate_delay(3, config)
        
        # Should be exactly the same without jitter
        assert delay1 == delay2
        assert delay1 == 2.0 * (3.0 ** 2)  # 18.0
    
    def test_calculate_delay_different_exponential_bases(self):
        """Test delay calculation with different exponential bases."""
        # Base 1.5 (slower growth)
        config_slow = RetryConfig(
            initial_delay=1.0,
            exponential_base=1.5,
            jitter=False
        )
        
        # Base 3.0 (faster growth)  
        config_fast = RetryConfig(
            initial_delay=1.0,
            exponential_base=3.0,
            jitter=False
        )
        
        slow_delay = calculate_delay(4, config_slow)
        fast_delay = calculate_delay(4, config_fast)
        
        # Faster base should produce larger delay
        assert fast_delay > slow_delay
        assert slow_delay == 1.0 * (1.5 ** 3)  # 3.375
        assert fast_delay == 1.0 * (3.0 ** 3)  # 27.0
    
    def test_calculate_delay_zero_jitter_factor(self):
        """Test delay calculation with zero jitter factor."""
        config = RetryConfig(
            initial_delay=5.0,
            jitter=True,
            jitter_factor=0.0
        )
        
        delay = calculate_delay(2, config)
        # With zero jitter factor, should be exactly the base delay
        assert delay == 5.0 * (2.0 ** 1)  # 10.0


class TestIsRetryableException:
    """Test suite for is_retryable_exception function."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = RetryConfig()
    
    def test_retryable_exceptions(self):
        """Test that configured retryable exceptions are identified correctly."""
        retryable_exceptions = [
            httpx.TimeoutException("Timeout"),
            httpx.ConnectError("Connection failed"),
            httpx.ReadTimeout("Read timeout"),
            ConnectionError("Connection error"),
            TimeoutError("Timeout error"),
            asyncio.TimeoutError("Async timeout")
        ]
        
        for exc in retryable_exceptions:
            assert is_retryable_exception(exc, self.config) is True
    
    def test_non_retryable_exceptions(self):
        """Test that configured non-retryable exceptions are identified correctly."""
        non_retryable_exceptions = [
            ValueError("Invalid value"),
            TypeError("Type error"),
            PermissionError("Permission denied")
        ]
        
        for exc in non_retryable_exceptions:
            assert is_retryable_exception(exc, self.config) is False
    
    def test_http_status_error_4xx(self):
        """Test that 4xx HTTP errors are not retryable."""
        # Mock HTTP response with 4xx status codes
        for status_code in [400, 401, 403, 404, 422, 429]:
            response = Mock()
            response.status_code = status_code
            
            exc = httpx.HTTPStatusError("Client error", request=Mock(), response=response)
            assert is_retryable_exception(exc, self.config) is False
    
    def test_http_status_error_5xx(self):
        """Test that 5xx HTTP errors are retryable."""
        # Mock HTTP response with 5xx status codes
        for status_code in [500, 502, 503, 504]:
            response = Mock()
            response.status_code = status_code
            
            exc = httpx.HTTPStatusError("Server error", request=Mock(), response=response)
            assert is_retryable_exception(exc, self.config) is True
    
    def test_custom_retryable_exceptions(self):
        """Test with custom retryable exceptions configuration."""
        custom_config = RetryConfig(
            retryable_exceptions={RuntimeError, OSError},
            non_retryable_exceptions={ValueError}
        )
        
        assert is_retryable_exception(RuntimeError("Runtime error"), custom_config) is True
        assert is_retryable_exception(OSError("OS error"), custom_config) is True
        assert is_retryable_exception(ValueError("Value error"), custom_config) is False
        assert is_retryable_exception(TypeError("Type error"), custom_config) is False
    
    def test_unknown_exception(self):
        """Test behavior with exceptions not in either list."""
        unknown_exc = KeyError("Unknown exception")
        assert is_retryable_exception(unknown_exc, self.config) is False


class TestGlobalRegistries:
    """Test suite for global registry functions."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = RetryConfig()
        # Clear registries before each test
        retry_strategy._circuit_breakers.clear()
        retry_strategy._retry_budgets.clear()
        retry_strategy._bulkheads.clear()
    
    def test_get_circuit_breaker_creation(self):
        """Test circuit breaker creation and retrieval."""
        operation = "test_operation"
        
        # First call should create new circuit breaker
        cb1 = get_circuit_breaker(operation, self.config)
        assert cb1 is not None
        assert cb1.operation == operation
        
        # Second call should return same instance
        cb2 = get_circuit_breaker(operation, self.config)
        assert cb1 is cb2
    
    def test_get_retry_budget_creation(self):
        """Test retry budget creation and retrieval."""
        operation = "test_operation"
        
        # First call should create new retry budget
        rb1 = get_retry_budget(operation, self.config)
        assert rb1 is not None
        assert rb1.operation == operation
        
        # Second call should return same instance
        rb2 = get_retry_budget(operation, self.config)
        assert rb1 is rb2
    
    def test_get_bulkhead_creation(self):
        """Test bulkhead creation and retrieval."""
        resource = "test_resource"
        size = 5
        
        # First call should create new bulkhead
        bh1 = get_bulkhead(resource, size)
        assert bh1 is not None
        assert bh1.resource == resource
        assert bh1.size == size
        
        # Second call should return same instance
        bh2 = get_bulkhead(resource, size)
        assert bh1 is bh2
    
    def test_multiple_operations_separate_instances(self):
        """Test that different operations get separate instances."""
        cb1 = get_circuit_breaker("operation1", self.config)
        cb2 = get_circuit_breaker("operation2", self.config)
        
        assert cb1 is not cb2
        assert cb1.operation != cb2.operation
        
        rb1 = get_retry_budget("operation1", self.config)
        rb2 = get_retry_budget("operation2", self.config)
        
        assert rb1 is not rb2
        assert rb1.operation != rb2.operation


class TestWithRetryDecorator:
    """Test suite for with_retry decorator."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.call_count = 0
        self.exception_count = 0
        # Clear global registries to avoid test interference
        retry_strategy._circuit_breakers.clear()
        retry_strategy._retry_budgets.clear()
        retry_strategy._bulkheads.clear()
    
    @pytest.mark.asyncio
    async def test_successful_function_no_retry(self):
        """Test decorator with function that succeeds on first try."""
        @with_retry("test_operation")
        async def successful_function():
            self.call_count += 1
            return "success"
        
        result = await successful_function()
        
        assert result == "success"
        assert self.call_count == 1
    
    @pytest.mark.asyncio
    async def test_function_with_retryable_exception(self):
        """Test decorator with function that fails then succeeds."""
        @with_retry("test_operation_retryable", RetryConfig(
            max_attempts=3,
            retry_budget_percent=90.0,  # More generous budget for testing
            circuit_breaker_threshold=10
        ))
        async def flaky_function():
            self.call_count += 1
            if self.call_count < 3:
                raise httpx.TimeoutException("Timeout")
            return "success"
        
        result = await flaky_function()
        
        assert result == "success"
        assert self.call_count == 3
    
    @pytest.mark.asyncio
    async def test_function_with_non_retryable_exception(self):
        """Test decorator with non-retryable exception."""
        @with_retry("test_operation")
        async def failing_function():
            self.call_count += 1
            raise ValueError("Not retryable")
        
        with pytest.raises(ValueError):
            await failing_function()
        
        assert self.call_count == 1  # Should not retry
    
    @pytest.mark.asyncio
    async def test_exhausted_retries(self):
        """Test decorator when all retries are exhausted."""
        @with_retry("test_operation", RetryConfig(
            max_attempts=2,
            retry_budget_percent=50.0,
            circuit_breaker_threshold=10  # High threshold to avoid circuit breaking
        ))
        async def always_failing_function():
            self.call_count += 1
            raise httpx.TimeoutException("Always fails")
        
        with pytest.raises(httpx.TimeoutException):
            await always_failing_function()
        
        assert self.call_count == 2  # Should try twice
    
    @pytest.mark.asyncio
    async def test_decorator_with_custom_config(self):
        """Test decorator with custom retry configuration."""
        custom_config = RetryConfig(
            max_attempts=5,
            initial_delay=0.1,
            exponential_base=1.5,
            retry_budget_percent=90.0,
            circuit_breaker_threshold=10
        )
        
        @with_retry("test_operation_custom", custom_config)
        async def test_function():
            self.call_count += 1
            if self.call_count < 4:
                raise httpx.TimeoutException("Retry me")
            return "finally_success"
        
        result = await test_function()
        
        assert result == "finally_success"
        assert self.call_count == 4
    
    @pytest.mark.asyncio
    async def test_decorator_preserves_function_metadata(self):
        """Test that decorator preserves original function metadata."""
        @with_retry("test_operation")
        async def documented_function():
            """This is a documented function."""
            return "result"
        
        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "This is a documented function."
    
    @pytest.mark.asyncio
    async def test_decorator_with_function_arguments(self):
        """Test decorator with function that takes arguments."""
        @with_retry("test_operation", RetryConfig(
            retry_budget_percent=50.0,
            circuit_breaker_threshold=10
        ))
        async def function_with_args(x, y, z=None):
            self.call_count += 1
            if self.call_count == 1:
                raise httpx.TimeoutException("Retry")
            return f"{x}-{y}-{z}"
        
        result = await function_with_args("a", "b", z="c")
        
        assert result == "a-b-c"
        assert self.call_count == 2
    
    @pytest.mark.asyncio
    async def test_multiple_decorated_functions_isolated(self):
        """Test that multiple decorated functions have isolated retry contexts."""
        call_count_1 = 0
        call_count_2 = 0
        
        @with_retry("operation1", RetryConfig(
            retry_budget_percent=60.0,
            circuit_breaker_threshold=10
        ))
        async def function1():
            nonlocal call_count_1
            call_count_1 += 1
            if call_count_1 < 2:
                raise httpx.TimeoutException("Retry")
            return "result1"
        
        @with_retry("operation2", RetryConfig(
            retry_budget_percent=60.0,
            circuit_breaker_threshold=10
        ))
        async def function2():
            nonlocal call_count_2
            call_count_2 += 1
            if call_count_2 < 3:
                raise httpx.TimeoutException("Retry")
            return "result2"
        
        # Execute both functions
        result1 = await function1()
        result2 = await function2()
        
        assert result1 == "result1"
        assert result2 == "result2"
        assert call_count_1 == 2
        assert call_count_2 == 3


class TestRetryDelayBehavior:
    """Test suite for retry delay behavior in actual execution."""
    
    def setup_method(self):
        """Set up test fixtures."""
        # Clear global registries to avoid test interference
        retry_strategy._circuit_breakers.clear()
        retry_strategy._retry_budgets.clear()
        retry_strategy._bulkheads.clear()
    
    @pytest.mark.asyncio
    async def test_retry_delays_are_applied(self):
        """Test that delays are actually applied between retries."""
        start_times = []
        
        @with_retry("test_operation_delays", RetryConfig(
            max_attempts=3,
            initial_delay=0.1,
            exponential_base=2.0,
            jitter=False,
            retry_budget_percent=90.0,
            circuit_breaker_threshold=10
        ))
        async def timed_function():
            start_times.append(asyncio.get_event_loop().time())
            if len(start_times) < 3:
                raise httpx.TimeoutException("Retry")
            return "success"
        
        result = await timed_function()
        
        assert result == "success"
        assert len(start_times) == 3
        
        # Check that delays were approximately correct
        # First retry delay should be ~0.1s, second ~0.2s
        delay1 = start_times[1] - start_times[0]
        delay2 = start_times[2] - start_times[1]
        
        # Allow some tolerance for timing
        assert 0.08 <= delay1 <= 0.15
        assert 0.18 <= delay2 <= 0.25