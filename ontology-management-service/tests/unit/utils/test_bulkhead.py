"""Unit tests for Bulkhead class from retry strategy module."""

import pytest
import asyncio
import sys
import os
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

Bulkhead = retry_strategy.Bulkhead
BulkheadFullError = retry_strategy.BulkheadFullError


class TestBulkhead:
    """Test suite for Bulkhead class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.resource = "test_resource"
        self.size = 3
        self.bulkhead = Bulkhead(self.resource, self.size)
    
    def test_bulkhead_initialization(self):
        """Test Bulkhead initialization."""
        assert self.bulkhead.resource == "test_resource"
        assert self.bulkhead.size == 3
        assert self.bulkhead.active == 0
        assert isinstance(self.bulkhead._lock, asyncio.Lock)
    
    @pytest.mark.asyncio
    async def test_acquire_single_resource(self):
        """Test acquiring a single resource."""
        await self.bulkhead.acquire()
        
        assert self.bulkhead.active == 1
    
    @pytest.mark.asyncio
    async def test_acquire_multiple_resources(self):
        """Test acquiring multiple resources up to limit."""
        # Acquire resources up to the limit
        for i in range(self.size):
            await self.bulkhead.acquire()
            assert self.bulkhead.active == i + 1
        
        # Should have reached the limit
        assert self.bulkhead.active == self.size
    
    @pytest.mark.asyncio
    async def test_acquire_exceeds_capacity(self):
        """Test that acquiring beyond capacity raises BulkheadFullError."""
        # Fill up the bulkhead
        for i in range(self.size):
            await self.bulkhead.acquire()
        
        # Next acquisition should fail
        with pytest.raises(BulkheadFullError) as exc_info:
            await self.bulkhead.acquire()
        
        assert "is full" in str(exc_info.value)
        assert f"{self.size}/{self.size}" in str(exc_info.value)
        assert self.resource in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_release_single_resource(self):
        """Test releasing a single resource."""
        # First acquire a resource
        await self.bulkhead.acquire()
        assert self.bulkhead.active == 1
        
        # Then release it
        await self.bulkhead.release()
        assert self.bulkhead.active == 0
    
    @pytest.mark.asyncio
    async def test_release_multiple_resources(self):
        """Test releasing multiple resources."""
        # Acquire multiple resources
        for i in range(self.size):
            await self.bulkhead.acquire()
        
        # Release them one by one
        for i in range(self.size):
            await self.bulkhead.release()
            assert self.bulkhead.active == self.size - i - 1
        
        assert self.bulkhead.active == 0
    
    @pytest.mark.asyncio
    async def test_release_without_acquire(self):
        """Test that releasing without acquiring doesn't go negative."""
        # Release without acquiring first
        await self.bulkhead.release()
        
        # Should not go below 0
        assert self.bulkhead.active == 0
        
        # Release again
        await self.bulkhead.release()
        assert self.bulkhead.active == 0
    
    @pytest.mark.asyncio
    async def test_acquire_release_cycle(self):
        """Test complete acquire-release cycle."""
        # Start with empty bulkhead
        assert self.bulkhead.active == 0
        
        # Fill it up
        for i in range(self.size):
            await self.bulkhead.acquire()
        
        # Should be full
        assert self.bulkhead.active == self.size
        
        # Try to acquire one more (should fail)
        with pytest.raises(BulkheadFullError):
            await self.bulkhead.acquire()
        
        # Release one
        await self.bulkhead.release()
        assert self.bulkhead.active == self.size - 1
        
        # Now should be able to acquire again
        await self.bulkhead.acquire()
        assert self.bulkhead.active == self.size
    
    @pytest.mark.asyncio
    async def test_concurrent_acquire_attempts(self):
        """Test concurrent acquisition attempts."""
        # Create tasks that will try to acquire resources concurrently
        async def acquire_task():
            try:
                await self.bulkhead.acquire()
                return True
            except BulkheadFullError:
                return False
        
        # Create more tasks than bulkhead capacity
        tasks = [acquire_task() for _ in range(self.size + 2)]
        
        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks)
        
        # Should have exactly 'size' successful acquisitions
        successful = sum(results)
        failed = len(results) - successful
        
        assert successful == self.size
        assert failed == 2
        assert self.bulkhead.active == self.size
    
    @pytest.mark.asyncio
    async def test_concurrent_release_operations(self):
        """Test concurrent release operations."""
        # First fill up the bulkhead
        for i in range(self.size):
            await self.bulkhead.acquire()
        
        # Create concurrent release tasks
        async def release_task():
            await self.bulkhead.release()
        
        tasks = [release_task() for _ in range(self.size)]
        await asyncio.gather(*tasks)
        
        # Should be empty
        assert self.bulkhead.active == 0
    
    @pytest.mark.asyncio
    async def test_mixed_concurrent_operations(self):
        """Test mixed concurrent acquire and release operations."""
        # Start with some resources acquired
        for i in range(2):
            await self.bulkhead.acquire()
        
        async def mixed_operations():
            await self.bulkhead.acquire()
            await asyncio.sleep(0.01)  # Small delay
            await self.bulkhead.release()
        
        # Run multiple mixed operations concurrently
        tasks = [mixed_operations() for _ in range(5)]
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Should end up with original count
        assert self.bulkhead.active == 2
    
    @pytest.mark.asyncio
    async def test_bulkhead_with_different_sizes(self):
        """Test bulkheads with different capacity sizes."""
        # Test size 1 (binary semaphore)
        small_bulkhead = Bulkhead("small", 1)
        await small_bulkhead.acquire()
        
        with pytest.raises(BulkheadFullError):
            await small_bulkhead.acquire()
        
        # Test large size
        large_bulkhead = Bulkhead("large", 100)
        for i in range(100):
            await large_bulkhead.acquire()
        
        assert large_bulkhead.active == 100
        
        with pytest.raises(BulkheadFullError):
            await large_bulkhead.acquire()
    
    @pytest.mark.asyncio
    async def test_bulkhead_metrics_recording(self):
        """Test that metrics are recorded correctly."""
        with patch.object(retry_strategy, 'bulkhead_usage') as mock_metric:
            await self.bulkhead.acquire()
            
            # Should record metrics on acquire
            mock_metric.labels.assert_called_with(resource=self.resource)
            mock_metric.labels.return_value.set.assert_called_with(1)
            
            mock_metric.reset_mock()
            
            await self.bulkhead.release()
            
            # Should record metrics on release
            mock_metric.labels.assert_called_with(resource=self.resource)
            mock_metric.labels.return_value.set.assert_called_with(0)
    
    @pytest.mark.asyncio
    async def test_bulkhead_as_context_manager(self):
        """Test using bulkhead in a context manager pattern."""
        # This would require implementing __aenter__ and __aexit__
        # For now, test manual acquire/release pattern
        
        class BulkheadContext:
            def __init__(self, bulkhead):
                self.bulkhead = bulkhead
            
            async def __aenter__(self):
                await self.bulkhead.acquire()
                return self
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                await self.bulkhead.release()
        
        # Test the context manager pattern
        async with BulkheadContext(self.bulkhead):
            assert self.bulkhead.active == 1
        
        # Should be released after context
        assert self.bulkhead.active == 0
    
    @pytest.mark.asyncio
    async def test_bulkhead_exception_during_operation(self):
        """Test bulkhead behavior when exceptions occur during operations."""
        await self.bulkhead.acquire()
        assert self.bulkhead.active == 1
        
        # Simulate an exception but still release properly
        try:
            raise ValueError("Test exception")
        except ValueError:
            await self.bulkhead.release()
        
        assert self.bulkhead.active == 0
    
    @pytest.mark.asyncio
    async def test_bulkhead_stress_test(self):
        """Test bulkhead under stress with many operations."""
        acquire_count = 0
        release_count = 0
        
        async def stress_operation():
            nonlocal acquire_count, release_count
            try:
                await self.bulkhead.acquire()
                acquire_count += 1
                await asyncio.sleep(0.001)  # Simulate work
                await self.bulkhead.release()
                release_count += 1
            except BulkheadFullError:
                pass  # Expected when bulkhead is full
        
        # Run many concurrent operations
        tasks = [stress_operation() for _ in range(50)]
        await asyncio.gather(*tasks)
        
        # All acquired resources should be released
        assert self.bulkhead.active == 0
        assert acquire_count == release_count
        assert acquire_count > 0  # At least some operations succeeded
    
    def test_bulkhead_thread_safety_structure(self):
        """Test that bulkhead has proper async lock structure."""
        # Verify that the lock is properly initialized
        assert hasattr(self.bulkhead, '_lock')
        assert isinstance(self.bulkhead._lock, asyncio.Lock)


