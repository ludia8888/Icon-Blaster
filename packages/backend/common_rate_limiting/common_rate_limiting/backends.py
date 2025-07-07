"""Rate Limiting Backends

Provides different storage backends for rate limiting.
"""

import asyncio
import json
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import redis.asyncio as redis


class Backend(ABC):
    """Abstract base class for rate limiting backends"""
    
    @abstractmethod
    async def initialize(self):
        """Initialize the backend"""
        pass
    
    @abstractmethod
    async def get_state(self, key: str) -> Dict[str, Any]:
        """Get current state for a key"""
        pass
    
    @abstractmethod
    async def update_state(self, key: str, state: Dict[str, Any], ttl: int):
        """Update state for a key with TTL"""
        pass
    
    @abstractmethod
    async def reset(self, key: str):
        """Reset state for a key"""
        pass
    
    @abstractmethod
    async def close(self):
        """Close connections and cleanup"""
        pass


class InMemoryBackend(Backend):
    """
    In-memory backend for rate limiting.
    Suitable for single-instance applications or testing.
    """
    
    def __init__(self):
        self._storage: Dict[str, Dict[str, Any]] = {}
        self._expiry: Dict[str, float] = {}
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def initialize(self):
        """Start cleanup task"""
        if not self._cleanup_task:
            self._cleanup_task = asyncio.create_task(self._cleanup_expired())
    
    async def get_state(self, key: str) -> Dict[str, Any]:
        """Get current state for a key"""
        async with self._lock:
            # Check if key exists and not expired
            if key in self._storage:
                if key not in self._expiry or time.time() < self._expiry[key]:
                    return self._storage[key].copy()
                else:
                    # Expired, remove it
                    del self._storage[key]
                    if key in self._expiry:
                        del self._expiry[key]
            
            return {}
    
    async def update_state(self, key: str, state: Dict[str, Any], ttl: int):
        """Update state for a key with TTL"""
        async with self._lock:
            self._storage[key] = state.copy()
            self._expiry[key] = time.time() + ttl
    
    async def reset(self, key: str):
        """Reset state for a key"""
        async with self._lock:
            if key in self._storage:
                del self._storage[key]
            if key in self._expiry:
                del self._expiry[key]
    
    async def close(self):
        """Stop cleanup task"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
    
    async def _cleanup_expired(self):
        """Periodically clean up expired entries"""
        while True:
            try:
                await asyncio.sleep(60)  # Run every minute
                async with self._lock:
                    current_time = time.time()
                    expired_keys = [
                        key for key, expiry in self._expiry.items()
                        if current_time >= expiry
                    ]
                    for key in expired_keys:
                        if key in self._storage:
                            del self._storage[key]
                        del self._expiry[key]
            except asyncio.CancelledError:
                break
            except Exception:
                # Log error but continue
                pass


class RedisBackend(Backend):
    """
    Redis backend for distributed rate limiting.
    Suitable for multi-instance applications.
    """
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        key_prefix: str = "rate_limit:",
        decode_responses: bool = False
    ):
        self.redis_url = redis_url
        self.key_prefix = key_prefix
        self.decode_responses = decode_responses
        self._client: Optional[redis.Redis] = None
    
    async def initialize(self):
        """Connect to Redis"""
        if not self._client:
            self._client = await redis.from_url(
                self.redis_url,
                decode_responses=self.decode_responses
            )
    
    async def get_state(self, key: str) -> Dict[str, Any]:
        """Get current state for a key"""
        if not self._client:
            raise RuntimeError("Backend not initialized")
        
        full_key = f"{self.key_prefix}{key}"
        data = await self._client.get(full_key)
        
        if data:
            if isinstance(data, bytes):
                data = data.decode("utf-8")
            return json.loads(data)
        
        return {}
    
    async def update_state(self, key: str, state: Dict[str, Any], ttl: int):
        """Update state for a key with TTL"""
        if not self._client:
            raise RuntimeError("Backend not initialized")
        
        full_key = f"{self.key_prefix}{key}"
        data = json.dumps(state)
        await self._client.setex(full_key, ttl, data)
    
    async def reset(self, key: str):
        """Reset state for a key"""
        if not self._client:
            raise RuntimeError("Backend not initialized")
        
        full_key = f"{self.key_prefix}{key}"
        await self._client.delete(full_key)
    
    async def close(self):
        """Close Redis connection"""
        if self._client:
            await self._client.close()
            self._client = None
    
    # Additional Redis-specific methods for compatibility
    
    async def increment_counter(
        self,
        key: str,
        window: int,
        limit: int
    ) -> tuple[int, int]:
        """
        Increment counter using Redis atomic operations.
        
        Returns:
            Tuple of (current_count, ttl)
        """
        if not self._client:
            raise RuntimeError("Backend not initialized")
        
        full_key = f"{self.key_prefix}{key}:{window}"
        
        # Use pipeline for atomic operations
        pipe = self._client.pipeline()
        pipe.incr(full_key)
        pipe.ttl(full_key)
        pipe.expire(full_key, window)
        
        results = await pipe.execute()
        current_count = results[0]
        ttl = results[1] if results[1] > 0 else window
        
        return current_count, ttl
    
    async def sliding_window_increment(
        self,
        key: str,
        window: int,
        limit: int,
        timestamp: Optional[float] = None
    ) -> tuple[int, float]:
        """
        Implement sliding window using Redis sorted sets.
        
        Returns:
            Tuple of (current_count, oldest_timestamp)
        """
        if not self._client:
            raise RuntimeError("Backend not initialized")
        
        if timestamp is None:
            timestamp = time.time()
        
        full_key = f"{self.key_prefix}{key}:sliding:{window}"
        
        # Remove old entries and add new one in a transaction
        pipe = self._client.pipeline()
        
        # Remove entries older than window
        min_timestamp = timestamp - window
        pipe.zremrangebyscore(full_key, 0, min_timestamp)
        
        # Add current request
        pipe.zadd(full_key, {str(timestamp): timestamp})
        
        # Count current entries
        pipe.zcard(full_key)
        
        # Get oldest entry
        pipe.zrange(full_key, 0, 0, withscores=True)
        
        # Set expiry
        pipe.expire(full_key, window + 1)
        
        results = await pipe.execute()
        current_count = results[2]
        
        # Get oldest timestamp
        oldest_entries = results[3]
        oldest_timestamp = oldest_entries[0][1] if oldest_entries else timestamp
        
        return current_count, oldest_timestamp