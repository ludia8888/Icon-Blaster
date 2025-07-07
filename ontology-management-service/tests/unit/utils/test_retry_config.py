"""Unit tests for RetryConfig class from retry strategy module."""

import pytest
import httpx
import asyncio
import sys
import os
from unittest.mock import Mock

# Add the project root to the path to import modules directly
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

# Import directly from the module file to avoid __init__.py issues
import importlib.util
spec = importlib.util.spec_from_file_location(
    "retry_strategy", 
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "utils", "retry_strategy.py")
)
retry_strategy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retry_strategy)

RetryConfig = retry_strategy.RetryConfig
RetryStrategy = retry_strategy.RetryStrategy


class TestRetryConfig:
    """Test suite for RetryConfig class."""
    
    def test_default_config_creation(self):
        """Test creating RetryConfig with default values."""
        config = RetryConfig()
        
        assert config.strategy == RetryStrategy.STANDARD
        assert config.max_attempts == 3
        assert config.initial_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.jitter is True
        assert config.jitter_factor == 0.1
        assert config.timeout is None
        assert config.circuit_breaker_threshold == 5
        assert config.circuit_breaker_timeout == 60.0
        assert config.bulkhead_size is None
        assert config.retry_budget_percent == 10.0
        assert config.retry_budget_window == 60.0
    
    def test_custom_config_creation(self):
        """Test creating RetryConfig with custom values."""
        config = RetryConfig(
            strategy=RetryStrategy.AGGRESSIVE,
            max_attempts=10,
            initial_delay=0.5,
            max_delay=120.0,
            exponential_base=1.5,
            jitter=False,
            jitter_factor=0.2,
            timeout=30.0,
            circuit_breaker_threshold=15,
            circuit_breaker_timeout=120.0,
            bulkhead_size=100,
            retry_budget_percent=25.0,
            retry_budget_window=120.0
        )
        
        assert config.strategy == RetryStrategy.AGGRESSIVE
        assert config.max_attempts == 10
        assert config.initial_delay == 0.5
        assert config.max_delay == 120.0
        assert config.exponential_base == 1.5
        assert config.jitter is False
        assert config.jitter_factor == 0.2
        assert config.timeout == 30.0
        assert config.circuit_breaker_threshold == 15
        assert config.circuit_breaker_timeout == 120.0
        assert config.bulkhead_size == 100
        assert config.retry_budget_percent == 25.0
        assert config.retry_budget_window == 120.0
    
    def test_default_retryable_exceptions(self):
        """Test default retryable exceptions are set correctly."""
        config = RetryConfig()
        
        expected_exceptions = {
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.ReadTimeout,
            ConnectionError,
            TimeoutError,
            asyncio.TimeoutError,
        }
        
        assert config.retryable_exceptions == expected_exceptions
    
    def test_default_non_retryable_exceptions(self):
        """Test default non-retryable exceptions are set correctly."""
        config = RetryConfig()
        
        expected_exceptions = {
            httpx.HTTPStatusError,
            ValueError,
            TypeError,
            PermissionError,
        }
        
        assert config.non_retryable_exceptions == expected_exceptions
    
    def test_custom_retryable_exceptions(self):
        """Test setting custom retryable exceptions."""
        custom_exceptions = {RuntimeError, OSError}
        config = RetryConfig(retryable_exceptions=custom_exceptions)
        
        assert config.retryable_exceptions == custom_exceptions
    
    def test_custom_non_retryable_exceptions(self):
        """Test setting custom non-retryable exceptions."""
        custom_exceptions = {KeyError, AttributeError}
        config = RetryConfig(non_retryable_exceptions=custom_exceptions)
        
        assert config.non_retryable_exceptions == custom_exceptions
    
    def test_for_strategy_aggressive(self):
        """Test factory method for aggressive strategy."""
        config = RetryConfig.for_strategy(RetryStrategy.AGGRESSIVE)
        
        assert config.strategy == RetryStrategy.AGGRESSIVE
        assert config.max_attempts == 10
        assert config.initial_delay == 0.5
        assert config.max_delay == 300.0
        assert config.exponential_base == 1.5
        assert config.circuit_breaker_threshold == 20
        assert config.retry_budget_percent == 20.0
    
    def test_for_strategy_standard(self):
        """Test factory method for standard strategy."""
        config = RetryConfig.for_strategy(RetryStrategy.STANDARD)
        
        assert config.strategy == RetryStrategy.STANDARD
        assert config.max_attempts == 5
        assert config.initial_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.circuit_breaker_threshold == 10
        assert config.retry_budget_percent == 10.0
    
    def test_for_strategy_conservative(self):
        """Test factory method for conservative strategy."""
        config = RetryConfig.for_strategy(RetryStrategy.CONSERVATIVE)
        
        assert config.strategy == RetryStrategy.CONSERVATIVE
        assert config.max_attempts == 3
        assert config.initial_delay == 2.0
        assert config.max_delay == 30.0
        assert config.exponential_base == 2.0
        assert config.circuit_breaker_threshold == 5
        assert config.retry_budget_percent == 5.0
    
    def test_for_strategy_custom_fallback(self):
        """Test factory method fallback for custom strategy."""
        config = RetryConfig.for_strategy(RetryStrategy.CUSTOM)
        
        # Should return default config for custom strategy
        assert config.strategy == RetryStrategy.STANDARD  # Default fallback
        assert config.max_attempts == 3
        assert config.initial_delay == 1.0
    
    def test_config_validation_positive_values(self):
        """Test that configuration accepts positive values."""
        config = RetryConfig(
            max_attempts=1,
            initial_delay=0.1,
            max_delay=0.2,
            exponential_base=1.1,
            jitter_factor=0.01,
            circuit_breaker_threshold=1,
            circuit_breaker_timeout=0.1,
            retry_budget_percent=0.1,
            retry_budget_window=0.1
        )
        
        assert config.max_attempts == 1
        assert config.initial_delay == 0.1
        assert config.max_delay == 0.2
        assert config.exponential_base == 1.1
        assert config.jitter_factor == 0.01
        assert config.circuit_breaker_threshold == 1
        assert config.circuit_breaker_timeout == 0.1
        assert config.retry_budget_percent == 0.1
        assert config.retry_budget_window == 0.1
    
    def test_jitter_factor_bounds(self):
        """Test jitter factor with boundary values."""
        # Test minimum
        config1 = RetryConfig(jitter_factor=0.0)
        assert config1.jitter_factor == 0.0
        
        # Test maximum reasonable value
        config2 = RetryConfig(jitter_factor=1.0)
        assert config2.jitter_factor == 1.0
    
    def test_exponential_base_edge_cases(self):
        """Test exponential base with edge cases."""
        # Test minimum (no exponential growth)
        config1 = RetryConfig(exponential_base=1.0)
        assert config1.exponential_base == 1.0
        
        # Test typical value
        config2 = RetryConfig(exponential_base=2.0)
        assert config2.exponential_base == 2.0
        
        # Test high value
        config3 = RetryConfig(exponential_base=10.0)
        assert config3.exponential_base == 10.0
    
    def test_retry_budget_percentage_bounds(self):
        """Test retry budget percentage bounds."""
        # Test 0% (no retries allowed)
        config1 = RetryConfig(retry_budget_percent=0.0)
        assert config1.retry_budget_percent == 0.0
        
        # Test 100% (all requests can be retries)
        config2 = RetryConfig(retry_budget_percent=100.0)
        assert config2.retry_budget_percent == 100.0
    
    def test_delay_relationship(self):
        """Test that delay configuration is logically consistent."""
        # Normal case: initial < max
        config1 = RetryConfig(initial_delay=1.0, max_delay=60.0)
        assert config1.initial_delay < config1.max_delay
        
        # Edge case: initial = max (no exponential growth)
        config2 = RetryConfig(initial_delay=5.0, max_delay=5.0)
        assert config2.initial_delay == config2.max_delay
    
    def test_config_immutability_after_creation(self):
        """Test that config values can be modified after creation."""
        config = RetryConfig()
        original_attempts = config.max_attempts
        
        # Modify the config (this should be allowed for configuration flexibility)
        config.max_attempts = 10
        assert config.max_attempts == 10
        assert config.max_attempts != original_attempts
    
    def test_bulkhead_none_vs_positive(self):
        """Test bulkhead size configuration."""
        # No bulkhead
        config1 = RetryConfig(bulkhead_size=None)
        assert config1.bulkhead_size is None
        
        # With bulkhead
        config2 = RetryConfig(bulkhead_size=50)
        assert config2.bulkhead_size == 50
    
    def test_timeout_none_vs_positive(self):
        """Test timeout configuration."""
        # No timeout
        config1 = RetryConfig(timeout=None)
        assert config1.timeout is None
        
        # With timeout
        config2 = RetryConfig(timeout=30.0)
        assert config2.timeout == 30.0