class TestBulkheadFullError:
    """Test suite for BulkheadFullError exception."""
    
    def test_bulkhead_full_error_creation(self):
        """Test creating BulkheadFullError."""
        error = BulkheadFullError("Test error message")
        assert str(error) == "Test error message"
    
    def test_bulkhead_full_error_inheritance(self):
        """Test that BulkheadFullError inherits from Exception."""
        error = BulkheadFullError("Test")
        assert isinstance(error, Exception)
    
    def test_bulkhead_full_error_with_details(self):
        """Test BulkheadFullError with detailed message."""
        resource = "database_connections"
        current = 10
        max_size = 10
        message = f"Bulkhead for {resource} is full ({current}/{max_size})"
        
        error = BulkheadFullError(message)
        assert resource in str(error)
        assert f"{current}/{max_size}" in str(error)


class TestBulkheadIntegration:
    """Integration tests for Bulkhead with other components."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.bulkhead = Bulkhead("test_resource", 3)
    
    @pytest.mark.asyncio
    async def test_multiple_bulkheads_independent(self):
        """Test that multiple bulkheads operate independently."""
        bulkhead1 = Bulkhead("resource1", 2)
        bulkhead2 = Bulkhead("resource2", 3)
        
        # Fill first bulkhead
        await bulkhead1.acquire()
        await bulkhead1.acquire()
        
        # Second bulkhead should still be available
        await bulkhead2.acquire()
        await bulkhead2.acquire()
        await bulkhead2.acquire()
        
        assert bulkhead1.active == 2
        assert bulkhead2.active == 3
        
        # First bulkhead should be full
        with pytest.raises(BulkheadFullError):
            await bulkhead1.acquire()
        
        # Second bulkhead should be full
        with pytest.raises(BulkheadFullError):
            await bulkhead2.acquire()
    
    @pytest.mark.asyncio
    async def test_bulkhead_with_timeout(self):
        """Test bulkhead operations with timeout."""
        # Fill the bulkhead
        for i in range(self.bulkhead.size):
            await self.bulkhead.acquire()
        
        # Try to acquire with timeout
        async def acquire_with_timeout():
            try:
                await asyncio.wait_for(self.bulkhead.acquire(), timeout=0.1)
                return True
            except (BulkheadFullError, asyncio.TimeoutError):
                return False
        
        result = await acquire_with_timeout()
        assert result is False