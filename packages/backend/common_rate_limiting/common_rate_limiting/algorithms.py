"""Rate Limiting Algorithms

Provides different algorithms for rate limiting.
"""

import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Any, Dict, Optional


class RateLimitAlgorithm(ABC):
    """Abstract base class for rate limiting algorithms"""
    
    @abstractmethod
    async def is_allowed(
        self,
        state: Dict[str, Any],
        limit: int,
        window: int,
        cost: int = 1,
        burst_size: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Check if request is allowed based on algorithm.
        
        Args:
            state: Current state from backend
            limit: Request limit
            window: Time window in seconds
            cost: Cost of this request
            burst_size: Optional burst size
            
        Returns:
            Dict containing:
                - allowed: Whether request is allowed
                - new_state: Updated state to store
                - remaining: Remaining requests
                - reset_time: When limit resets
                - retry_after: Seconds until retry (if not allowed)
        """
        pass


class FixedWindowAlgorithm(RateLimitAlgorithm):
    """
    Fixed window algorithm.
    Simple but can have burst issues at window boundaries.
    """
    
    async def is_allowed(
        self,
        state: Dict[str, Any],
        limit: int,
        window: int,
        cost: int = 1,
        burst_size: Optional[int] = None
    ) -> Dict[str, Any]:
        """Check if request is allowed using fixed window"""
        current_time = time.time()
        window_start = int(current_time // window) * window
        window_end = window_start + window
        
        # Get current count for this window
        count_key = f"count_{window_start}"
        current_count = state.get(count_key, 0)
        
        # Check if allowed
        allowed = (current_count + cost) <= limit
        
        # Calculate new state
        new_state = {}
        if allowed:
            new_state[count_key] = current_count + cost
            remaining = limit - (current_count + cost)
        else:
            new_state[count_key] = current_count
            remaining = 0
        
        # Calculate reset time
        reset_time = datetime.utcfromtimestamp(window_end)
        retry_after = int(window_end - current_time) if not allowed else None
        
        return {
            "allowed": allowed,
            "new_state": new_state,
            "remaining": remaining,
            "reset_time": reset_time,
            "retry_after": retry_after
        }


class SlidingWindowAlgorithm(RateLimitAlgorithm):
    """
    Sliding window algorithm.
    More accurate than fixed window, prevents bursts.
    """
    
    async def is_allowed(
        self,
        state: Dict[str, Any],
        limit: int,
        window: int,
        cost: int = 1,
        burst_size: Optional[int] = None
    ) -> Dict[str, Any]:
        """Check if request is allowed using sliding window"""
        current_time = time.time()
        window_start = current_time - window
        
        # Get request history
        requests = state.get("requests", [])
        
        # Filter out old requests
        valid_requests = [
            req for req in requests
            if req["timestamp"] > window_start
        ]
        
        # Count current requests
        current_count = sum(req.get("cost", 1) for req in valid_requests)
        
        # Check if allowed
        allowed = (current_count + cost) <= limit
        
        # Calculate new state
        new_state = {"requests": valid_requests}
        if allowed:
            valid_requests.append({
                "timestamp": current_time,
                "cost": cost
            })
            remaining = limit - (current_count + cost)
        else:
            remaining = 0
        
        # Calculate reset time (when oldest request expires)
        if valid_requests:
            oldest_timestamp = min(req["timestamp"] for req in valid_requests)
            reset_time = datetime.utcfromtimestamp(oldest_timestamp + window)
            retry_after = int(oldest_timestamp + window - current_time) if not allowed else None
        else:
            reset_time = datetime.utcfromtimestamp(current_time + window)
            retry_after = None
        
        return {
            "allowed": allowed,
            "new_state": new_state,
            "remaining": remaining,
            "reset_time": reset_time,
            "retry_after": retry_after
        }


class TokenBucketAlgorithm(RateLimitAlgorithm):
    """
    Token bucket algorithm.
    Allows bursts up to bucket size, refills at constant rate.
    """
    
    async def is_allowed(
        self,
        state: Dict[str, Any],
        limit: int,
        window: int,
        cost: int = 1,
        burst_size: Optional[int] = None
    ) -> Dict[str, Any]:
        """Check if request is allowed using token bucket"""
        current_time = time.time()
        
        # Calculate refill rate (tokens per second)
        refill_rate = limit / window
        
        # Get bucket state
        tokens = state.get("tokens", limit)
        last_refill = state.get("last_refill", current_time)
        
        # Use burst_size if specified, otherwise use limit
        bucket_size = burst_size or limit
        
        # Calculate tokens to add since last refill
        time_passed = current_time - last_refill
        tokens_to_add = time_passed * refill_rate
        
        # Update token count (cap at bucket size)
        tokens = min(tokens + tokens_to_add, bucket_size)
        
        # Check if allowed
        allowed = tokens >= cost
        
        # Calculate new state
        if allowed:
            new_tokens = tokens - cost
            remaining = int(new_tokens)
        else:
            new_tokens = tokens
            remaining = 0
        
        new_state = {
            "tokens": new_tokens,
            "last_refill": current_time
        }
        
        # Calculate when we'll have enough tokens
        if not allowed:
            tokens_needed = cost - tokens
            time_to_refill = tokens_needed / refill_rate
            retry_after = int(time_to_refill)
            reset_time = datetime.utcfromtimestamp(current_time + time_to_refill)
        else:
            retry_after = None
            # Next full refill
            tokens_to_full = bucket_size - new_tokens
            time_to_full = tokens_to_full / refill_rate
            reset_time = datetime.utcfromtimestamp(current_time + time_to_full)
        
        return {
            "allowed": allowed,
            "new_state": new_state,
            "remaining": remaining,
            "reset_time": reset_time,
            "retry_after": retry_after
        }


class LeakyBucketAlgorithm(RateLimitAlgorithm):
    """
    Leaky bucket algorithm.
    Processes requests at constant rate, queues up to bucket size.
    """
    
    async def is_allowed(
        self,
        state: Dict[str, Any],
        limit: int,
        window: int,
        cost: int = 1,
        burst_size: Optional[int] = None
    ) -> Dict[str, Any]:
        """Check if request is allowed using leaky bucket"""
        current_time = time.time()
        
        # Calculate leak rate (requests per second)
        leak_rate = limit / window
        
        # Get bucket state
        queue_size = state.get("queue_size", 0)
        last_leak = state.get("last_leak", current_time)
        
        # Use burst_size if specified, otherwise use limit
        bucket_size = burst_size or limit
        
        # Calculate how much has leaked since last check
        time_passed = current_time - last_leak
        leaked = time_passed * leak_rate
        
        # Update queue size
        queue_size = max(0, queue_size - leaked)
        
        # Check if request fits in bucket
        allowed = (queue_size + cost) <= bucket_size
        
        # Calculate new state
        if allowed:
            new_queue_size = queue_size + cost
            remaining = int(bucket_size - new_queue_size)
        else:
            new_queue_size = queue_size
            remaining = 0
        
        new_state = {
            "queue_size": new_queue_size,
            "last_leak": current_time
        }
        
        # Calculate when bucket will have space
        if not allowed:
            space_needed = (queue_size + cost) - bucket_size
            time_to_leak = space_needed / leak_rate
            retry_after = int(time_to_leak)
            reset_time = datetime.utcfromtimestamp(current_time + time_to_leak)
        else:
            retry_after = None
            # When bucket will be empty
            time_to_empty = new_queue_size / leak_rate
            reset_time = datetime.utcfromtimestamp(current_time + time_to_empty)
        
        return {
            "allowed": allowed,
            "new_state": new_state,
            "remaining": remaining,
            "reset_time": reset_time,
            "retry_after": retry_after
        }