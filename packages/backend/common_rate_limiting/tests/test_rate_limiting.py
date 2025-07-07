"""Tests for common_rate_limiting package"""

import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from common_rate_limiting import (
    RateLimiter,
    RateLimitExceeded,
    FastAPIRateLimitMiddleware,
    rate_limit_decorator,
    RedisBackend,
    InMemoryBackend,
    SlidingWindowAlgorithm,
    TokenBucketAlgorithm,
    FixedWindowAlgorithm,
)
from common_rate_limiting.core import RateLimitScope


class TestRateLimiterCore:
    """Test core RateLimiter functionality"""
    
    @pytest.mark.asyncio
    async def test_basic_rate_limiting(self):
        """Test basic rate limiting with in-memory backend"""
        limiter = RateLimiter(default_limit=5, default_window=60)
        await limiter.initialize()
        
        # Should allow first 5 requests
        for i in range(5):
            result = await limiter.check_rate_limit("test_key")
            assert result["allowed"] is True
            assert result["remaining"] == 4 - i
        
        # 6th request should be rejected
        with pytest.raises(RateLimitExceeded) as exc_info:
            await limiter.check_rate_limit("test_key")
        
        assert exc_info.value.remaining == 0
        assert exc_info.value.limit == 5
        
        await limiter.close()
    
    @pytest.mark.asyncio
    async def test_different_keys(self):
        """Test that different keys have separate limits"""
        limiter = RateLimiter(default_limit=2, default_window=60)
        await limiter.initialize()
        
        # Use limit for key1
        await limiter.check_rate_limit("key1")
        await limiter.check_rate_limit("key1")
        
        # key2 should still have full limit
        result = await limiter.check_rate_limit("key2")
        assert result["allowed"] is True
        assert result["remaining"] == 1
        
        # key1 should be exhausted
        with pytest.raises(RateLimitExceeded):
            await limiter.check_rate_limit("key1")
        
        await limiter.close()
    
    @pytest.mark.asyncio
    async def test_custom_limit_and_window(self):
        """Test custom limit and window per request"""
        limiter = RateLimiter(default_limit=10, default_window=60)
        await limiter.initialize()
        
        # Use custom limit
        result = await limiter.check_rate_limit("test_key", limit=2, window=30)
        assert result["allowed"] is True
        assert result["remaining"] == 1
        
        await limiter.check_rate_limit("test_key", limit=2, window=30)
        
        # Should be rejected with custom limit
        with pytest.raises(RateLimitExceeded):
            await limiter.check_rate_limit("test_key", limit=2, window=30)
        
        await limiter.close()
    
    @pytest.mark.asyncio
    async def test_cost_parameter(self):
        """Test requests with different costs"""
        limiter = RateLimiter(default_limit=10, default_window=60)
        await limiter.initialize()
        
        # Request with cost 5
        result = await limiter.check_rate_limit("test_key", cost=5)
        assert result["allowed"] is True
        assert result["remaining"] == 5
        
        # Request with cost 3
        result = await limiter.check_rate_limit("test_key", cost=3)
        assert result["allowed"] is True
        assert result["remaining"] == 2
        
        # Request with cost 3 should exceed
        with pytest.raises(RateLimitExceeded):
            await limiter.check_rate_limit("test_key", cost=3)
        
        await limiter.close()
    
    @pytest.mark.asyncio
    async def test_reset_functionality(self):
        """Test resetting rate limit for a key"""
        limiter = RateLimiter(default_limit=2, default_window=60)
        await limiter.initialize()
        
        # Use up limit
        await limiter.check_rate_limit("test_key")
        await limiter.check_rate_limit("test_key")
        
        # Should be rejected
        with pytest.raises(RateLimitExceeded):
            await limiter.check_rate_limit("test_key")
        
        # Reset the key
        await limiter.reset("test_key")
        
        # Should be allowed again
        result = await limiter.check_rate_limit("test_key")
        assert result["allowed"] is True
        assert result["remaining"] == 1
        
        await limiter.close()