class TestRetryStrategy:
    """Test suite for RetryStrategy enum."""
    
    def test_retry_strategy_enum_values(self):
        """Test that all retry strategy enum values are correct."""
        assert RetryStrategy.AGGRESSIVE.value == "aggressive"
        assert RetryStrategy.STANDARD.value == "standard"
        assert RetryStrategy.CONSERVATIVE.value == "conservative"
        assert RetryStrategy.CUSTOM.value == "custom"
    
    def test_retry_strategy_enum_membership(self):
        """Test enum membership and comparison."""
        assert RetryStrategy.AGGRESSIVE in RetryStrategy
        assert RetryStrategy.STANDARD in RetryStrategy
        assert RetryStrategy.CONSERVATIVE in RetryStrategy
        assert RetryStrategy.CUSTOM in RetryStrategy
        
        # Test inequality
        assert RetryStrategy.AGGRESSIVE != RetryStrategy.STANDARD
        assert RetryStrategy.CONSERVATIVE != RetryStrategy.CUSTOM
    
    def test_retry_strategy_from_string(self):
        """Test creating enum from string values."""
        assert RetryStrategy("aggressive") == RetryStrategy.AGGRESSIVE
        assert RetryStrategy("standard") == RetryStrategy.STANDARD
        assert RetryStrategy("conservative") == RetryStrategy.CONSERVATIVE
        assert RetryStrategy("custom") == RetryStrategy.CUSTOM
    
    def test_retry_strategy_invalid_value(self):
        """Test that invalid strategy values raise ValueError."""
        with pytest.raises(ValueError):
            RetryStrategy("invalid_strategy")
    
    def test_all_strategies_have_configs(self):
        """Test that all strategies except CUSTOM have predefined configs."""
        # These should work without error
        RetryConfig.for_strategy(RetryStrategy.AGGRESSIVE)
        RetryConfig.for_strategy(RetryStrategy.STANDARD)
        RetryConfig.for_strategy(RetryStrategy.CONSERVATIVE)
        
        # CUSTOM should fall back to default
        custom_config = RetryConfig.for_strategy(RetryStrategy.CUSTOM)
        default_config = RetryConfig()
        
        # They should have the same values (fallback behavior)
        assert custom_config.max_attempts == default_config.max_attempts
        assert custom_config.initial_delay == default_config.initial_delay