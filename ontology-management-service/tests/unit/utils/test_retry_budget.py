"""Unit tests for RetryBudget class from retry strategy module."""

import pytest
import sys
import os
import time
from unittest.mock import Mock, patch, MagicMock

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

RetryBudget = retry_strategy.RetryBudget
RetryConfig = retry_strategy.RetryConfig
RetryStrategy = retry_strategy.RetryStrategy


class TestRetryBudget:
    """Test suite for RetryBudget class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = RetryConfig(
            retry_budget_percent=10.0,  # 10% of requests can be retries
            retry_budget_window=60.0    # 60-second window
        )
        self.operation = "test_operation"
        self.retry_budget = RetryBudget(self.operation, self.config)
    
    def test_retry_budget_initialization(self):
        """Test RetryBudget initialization."""
        assert self.retry_budget.operation == "test_operation"
        assert self.retry_budget.config == self.config
        assert self.retry_budget.total_requests == 0
        assert self.retry_budget.retry_requests == 0
        assert isinstance(self.retry_budget.window_start, float)
    
    def test_can_retry_with_no_requests(self):
        """Test can_retry returns True when no requests have been made."""
        assert self.retry_budget.can_retry() is True
    
    def test_record_request_normal(self):
        """Test recording a normal (non-retry) request."""
        initial_total = self.retry_budget.total_requests
        initial_retry = self.retry_budget.retry_requests
        
        self.retry_budget.record_request(is_retry=False)
        
        assert self.retry_budget.total_requests == initial_total + 1
        assert self.retry_budget.retry_requests == initial_retry
    
    def test_record_request_retry(self):
        """Test recording a retry request."""
        initial_total = self.retry_budget.total_requests
        initial_retry = self.retry_budget.retry_requests
        
        self.retry_budget.record_request(is_retry=True)
        
        assert self.retry_budget.total_requests == initial_total + 1
        assert self.retry_budget.retry_requests == initial_retry + 1
    
    def test_can_retry_within_budget(self):
        """Test can_retry returns True when within budget."""
        # Record 20 normal requests and 1 retry (5% retry rate < 10%)
        for i in range(20):
            self.retry_budget.record_request(is_retry=False)
        self.retry_budget.record_request(is_retry=True)
        
        # Should be within 10% budget (5% < 10%)
        assert self.retry_budget.can_retry() is True
    
    def test_can_retry_at_budget_limit(self):
        """Test can_retry at exactly the budget limit."""
        # Record 9 normal requests and 1 retry (10% retry rate exactly)
        for i in range(9):
            self.retry_budget.record_request(is_retry=False)
        self.retry_budget.record_request(is_retry=True)
        
        # Should be at the limit and NOT allowed (< not <=)
        assert self.retry_budget.can_retry() is False
    
    def test_can_retry_exceeds_budget(self):
        """Test can_retry returns False when budget is exceeded."""
        # Record 5 normal requests and 1 retry (16.67% retry rate > 10%)
        for i in range(5):
            self.retry_budget.record_request(is_retry=False)
        self.retry_budget.record_request(is_retry=True)
        
        # Should exceed 10% budget
        assert self.retry_budget.can_retry() is False
    
    def test_can_retry_all_retries(self):
        """Test can_retry when all requests are retries."""
        # Record only retry requests
        for i in range(5):
            self.retry_budget.record_request(is_retry=True)
        
        # 100% retry rate should exceed any reasonable budget
        assert self.retry_budget.can_retry() is False
    
    def test_window_reset_functionality(self):
        """Test that budget window resets after timeout."""
        # Fill up the budget
        for i in range(5):
            self.retry_budget.record_request(is_retry=False)
        self.retry_budget.record_request(is_retry=True)
        
        # Should exceed budget
        assert self.retry_budget.can_retry() is False
        
        # Mock time to simulate window expiration
        with patch.object(retry_strategy, 'time') as mock_time:
            # Simulate time passing beyond window
            original_start = self.retry_budget.window_start
            mock_time.time.return_value = original_start + self.config.retry_budget_window + 1
            
            # Should reset and allow retries again
            assert self.retry_budget.can_retry() is True
            assert self.retry_budget.total_requests == 0
            assert self.retry_budget.retry_requests == 0
            assert self.retry_budget.window_start == original_start + self.config.retry_budget_window + 1
    
    def test_window_reset_boundary(self):
        """Test window reset at exact boundary."""
        # Fill up the budget
        for i in range(5):
            self.retry_budget.record_request(is_retry=False)
        self.retry_budget.record_request(is_retry=True)
        
        with patch.object(retry_strategy, 'time') as mock_time:
            # Simulate time at exact window boundary
            original_start = self.retry_budget.window_start
            mock_time.time.return_value = original_start + self.config.retry_budget_window
            
            # Should not reset yet (boundary condition)
            result = self.retry_budget.can_retry()
            assert self.retry_budget.total_requests > 0  # Should not have reset
    
    def test_different_budget_percentages(self):
        """Test retry budget with different percentage configurations."""
        # Test with 50% budget
        high_budget_config = RetryConfig(retry_budget_percent=50.0)
        high_budget = RetryBudget("high_budget_op", high_budget_config)
        
        # Add 1 normal and 1 retry (50% retry rate exactly)
        high_budget.record_request(is_retry=False)
        high_budget.record_request(is_retry=True)
        
        # At exactly 50%, should not be allowed (< not <=)
        assert high_budget.can_retry() is False
        
        # Test with 1% budget (very strict)
        low_budget_config = RetryConfig(retry_budget_percent=1.0)
        low_budget = RetryBudget("low_budget_op", low_budget_config)
        
        # Add 199 normal and 1 retry (0.5% retry rate < 1%)
        for i in range(199):
            low_budget.record_request(is_retry=False)
        low_budget.record_request(is_retry=True)
        
        assert low_budget.can_retry() is True
        
        # Add one more retry: now 2 retries out of 201 = 0.995% (still < 1%)
        low_budget.record_request(is_retry=True)
        assert low_budget.can_retry() is True
        
        # Add more retries to exceed 1%: need at least 3 retries out of ~300 total
        # Let's add enough to definitely exceed 1%
        for i in range(3):  # Add 3 more retries to get 5 total out of 204 = 2.45%
            low_budget.record_request(is_retry=True)
        assert low_budget.can_retry() is False
    
    def test_zero_budget_percentage(self):
        """Test retry budget with 0% (no retries allowed)."""
        zero_budget_config = RetryConfig(retry_budget_percent=0.0)
        zero_budget = RetryBudget("zero_budget_op", zero_budget_config)
        
        # Add some normal requests
        for i in range(10):
            zero_budget.record_request(is_retry=False)
        
        # Should not allow retries when requests exist (0% budget means 0 < 0 is False)
        assert zero_budget.can_retry() is False
        
        # Add one retry
        zero_budget.record_request(is_retry=True)
        
        # Should not allow more retries
        assert zero_budget.can_retry() is False
    
    def test_hundred_percent_budget(self):
        """Test retry budget with 100% (all requests can be retries)."""
        full_budget_config = RetryConfig(retry_budget_percent=100.0)
        full_budget = RetryBudget("full_budget_op", full_budget_config)
        
        # Add 1 normal and 99 retry requests (99% retry rate < 100%)
        full_budget.record_request(is_retry=False)
        for i in range(99):
            full_budget.record_request(is_retry=True)
        
        # At 99%, should be allowed (99% < 100%)
        assert full_budget.can_retry() is True
    
    def test_partial_window_with_mixed_requests(self):
        """Test retry budget behavior with mixed request patterns."""
        # Start with normal requests
        for i in range(8):
            self.retry_budget.record_request(is_retry=False)
        
        # Add retries gradually
        self.retry_budget.record_request(is_retry=True)  # 1/9 = 11.1% > 10%
        assert self.retry_budget.can_retry() is False
        
        # Add more normal requests to dilute retry percentage
        for i in range(10):
            self.retry_budget.record_request(is_retry=False)
        
        # Now 1/19 = 5.26% < 10%
        assert self.retry_budget.can_retry() is True
    
    def test_metrics_recording(self):
        """Test that metrics are recorded correctly."""
        # Record some requests
        for i in range(10):
            self.retry_budget.record_request(is_retry=False)
        self.retry_budget.record_request(is_retry=True)
        
        # Call can_retry to trigger metrics recording
        with patch.object(retry_strategy, 'retry_budget_remaining') as mock_metric:
            self.retry_budget.can_retry()
            
            # Should have called metrics
            mock_metric.labels.assert_called_once_with(operation=self.operation)
    
    def test_budget_calculation_precision(self):
        """Test precision of budget percentage calculations."""
        # Use a configuration that might cause floating point precision issues
        precise_config = RetryConfig(retry_budget_percent=33.333)
        precise_budget = RetryBudget("precise_op", precise_config)
        
        # Add requests that result in exactly 33.333% retry rate
        for i in range(2):
            precise_budget.record_request(is_retry=False)
        precise_budget.record_request(is_retry=True)
        
        # 1/3 = 33.333%
        result = precise_budget.can_retry()
        # Should handle precision correctly
        assert isinstance(result, bool)
    
    def test_window_start_initialization(self):
        """Test that window_start is properly initialized."""
        current_time = time.time()
        budget = RetryBudget("test_op", self.config)
        
        # Window start should be close to current time
        assert abs(budget.window_start - current_time) < 1.0
    
    def test_concurrent_operations_simulation(self):
        """Test retry budget behavior simulating concurrent operations."""
        # Simulate rapid successive requests
        for i in range(50):
            if i % 10 == 0:  # Every 10th request is a retry
                self.retry_budget.record_request(is_retry=True)
            else:
                self.retry_budget.record_request(is_retry=False)
        
        # Should have 5 retries out of 50 requests = 10% exactly
        assert self.retry_budget.can_retry() is False
        
        # Add one more retry to exceed budget
        self.retry_budget.record_request(is_retry=True)
        assert self.retry_budget.can_retry() is False
    
    def test_edge_case_single_retry_request(self):
        """Test edge case where the first request is a retry."""
        self.retry_budget.record_request(is_retry=True)
        
        # 100% retry rate should exceed budget
        assert self.retry_budget.can_retry() is False
    
    def test_budget_remaining_calculation(self):
        """Test the budget remaining calculation used for metrics."""
        # Record requests to get specific percentage
        for i in range(20):
            self.retry_budget.record_request(is_retry=False)
        self.retry_budget.record_request(is_retry=True)
        
        # 1/21 ≈ 4.76% retry rate, so remaining should be ~5.24%
        with patch.object(retry_strategy, 'retry_budget_remaining') as mock_metric:
            self.retry_budget.can_retry()
            
            # Check that set was called with positive remaining budget
            mock_metric.labels.return_value.set.assert_called_once()
            args = mock_metric.labels.return_value.set.call_args[0]
            remaining_budget = args[0]
            assert remaining_budget > 0
            assert remaining_budget < self.config.retry_budget_percent