class TestAlgorithms:
    """Test different rate limiting algorithms"""
    
    @pytest.mark.asyncio
    async def test_fixed_window_algorithm(self):
        """Test fixed window algorithm"""
        algo = FixedWindowAlgorithm()
        
        # First request in window
        result = await algo.is_allowed({}, limit=5, window=60)
        assert result["allowed"] is True
        assert result["remaining"] == 4
        
        # Use the updated state
        state = result["new_state"]
        for i in range(3):
            result = await algo.is_allowed(state, limit=5, window=60)
            state = result["new_state"]
            assert result["allowed"] is True
        
        # 5th request
        result = await algo.is_allowed(state, limit=5, window=60)
        assert result["allowed"] is True
        assert result["remaining"] == 0
        state = result["new_state"]
        
        # 6th request should fail
        result = await algo.is_allowed(state, limit=5, window=60)
        assert result["allowed"] is False
        assert result["retry_after"] is not None
    
    @pytest.mark.asyncio
    async def test_sliding_window_algorithm(self):
        """Test sliding window algorithm"""
        algo = SlidingWindowAlgorithm()
        
        # Add requests over time
        state = {}
        current_time = time.time()
        
        # Add 3 requests
        for i in range(3):
            result = await algo.is_allowed(state, limit=5, window=60)
            assert result["allowed"] is True
            state = result["new_state"]
        
        # Verify request history is maintained
        assert len(state["requests"]) == 3
        assert all(req["timestamp"] >= current_time for req in state["requests"])
    
    @pytest.mark.asyncio
    async def test_token_bucket_algorithm(self):
        """Test token bucket algorithm"""
        algo = TokenBucketAlgorithm()
        
        # Start with full bucket
        result = await algo.is_allowed({}, limit=10, window=60, burst_size=15)
        assert result["allowed"] is True
        # Should have burst_size tokens initially
        assert result["new_state"]["tokens"] == 9  # 10 - 1
        
        # Use burst capacity
        state = result["new_state"]
        for i in range(9):
            result = await algo.is_allowed(state, limit=10, window=60, burst_size=15)
            assert result["allowed"] is True
            state = result["new_state"]
        
        # Bucket should be empty
        assert state["tokens"] == 0
        
        # Next request should fail
        result = await algo.is_allowed(state, limit=10, window=60, burst_size=15)
        assert result["allowed"] is False
        assert result["retry_after"] > 0


class TestBackends:
    """Test different storage backends"""
    
    @pytest.mark.asyncio
    async def test_in_memory_backend(self):
        """Test in-memory backend"""
        backend = InMemoryBackend()
        await backend.initialize()
        
        # Test empty state
        state = await backend.get_state("test_key")
        assert state == {}
        
        # Update state
        test_state = {"count": 5, "timestamp": time.time()}
        await backend.update_state("test_key", test_state, ttl=60)
        
        # Retrieve state
        retrieved = await backend.get_state("test_key")
        assert retrieved["count"] == 5
        
        # Reset state
        await backend.reset("test_key")
        state = await backend.get_state("test_key")
        assert state == {}
        
        await backend.close()
    
    @pytest.mark.asyncio
    async def test_in_memory_backend_expiry(self):
        """Test that in-memory backend expires entries"""
        backend = InMemoryBackend()
        await backend.initialize()
        
        # Set state with short TTL
        await backend.update_state("test_key", {"count": 1}, ttl=1)
        
        # Should exist immediately
        state = await backend.get_state("test_key")
        assert state["count"] == 1
        
        # Wait for expiry
        await asyncio.sleep(1.1)
        
        # Should be expired
        state = await backend.get_state("test_key")
        assert state == {}
        
        await backend.close()


class TestMiddleware:
    """Test middleware implementations"""
    
    @pytest.fixture
    def app(self):
        """Create FastAPI app with rate limiting"""
        app = FastAPI()
        
        # Add rate limit middleware
        limiter = RateLimiter(default_limit=5, default_window=60)
        app.add_middleware(
            FastAPIRateLimitMiddleware,
            rate_limiter=limiter,
            limit=5,
            window=60
        )
        
        @app.get("/test")
        async def test_endpoint():
            return {"message": "success"}
        
        @app.get("/exempt")
        async def exempt_endpoint():
            return {"message": "exempt"}
        
        return app
    
    def test_fastapi_middleware_basic(self, app):
        """Test FastAPI middleware basic functionality"""
        client = TestClient(app)
        
        # First 5 requests should succeed
        for i in range(5):
            response = client.get("/test")
            assert response.status_code == 200
            assert "X-RateLimit-Limit" in response.headers
            assert "X-RateLimit-Remaining" in response.headers
            assert int(response.headers["X-RateLimit-Remaining"]) == 4 - i
        
        # 6th request should be rate limited
        response = client.get("/test")
        assert response.status_code == 429
        assert "Retry-After" in response.headers
    
    def test_fastapi_middleware_headers(self, app):
        """Test that rate limit headers are properly set"""
        client = TestClient(app)
        
        response = client.get("/test")
        assert response.status_code == 200
        assert response.headers["X-RateLimit-Limit"] == "5"
        assert response.headers["X-RateLimit-Remaining"] == "4"
        assert "X-RateLimit-Reset" in response.headers
    
    @pytest.mark.asyncio
    async def test_rate_limit_decorator(self):
        """Test rate limit decorator"""
        # Create a mock request
        mock_request = MagicMock()
        mock_request.url.path = "/test"
        mock_request.client.host = "127.0.0.1"
        
        call_count = 0
        
        @rate_limit_decorator(limit=3, window=60)
        async def test_function(request):
            nonlocal call_count
            call_count += 1
            return {"count": call_count}
        
        # First 3 calls should succeed
        for i in range(3):
            result = await test_function(mock_request)
            assert result["count"] == i + 1
        
        # 4th call should raise HTTPException
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await test_function(mock_request)
        
        assert exc_info.value.status_code == 429


class TestCompatibility:
    """Test compatibility with existing implementations"""
    
    @pytest.mark.asyncio
    async def test_user_service_compatibility(self):
        """Test compatibility with user-service rate limiter"""
        # Create limiter similar to user-service
        limiter = RateLimiter(
            backend=InMemoryBackend(),  # Would be RedisBackend in production
            algorithm=SlidingWindowAlgorithm(),
            default_limit=100,
            default_window=60,
            scope=RateLimitScope.IP
        )
        await limiter.initialize()
        
        # Mock request object
        mock_request = MagicMock()
        mock_request.client.host = "192.168.1.1"
        
        # Get key based on IP
        key = limiter.get_key(mock_request)
        assert key == "ip:192.168.1.1"
        
        # Check rate limit
        result = await limiter.check_rate_limit(key)
        assert result["allowed"] is True
        assert result["remaining"] == 99
        
        await limiter.close()
    
    @pytest.mark.asyncio
    async def test_oms_gateway_compatibility(self):
        """Test compatibility with OMS gateway rate limiter"""
        # Create distributed rate limiter
        from common_rate_limiting.core import DistributedRateLimiter
        
        # Mock Redis backend for testing
        mock_backend = AsyncMock(spec=RedisBackend)
        mock_backend.get_state = AsyncMock(return_value={})
        mock_backend.update_state = AsyncMock()
        mock_backend.initialize = AsyncMock()
        mock_backend.close = AsyncMock()
        
        limiter = DistributedRateLimiter()
        limiter.backend = mock_backend
        await limiter.initialize()
        
        # Test multiple window support
        limits = {
            60: 100,    # 100 per minute
            3600: 1000, # 1000 per hour
            86400: 10000 # 10000 per day
        }
        
        # Should check all windows
        with pytest.raises(RateLimitExceeded):
            # Force one window to fail
            mock_backend.get_state = AsyncMock(return_value={"count_0": 100})
            await limiter.check_multiple_windows("test_key", limits)
        
        await limiter.close()